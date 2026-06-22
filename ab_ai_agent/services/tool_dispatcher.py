# -*- coding: utf-8 -*-
"""Phase H — tool dispatcher.

Maps a tool's `code` to its Python implementation. Vertical modules
register their callables here via `register()` on their __init__
hook. Built-in tools (text utilities, date helpers) live in this
module directly.

Dispatch is JSON-schema-validated, ACL-checked, and replay-safe for
write actions (idempotency_key + audit log lookup).
"""
from __future__ import annotations

import json
import logging
import time

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# Module-level registry. Domain modules call `register()` on install.
_REGISTRY: dict = {}


def register(code: str, fn):
    """Register a Python callable under a stable tool code.

    `fn` signature: `fn(env, agent, **arguments) -> dict | str | list`.
    Return value is JSON-serialised before being fed back to the LLM.

    Idempotent — re-registering the same code overwrites the previous
    entry. Useful for hot-reload during development.
    """
    _REGISTRY[code] = fn
    _logger.debug("Registered AI tool: %s", code)


def get(code: str):
    """Return the registered callable or None."""
    return _REGISTRY.get(code)


def all_tools():
    """Snapshot of the registry. Used by views to validate that every
    ai.agent.tool record has a corresponding implementation."""
    return dict(_REGISTRY)


def dispatch(env, tool_record, arguments, *, agent=None, agent_run=None):
    """Run a tool by record.

    Validates ACL, dispatches to the registered callable or the
    ir.actions.server target. Returns ``{'ok': bool, 'result': ...,
    'error': str, 'duration_ms': int}``. Never raises — every failure
    becomes part of the LLM context so the model can recover.
    """
    started = time.perf_counter()

    # ── ACL ────────────────────────────────────────────────────
    if not tool_record.is_invocable_by(env.user):
        return _error('forbidden', tool_record, time.perf_counter() - started,
                      f'You do not have permission to invoke {tool_record.code}.')

    # ── PII gate ───────────────────────────────────────────────
    if tool_record.requires_pii and (not agent or not agent.allow_pii):
        return _error('pii_blocked', tool_record, time.perf_counter() - started,
                      'This tool needs PII access; agent.allow_pii is False.')

    # ── Write-action gate ──────────────────────────────────────
    if tool_record.is_write_action and (not agent or not agent.allow_write_actions):
        return _error('write_blocked', tool_record, time.perf_counter() - started,
                      'Agent is not allowed to invoke write actions.')

    # ── Strip the __end_message helper from arguments ──────────
    arguments = dict(arguments or {})
    end_message = arguments.pop('__end_message', None)

    # ── Dispatch ───────────────────────────────────────────────
    try:
        if tool_record.dispatch_kind == 'server_action':
            result = _dispatch_server_action(env, tool_record, arguments, agent=agent)
        else:
            result = _dispatch_python(env, tool_record, arguments, agent=agent)
    except UserError as ue:
        return _error('user_error', tool_record, time.perf_counter() - started,
                      str(ue), end_message=end_message)
    except Exception as e:
        _logger.exception("Tool %s failed", tool_record.code)
        return _error('exception', tool_record, time.perf_counter() - started,
                      f'{type(e).__name__}: {e}', end_message=end_message)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        'ok': True,
        'tool': tool_record.code,
        'result': result,
        'duration_ms': duration_ms,
        'end_message': end_message,
    }


def _dispatch_python(env, tool, arguments, agent=None):
    fn = get(tool.code)
    if not fn:
        raise UserError(
            f'No Python implementation registered for tool "{tool.code}". '
            f'Vertical module not installed?'
        )
    return fn(env, agent=agent, **arguments)


def _dispatch_server_action(env, tool, arguments, agent=None):
    if not tool.server_action_id:
        raise UserError(f'Tool {tool.code} has no server_action_id.')
    action = tool.server_action_id.with_context(
        ai_tool_arguments=arguments,
        ai_tool_agent_id=agent.id if agent else False,
    )
    result = action.run()
    # ir.actions.server typically returns the next action dict or None.
    # We pass it through so the LLM can see what happened.
    return result


def _error(kind, tool, duration_s, message, end_message=None):
    return {
        'ok': False,
        'tool': tool.code if tool else '',
        'error': kind,
        'message': message,
        'duration_ms': int(duration_s * 1000),
        'end_message': end_message,
    }


# ─── Built-in tools — minimal, registered on import ──────────────

def _builtin_date_reference(env, agent=None, **kwargs):
    """Return a date-calculation cheat-sheet so the LLM doesn't do
    its own math. Mirrors Odoo 19 native's pattern (§3.8)."""
    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    month_end = next_month - timedelta(days=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    quarter = (today.month - 1) // 3 + 1
    q_start_month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    q_start = today.replace(month=q_start_month, day=1)
    return {
        'today': str(today),
        'yesterday': str(yesterday),
        'tomorrow': str(tomorrow),
        'this_week': f'{week_start} to {week_end}',
        'this_month': f'{month_start} to {month_end}',
        'last_month': f'{last_month_start} to {last_month_end}',
        'this_quarter_start': str(q_start),
        'this_year': f'{today.replace(month=1, day=1)} to {today.replace(month=12, day=31)}',
    }


def _builtin_echo(env, agent=None, **kwargs):
    """Sanity tool — returns its arguments. Used by golden-set tests."""
    return {'echo': kwargs}


# ─── Navigation tools ─────────────────────────────────────────────────
# Each returns an action descriptor in `action` — the runtime lifts that
# onto envelope.action and the chat surface paints an "Open" button.

def _builtin_open_record(env, agent=None, model=None, id=None,
                        view_type='form', **_kw):
    """Open a specific record in its default form view.

    Args:
      model: technical model name (e.g. 'sale.order', 'account.move')
      id:    record id
      view_type: 'form' (default) | 'kanban' | 'list'
    """
    if not model or not id:
        return {'error': 'model + id are required'}
    if model not in env:
        return {'error': f'unknown model: {model}'}
    try:
        rec = env[model].browse(int(id))
        if not rec.exists():
            return {'error': f'{model} id={id} not found'}
        rec.check_access('read')
        display = rec.display_name
    except Exception as e:
        return {'error': str(e)}
    return {
        'message': f'Opening {display}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': display,
            'res_model': model,
            'res_id': int(id),
            'view_mode': view_type,
            'views': [[False, view_type]],
            'target': 'current',
        },
    }


def _builtin_open_list(env, agent=None, model=None, domain=None,
                     group_by=None, name=None, **_kw):
    """Open a filtered list view of a model.

    Args:
      model:    technical model name
      domain:   Odoo domain (list of tuples) or empty for all records
      group_by: list of field names to group by
      name:     optional display label for the list
    """
    if not model:
        return {'error': 'model is required'}
    if model not in env:
        return {'error': f'unknown model: {model}'}
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {}
    if group_by:
        if isinstance(group_by, str):
            group_by = [group_by]
        ctx['group_by'] = group_by
    return {
        'message': f'Opening {name or model} list ({len(safe_domain)} filter(s))',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or env[model]._description or model,
            'res_model': model,
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_pivot(env, agent=None, model=None, measures=None,
                       row_groupbys=None, col_groupbys=None,
                       domain=None, name=None, **_kw):
    """Open a pivot analytics view."""
    if not model or model not in env:
        return {'error': f'unknown model: {model}'}
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {
        'pivot_measures': measures or [],
        'pivot_row_groupby': row_groupbys or [],
        'pivot_column_groupby': col_groupbys or [],
    }
    return {
        'message': f'Opening pivot of {model}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or f'{env[model]._description or model} — Pivot',
            'res_model': model,
            'view_mode': 'pivot,list',
            'views': [[False, 'pivot'], [False, 'list']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_graph(env, agent=None, model=None, measure=None,
                       mode='bar', group_by=None, domain=None,
                       name=None, **_kw):
    """Open a graph view (bar / line / pie)."""
    if not model or model not in env:
        return {'error': f'unknown model: {model}'}
    if mode not in ('bar', 'line', 'pie'):
        mode = 'bar'
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {'graph_mode': mode}
    if measure:
        ctx['graph_measure'] = measure
    if group_by:
        if isinstance(group_by, str):
            group_by = [group_by]
        ctx['graph_groupbys'] = group_by
    return {
        'message': f'Opening {mode} chart of {model}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or f'{env[model]._description or model} — {mode.title()}',
            'res_model': model,
            'view_mode': 'graph,list',
            'views': [[False, 'graph'], [False, 'list']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_action(env, agent=None, xmlid=None, **_kw):
    """Open a server-registered action by xmlid.

    Useful for built-in reports: 'account.action_account_pl_report',
    'account.action_account_balance_report', 'sale.action_orders', etc.
    """
    if not xmlid:
        return {'error': 'xmlid required'}
    try:
        action = env.ref(xmlid, raise_if_not_found=False)
        if not action:
            return {'error': f'action {xmlid} not found'}
        if not hasattr(action, 'read'):
            return {'error': f'{xmlid} is not an action'}
        action_dict = action.sudo().read()[0]
        # Strip sentinel keys that aren't part of the act_window contract.
        for k in ('create_uid', 'write_uid', 'create_date', 'write_date'):
            action_dict.pop(k, None)
        return {
            'message': f'Opening {action.name}',
            'action': action_dict,
        }
    except Exception as e:
        return {'error': str(e)}


# ─── HR domain tools ─────────────────────────────────────────────────
# Defensive: skipped when hr / hr.attendance modules aren't installed.

def _builtin_hr_attendance_missing_today(env, agent=None, limit=50, **_kw):
    """Employees with no check-in for today. The "morning roll call"."""
    Emp = env.get('hr.employee')
    Att = env.get('hr.attendance')
    if Emp is None or Att is None:
        return {'error': 'hr.attendance not installed on this instance'}
    from odoo import fields as _fields
    today = _fields.Date.context_today(env['res.users'])
    today_start = f'{today} 00:00:00'
    try:
        with env.cr.savepoint(flush=False):
            attended_ids = Att.sudo().search([
                ('check_in', '>=', today_start),
            ]).mapped('employee_id').ids
            missing = Emp.sudo().search([
                ('active', '=', True),
                ('id', 'not in', attended_ids),
            ], limit=int(limit))
    except Exception as e:
        return {'error': str(e)}
    rows = [{
        'id': e.id,
        'name': e.name,
        'department': e.department_id.name if e.department_id else '',
        'job': e.job_title or '',
    } for e in missing]
    return {
        'count': len(rows),
        'date': str(today),
        'employees': rows,
    }


def _builtin_hr_leave_pending(env, agent=None, limit=50, **_kw):
    """Leave requests awaiting approval."""
    Leave = env.get('hr.leave')
    if Leave is None:
        return {'error': 'hr.leave not installed'}
    try:
        with env.cr.savepoint(flush=False):
            rows = Leave.sudo().search([('state', '=', 'confirm')],
                                       limit=int(limit), order='date_from')
    except Exception as e:
        return {'error': str(e)}
    return {
        'count': len(rows),
        'leaves': [{
            'id': l.id,
            'employee': l.employee_id.name if l.employee_id else '',
            'type': l.holiday_status_id.name if l.holiday_status_id else '',
            'date_from': str(l.date_from) if l.date_from else '',
            'date_to': str(l.date_to) if l.date_to else '',
            'days': l.number_of_days,
        } for l in rows],
    }


def _builtin_hr_attendance_open_shifts(env, agent=None, **_kw):
    """Currently clocked-in employees who haven't clocked out yet."""
    Att = env.get('hr.attendance')
    if Att is None:
        return {'error': 'hr.attendance not installed'}
    try:
        with env.cr.savepoint(flush=False):
            rows = Att.sudo().search([('check_out', '=', False)],
                                     order='check_in desc', limit=100)
    except Exception as e:
        return {'error': str(e)}
    return {
        'count': len(rows),
        'open_attendances': [{
            'id': a.id,
            'employee': a.employee_id.name if a.employee_id else '',
            'check_in': str(a.check_in) if a.check_in else '',
            'department': a.employee_id.department_id.name if a.employee_id and a.employee_id.department_id else '',
        } for a in rows],
    }


# ─── Analysis tools ──────────────────────────────────────────────────
# Numbers come straight from the ORM/SQL — NEVER from the model. The
# tool returns a `render` envelope (chart + KPI grid + peak callout);
# runtime.py lifts that onto envelope.render verbatim (same path as
# `action`). The LLM only writes the surrounding narrative paragraph.

_DA_METRICS = {
    # key: (table, amount_col, date_col, state_sql, label)
    'pos_sales': ("pos_order", "amount_total", "date_order",
                  "state IN ('paid','done','invoiced')", "POS sales"),
    'sale_orders': ("sale_order", "amount_total", "date_order",
                    "state IN ('sale','done')", "Sales orders"),
    'invoiced_revenue': ("account_move", "amount_total_signed", "invoice_date",
                         "move_type = 'out_invoice' AND state = 'posted'",
                         "Invoiced revenue"),
}
_DA_GROUPS = {'day', 'week', 'month'}


def _builtin_data_analysis(env, agent=None, metric='pos_sales',
                           period_days=30, group='day', **_kw):
    """Deterministic timeseries analysis → render envelope.

    Args:
      metric:      pos_sales | sale_orders | invoiced_revenue
      period_days: lookback window (1–365, default 30)
      group:       day | week | month (bucket granularity)
    """
    from datetime import timedelta
    from odoo import fields as _fields

    spec = _DA_METRICS.get(metric)
    if not spec:
        return {'error': f'unknown metric {metric!r}; '
                         f'choose one of {sorted(_DA_METRICS)}'}
    table, amt_col, date_col, state_sql, label = spec
    group = group if group in _DA_GROUPS else 'day'
    try:
        period_days = max(1, min(365, int(period_days)))
    except (TypeError, ValueError):
        period_days = 30

    today = _fields.Date.context_today(env['res.users'])
    start = today - timedelta(days=period_days)
    prev_start = start - timedelta(days=period_days)
    unit = (env.company.currency_id.symbol or 'SAR')

    # Guard: table may not exist on every tenant (no POS, no accounting).
    env.cr.execute("SELECT to_regclass(%s)", (f'public.{table}',))
    if not (env.cr.fetchone() or [None])[0]:
        return {'error': f'{metric}: table {table} not present on this instance'}

    q = (
        f"SELECT date_trunc(%s, {date_col})::date d, "
        f"       COALESCE(SUM({amt_col}), 0) amt, COUNT(*) n "
        f"  FROM {table} "
        f" WHERE {state_sql} AND {date_col} >= %s AND {date_col} < %s "
        f" GROUP BY 1 ORDER BY 1"
    )
    try:
        with env.cr.savepoint(flush=False):
            env.cr.execute(q, (group, start, today))
            rows = env.cr.fetchall()
            env.cr.execute(
                f"SELECT COALESCE(SUM({amt_col}), 0) FROM {table} "
                f"WHERE {state_sql} AND {date_col} >= %s AND {date_col} < %s",
                (prev_start, start),
            )
            prev_total = float((env.cr.fetchone() or [0])[0] or 0)
    except Exception as e:  # never raise into the hop loop
        return {'error': f'{metric} query failed: {type(e).__name__}: {e}'}

    if not rows:
        return {
            'render': {
                'layout': 'report',
                'title': f'{label} — last {period_days} days',
                'blocks': [{
                    'type': 'callout', 'tone': 'warn',
                    'title': 'No data',
                    'body': f'No {label.lower()} between {start} and {today}.',
                }],
            },
            'summary': f'No {label.lower()} in the last {period_days} days.',
        }

    x = [r[0].isoformat() for r in rows]
    amounts = [round(float(r[1]), 2) for r in rows]
    counts = [int(r[2]) for r in rows]
    total = round(sum(amounts), 2)
    txn = sum(counts)
    avg = round(total / len(x), 2)
    peak = max(rows, key=lambda r: r[1])
    delta = (((total - prev_total) / prev_total * 100.0)
             if prev_total else None)
    tone = 'good' if (delta is None or delta >= 0) else 'bad'
    delta_txt = (f'{delta:+.1f}%' if delta is not None else '—')
    insight = (
        f'{"Up" if (delta or 0) >= 0 else "Down"} {abs(delta):.1f}% vs the '
        f'previous {period_days} days.' if delta is not None
        else 'No comparable prior period.'
    )

    kpis = [
        {'label': 'Total', 'value': f'{total:,.0f} {unit}',
         'delta_pct': delta_txt, 'tone': tone},
        {'label': 'Transactions', 'value': f'{txn:,}'},
        {'label': f'Avg / {group}', 'value': f'{avg:,.0f} {unit}'},
    ]
    return {
        'render': {
            'layout': 'report',
            'title': f'{label} — last {period_days} days',
            'blocks': [
                {'type': 'kpi_grid', 'items': kpis},
                {'type': 'chart', 'chart': 'area',
                 'title': f'{label} by {group}', 'x': x,
                 'series': [
                     {'name': f'{label} ({unit})', 'data': amounts},
                     {'name': 'Transactions', 'data': counts, 'axis': 'right'},
                 ],
                 'unit': unit, 'tone': tone, 'insight': insight},
                {'type': 'callout', 'tone': 'info', 'title': 'Peak',
                 'body': f'{peak[0]}: {float(peak[1]):,.0f} {unit} '
                         f'across {int(peak[2])} transactions.'},
            ],
        },
        # Compact factual line the LLM bases its narrative on. The model
        # is told NOT to restate the table — just interpret this.
        'summary': (
            f'{label}: {total:,.0f} {unit} over {len(x)} {group}-buckets '
            f'({txn} transactions), {delta_txt} vs prior {period_days}d, '
            f'peak {peak[0]} at {float(peak[1]):,.0f} {unit}.'
        ),
    }


# key -> (model, date_field, [(label, fname), ...], extra_domain, title)
_RECENT_KINDS = {
    'invoices': ('account.move', 'invoice_date',
                 [('Number', 'name'), ('Customer', 'partner_id'),
                  ('Date', 'invoice_date'), ('Total', 'amount_total'),
                  ('Status', 'state')],
                 [('move_type', '=', 'out_invoice')], 'Latest customer invoices'),
    'bills': ('account.move', 'invoice_date',
              [('Number', 'name'), ('Vendor', 'partner_id'),
               ('Date', 'invoice_date'), ('Total', 'amount_total'),
               ('Status', 'state')],
              [('move_type', '=', 'in_invoice')], 'Latest vendor bills'),
    'sale_orders': ('sale.order', 'date_order',
                    [('Order', 'name'), ('Customer', 'partner_id'),
                     ('Date', 'date_order'), ('Total', 'amount_total'),
                     ('Status', 'state')], [], 'Latest sales orders'),
    'pos_orders': ('pos.order', 'date_order',
                   [('Receipt', 'name'), ('Customer', 'partner_id'),
                    ('Date', 'date_order'), ('Total', 'amount_total'),
                    ('Status', 'state')], [], 'Latest POS orders'),
    'purchase_orders': ('purchase.order', 'date_order',
                        [('Order', 'name'), ('Vendor', 'partner_id'),
                         ('Date', 'date_order'), ('Total', 'amount_total'),
                         ('Status', 'state')], [], 'Latest purchase orders'),
    'customers': ('res.partner', 'create_date',
                  [('Name', 'name'), ('Email', 'email'),
                   ('Phone', 'phone'), ('City', 'city')],
                  [('customer_rank', '>', 0)], 'Most recently added customers'),
}


def _builtin_recent_records(env, agent=None, kind=None, model=None,
                            limit=10, **_kw):
    """The N most recently ADDED records of a business object.

    Answers "latest invoice added", "last 5 sale orders", "newest
    customers" — questions the model otherwise recycles stale context
    for. Numbers/IDs come straight from the ORM under the caller's
    access rights (record rules / branch isolation respected).

    Args:
      kind:  invoices | bills | sale_orders | pos_orders |
             purchase_orders | customers
      model: technical model name (advanced; overrides kind, ordered
             by create_date desc)
      limit: 1-50 (default 10)
    """
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit = 10

    if kind and kind in _RECENT_KINDS:
        mname, date_field, cols, domain, title = _RECENT_KINDS[kind]
    elif model:
        mname, date_field, cols, domain, title = (
            model, 'create_date',
            [('Name', 'display_name'), ('Created', 'create_date')],
            [], f'Latest {model} records')
    else:
        return {'error': 'kind required, one of %s (or a model=)'
                         % sorted(_RECENT_KINDS)}

    if mname not in env:
        return {'error': f'{mname} not installed on this instance'}
    Model = env[mname]
    try:
        Model.check_access('read')
    except Exception as e:
        return {'error': f'no read access to {mname}: {e}'}
    if date_field not in Model._fields:
        date_field = 'create_date'

    try:
        recs = Model.search(domain or [], order=f'{date_field} desc, id desc',
                            limit=limit)
    except Exception as e:
        return {'error': f'{mname} query failed: {type(e).__name__}: {e}'}
    if not recs:
        return {'render': {'layout': 'report', 'title': title,
                           'blocks': [{'type': 'callout', 'tone': 'warn',
                                       'title': 'Nothing found',
                                       'body': f'No {kind or mname} records.'}]},
                'summary': f'No {kind or mname} records found.'}

    def _cell(rec, fname):
        if fname not in rec._fields:
            return ''
        val = rec[fname]
        f = rec._fields[fname]
        if f.type == 'many2one':
            return val.display_name or '' if val else ''
        if f.type in ('date', 'datetime'):
            return str(val) if val else ''
        if f.type in ('float', 'monetary'):
            return f'{val:,.2f}'
        return '' if val in (False, None) else str(val)

    headers = [c[0] for c in cols]
    rows = [[_cell(r, c[1]) for c in cols] for r in recs]
    newest = recs[0]
    nd = newest[date_field] if date_field in newest._fields else None
    return {
        'render': {
            'layout': 'report', 'title': title,
            'blocks': [{
                'type': 'data_table',
                'title': f'{len(recs)} most recent (newest first)',
                'headers': headers, 'rows': rows,
            }],
        },
        'summary': (
            f'{len(recs)} most recent {kind or mname}; newest: '
            f'{newest.display_name} ({nd}).'
        ),
    }


# ─── Write action: confirm / validate / post a record by its number ──
# "INV/2026/00001 please post", "SO00047 confirm", "WH/IN/00012
# validate", "PBNK1/2026/0003 post". Domain-agnostic: resolves the
# reference across the standard business docs and runs the one
# canonical finalize method per model. WRITE action — the dispatcher
# blocks it unless agent.allow_write_actions is True.

# (model, [number-ish fields], finalize method, already-done predicate)
_RECORD_ACTION_SPECS = (
    ('sale.order',     ('name', 'client_order_ref'),
     'action_confirm', lambda r: r.state in ('sale', 'done')),
    ('purchase.order', ('name', 'partner_ref'),
     'button_confirm', lambda r: r.state in ('purchase', 'done')),
    ('account.move',   ('name', 'ref', 'payment_reference'),
     'action_post',    lambda r: r.state == 'posted'),
    ('stock.picking',  ('name', 'origin'),
     'button_validate', lambda r: r.state == 'done'),
    ('account.payment', ('name',),
     'action_post',    lambda r: r.state == 'posted'),
)


def _builtin_record_action(env, agent=None, reference=None, action=None, **_kw):
    """Find a record by its number and finalize it (confirm SO/PO,
    post invoice/bill/payment, validate picking). Returns an `action`
    so the chat shows an Open chip."""
    ref = (reference or '').strip()
    if not ref:
        return {'error': 'reference required, e.g. "INV/2026/00001" or "SO00047"'}
    for model, fnames, method, is_done in _RECORD_ACTION_SPECS:
        if model not in env:
            continue
        # Exact (case-insensitive) match only. A substring `ilike` could
        # finalize the WRONG record — "INV/2026/0004" must never resolve to
        # "INV/2026/00045" and post it.
        dom = ['|'] * (len(fnames) - 1) + [(f, '=ilike', ref) for f in fnames]
        try:
            rec = env[model].search(dom, limit=1)
        except Exception:
            rec = None
        if not rec:
            continue
        label = rec.display_name
        descriptor = {
            'type': 'ir.actions.act_window', 'name': label,
            'res_model': model, 'res_id': rec.id,
            'view_mode': 'form', 'views': [[False, 'form']],
            'target': 'current',
        }
        if is_done(rec):
            return {'message': f'{label} is already finalized — nothing to do.',
                    'already_done': True, 'action': descriptor}
        # Enforce write access AS THE REQUESTING USER (env is not sudo here)
        # so the agent can never finalize a record the user couldn't post
        # through the UI. Mirrors native Odoo 19 AI, which runs tool bodies
        # su=False precisely so record rules / ACLs still apply.
        try:
            rec.check_access('write')
        except Exception as e:
            return {'error': f'{label}: not permitted ({type(e).__name__}).',
                    'action': descriptor}
        try:
            getattr(rec, method)()
        except Exception as e:
            return {'error': f'{label}: {type(e).__name__}: {e}',
                    'action': descriptor}
        verb = {'action_confirm': 'confirmed', 'button_confirm': 'confirmed',
                'action_post': 'posted', 'button_validate': 'validated'}[method]
        return {'message': f'{label} {verb}.', 'done': True,
                'action': descriptor}
    return {'error': f'No sale order, purchase order, invoice/bill, '
                     f'picking or payment matches "{ref}".'}


# ─── T.2a — semantic search (pgvector keystone) ──────────────────────
# One generic tool replaces three always-on context blocks once the
# corresponding flags are flipped: ``_org_knowledge_block`` (today's
# ai.chat.fact retrieval), ``_record_context_block`` (record dump),
# and ``_business_snapshot_block`` (when each metric model gets an
# embedding column). Calls ``ai.semantic.index.search`` and returns
# pipe-CSV the LLM can parse cheaply.

def _builtin_semantic_search(env, agent=None, model=None, query=None,
                             limit=5, extra_domain=None,
                             vector_col='ai_embedding',
                             name_field='display_name',
                             hint_fields=None,
                             min_similarity=0.35, **_kw):
    """Find records semantically similar to a natural-language query.

    Args:
      model:           Odoo model name, e.g. 'crm.lead', 'res.partner',
                       'ai.chat.fact'. Must have an embedding column
                       (provisioned via ``ai.semantic.index.provision``).
      query:           the natural-language question / search text.
      limit:           how many hits (1-20, default 5).
      extra_domain:    optional Odoo domain ANDed with the result.
      vector_col:      embedding column name (default 'ai_embedding';
                       legacy 'embedding' for ai.chat.fact).
      name_field:      display field, default 'display_name'.
      hint_fields:     extra fields the LLM may want — list of names.
                       Returned as part of each row's hints dict.
      min_similarity:  cosine floor (0..1, default 0.35).

    Returns:
      ``{'rows': [...], 'csv': '...'}`` — the LLM should prefer 'csv'.
    """
    if not model or not query:
        return {'error': 'model + query are required'}
    Index = env.get('ai.semantic.index')
    if Index is None:
        return {'error': 'ai.semantic.index service not installed'}
    try:
        rows = Index.sudo().search(
            model, query,
            limit=int(limit), extra_domain=extra_domain,
            vector_col=vector_col, name_field=name_field,
            hint_fields=hint_fields or [],
            min_similarity=float(min_similarity),
        )
    except Exception as e:
        return {'error': f'semantic_search failed: {type(e).__name__}: {e}'}
    csv = Index.sudo().to_csv(rows, hint_keys=hint_fields or None)
    return {'rows': rows, 'csv': csv, 'count': len(rows), 'model': model}


register('semantic_search', _builtin_semantic_search)

register('date_reference', _builtin_date_reference)
register('echo', _builtin_echo)
register('record_action', _builtin_record_action)
register('data_analysis', _builtin_data_analysis)
register('recent_records', _builtin_recent_records)
register('open_record', _builtin_open_record)
register('open_list', _builtin_open_list)
register('open_pivot', _builtin_open_pivot)
register('open_graph', _builtin_open_graph)
register('open_action', _builtin_open_action)
register('hr_attendance_missing_today', _builtin_hr_attendance_missing_today)
register('hr_leave_pending', _builtin_hr_leave_pending)
register('hr_attendance_open_shifts', _builtin_hr_attendance_open_shifts)
