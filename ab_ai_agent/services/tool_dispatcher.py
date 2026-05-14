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


register('date_reference', _builtin_date_reference)
register('echo', _builtin_echo)
register('open_record', _builtin_open_record)
register('open_list', _builtin_open_list)
register('open_pivot', _builtin_open_pivot)
register('open_graph', _builtin_open_graph)
register('open_action', _builtin_open_action)
register('hr_attendance_missing_today', _builtin_hr_attendance_missing_today)
register('hr_leave_pending', _builtin_hr_leave_pending)
register('hr_attendance_open_shifts', _builtin_hr_attendance_open_shifts)
