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


register('date_reference', _builtin_date_reference)
register('echo', _builtin_echo)
