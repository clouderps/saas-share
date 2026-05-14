# -*- coding: utf-8 -*-
"""Phase H — agent run loop.

Plan → call tools → reflect → respond. Provider-agnostic ReAct loop
with `__end_message` early-termination, replay-safe write actions,
per-run cost cap, local budget guard, and bus-based observability.

Every invocation:
  1. Creates an ai.agent.run row (audit + replay source).
  2. Checks the local budget (Part 12) before any network call.
  3. Composes the system prompt from agent.system_prompt + topics + date.
  4. Loops: call_llm → execute tools → if no more tools, render + return.
  5. Writes ai.usage.local.log via the meter on every hop.
  6. Pushes bus events on the live-meter channel.
"""
from __future__ import annotations

import json
import logging
import time

from odoo import fields

from . import llm_adapter
from . import meter as meter_svc
from . import tool_dispatcher
from . import citation as citation_svc

_logger = logging.getLogger(__name__)


def run(env, *, agent, user_question, conversation=None, surface='chat',
        record_ref=None, skill=None, locale='en', max_hops=None,
        on_event=None, source_lookup=None):
    """Execute one agent run.

    Returns:
        ``(response_text, agent_run_record, envelope_dict)``

    Args:
        env: odoo Environment (with the calling user)
        agent: ai.agent record (required)
        user_question: the user's input
        conversation: loose pointer (string) to the chat conv if any
        surface: where the run was triggered
        record_ref: optional recordset the run is about
        skill: optional ai.agent.skill the user clicked
        locale: 'en' | 'ar'
        max_hops: override agent.max_hops (capped to it)
        on_event: callable(kind, **kw) for bus emission (optional)
        source_lookup: dict for citation rendering
    """
    if agent is None:
        raise ValueError('runtime.run() requires an agent record')
    started_perf = time.perf_counter()
    on_event = on_event or (lambda *a, **k: None)

    # ── 1. Audit row ──────────────────────────────────────────
    Run = env['ai.agent.run'].sudo()
    agent_run = Run.create({
        'agent_id': agent.id,
        'skill_id': skill.id if skill else False,
        'user_id': env.uid,
        'company_id': env.company.id,
        'surface': surface,
        'record_ref': _stringify_ref(record_ref),
        'conversation_id': str(conversation) if conversation else '',
        'question': user_question or '',
    })
    on_event('start', run_id=agent_run.id, agent=agent.name, agent_code=agent.code)

    # ── 2. Budget guard (local mirror) ────────────────────────
    Budget = env.get('ai.usage.local.budget')
    if Budget is not None:
        budget_check = Budget.sudo().check(env, agent=agent, surface=surface)
        if not budget_check['allow']:
            envelope = _budget_envelope(budget_check, locale)
            agent_run.finalize(
                state='budget',
                response=envelope.get('response') or '',
                error=budget_check['reason'],
                latency_ms=int((time.perf_counter() - started_perf) * 1000),
            )
            on_event('done', run_id=agent_run.id, state='budget')
            return envelope['response'], agent_run, envelope

    # ── 3. Build system prompt + tool schemas ─────────────────
    system_prompt = _compose_system_prompt(env, agent, locale=locale, skill=skill,
                                           record_ref=record_ref)
    tools = _resolve_tools(env, agent)
    llm_tool_schemas = [t.as_llm_schema(agent=agent) for t in tools]

    # ── 4. Hop loop ───────────────────────────────────────────
    hard_cap = min(agent.max_hops or 6, max_hops or 20)
    cost_cap = float(agent.max_cost_usd or 0)
    transcript = [user_question]
    tool_calls_audit = []
    cum_cost = 0.0
    cum_tokens = {'p': 0, 'c': 0, 'cached': 0}
    final_text = ''
    final_provider = ''
    final_model = ''
    last_routed_via = ''

    for hop in range(hard_cap):
        prompt_for_llm = "\n\n".join(transcript)
        on_event('thinking', run_id=agent_run.id, hop=hop + 1)

        response, usage, routed_via = llm_adapter.call_llm(
            env, agent,
            system_prompt=system_prompt,
            user_prompt=prompt_for_llm,
            tools=llm_tool_schemas,
            temperature=agent.temperature(),
            max_tokens=2000,
        )
        last_routed_via = routed_via

        # Persist a meter row per hop.
        meter_svc.record(
            env,
            request_id=usage.get('request_id') or '',
            surface=surface,
            feature='agent',
            agent=agent, agent_skill=skill, agent_run=agent_run,
            record_ref=record_ref,
            provider=usage.get('provider', ''),
            model_used=usage.get('model', ''),
            model_class=agent.model_class,
            routed_via=routed_via,
            cache_hit=bool(usage.get('cache_hit')),
            prompt_tokens=int(usage.get('prompt_tokens') or 0),
            completion_tokens=int(usage.get('completion_tokens') or 0),
            cached_tokens=int(usage.get('cached_tokens') or 0),
            web_grounding_calls=int(usage.get('web_grounding_calls') or 0),
            duration_ms=int((usage.get('duration') or 0) * 1000),
            status='sim' if routed_via == 'sim' else 'ok',
            prompt_excerpt=user_question[:200],
        )

        cum_cost += float(usage.get('cost_usd') or 0.0)
        cum_tokens['p'] += int(usage.get('prompt_tokens') or 0)
        cum_tokens['c'] += int(usage.get('completion_tokens') or 0)
        cum_tokens['cached'] += int(usage.get('cached_tokens') or 0)
        final_provider = usage.get('provider', '') or final_provider
        final_model = usage.get('model', '') or final_model

        # Cost cap.
        if cost_cap and cum_cost > cost_cap:
            envelope = _cost_capped_envelope(agent, cum_cost, cost_cap, locale)
            agent_run.finalize(
                state='cost_capped',
                response=envelope['response'],
                error=f'Per-run cap of ${cost_cap:.4f} hit; spent ${cum_cost:.4f}',
                latency_ms=int((time.perf_counter() - started_perf) * 1000),
                tool_calls=tool_calls_audit,
            )
            on_event('done', run_id=agent_run.id, state='cost_capped')
            agent_run.sudo().write({
                'hops': hop + 1,
                'cost_usd': cum_cost,
                'prompt_tokens': cum_tokens['p'],
                'completion_tokens': cum_tokens['c'],
                'cached_tokens': cum_tokens['cached'],
                'model_used': final_model,
                'provider_used': final_provider,
                'routed_via': last_routed_via,
            })
            return envelope['response'], agent_run, envelope

        # Parse the LLM output. We support two protocols:
        #   a) Provider-native tool calls when the gateway tool path
        #      surfaces a structured tool_calls list (future).
        #   b) JSON-action protocol: response text is a single JSON
        #      object {"action": "tool" | "final", ...}. Same as
        #      our existing ab_ai_chatbot.services.agent_loop.
        parsed = _parse_response(response)

        if parsed.get('kind') == 'tool' and parsed.get('tool'):
            tool_record = _find_tool(tools, parsed['tool'])
            if not tool_record:
                transcript.append(
                    f'Tool result: {{"error": "unknown_tool: {parsed["tool"]}"}}'
                )
                tool_calls_audit.append({
                    'tool': parsed['tool'], 'ok': False, 'error': 'unknown_tool',
                })
                on_event('tool_call', tool=parsed['tool'], ok=False)
                continue
            on_event('tool_call', tool=tool_record.code, args=parsed.get('args'))
            tool_outcome = tool_dispatcher.dispatch(
                env, tool_record, parsed.get('args') or {},
                agent=agent, agent_run=agent_run,
            )
            tool_calls_audit.append(tool_outcome)

            # __end_message early termination — Odoo 19 native pattern.
            if tool_outcome.get('ok') and tool_outcome.get('end_message'):
                final_text = tool_outcome['end_message']
                break

            transcript.append(
                'Tool result for `%s`: %s' % (
                    tool_record.code,
                    _truncate(json.dumps(tool_outcome.get('result'), default=str), 4000),
                )
            )
            transcript.append(
                'Decide your next step. Either call another tool or '
                'return a "final" action with your answer.'
            )
            continue

        if parsed.get('kind') == 'final':
            final_text = parsed.get('text') or ''
            break

        # No structured action — treat as a final freeform answer.
        final_text = response if isinstance(response, str) else (
            '\n'.join(response) if isinstance(response, list) else str(response)
        )
        break

    if not final_text:
        # We hit max_hops without a terminal step.
        envelope = _maxhops_envelope(agent, locale)
        agent_run.finalize(
            state='maxhops',
            response=envelope['response'],
            error='max_hops reached',
            latency_ms=int((time.perf_counter() - started_perf) * 1000),
            tool_calls=tool_calls_audit,
        )
        agent_run.sudo().write({
            'hops': hard_cap, 'cost_usd': cum_cost,
            'prompt_tokens': cum_tokens['p'],
            'completion_tokens': cum_tokens['c'],
            'cached_tokens': cum_tokens['cached'],
            'model_used': final_model, 'provider_used': final_provider,
            'routed_via': last_routed_via,
        })
        on_event('done', run_id=agent_run.id, state='maxhops')
        return envelope['response'], agent_run, envelope

    # ── 5. Citations ──────────────────────────────────────────
    rendered_text, sources = citation_svc.apply_numeric_citations(
        final_text, source_lookup or {})

    # ── 6. Build the final envelope ───────────────────────────
    latency_ms = int((time.perf_counter() - started_perf) * 1000)
    envelope = {
        'response': rendered_text,
        'agent_id': agent.id,
        'agent_code': agent.code,
        'usage': {
            'prompt_tokens': cum_tokens['p'],
            'completion_tokens': cum_tokens['c'],
            'cached_tokens': cum_tokens['cached'],
            'total_tokens': cum_tokens['p'] + cum_tokens['c'] + cum_tokens['cached'],
            'cost_usd': round(cum_cost, 6),
            'model': final_model,
            'provider': final_provider,
            'duration_ms': latency_ms,
        },
        'provenance': {
            'routed_via': last_routed_via,
            'hops': hop + 1 if 'hop' in locals() else 0,
        },
        'tool_calls': [
            {'tool': c.get('tool'), 'ok': c.get('ok'),
             'duration_ms': c.get('duration_ms'),
             'error': c.get('error')}
            for c in tool_calls_audit
        ],
        'sources': sources,
    }

    agent_run.finalize(
        state='done',
        response=rendered_text,
        latency_ms=latency_ms,
        tool_calls=tool_calls_audit,
    )
    agent_run.sudo().write({
        'hops': hop + 1 if 'hop' in locals() else 0,
        'cost_usd': cum_cost,
        'prompt_tokens': cum_tokens['p'],
        'completion_tokens': cum_tokens['c'],
        'cached_tokens': cum_tokens['cached'],
        'model_used': final_model,
        'provider_used': final_provider,
        'routed_via': last_routed_via,
    })

    # Live meter chip push.
    try:
        summary = env['ai.usage.local.log'].sudo().usage_summary('today')
        meter_svc.emit_live(env, summary)
    except Exception:
        pass

    on_event('done', run_id=agent_run.id, state='done', envelope=envelope)
    return rendered_text, agent_run, envelope


# ───────────────────────── helpers ──────────────────────────

def _compose_system_prompt(env, agent, *, locale='en', skill=None, record_ref=None):
    """Compose the system prompt = persona + topics + date reference."""
    parts = [agent.system_prompt or '']

    # Today + date math (§3.8 borrowed pattern).
    date_block = tool_dispatcher.get('date_reference')(env, agent=agent)
    parts.append(
        '## Today\n'
        f'- Today: {date_block["today"]}\n'
        f'- Yesterday: {date_block["yesterday"]} ; Tomorrow: {date_block["tomorrow"]}\n'
        f'- This week: {date_block["this_week"]}\n'
        f'- This month: {date_block["this_month"]} ; Last month: {date_block["last_month"]}\n'
        f'- This quarter starts: {date_block["this_quarter_start"]}\n'
        f'Use these dates for relative-date math; never compute them yourself.'
    )

    # Topic instructions.
    if agent.topic_ids:
        topic_text = '\n\n'.join(
            f'### Topic: {t.name}\n{t.instructions or ""}'.strip()
            for t in agent.topic_ids
        )
        parts.append(topic_text)

    # Tool protocol.
    if agent.all_tool_ids:
        parts.append(_tool_protocol_block(agent.all_tool_ids))

    # Record context.
    if record_ref:
        try:
            parts.append(
                f'## Active record\n'
                f'You are helping the user with `{record_ref._name}` id {record_ref.id} '
                f'("{record_ref.display_name}"). Use this as primary context.'
            )
        except Exception:
            pass

    # Skill context.
    if skill:
        parts.append(
            f'## Skill invoked\n'
            f'The user clicked the "{skill.name}" skill. Stay focused on this task.'
        )

    # Locale.
    if locale == 'ar':
        parts.append(
            '## Locale\nRespond in clear modern Arabic. RTL-friendly. '
            'Mix English technical terms only when they have no common '
            'Arabic equivalent (e.g. ZATCA).'
        )
    else:
        parts.append('## Locale\nRespond in clear, concise English.')

    return '\n\n'.join(p for p in parts if p)


def _tool_protocol_block(tools):
    """JSON-action contract the LLM follows. Mirrors our existing
    chatbot.services.agent_loop convention for compatibility."""
    lines = [
        '## Tool protocol',
        'When you want to take an action, reply with EXACTLY one JSON object:',
        '```json',
        '{"action": "tool", "tool": "<tool_code>", "args": { ... }}',
        '```',
        'When you are done and have your final answer, reply with:',
        '```json',
        '{"action": "final", "text": "your user-visible answer"}',
        '```',
        'No prose outside the JSON. No code fences except as shown.',
        'Available tools (call by code):',
    ]
    for tool in tools:
        lines.append(f'- `{tool.code}` — {tool.description}')
    return '\n'.join(lines)


def _resolve_tools(env, agent):
    """Effective tool set for the agent, ACL-filtered for the current user."""
    return agent.all_tool_ids.filtered(lambda t: t.is_invocable_by(env.user))


def _find_tool(tools, code):
    for t in tools:
        if t.code == code:
            return t
    return None


def _parse_response(text):
    """Parse the LLM's response into {'kind': 'tool'|'final', ...}.

    Tolerant: strips fences, accepts a JSON object embedded in surrounding
    prose, and falls back to treating the whole thing as a final answer.
    """
    if not text:
        return {'kind': 'final', 'text': ''}
    if isinstance(text, list):
        text = '\n'.join(str(x) for x in text)
    raw = str(text).strip()
    # Strip ```json fences.
    if raw.startswith('```'):
        raw = raw.split('```', 2)
        raw = raw[1] if len(raw) >= 2 else ''
        if raw.lower().startswith('json'):
            raw = raw[4:]
        raw = raw.strip().rstrip('`').strip()
    try:
        obj = json.loads(raw)
    except Exception:
        obj = None
    if isinstance(obj, dict) and 'action' in obj:
        if obj.get('action') == 'tool':
            return {'kind': 'tool', 'tool': obj.get('tool'),
                    'args': obj.get('args') or {}}
        if obj.get('action') == 'final':
            return {'kind': 'final', 'text': obj.get('text') or ''}
    return {'kind': 'final', 'text': text}


def _truncate(s, limit):
    s = s or ''
    return s if len(s) <= limit else s[:limit] + ' …[truncated]'


def _stringify_ref(ref):
    if not ref:
        return False
    if isinstance(ref, str):
        return ref
    try:
        return f'{ref._name},{ref.id}'
    except Exception:
        return False


# ───── envelopes for terminal non-done states ─────

def _budget_envelope(check, locale):
    if locale == 'ar':
        msg = 'تم بلوغ حد ميزانية الذكاء الاصطناعي. تواصل مع المسؤول لرفع الحد.'
    else:
        msg = ('The AI budget for this scope is exhausted. Contact your '
               'administrator to raise the limit.')
    return {
        'response': msg,
        'error': 'BUDGET_EXCEEDED_LOCAL',
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': 'AI budget reached', 'body': msg,
                 'tone': 'bad', 'icon': 'fa-exclamation-triangle'},
            ],
        },
    }


def _cost_capped_envelope(agent, spent, cap, locale):
    msg = (f'This run hit the per-run cost cap of ${cap:.4f} '
           f'(spent ${spent:.4f}). The agent stopped here for safety.')
    return {
        'response': msg,
        'error': 'COST_CAPPED',
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': 'Cost cap reached', 'body': msg,
                 'tone': 'bad', 'icon': 'fa-shield'},
            ],
        },
    }


def _maxhops_envelope(agent, locale):
    msg = (f'I reached the maximum of {agent.max_hops} steps without a clear '
           'answer. Could you rephrase or narrow the question?')
    return {
        'response': msg,
        'error': 'MAX_HOPS',
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': 'Step limit reached', 'body': msg,
                 'tone': 'warn', 'icon': 'fa-clock-o'},
            ],
        },
    }
