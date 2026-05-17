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
    # Retrieve org knowledge ONCE here so it's both injected and
    # captured on the audit row (monitor) without a double RAG hit.
    kb_block = _org_knowledge_block(env, user_question)
    system_prompt = _compose_system_prompt(env, agent, locale=locale, skill=skill,
                                           record_ref=record_ref,
                                           user_question=user_question,
                                           org_knowledge=kb_block)
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

    # Tool-produced render wins when the LLM didn't emit one itself.
    # Analysis/report tools (data_analysis, …) return
    # {'render': {...}, 'summary': '...'} — the numbers come straight
    # from the ORM, never the model, so we lift `render` off the most
    # recent successful tool result (same pattern as `action` below)
    # and keep the LLM's prose as the narrative.
    if not extracted_render:
        for call in reversed(tool_calls_audit):
            if not call.get('ok'):
                continue
            res = call.get('result') or {}
            if isinstance(res, dict) and isinstance(res.get('render'), dict):
                extracted_render = res['render']
                if not extracted_text:
                    extracted_text = (res.get('summary')
                                      or extracted_render.get('title') or '')
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
    if _tool_ok or kb_block:
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

def _compose_system_prompt(env, agent, *, locale='en', skill=None,
                           record_ref=None, user_question=None,
                           org_knowledge=None):
    """Compose the system prompt = persona + topics + date reference
    + live business snapshot + org knowledge (RAG) + user context
    + record context.

    The aim is comprehensive data knowledge BEFORE the LLM picks a
    tool: counts of every key entity (orders, invoices, POS sessions,
    customers, employees) injected up front so the model can answer
    overview questions without round-trips, and can spot what tool
    to call for deeper figures."""
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

    # Live business snapshot — comprehensive counts + open items so
    # the agent can answer overview questions without a tool round-trip.
    snapshot = _business_snapshot_block(env)
    if snapshot:
        parts.append(snapshot)

    # Organisation knowledge (RAG) — semantic retrieval against the
    # tenant knowledge base, scoped to the user's question. Restores
    # the grounding the legacy chatbot path injected before the
    # chatbot + Ask AI were unified onto this runtime.
    kb = (org_knowledge if org_knowledge is not None
          else _org_knowledge_block(env, user_question))
    if kb:
        parts.append(kb)

    # Caller context — who is asking, from where.
    parts.append(_user_context_block(env))

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

    # Tool protocol.
    if agent.all_tool_ids:
        parts.append(_tool_protocol_block(agent.all_tool_ids))

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
    # Quick reject — must look like an object.
    if not (raw.startswith('{') and raw.endswith('}')):
        return None
    import json as _json
    try:
        obj = _json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    if 'render' not in obj:
        return None
    render = obj.get('render')
    if not isinstance(render, dict):
        return None
    return {
        'render': render,
        'response': obj.get('response') or obj.get('summary') or '',
    }


def _business_snapshot_block(env):
    """Pre-fetch comprehensive counts + open-item summaries so the
    LLM has business-wide context before its first tool call.

    Each probe is wrapped in a savepoint — missing models/tables
    on this tenant just produce a "—" placeholder, never crash.

    Output is markdown CSV-style for token efficiency (§3.7 pattern)."""
    snippets = []

    def _safe_count(model, domain=None):
        try:
            with env.cr.savepoint(flush=False):
                if model not in env:
                    return None
                return env[model].sudo().search_count(domain or [])
        except Exception:
            return None

    def _safe_sum(model, field, domain=None):
        try:
            with env.cr.savepoint(flush=False):
                if model not in env:
                    return None
                groups = env[model].sudo().read_group(
                    domain or [], [field], [],
                )
                return groups[0].get(field) if groups else None
        except Exception:
            return None

    today_iso = env.cr.mogrify("%s", (env['ir.fields.converter']._cached_today() if False else None,)) if False else ''
    from odoo import fields as _odoo_fields
    today = _odoo_fields.Date.context_today(env['res.users'])
    month_start = today.replace(day=1)

    # ── Sales ───────────────────────────────────────────────────
    rows = []
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
        rows.append(f'- Sale orders confirmed today: {_fmt_count(n_so_today)} (total: {_fmt_money(amt_so_today)})')
        rows.append(f'- Sale orders confirmed this month: {_fmt_count(n_so_month)} (total: {_fmt_money(amt_so_month)})')
        rows.append(f'- Sale orders still in draft: {_fmt_count(n_so_draft)}')

    # ── POS ─────────────────────────────────────────────────────
    n_pos_today = _safe_count('pos.order', [('date_order', '>=', str(today))])
    amt_pos_today = _safe_sum('pos.order', 'amount_total', [('date_order', '>=', str(today))])
    n_pos_sessions = _safe_count('pos.session', [('state', '=', 'opened')])
    if any(v is not None for v in (n_pos_today, n_pos_sessions)):
        rows.append(f'- POS orders today: {_fmt_count(n_pos_today)} (total: {_fmt_money(amt_pos_today)})')
        rows.append(f'- POS sessions currently open: {_fmt_count(n_pos_sessions)}')

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
        rows.append(f'- Customer invoices in draft: {_fmt_count(n_inv_draft)}')
        rows.append(f'- Customer invoices overdue: {_fmt_count(n_inv_overdue)} (open balance: {_fmt_money(amt_inv_overdue)})')

    # ── Inventory ──────────────────────────────────────────────
    n_picking_todo = _safe_count('stock.picking', [
        ('state', 'in', ('assigned', 'confirmed')),
    ])
    if n_picking_todo is not None:
        rows.append(f'- Stock pickings pending: {_fmt_count(n_picking_todo)}')

    # ── HR ──────────────────────────────────────────────────────
    n_emp = _safe_count('hr.employee', [('active', '=', True)])
    n_leave_pending = _safe_count('hr.leave', [('state', '=', 'confirm')])
    if n_emp is not None:
        rows.append(f'- Active employees: {_fmt_count(n_emp)}'
                    + (f' · pending leave requests: {_fmt_count(n_leave_pending)}' if n_leave_pending is not None else ''))

    # ── CRM ────────────────────────────────────────────────────
    n_lead_open = _safe_count('crm.lead', [('active', '=', True), ('type', '=', 'opportunity')])
    if n_lead_open is not None:
        rows.append(f'- Open CRM opportunities: {_fmt_count(n_lead_open)}')

    # ── Customers ─────────────────────────────────────────────
    n_partner = _safe_count('res.partner', [('customer_rank', '>', 0)])
    if n_partner is not None:
        rows.append(f'- Customers on file: {_fmt_count(n_partner)}')

    if not rows:
        return ''
    return (
        '## Live business snapshot\n'
        + '\n'.join(rows)
        + '\n\nUse these counts to ground overview answers. For exact '
          'amounts or breakdowns by period/branch/product, call the '
          'matching tool (`sales_totals`, `pl_summary`, `top_customers`, …).'
    )


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
