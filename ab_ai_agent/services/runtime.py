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
import re
import time

from odoo import fields
from odoo.addons.ab_ai_base.models.ai_service import CACHE_BREAK

from . import llm_adapter
from . import meter as meter_svc
from . import tool_dispatcher
from . import citation as citation_svc

_logger = logging.getLogger(__name__)


def run(env, *, agent, user_question, conversation=None, surface='chat',
        record_ref=None, skill=None, locale='en', max_hops=None,
        screen=None, history=None,
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

    # ── 2b. AI plan: only the first N active agents answer ────
    working = env['ai.agent'].sudo()._working_agent_ids()
    if working is not None and agent.id not in working:
        envelope = _agent_limit_envelope(env['ai.agent'].sudo()._agent_limit(), locale)
        agent_run.finalize(
            state='budget',
            response=envelope['response'],
            error='AGENT_LIMIT',
            latency_ms=int((time.perf_counter() - started_perf) * 1000),
        )
        on_event('done', run_id=agent_run.id, state='budget')
        return envelope['response'], agent_run, envelope

    # ── 3. Build system prompt + tool schemas ─────────────────
    # Retrieve org knowledge ONCE here so it's both injected and
    # captured on the audit row (monitor) without a double RAG hit.
    kb_block = _org_knowledge_block(env, user_question)
    # Screen context: what the user is looking at, re-derived as the
    # user (ai.screen.context never trusts the browser descriptor).
    screen_block = ''
    if screen:
        try:
            screen_block = env['ai.screen.context'].prompt_block(screen)
            # Tools may default to what is on screen ("confirm this"):
            # the validated model / open record, never the raw descriptor.
            norm = env['ai.screen.context'].normalize(screen) or {}
            if norm.get('model'):
                env = env(context=dict(env.context, ai_screen={
                    'model': norm['model'], 'res_id': norm.get('res_id') or False}))
        except Exception:
            _logger.info('screen context failed', exc_info=True)
    # Only the tools this question can use (performance: the tool list is
    # the largest part of every request), then the prompt that goes with them.
    tools = _route_tools(env, _resolve_tools(env, agent), user_question, screen)
    system_prompt = _compose_system_prompt(env, agent, locale=locale, skill=skill,
                                           screen_block=screen_block,
                                           record_ref=record_ref,
                                           user_question=user_question,
                                           org_knowledge=kb_block,
                                           tools=tools)
    llm_tool_schemas = [t.as_llm_schema(agent=agent) for t in tools]
    strong_model = _route_model(env, user_question)

    # ── 4. Hop loop ───────────────────────────────────────────
    hard_cap = min(agent.max_hops or 6, max_hops or 20)
    cost_cap = float(agent.max_cost_usd or 0)
    # Recent turns of THIS conversation, so "open the first one" / "and
    # last month?" resolve against what was just said. Goes in the user
    # prompt, not the system prompt, so it never breaks prefix caching.
    transcript = ([f'## Earlier in this conversation (oldest first)\n{history}\n\n'
                   f'## Current message\n{user_question}']
                  if history else [user_question])
    tool_calls_audit = []
    forced_tool_retry_used = False
    cum_cost = 0.0
    cum_tokens = {'p': 0, 'c': 0, 'cached': 0}
    final_text = ''
    final_provider = ''
    final_model = ''
    last_routed_via = ''
    # Set when a write tool proposed a change: the run stops right there
    # and the answer carries Confirm / Cancel chips (never executed here).
    pending_confirmation = None

    for hop in range(hard_cap):
        prompt_for_llm = "\n\n".join(transcript)
        on_event('thinking', run_id=agent_run.id, hop=hop + 1)

        try:
            response, usage, routed_via = llm_adapter.call_llm(
                env, agent,
                system_prompt=system_prompt,
                user_prompt=prompt_for_llm,
                tools=llm_tool_schemas,
                model_override=strong_model,
                temperature=agent.temperature(),
                # None = take the ceiling from the provider config
                # rather than pinning it here, where it silently
                # overrode that setting on gateway-routed tenants.
                max_tokens=None,
            )
        except llm_adapter.AiProviderError as e:
            # A configured provider/gateway failed — finalize as a real
            # error so monitoring sees it; never present a fake answer.
            envelope = _provider_error_envelope(locale)
            agent_run.finalize(
                state='error',
                response=envelope['response'],
                error=str(e)[:500],
                latency_ms=int((time.perf_counter() - started_perf) * 1000),
                tool_calls=tool_calls_audit,
            )
            on_event('done', run_id=agent_run.id, state='error')
            agent_run.sudo().write({
                'hops': hop + 1,
                'cost_usd': cum_cost,
                'routed_via': last_routed_via,
            })
            return envelope['response'], agent_run, envelope
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
        #   a) Provider-native tool calls — when ab_ai_base surfaces a
        #      structured ``usage['tool_calls']`` (OpenAI tool_calls /
        #      Anthropic tool_use blocks). Flag-gated via
        #      ``ab_ai_agent.native_tools_enabled``. Saves 600–1 200
        #      tokens / turn and unlocks parallel tool calls.
        #   b) JSON-action protocol — response text is a single JSON
        #      object {"action": "tool" | "final", ...}. Legacy path,
        #      identical to our pre-T.1/3 behavior. Used when the flag
        #      is off OR when the model didn't emit native tool_calls.
        native_calls = usage.get('tool_calls') or []
        if native_calls:
            # Native path: every call in the response is dispatched in
            # order. Anthropic / OpenAI both support parallel tool use
            # (multiple tool blocks in one response); we run them
            # sequentially because the existing dispatcher / audit
            # contract is per-call, and the typical pattern is still
            # one tool per hop.
            consumed_calls = []
            for nc in native_calls:
                tool_name = nc.get('name')
                tool_record = _find_tool(tools, tool_name)
                if not tool_record:
                    transcript.append(
                        f'Tool result: {{"error": "unknown_tool: {tool_name}"}}'
                    )
                    tool_calls_audit.append({
                        'tool': tool_name, 'ok': False, 'error': 'unknown_tool',
                    })
                    on_event('tool_call', tool=tool_name, ok=False)
                    consumed_calls.append((tool_name, False, None))
                    continue
                args = nc.get('arguments') or {}
                on_event('tool_call', tool=tool_record.code, args=args)
                tool_outcome = tool_dispatcher.dispatch(
                    env, tool_record, args,
                    agent=agent, agent_run=agent_run,
                )
                tool_calls_audit.append(tool_outcome)
                consumed_calls.append((tool_record.code, tool_outcome.get('ok'),
                                       tool_outcome))
                pending_confirmation = _proposal_of(tool_outcome)
                if pending_confirmation:
                    final_text = _confirmation_text(pending_confirmation, locale)
                    break
                # __end_message early termination — Odoo 19 native pattern.
                if tool_outcome.get('ok') and tool_outcome.get('end_message'):
                    final_text = tool_outcome['end_message']
                    break
            if final_text:
                break
            # Re-prompt: append every result so the next hop sees them
            # together. We keep stringified results (the model parses
            # them just like the legacy path) — a future refactor can
            # switch to provider-native tool_result blocks for true
            # parallel correlation, but that requires a messages[]
            # transcript instead of a string.
            for code, _ok, outcome in consumed_calls:
                if not outcome:
                    continue
                transcript.append(
                    'Tool result for `%s`: %s' % (
                        code,
                        _truncate(json.dumps(outcome.get('result'), default=str), 4000),
                    )
                )
            transcript.append(
                'Decide your next step. Either call another tool or '
                'return a "final" action with your answer.'
            )
            continue

        if not native_calls and not str(response or '').strip() and hop < hard_cap - 1:
            # An empty reply (Gemini: a malformed function call, reported
            # only as a finish reason) is not an answer — say so and let
            # the model try again instead of ending with "no answer".
            transcript.append(
                'Your previous reply was empty or an invalid function call '
                f'({usage.get("finish_reason") or "no content"}). Try again: call one '
                'tool with valid arguments, or answer the user in plain text.')
            continue

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

            pending_confirmation = _proposal_of(tool_outcome)
            if pending_confirmation:
                final_text = _confirmation_text(pending_confirmation, locale)
                break

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
        else:
            # No structured action — treat as a final freeform answer.
            final_text = response if isinstance(response, str) else (
                '\n'.join(response) if isinstance(response, list) else str(response)
            )
        final_text = _strip_control_tokens(final_text)

        # ── Grounding retry (#3) ──────────────────────────────
        # A data question answered with NO tool and NO knowledge
        # base is the single biggest source of wrong answers
        # (it recycles training data / stale context). Force ONE
        # corrective hop that must call a tool before we accept a
        # pure-LLM answer. Single-shot (no infinite loop): if the
        # model still won't use a tool, we take the answer.
        if (not forced_tool_retry_used
                and not any(c.get('ok') for c in tool_calls_audit)
                and not kb_block
                and not screen_block      # screen facts ARE live data
                and agent.all_tool_ids
                and hop < hard_cap - 1
                and _looks_like_data_question(user_question)):
            forced_tool_retry_used = True
            on_event('grounding_retry', run_id=agent_run.id, hop=hop + 1)
            transcript.append(
                'STOP. You answered a business/data question WITHOUT '
                'calling any tool, so the answer is not grounded in '
                'real data and is likely wrong. Do NOT answer from '
                'memory or from earlier conversation. Pick the single '
                'most relevant tool for this question and return a '
                '{"action":"tool", ...} now. Only after a tool returns '
                'may you give a "final" answer.'
            )
            continue

        break

    if not final_text:
        # We hit max_hops without a terminal step.
        envelope = _maxhops_envelope(agent, locale, partial=final_text)
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

    # ── 5. Lift render envelope ───────────────────────────────
    # The LLM was told to emit a JSON `render` block for reports.
    # When `final_text` is itself a JSON object with a `render` key,
    # extract that block and stash on the envelope so the OWL
    # <AiResponse/> renderer paints it as a data_table / kpi_grid
    # instead of dumping the raw JSON in the chat bubble.
    extracted_render = None
    extracted_text = final_text
    parsed_payload = _try_parse_report_payload(final_text)
    if parsed_payload:
        extracted_render = parsed_payload.get('render')
        extracted_text = parsed_payload.get('response') or parsed_payload.get('summary') or ''
        if not extracted_text and extracted_render:
            extracted_text = extracted_render.get('title') or ''

    # Tables the model typed into its prose (HTML or markdown) reach the
    # user as raw tags / pipes. Turn them into the renderer's own table.
    if not extracted_render:
        extracted_text, table = _absorb_prose_table(extracted_text)
        if table:
            extracted_render = {'layout': 'report', 'title': '', 'blocks': [table]}

    # Tool-produced render wins when the LLM didn't emit one itself.
    # Analysis/report tools (data_analysis, recent_records, …) return
    # {'render': {...}, 'summary': '...'} — numbers come straight from
    # the ORM, never the model. A compound request ("latest SO and
    # invoice and purchase") makes the agent call a tool once per
    # entity, so we MERGE every successful tool render into one
    # envelope (each as its own titled section) instead of keeping
    # only the last. The LLM's prose stays the narrative.
    if not extracted_render:
        tool_renders = []
        for call in tool_calls_audit:                 # natural call order
            if not call.get('ok'):
                continue
            res = call.get('result') or {}
            r = res.get('render') if isinstance(res, dict) else None
            if isinstance(r, dict) and r.get('blocks'):
                tool_renders.append((r, res.get('summary') or ''))
        if len(tool_renders) == 1:
            extracted_render = tool_renders[0][0]
            if not extracted_text:
                extracted_text = (tool_renders[0][1]
                                  or extracted_render.get('title') or '')
        elif len(tool_renders) > 1:
            merged = []
            for r, _summary in tool_renders:
                sect = r.get('title')
                if sect:
                    merged.append({'type': 'text', 'text': f'### {sect}'})
                merged.extend(r.get('blocks') or [])
            extracted_render = {
                'layout': 'report',
                'title': env._('Results'),
                'blocks': merged,
            }
            if not extracted_text:
                extracted_text = ' '.join(
                    s for _r, s in tool_renders if s)[:600]

    if pending_confirmation:
        chips = _confirmation_chips(pending_confirmation, locale)
        # The question itself must be on the card, not only the buttons.
        question = {'type': 'callout', 'tone': 'warn',
                    'title': pending_confirmation.get('summary') or '',
                    # What will happen (fields, lines, message), then the
                    # reminder. Callout bodies are plain text.
                    'body': '\n'.join((pending_confirmation.get('details') or [])
                                      + [_confirmation_text({'summary': ''}, locale)
                                         .strip().replace('**', '')])}
        if extracted_render:
            extracted_render = dict(extracted_render)
            extracted_render['blocks'] = list(extracted_render.get('blocks') or []) + [question, chips]
        else:
            extracted_render = {'layout': 'report', 'title': '', 'blocks': [question, chips]}

    # Tools that return plain rows (no render of their own) — the model
    # then writes "as follows:" and the list never reaches the user.
    # Show the rows of the last such result as a table.
    if not extracted_render:
        for call in reversed(tool_calls_audit):
            if call.get('tool') in _META_TOOLS:
                continue
            table = _auto_table(call.get('result')) if call.get('ok') else None
            if table:
                extracted_render = {'layout': 'report', 'title': '', 'blocks': [table]}
                break

    # ── 6. Citations ──────────────────────────────────────────
    rendered_text, sources = citation_svc.apply_numeric_citations(
        extracted_text, source_lookup or {})

    # ── 6b. Lift `action` from the most recent successful tool ─
    # Navigation tools (open_record / open_list / open_action / …)
    # return {'action': {…}} — the chat's "Open" button reads
    # envelope.action so the user lands on the view with one click.
    pending_action = None
    for call in reversed(tool_calls_audit):
        if not call.get('ok'):
            continue
        result = call.get('result') or {}
        if isinstance(result, dict) and result.get('action'):
            pending_action = result['action']
            break

    # Models keep writing `<action-button action_xmlid="…">label</…>`
    # into the prose instead of calling open_action, and the answer is
    # plain text, so the user reads the tag itself. Telling the model not
    # to did not stop it. Honour the intent instead: pull the xmlid out,
    # resolve it the same way open_action would, and drop the markup.
    rendered_text, inline_action = _absorb_action_markup(env, rendered_text)
    if inline_action and not pending_action:
        pending_action = inline_action

    # "Where do I…?" answered with a path but no button: the menu search
    # already found the destination, so give the user the way there.
    if not pending_action:
        for call in tool_calls_audit:
            res = call.get('result') if call.get('ok') else None
            if call.get('tool') == 'find_menu' and isinstance(res, dict) and res.get('matches'):
                xmlid = res['matches'][0].get('action_xmlid')
                opened = tool_dispatcher.get('open_action')(env, xmlid=xmlid) if xmlid else {}
                if isinstance(opened, dict) and opened.get('action'):
                    pending_action = opened['action']
                break

    # ── 7. Build the final envelope ───────────────────────────
    latency_ms = int((time.perf_counter() - started_perf) * 1000)
    envelope = {
        'response': rendered_text,
        'render': extracted_render,
        'action': pending_action,
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

    # Grounding signal — the triage lever for "this answer is wrong".
    # grounded   = a tool returned data OR KB facts were injected
    # partial    = tools were attempted but all failed
    # ungrounded = pure-LLM answer (no tool, no KB) — most likely
    #              to be inaccurate; the monitor flags these red.
    _tool_ok = any(c.get('ok') for c in tool_calls_audit)
    if _tool_ok or kb_block or screen_block:
        grounded = 'grounded'
    elif tool_calls_audit:
        grounded = 'partial'
    else:
        grounded = 'ungrounded'
    envelope['provenance']['grounded'] = grounded

    agent_run.finalize(
        state='done',
        response=rendered_text,
        latency_ms=latency_ms,
        tool_calls=tool_calls_audit,
        system_prompt=system_prompt,
        retrieved_context=kb_block or '',
        grounded=grounded,
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

def _proposal_of(tool_outcome):
    """The confirmation payload when a tool PROPOSED a change, else None."""
    if not (tool_outcome or {}).get('ok'):
        return None
    result = tool_outcome.get('result')
    if isinstance(result, dict) and result.get('requires_confirmation'):
        conf = result.get('confirmation') or {}
        if conf.get('key'):
            return conf
    return None


def _confirmation_text(conf, locale):
    # The details are part of the text so a spoken answer says exactly
    # what will happen before the user confirms by voice.
    summary = '\n'.join([conf.get('summary') or ''] + list(conf.get('details') or [])).strip()
    if str(locale or '').startswith('ar'):
        return (f'{summary}\n\nلم يتغير شيء بعد. اضغط **تأكيد** للتنفيذ '
                f'أو **إلغاء** للتراجع.')
    return (f'{summary}\n\nNothing has changed yet. Press **Confirm** to '
            f'go ahead or **Cancel** to leave it as it is.')


def _confirmation_chips(conf, locale):
    """Confirm / Cancel chips. The chip carries only the proposal key;
    the confirm endpoint looks the call up server-side, so nothing the
    browser sends can change WHAT gets executed."""
    arabic = str(locale or '').startswith('ar')
    key = conf['key']
    return {
        'type': 'suggestion_chips',
        'title': '',
        'items': [
            {'label': 'تأكيد' if arabic else 'Confirm', 'icon': 'fa-check',
             'action': {'type': 'confirm_pending', 'key': key}},
            {'label': 'إلغاء' if arabic else 'Cancel', 'icon': 'fa-times',
             'action': {'type': 'cancel_pending', 'key': key}},
        ],
    }


def _compose_system_prompt(env, agent, *, locale='en', skill=None,
                           record_ref=None, user_question=None,
                           org_knowledge=None, screen_block='', tools=None):
    """Compose the system prompt = persona + topics + date reference
    + live business snapshot + org knowledge (RAG) + user context
    + record context.

    The aim is comprehensive data knowledge BEFORE the LLM picks a
    tool: counts of every key entity (orders, invoices, POS sessions,
    customers, employees) injected up front so the model can answer
    overview questions without round-trips, and can spot what tool
    to call for deeper figures."""
    # ── STABLE PREFIX ──────────────────────────────────────────
    # Everything here depends only on the agent, not on the question,
    # the data or the moment. It must come FIRST and stay byte-identical
    # between turns, because that is the only thing a provider prefix
    # cache can match on.
    #
    # It used to be interleaved: persona, then the live snapshot, then
    # per-question RAG, and only THEN the report/chart/topic/tool blocks
    # — several thousand invariant tokens sitting behind content that
    # changes with every question. No two requests shared a prefix, so
    # nothing was ever cacheable. Ordering is the whole fix; not one
    # block was added or removed.
    parts = [agent.system_prompt or '']

    # How to render reports (P&L, sales summary, etc.) as data_table.
    parts.append(_report_rendering_block())

    # How to answer trend/analytics questions with an accurate chart.
    parts.append(_chart_rendering_block())

    # Topic instructions.
    if agent.topic_ids:
        topic_text = '\n\n'.join(
            f'### Topic: {t.name}\n{t.instructions or ""}'.strip()
            for t in agent.topic_ids
        )
        parts.append(topic_text)

    # Tool protocol — the largest invariant block, so it earns its place
    # inside the cacheable prefix rather than after the volatile parts.
    offered = tools if tools is not None else _resolve_tools(env, agent)
    if offered:
        parts.append(_tool_protocol_block(offered,
                                          native=llm_adapter.native_tools_active(env)))

    # ── VOLATILE SUFFIX ────────────────────────────────────────
    # From here on the content varies by user, by data, by question or
    # by the minute. Anything appended below this line shortens the
    # cacheable prefix for everyone, so add with care.

    # Boundary for providers with explicit cache markers (Anthropic):
    # ab_ai_base splits here and caches only what comes before. Other
    # providers strip it (they cache by prefix on their own).
    parts.append(CACHE_BREAK)

    # Caller context — who is asking, from where. Stable per user, but
    # differs between users, so it cannot sit in the shared prefix.
    parts.append(_user_context_block(env))

    # What this user asked us to remember (their preferences / notes),
    # when memory is on and the user has not opted out.
    memory = _user_memory_block(env)
    if memory:
        parts.append(memory)

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

    # Live business snapshot — comprehensive counts + open items so
    # the agent can answer overview questions without a tool round-trip.
    # Skipped when the question comes with a screen: the screen block is
    # the relevant, smaller context, and the ~14 snapshot probes were the
    # largest per-turn cost (docs/ghaima-ai/IMPLEMENTATION_PLAN.md §3.7).
    if screen_block:
        parts.append(screen_block)
    else:
        snapshot = _business_snapshot_block(env)
        if snapshot:
            parts.append(snapshot)

    # Organisation knowledge (RAG) — retrieved against THIS question, so
    # it is the most volatile block and goes last before record context.
    kb = (org_knowledge if org_knowledge is not None
          else _org_knowledge_block(env, user_question))
    if kb:
        parts.append(kb)

    # Record context — when the call comes from chatter, we dump the
    # record's actual field values into the prompt so the LLM can
    # answer from real data instead of guessing. Uses Odoo 19's
    # `_ai_truncate` pattern through ai.usage.local.log's referenceable
    # whitelist; here we go through fields_get + read with a max-size
    # guard so we don't blow the token budget on a 100-line invoice.
    if record_ref:
        try:
            parts.append(_record_context_block(env, record_ref))
        except Exception as e:
            _logger.debug("record_context_block failed", exc_info=True)
            parts.append(
                f'## Active record\n'
                f'You are helping the user with `{record_ref._name}` id {record_ref.id}.'
            )

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


def _try_parse_report_payload(text):
    """When the LLM emits a final answer as JSON `{"render": {...}}`,
    return a dict with parsed render + optional summary. Returns None
    if `text` isn't a parseable report payload.

    Tolerant of ```json fences and surrounding whitespace."""
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    # Strip ```json … ``` fences.
    if raw.startswith('```'):
        raw = raw.lstrip('`')
        if raw.lower().startswith('json'):
            raw = raw[4:]
        raw = raw.strip()
        if raw.endswith('```'):
            raw = raw[:-3].rstrip()
    import json as _json
    decoder = _json.JSONDecoder(strict=False)
    if raw.startswith('{') and raw.endswith('}'):
        try:
            obj = decoder.decode(raw)
        except (ValueError, TypeError):
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get('render'), dict):
            return {'render': obj['render'],
                    'response': obj.get('response') or obj.get('summary') or ''}
    # The other shape models produce: prose, then the {"render": …} object
    # (the user used to read that JSON verbatim). Lift the object out and
    # keep the prose as the answer text.
    at = raw.find('{"render"')
    if at < 0:
        return None
    try:
        obj, end = decoder.raw_decode(raw[at:])
    except ValueError:
        return None
    if not (isinstance(obj, dict) and isinstance(obj.get('render'), dict)):
        return None
    prose = (raw[:at] + raw[at + end:]).strip()
    return {'render': obj['render'],
            'response': prose or obj.get('response') or obj.get('summary') or ''}


def _csv_everywhere_enabled(env):
    """T.1 Tactic 7 — when on, multi-row context blocks render as
    pipe-delimited CSV instead of markdown bullets. Saves ~40 % tokens
    on tabular data (no labels repeated per row). Default off."""
    icp = env['ir.config_parameter'].sudo()
    return str(icp.get_param('ab_ai_agent.csv_everywhere', 'False')).lower() \
            in ('1', 'true', 'yes')


def _business_snapshot_block(env):
    """Pre-fetch comprehensive counts + open-item summaries so the
    LLM has business-wide context before its first tool call.

    Each probe is wrapped in a savepoint — missing models/tables
    on this tenant just produce a "—" placeholder, never crash.

    Renders as markdown bullets by default. When
    ``ab_ai_agent.csv_everywhere`` is True, emits the same data as
    pipe-delimited CSV (`section|metric|value|extra`), which the LLM
    parses just as reliably but at ~40 % fewer tokens.
    """
    # NOTE: reads run as the REQUESTING USER (no sudo) so record rules and
    # the ab.branch.mixin _search filter apply — a branch-scoped or
    # low-privilege user gets only their own scope in the snapshot, never
    # company-wide / cross-branch totals. A model the user can't read just
    # raises AccessError → caught → "—" placeholder.
    def _safe_count(model, domain=None):
        try:
            with env.cr.savepoint(flush=False):
                if model not in env:
                    return None
                return env[model].search_count(domain or [])
        except Exception:
            return None

    def _safe_sum(model, field, domain=None):
        try:
            with env.cr.savepoint(flush=False):
                if model not in env:
                    return None
                groups = env[model].read_group(
                    domain or [], [field], [],
                )
                return groups[0].get(field) if groups else None
        except Exception:
            return None

    from odoo import fields as _odoo_fields
    today = _odoo_fields.Date.context_today(env['res.users'])
    month_start = today.replace(day=1)

    # Collect (section, metric, value, extra) tuples — value/extra may
    # be None and are stripped in the render step.
    facts = []

    # ── Sales ───────────────────────────────────────────────────
    n_so_today = _safe_count('sale.order', [
        ('date_order', '>=', str(today)),
        ('state', 'in', ('sale', 'done')),
    ])
    n_so_month = _safe_count('sale.order', [
        ('date_order', '>=', str(month_start)),
        ('state', 'in', ('sale', 'done')),
    ])
    n_so_draft = _safe_count('sale.order', [('state', '=', 'draft')])
    amt_so_today = _safe_sum('sale.order', 'amount_total', [
        ('date_order', '>=', str(today)),
        ('state', 'in', ('sale', 'done')),
    ])
    amt_so_month = _safe_sum('sale.order', 'amount_total', [
        ('date_order', '>=', str(month_start)),
        ('state', 'in', ('sale', 'done')),
    ])
    if any(v is not None for v in (n_so_today, n_so_month)):
        facts.append(('sales', 'orders_today', n_so_today, amt_so_today))
        facts.append(('sales', 'orders_month', n_so_month, amt_so_month))
        facts.append(('sales', 'orders_draft', n_so_draft, None))

    # ── POS ─────────────────────────────────────────────────────
    n_pos_today = _safe_count('pos.order', [('date_order', '>=', str(today))])
    amt_pos_today = _safe_sum('pos.order', 'amount_total', [('date_order', '>=', str(today))])
    n_pos_sessions = _safe_count('pos.session', [('state', '=', 'opened')])
    if any(v is not None for v in (n_pos_today, n_pos_sessions)):
        facts.append(('pos', 'orders_today', n_pos_today, amt_pos_today))
        facts.append(('pos', 'sessions_open', n_pos_sessions, None))

    # ── Invoices / AR ──────────────────────────────────────────
    n_inv_draft = _safe_count('account.move', [
        ('move_type', '=', 'out_invoice'), ('state', '=', 'draft'),
    ])
    n_inv_overdue = _safe_count('account.move', [
        ('move_type', '=', 'out_invoice'),
        ('state', '=', 'posted'),
        ('payment_state', 'in', ('not_paid', 'partial')),
        ('invoice_date_due', '<', str(today)),
    ])
    amt_inv_overdue = _safe_sum('account.move', 'amount_residual', [
        ('move_type', '=', 'out_invoice'),
        ('state', '=', 'posted'),
        ('payment_state', 'in', ('not_paid', 'partial')),
        ('invoice_date_due', '<', str(today)),
    ])
    if any(v is not None for v in (n_inv_draft, n_inv_overdue)):
        facts.append(('invoice', 'draft', n_inv_draft, None))
        facts.append(('invoice', 'overdue', n_inv_overdue, amt_inv_overdue))

    # ── Inventory ──────────────────────────────────────────────
    n_picking_todo = _safe_count('stock.picking', [
        ('state', 'in', ('assigned', 'confirmed')),
    ])
    if n_picking_todo is not None:
        facts.append(('stock', 'pickings_pending', n_picking_todo, None))

    # ── HR ──────────────────────────────────────────────────────
    n_emp = _safe_count('hr.employee', [('active', '=', True)])
    n_leave_pending = _safe_count('hr.leave', [('state', '=', 'confirm')])
    if n_emp is not None:
        facts.append(('hr', 'employees_active', n_emp, None))
        if n_leave_pending is not None:
            facts.append(('hr', 'leave_pending', n_leave_pending, None))

    # ── CRM ────────────────────────────────────────────────────
    n_lead_open = _safe_count('crm.lead', [('active', '=', True), ('type', '=', 'opportunity')])
    if n_lead_open is not None:
        facts.append(('crm', 'opportunities_open', n_lead_open, None))

    # ── Customers ─────────────────────────────────────────────
    n_partner = _safe_count('res.partner', [('customer_rank', '>', 0)])
    if n_partner is not None:
        facts.append(('customers', 'total', n_partner, None))

    if not facts:
        return ''

    tail = (
        '\n\nUse these counts to ground overview answers. For exact '
        'amounts or breakdowns by period/branch/product, call the '
        'matching tool (`sales_totals`, `pl_summary`, `top_customers`, …).'
    )

    if _csv_everywhere_enabled(env):
        # CSV form — single line per fact, pipe-delimited. No repeated
        # labels. ~40 % fewer tokens than the markdown form.
        lines = ['## Live business snapshot (CSV)',
                 'section|metric|count|amount']
        for section, metric, count, amount in facts:
            count_s = '' if count is None else f'{int(count)}'
            amount_s = '' if amount is None else f'{float(amount):.2f}'
            lines.append(f'{section}|{metric}|{count_s}|{amount_s}')
        return '\n'.join(lines) + tail

    # Markdown form — legacy.
    rows = []
    for section, metric, count, amount in facts:
        label = _SNAPSHOT_LABELS.get((section, metric), f'{section}.{metric}')
        if amount is not None and count is not None:
            rows.append(f'- {label}: {_fmt_count(count)} (total: {_fmt_money(amount)})')
        elif count is not None:
            rows.append(f'- {label}: {_fmt_count(count)}')
        elif amount is not None:
            rows.append(f'- {label}: {_fmt_money(amount)}')
    return '## Live business snapshot\n' + '\n'.join(rows) + tail


_SNAPSHOT_LABELS = {
    ('sales', 'orders_today'):       'Sale orders confirmed today',
    ('sales', 'orders_month'):       'Sale orders confirmed this month',
    ('sales', 'orders_draft'):       'Sale orders still in draft',
    ('pos', 'orders_today'):         'POS orders today',
    ('pos', 'sessions_open'):        'POS sessions currently open',
    ('invoice', 'draft'):            'Customer invoices in draft',
    ('invoice', 'overdue'):          'Customer invoices overdue',
    ('stock', 'pickings_pending'):   'Stock pickings pending',
    ('hr', 'employees_active'):      'Active employees',
    ('hr', 'leave_pending'):         'Pending leave requests',
    ('crm', 'opportunities_open'):   'Open CRM opportunities',
    ('customers', 'total'):          'Customers on file',
}


def _user_context_block(env):
    """Who's asking + which company + which surface."""
    user = env.user
    company = env.company
    parts = ['## Caller']
    parts.append(f'- User: {user.name} (id {user.id}, login {user.login})')
    if user.lang:
        parts.append(f'- User locale: {user.lang}')
    parts.append(f'- Company: {company.name} (id {company.id})')
    if getattr(company, 'currency_id', False):
        parts.append(f'- Currency: {company.currency_id.name}')
    if getattr(company, 'country_id', False):
        parts.append(f'- Country: {company.country_id.name}')
    if user.tz:
        parts.append(f'- Timezone: {user.tz}')
    return '\n'.join(parts)


_DATA_Q_HINTS = (
    'sale', 'sales', 'invoice', 'bill', 'order', 'customer', 'client',
    'revenue', 'profit', 'loss', 'p&l', 'pnl', 'margin', 'stock',
    'inventory', 'product', 'employee', 'attendance', 'leave', 'payment',
    'cash', 'bank', 'total', 'amount', 'balance', 'overdue', 'aging',
    'trend', 'report', 'pos', 'session', 'how many', 'how much', 'count',
    'list', 'latest', 'recent', 'last ', 'top ', 'best', 'worst',
    'compare', 'today', 'yesterday', 'week', 'month', 'quarter', 'year',
    'expense', 'purchase', 'vendor', 'supplier', 'tax', 'due',
    # Arabic
    'مبيعات', 'فاتورة', 'فواتير', 'طلب', 'طلبات', 'عميل', 'عملاء',
    'مخزون', 'ربح', 'تقرير', 'كم', 'اجمالي', 'إجمالي', 'احدث', 'أحدث',
    'اخر', 'آخر', 'رصيد', 'دفعة', 'مصروف', 'ضريبة',
)


def _looks_like_data_question(q):
    """Conservative heuristic: does this question want real business
    data (so an answer with no tool/KB is probably wrong)? A digit or
    any business-noun hint qualifies; pure greetings / how-to / concept
    questions do not, so we don't force a pointless tool hop on them."""
    if not q:
        return False
    t = q.lower()
    if any(ch.isdigit() for ch in t):
        return True
    return any(h in t for h in _DATA_Q_HINTS)


def _org_knowledge_block(env, query):
    """RAG grounding for the unified runtime.

    Dependency-safe: ab_ai_agent (saas-share) must not import the
    domain chatbot module, so we duck-type a knowledge model that
    exposes ``to_prompt_block``. Today that is ab_ai_chatbot's
    ``ai.chat.fact`` (hybrid pgvector + pg_trgm retrieval with a
    similarity floor). Absent / failing → empty string, never raises.

    top_k is ``ab_ai_agent.rag_top_k`` (default 4)."""
    if not query:
        return ''
    Fact = env.get('ai.chat.fact')
    if Fact is None or not hasattr(Fact, 'to_prompt_block'):
        return ''
    try:
        top_k = int(env['ir.config_parameter'].sudo()
                    .get_param('ab_ai_agent.rag_top_k', '4'))
    except (TypeError, ValueError):
        top_k = 4
    try:
        return Fact.sudo().to_prompt_block(query, limit=top_k) or ''
    except Exception:
        _logger.debug('org knowledge retrieval failed', exc_info=True)
        return ''


def _report_rendering_block():
    """Tell the LLM how to format report-style answers using the
    block kit the <AiResponse/> renderer understands."""
    return (
        '## How to render a report\n'
        'When the user asks for a structured view — P&L, sales summary, '
        'top customers, AR aging — your final answer should be a JSON '
        '`final` action whose `text` is a JSON object with a top-level '
        '`render` block. The renderer paints `kpi_grid`, `data_table`, '
        '`highlight_list`, and `callout` blocks natively.\n\n'
        'Example for P&L:\n'
        '```json\n'
        '{"action": "final", "text": "{\\"render\\": {\\"layout\\": \\"report\\", '
        '\\"title\\": \\"Profit & Loss — Oct 2026\\", \\"blocks\\": ['
        '{\\"type\\": \\"kpi_grid\\", \\"items\\": ['
        '{\\"label\\": \\"Revenue\\", \\"value\\": \\"125,400 SAR\\"}, '
        '{\\"label\\": \\"COGS\\", \\"value\\": \\"68,200 SAR\\"}, '
        '{\\"label\\": \\"Gross margin\\", \\"value\\": \\"45.6 %\\", \\"tone\\": \\"good\\"}]}, '
        '{\\"type\\": \\"data_table\\", \\"title\\": \\"By account\\", '
        '\\"headers\\": [\\"Account\\", \\"Amount\\"], \\"rows\\": [[\\"Sales\\", \\"125,400\\"], [\\"COGS\\", \\"-68,200\\"]]}]}}"}\n'
        '```\n'
        'Plain prose answers stay plain strings — use the render block '
        'only when the data benefits from a table or KPI tiles.'
    )


def _chart_rendering_block():
    """Tell the LLM to route trend/analytics questions through the
    deterministic data_analysis tool instead of inventing numbers."""
    return (
        '## Trends & charts (CRITICAL)\n'
        'For ANY question about a metric over time or vs another period '
        '— "sales trend", "POS sales last 30 days", "how are we doing", '
        '"compare this month to last", "weekly/monthly breakdown" — you '
        'MUST call the `data_analysis` tool. NEVER hand-build chart JSON '
        'and NEVER invent or estimate figures: the tool computes them '
        'from the database and returns the chart, KPI grid and peak '
        'callout fully rendered.\n'
        '- Pick `metric` (pos_sales | sale_orders | invoiced_revenue), '
        '`period_days`, and `group` (day/week/month) from the question.\n'
        '- After the tool returns, DO NOT restate the table or numbers. '
        'Your `final` answer is ONE short paragraph (plain string): what '
        'changed, why it matters, and one concrete recommended action.\n'
        'The chart is attached automatically — your prose sits above it.'
    )


def _fmt_count(n):
    if n is None:
        return '—'
    try:
        return f'{int(n):,}'
    except Exception:
        return str(n)


def _fmt_money(amt):
    if amt is None:
        return '—'
    try:
        return f'{float(amt):,.2f}'
    except Exception:
        return str(amt)


def _record_context_block(env, record):
    """Dump a record's fields into a Markdown block for the system prompt.

    Goals:
      * Show the LLM real data so the answer is grounded
      * Bounded size — skip binary + html, truncate text, cap relational
        previews at 50 items
      * ACL-safe — relies on the active env (current user's permissions)

    Returns a string ready to append to the system prompt parts."""
    if not record or not record.exists():
        return ''
    Model = env[record._name]
    model_label = Model._description or record._name

    # Pull fields the user can read. Skip noisy types upfront.
    skip_types = {'binary', 'html'}
    skip_names = {'__last_update', 'create_date', 'write_date',
                  'create_uid', 'write_uid', 'message_ids',
                  'message_follower_ids', 'message_partner_ids',
                  'activity_ids', 'activity_user_id', 'activity_state',
                  'activity_summary', 'activity_date_deadline',
                  'website_message_ids', 'access_token'}
    fields_info = Model.fields_get()

    lines = [
        '## Active record (the user is looking at this)',
        f'- Model: `{record._name}` ({model_label})',
        f'- Record id: {record.id}',
    ]
    try:
        lines.append(f'- Display name: "{record.display_name}"')
    except Exception:
        pass

    # Chatter snapshot — last 3 message bodies (text-only).
    try:
        if 'message_ids' in record._fields and record.message_ids:
            recent = record.sudo().message_ids.sorted('date', reverse=True)[:3]
            chatter_bits = []
            for m in recent:
                body = (m.body or '').strip()
                # Strip HTML; budget per bubble.
                import re as _re
                txt = _re.sub(r'<[^>]+>', ' ', body)
                txt = _re.sub(r'\s+', ' ', txt).strip()
                if txt:
                    who = (m.author_id.name if m.author_id else m.email_from) or 'system'
                    chatter_bits.append(f'  - {m.date} · {who}: "{txt[:300]}"')
            if chatter_bits:
                lines.append('- Recent chatter:')
                lines.extend(chatter_bits)
    except Exception:
        pass

    lines.append('')
    lines.append('### Field values')
    for fname, info in sorted(fields_info.items()):
        if fname in skip_names:
            continue
        ftype = info.get('type', '')
        if ftype in skip_types:
            continue
        try:
            value = record[fname]
        except Exception:
            continue
        if value in (False, None, '', []):
            continue
        # Relational handling.
        if ftype == 'many2one':
            try:
                value = f'{value.display_name} (id {value.id})'
            except Exception:
                continue
        elif ftype in ('one2many', 'many2many'):
            try:
                items = value[:50]
                names = [r.display_name for r in items]
                value = f'[{len(value)} total] ' + ', '.join(filter(None, names))[:600]
            except Exception:
                continue
        elif isinstance(value, str) and len(value) > 800:
            value = value[:800] + ' …[truncated]'
        elif hasattr(value, 'strftime'):
            value = value.strftime('%Y-%m-%d %H:%M' if ftype == 'datetime' else '%Y-%m-%d')
        label = info.get('string') or fname
        lines.append(f'- **{label}** (`{fname}`): {value}')

    lines.append('')
    lines.append('Use these field values as ground truth. Cite the field '
                 'name in your answer when relevant.')
    return '\n'.join(lines)


def _tool_protocol_block(tools, native=False):
    """How the model acts and answers.

    native: tools arrive as provider function declarations, so the model
    calls them natively and answers in plain markdown — no JSON protocol
    for it to break. Otherwise the JSON-action text contract (mirrors the
    chatbot.services.agent_loop convention)."""
    if native:
        lines = [
            '## Tools',
            'Use the provided functions to look things up or act; call as many '
            'as the question needs. To change anything (confirm, post, validate, '
            'cancel) call `screen_button` (or `record_action` for a document named '
            'by its number): it shows the user Confirm / Cancel buttons — never ask '
            'for confirmation in text. When you have the answer, reply to the user '
            'in plain text (markdown allowed: short paragraphs, bullet lists, '
            'tables). Never write JSON, code fences or tool names in the reply.',
        ]
        # No tool list here: the function declarations already carry every
        # name and description — listing them twice doubled the prompt.
        return '\n'.join(lines)
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
    """Effective tool set for the agent, ACL-filtered for the current user.

    Write tools the agent may not run are not offered at all: listing a
    tool the dispatcher will refuse only teaches the model to call it
    again and again (a native-tools run spent 12 steps on a blocked
    confirm_sale_order while screen_button — confirm-first — was there).
    """
    icp = env['ir.config_parameter'].sudo()

    def flag(key, default='True'):
        return str(icp.get_param(key, default)).lower() in ('1', 'true', 'yes')
    actions_on = flag('ab_ai_agent.actions_enabled')
    # The plan (central) is a ceiling: a tenant setting cannot re-enable
    # what the subscription does not include.
    from .llm_adapter import gateway_policy
    if gateway_policy(env).get('actions') is False:
        actions_on = False
    memory_on = flag('ab_ai_agent.user_memory')

    def allowed(t):
        if not t.is_invocable_by(env.user):
            return False
        if t.code in ACTION_TOOLS and not actions_on:
            return False
        if t.is_write_action:
            # A user's own memory is theirs to write; everything else needs
            # the agent's write permission (confirm-first action tools are
            # not write actions at dispatch — they only propose).
            return (t.category == 'memory' and memory_on) or agent.allow_write_actions
        return True
    return agent.all_tool_ids.filtered(allowed)


ACTION_TOOLS = frozenset({'screen_button', 'act_on_record', 'create_record', 'update_record',
                          'post_message', 'schedule_activity'})

# Tool routing: which tools a question can need. CORE is always offered;
# a group joins when the question (Arabic or English) mentions its world.
_CORE_TOOLS = frozenset({'explain_screen', 'open_record', 'open_list', 'open_action', 'find_menu',
                         'list_my_apps', 'date_reference', 'query_data', 'get_record',
                         'search_records', 'recent_records', 'kb_search', 'kb_read'})
_TOOL_GROUPS = (
    (ACTION_TOOLS | {'record_action'},
     ('أنشئ', 'انشئ', 'اعمل', 'سو', 'أضف', 'اضف', 'أكد', 'اكد', 'اعتمد', 'وافق', 'ارفض', 'أرسل', 'ارسل',
      'رحل', 'رحّل', 'ألغ', 'الغ', 'غير', 'غيّر', 'عدل', 'عدّل', 'حدث', 'ذكر', 'جدول', 'اكتب', 'سجل',
      'create', 'add', 'new', 'make', 'confirm', 'approve', 'validate', 'reject', 'refuse', 'send',
      'post', 'cancel', 'change', 'update', 'set ', 'edit', 'remind', 'schedule', 'log ', 'note',
      'press', 'click')),
    ({'sales_totals', 'top_customers', 'top_products', 'sales_trend_monthly', 'sales_by_branch',
      'data_analysis', 'open_graph', 'open_pivot', 'customer_activity'},
     ('مبيع', 'بيع', 'عميل', 'عملاء', 'منتج', 'فرع', 'إيراد', 'ايراد', 'اتجاه', 'رسم', 'مقارن',
      'sale', 'sold', 'revenue', 'customer', 'product', 'branch', 'trend', 'chart', 'compare', 'top')),
    ({'ar_aging', 'overdue_receivables', 'top_overdue_partners', 'cash_position', 'cashflow_by_journal',
      'cashflow_daily', 'pl_summary', 'pl_trend', 'tax_summary'},
     ('فاتور', 'متأخر', 'متاخر', 'مستحق', 'دين', 'نقد', 'صندوق', 'بنك', 'ربح', 'خسار', 'ضريب', 'حساب',
      'invoice', 'overdue', 'receivable', 'aging', 'cash', 'bank', 'profit', 'loss', 'p&l', 'tax', 'vat',
      'account')),
    ({'inventory_summary', 'low_stock_products', 'out_of_stock_products', 'product_stock_status',
      'reorder_rules'},
     ('مخزون', 'مخزن', 'كمية', 'نفد', 'نفاد', 'stock', 'inventory', 'warehouse', 'quantity', 'reorder')),
    ({'pos_session_status', 'top_cashiers'},
     ('كاشير', 'نقاط البيع', 'جلسة', 'وردية', 'pos', 'cashier', 'session', 'shift')),
    ({'hr_attendance_missing_today', 'hr_leave_pending', 'hr_attendance_open_shifts'},
     ('موظف', 'حضور', 'غياب', 'إجاز', 'اجاز', 'دوام', 'employee', 'attendance', 'leave', 'absent',
      'time off', 'staff')),
    ({'remember_note', 'remember_fact', 'update_preference'},
     ('تذكر', 'احفظ', 'فضل', 'دائما', 'دائماً', 'remember', 'prefer', 'always', 'note that')),
)
_ALL_ROUTED = frozenset().union(*(g for g, _w in _TOOL_GROUPS)) | _CORE_TOOLS


def _user_memory_block(env):
    icp = env['ir.config_parameter'].sudo()
    if str(icp.get_param('ab_ai_agent.user_memory', 'True')).lower() not in ('1', 'true', 'yes'):
        return ''
    Profile = env.get('ai.chat.user.profile')
    if Profile is None:
        return ''
    try:
        profile = Profile.get_for_user()
        if not profile.opt_in_memory:
            return ''
        block = profile.to_prompt_block() or ''
    except Exception:
        _logger.debug('user memory unavailable', exc_info=True)
        return ''
    return f'## What this user asked you to remember\n{block[:1500]}' if block.strip() else ''


_COMPLEX_WORDS = ('حلل', 'تحليل', 'قارن', 'مقارنة', 'لماذا', 'ليش', 'خطة', 'اقترح', 'توقع', 'استراتيج',
                  'analy', 'compare', 'why', 'plan', 'suggest', 'forecast', 'strategy', 'explain why',
                  'recommend')


def _route_model(env, question):
    """The stronger model for complex questions (analysis, why, plans,
    multi-part), when one is configured; None = the default model."""
    strong = (env['ir.config_parameter'].sudo().get_param('ab_ai_agent.strong_model') or '').strip()
    if not strong:
        return None
    q = (question or '').lower()
    parts = sum(q.count(c) for c in ('?', '؟', ' and ', ' و'))
    if any(w in q for w in _COMPLEX_WORDS) or len(q) > 220 or parts >= 3:
        return strong
    return None


def _route_tools(env, tools, question, screen=None):
    """The tools this question can use.

    Every function declaration costs tokens on every step; 50 tools is the
    largest part of a request. Core tools are always there; a group joins
    when the question mentions its subject; a question that matches no
    group keeps everything (never worse than before). Tools no group
    knows (from other modules) are always kept. Switch:
    ``ab_ai_agent.tool_routing``.
    """
    icp = env['ir.config_parameter'].sudo()
    if str(icp.get_param('ab_ai_agent.tool_routing', 'True')).lower() not in ('1', 'true', 'yes'):
        return tools
    q = f" {(question or '').lower()} "
    wanted, matched = set(_CORE_TOOLS), False
    for group, words in _TOOL_GROUPS:
        if any(w in q for w in words):
            wanted |= group
            matched = True
    if (screen or {}).get('res_id') or (screen or {}).get('view_type') == 'form':
        wanted |= ACTION_TOOLS          # "this" record: acting on it is likely
    if not matched:
        return tools
    return tools.filtered(lambda t: t.code in wanted or t.code not in _ALL_ROUTED)


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
    obj = _loads_tolerant(raw)
    if obj is None:
        # Invalid JSON that is still unmistakably a final answer — usually
        # unescaped quotes inside the text ("أمر البيع"). Take the text.
        m = _FINAL_SHAPE.match(raw)
        if m:
            body = m.group(1).replace('\\n', '\n').replace('\\"', '"')
            return {'kind': 'final', 'text': body}
    if isinstance(obj, dict) and ('action' in obj or 'tool' in obj or 'tool_code' in obj):
        action = obj.get('action')
        tool = obj.get('tool') or obj.get('tool_code')
        if action == 'final':
            return {'kind': 'final', 'text': obj.get('text') or obj.get('response') or ''}
        # Models answer the protocol in several shapes:
        #   {"action": "tool", "tool": "open_record", "args": {…}}   (asked for)
        #   {"action": "open_record", "args": {…}}                     (tool as action)
        #   {"action": "open_record", "tool_code": "open_record", …}
        # All are the same intent: run the tool. Showing the JSON to the
        # user instead (what happened before) is the one wrong answer.
        if action == 'tool' or tool or (isinstance(action, str) and 'args' in obj):
            name = tool if tool else action
            if isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_]{1,63}', name):
                return {'kind': 'tool', 'tool': name, 'args': obj.get('args') or {}}
    return {'kind': 'final', 'text': text}


_FINAL_SHAPE = re.compile(
    r'^\s*\{\s*"action"\s*:\s*"final"\s*,\s*"text"\s*:\s*"(.*)"\s*\}\s*$', re.DOTALL)


def _loads_tolerant(raw):
    """A JSON object from model output, or None.

    strict=False accepts the literal newlines models put inside strings
    (invalid JSON, but unambiguous); raw_decode finds an object that is
    preceded or followed by prose.
    """
    for candidate in (raw, raw[raw.find('{'):] if '{' in raw else ''):
        if not candidate:
            continue
        try:
            obj, _end = json.JSONDecoder(strict=False).raw_decode(candidate)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    return None


#: Protocol tokens the topic prompts instruct the model to emit. They
#: are control flow, not prose — but models routinely type them into
#: the answer instead of acting on them, and the user then reads
#: "…Opening this screen for you now. __end_message".
_CONTROL_TOKENS = ('__end_message',)


#: `<action-button action_xmlid="account.action_move_out_invoice">Open</…>`
#: and the underscore spelling the model also produces, self-closing or not.
_ACTION_MARKUP = re.compile(
    r'<action[-_]button\b[^>]*?action_xmlid\s*=\s*["\']([^"\']+)["\'][^>]*>'
    r'(?:(.*?)</action[-_]button>|)',
    re.IGNORECASE | re.DOTALL)

#: Direction wrappers the model adds around Arabic. The UI already sets
#: dir on the shell, so these only ever reach the user as literal text.
_DIR_MARKUP = re.compile(r'</?span\b[^>]*>', re.IGNORECASE)

#: The other shape of the same mistake: instead of *calling* a tool the
#: model writes the call out as JSON in its prose —
#: `{"action": "tool", "tool": "open_action", "args": {…}}`. Intermittent,
#: but when it happens the user reads raw JSON. One level of nesting is
#: enough for the `args` object.
_TOOL_JSON = re.compile(
    r'\{[^{}]*"tool"\s*:\s*"[a-z_]+"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')

#: Any xmlid the model named, whichever wrapper it used.
_XMLID = re.compile(r'action_xmlid"?\s*[:=]\s*"?\'?([\w.]+\.[\w.]+)')


def _absorb_action_markup(env, text):
    """Turn hallucinated button markup into a real action.

    Returns ``(clean_text, action_dict_or_None)``. The label inside the
    tag is kept as prose so the sentence still reads, and the xmlid is
    resolved through the same path open_action uses — an xmlid the user
    cannot reach resolves to nothing rather than to a broken button.
    """
    if not text:
        return text, None
    found = []

    def _swap(match):
        found.append(match.group(1).strip())
        return (match.group(2) or '').strip()

    cleaned = _ACTION_MARKUP.sub(_swap, text)
    cleaned = _DIR_MARKUP.sub('', cleaned)

    # A written-out tool call carries no label worth keeping — drop the
    # blob entirely, but honour the xmlid inside it first.
    for blob in _TOOL_JSON.findall(cleaned):
        found.extend(_XMLID.findall(blob))
    cleaned = _TOOL_JSON.sub('', cleaned)
    cleaned = '\n'.join(line.rstrip() for line in cleaned.split('\n')).strip()

    if not found:
        return cleaned, None
    action = None
    for xmlid in found:
        result = tool_dispatcher._builtin_open_action(env, xmlid=xmlid)
        if isinstance(result, dict) and result.get('action'):
            action = result['action']
            break
    return cleaned, action


_BOLD_TAG = re.compile(r'</?(?:b|strong)>', re.IGNORECASE)
_BR_TAG = re.compile(r'<br\s*/?>', re.IGNORECASE)
_ANY_TAG = re.compile(r'</?(?:div|p|span|section|article|ul|ol|li|h[1-6]|font|em|i|u)\b[^>]*>', re.IGNORECASE)


# Tools that describe the system rather than the business: their rows are
# plumbing (field names, menu ids, xmlids) and must never be shown as a table.
_META_TOOLS = frozenset({
    'explain_screen', 'find_menu', 'list_my_apps', 'date_reference', 'echo',
    'open_record', 'open_list', 'open_pivot', 'open_graph', 'open_action',
    'screen_button', 'record_action', 'list_commands', 'run_command', 'semantic_search',
})
_PLUMBING_KEYS = frozenset({'field', 'xmlid', 'action_xmlid', 'menu_id', 'model', 'type'})


def _auto_table(result, max_rows=25):
    """data_table block from a tool result holding a list of row dicts."""
    if isinstance(result, dict) and isinstance(result.get('rows'), list) \
            and isinstance(result.get('headers'), list) and result['rows'] \
            and isinstance(result['rows'][0], (list, tuple)):
        # {"headers": [...], "rows": [[...], ...]} (fact-table tools)
        return {'type': 'data_table', 'headers': [str(h) for h in result['headers']],
                'rows': [['' if c in (None, False) else (f'{c:,.2f}' if isinstance(c, float) else str(c))
                          for c in r] for r in result['rows'][:max_rows]]}
    rows = None
    if isinstance(result, list):
        rows = result
    elif isinstance(result, dict) and not result.get('error') and not result.get('render'):
        rows = next((v for v in result.values()
                     if isinstance(v, list) and v and isinstance(v[0], dict)), None)
    if not rows or not isinstance(rows[0], dict):
        return None
    if _PLUMBING_KEYS & set(rows[0]):
        return None
    headers = [k for k in rows[0] if k not in ('id', 'res_id', 'model') and not k.startswith('_')][:8]
    if not headers:
        return None

    def cell(v):
        if isinstance(v, float):
            return f'{v:,.2f}'
        if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], int):
            return str(v[1])                     # many2one pair
        return '' if v in (None, False) else str(v)
    return {'type': 'data_table',
            'headers': [h.replace('_', ' ').capitalize() for h in headers],
            'rows': [[cell(r.get(h)) for h in headers] for r in rows[:max_rows]]}
_HTML_TABLE = re.compile(r'(?:<div[^>]*>\s*)?<table\b.*?</table>(?:\s*</div>)?', re.IGNORECASE | re.DOTALL)
_MD_TABLE = re.compile(r'(?:^\s*\|.*\|\s*$\n?){3,}', re.MULTILINE)


def _absorb_prose_table(text):
    """(text without the table, data_table block | None)."""
    if not text or not isinstance(text, str):
        return text, None
    m = _HTML_TABLE.search(text)
    if m:
        try:
            from lxml import html as lhtml
            doc = lhtml.fromstring(m.group(0))
            rows = [[c.text_content().strip() for c in tr.xpath('./th|./td')]
                    for tr in doc.xpath('.//tr')]
            rows = [r for r in rows if r]
            if len(rows) >= 2:
                block = {'type': 'data_table', 'headers': rows[0], 'rows': rows[1:]}
                return (text[:m.start()] + text[m.end():]).strip(), block
        except Exception:
            pass
    m = _MD_TABLE.search(text)
    if m:
        lines = [ln.strip().strip('|') for ln in m.group(0).strip().splitlines()]
        cells = [[c.strip() for c in ln.split('|')] for ln in lines]
        cells = [r for r in cells if not all(re.fullmatch(r':?-{2,}:?', c or '-') for c in r)]
        if len(cells) >= 2:
            block = {'type': 'data_table', 'headers': cells[0], 'rows': cells[1:]}
            return (text[:m.start()] + text[m.end():]).strip(), block
    return text, None


def _strip_control_tokens(text):
    """Remove protocol tokens the model echoed into its visible answer."""
    if not text:
        return text
    for token in _CONTROL_TOKENS:
        text = text.replace(token, '')
    # Answers render as markdown, so HTML bold arrives as literal "<b>":
    # say it the markdown way; line breaks become newlines, and any other
    # tag (<div dir="rtl">, <p>, <span>) is dropped — it could only ever
    # be shown as text. Tables were lifted into blocks before this.
    text = _BOLD_TAG.sub('**', text)
    text = _BR_TAG.sub('\n', text)
    text = re.sub(r'<li\b[^>]*>', '\n- ', text, flags=re.IGNORECASE)
    text = _ANY_TAG.sub('', text)
    # Collapse the whitespace the removal leaves behind, without
    # touching intentional paragraph breaks inside the answer.
    return '\n'.join(line.rstrip() for line in text.split('\n')).strip()


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

def _agent_limit_envelope(limit, locale):
    if locale == 'ar':
        msg = (f'باقة الذكاء الاصطناعي الحالية تسمح بـ {limit} وكيل نشط فقط، وهذا الوكيل خارج الحد. '
               'استخدم مساعد غيمة أو قم بترقية الباقة.')
    else:
        msg = (f'Your AI plan allows {limit} active agent(s) and this agent is beyond the limit. '
               'Use the Ghaima Assistant or upgrade the AI plan.')
    return {
        'response': msg,
        'error': 'AGENT_LIMIT',
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': 'AI plan limit', 'body': msg,
                 'tone': 'bad', 'icon': 'fa-exclamation-triangle'},
            ],
        },
    }


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


def _provider_error_envelope(locale):
    if locale == 'ar':
        msg = ('تعذّر الوصول إلى مزوّد الذكاء الاصطناعي، فلم يتم إنشاء إجابة. '
               'حاول مرة أخرى لاحقًا أو تواصل مع المسؤول.')
    else:
        msg = ('The AI provider could not be reached, so no answer was '
               'generated. Please try again shortly or contact your '
               'administrator.')
    return {
        'response': msg,
        'error': 'PROVIDER_ERROR',
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': 'AI unavailable', 'body': msg,
                 'tone': 'bad', 'icon': 'fa-exclamation-triangle'},
            ],
        },
    }


def _maxhops_envelope(agent, locale, partial=''):
    """What to say when the agent ran out of steps.

    This used to surface as a red failure card reading "MAX_HOPS" over
    "the provider returned an error" — none of which is true or useful.
    Nothing failed: the assistant worked through its step budget and did
    not converge, which to the person asking is simply an answer that
    did not arrive. So: no error code, no step counts (a number the user
    cannot act on), warn tone rather than danger, and their own language
    — `locale` was accepted here and never used, so Arabic users read an
    English apology.

    `partial` is usually empty — reaching the cap means the model was
    still mid tool-chain, and tool actions carry no prose. It is honoured
    anyway so that if a future path does arrive here holding text, that
    text is shown rather than replaced by a generic apology.
    """
    arabic = str(locale or '').startswith('ar')
    if arabic:
        title = 'لم أصل إلى إجابة كاملة'
        ask = ('لم أتمكّن من الوصول إلى إجابة نهائية لهذا السؤال. '
               'جرّب تضييق السؤال أو اسأل عن جزء واحد منه.')
    else:
        title = "I couldn't finish this one"
        ask = ('I could not get to a complete answer for this question. '
               'Try narrowing it, or ask about one part at a time.')

    partial = (partial or '').strip()
    body = f'{partial}\n\n{ask}' if partial else ask
    return {
        'response': body,
        # Deliberately no 'error' key: the generic error renderer paints
        # a red "AI request failed" card off it, and this is not a
        # failure the user caused or can fix by retrying identically.
        # The run record still records state='maxhops' for the audit.
        'render': {
            'layout': 'chat',
            'blocks': [
                {'type': 'callout', 'title': title, 'body': body,
                 'tone': 'warn', 'icon': 'fa-lightbulb-o'},
            ],
        },
    }
