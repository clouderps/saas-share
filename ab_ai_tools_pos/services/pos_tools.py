# -*- coding: utf-8 -*-
"""Read-only POS tools for the shared ab_ai_agent registry.

Every tool runs as the calling user: ORM only (record rules apply),
scoped to ``env.companies``, rows capped at MAX_ROWS. None of them opens
or closes a session or takes a payment.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, fields
from odoo.exceptions import UserError

from odoo.addons.ab_ai_agent.services import tool_dispatcher

MAX_ROWS = 500
OPEN_STATES = ('opening_control', 'opened', 'closing_control')

# code -> xmlid name (used by the pre_init_hook to adopt existing rows)
TOOL_XMLIDS = {
    'pos_session_status': 'tool_pos_session_status',
    'top_cashiers': 'tool_top_cashiers',
    'pos_shift_summary': 'tool_pos_shift_summary',
    'pos_payment_mix': 'tool_pos_payment_mix',
}


def _limit(value, default):
    try:
        value = int(value) if value not in (None, '') else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, MAX_ROWS))


def _parse_date(value, label):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise UserError(_("Invalid date for %(label)s: %(value)s (use YYYY-MM-DD).",
                          label=label, value=value))


def _utc_bounds(env, day_from, day_to):
    """[start, end) UTC naive datetimes for local calendar days."""
    tz = pytz.timezone(env.user.tz or env.context.get('tz') or 'UTC')
    start = tz.localize(datetime.combine(day_from, time.min)).astimezone(pytz.UTC)
    end = tz.localize(datetime.combine(day_to + timedelta(days=1), time.min)).astimezone(pytz.UTC)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def _company_domain(env, path='company_id'):
    return [(path, 'in', env.companies.ids)]


def _session_payments(env, sessions):
    """{session_id: total paid} in one grouped query."""
    if not sessions:
        return {}
    groups = env['pos.payment']._read_group(
        [('session_id', 'in', sessions.ids)], ['session_id'], ['amount:sum'])
    return {s.id: amount or 0.0 for s, amount in groups}


def pos_session_status(env, agent=None, limit=10, **_kw):
    lim = _limit(limit, 10)
    sessions = env['pos.session'].search(
        [('state', 'in', list(OPEN_STATES))] + _company_domain(env, 'config_id.company_id'),
        order='start_at desc', limit=lim)
    paid = _session_payments(env, sessions)
    rows = [[
        s.config_id.name or '',
        s.user_id.name or '',
        fields.Datetime.to_string(s.start_at) if s.start_at else '',
        s.state,
        round(paid.get(s.id, 0.0), 2),
    ] for s in sessions]
    return {
        'headers': ['POS', 'Cashier', 'Opened', 'State', 'Sales'],
        'rows': rows,
        'total_rows': len(rows),
    }


def top_cashiers(env, agent=None, limit=5, on_date=None, **_kw):
    lim = _limit(limit, 5)
    day = _parse_date(on_date, 'on_date') or fields.Date.context_today(env.user)
    start, end = _utc_bounds(env, day, day)
    groups = env['pos.order']._read_group(
        [('date_order', '>=', start), ('date_order', '<', end),
         ('state', 'in', ('paid', 'done', 'invoiced'))] + _company_domain(env),
        ['user_id'], ['amount_total:sum', 'session_id:count_distinct', '__count'])
    data = sorted(
        ((u, total or 0.0, n_sess, n) for u, total, n_sess, n in groups if u),
        key=lambda r: r[1], reverse=True)[:lim]
    return {
        'on_date': day.isoformat(),
        'headers': ['Cashier', 'Sales', 'Sessions', 'Orders'],
        'rows': [[u.name, round(total, 2), n_sess, n] for u, total, n_sess, n in data],
        'total_rows': len(data),
    }


def pos_shift_summary(env, agent=None, config_id=None, **_kw):
    """Current (else last) session per POS the user can see."""
    cfg_domain = _company_domain(env)
    if config_id:
        cfg_domain.append(('id', '=', int(config_id)))
    configs = env['pos.config'].search(cfg_domain, limit=MAX_ROWS)
    if not configs:
        return {'shifts': [], 'total_rows': 0}
    Session = env['pos.session']
    sessions = Session
    for cfg in configs:
        current = Session.search([('config_id', '=', cfg.id), ('state', 'in', list(OPEN_STATES))],
                                 order='start_at desc, id desc', limit=1)
        sessions |= current or Session.search([('config_id', '=', cfg.id)],
                                              order='id desc', limit=1)
    order_stats = {
        s.id: (n, total or 0.0) for s, n, total in env['pos.order']._read_group(
            [('session_id', 'in', sessions.ids), ('state', '!=', 'cancel')],
            ['session_id'], ['__count', 'amount_total:sum'])
    }
    mix = {}
    for s, method, amount, n in env['pos.payment']._read_group(
            [('session_id', 'in', sessions.ids)],
            ['session_id', 'payment_method_id'], ['amount:sum', '__count']):
        mix.setdefault(s.id, []).append({
            'method': method.name or '', 'amount': round(amount or 0.0, 2), 'count': n})
    shifts = []
    for s in sessions:
        n, total = order_stats.get(s.id, (0, 0.0))
        shifts.append({
            'pos': s.config_id.name or '',
            'session': s.name,
            'state': s.state,
            'is_current': s.state in OPEN_STATES,
            'cashier': s.user_id.name or '',
            'opened': fields.Datetime.to_string(s.start_at) if s.start_at else '',
            'closed': fields.Datetime.to_string(s.stop_at) if s.stop_at else '',
            'currency': s.currency_id.name or '',
            'orders': n,
            'total': round(total, 2),
            'payment_mix': sorted(mix.get(s.id, []), key=lambda r: -r['amount']),
        })
    return {'shifts': shifts, 'total_rows': len(shifts)}


def pos_payment_mix(env, agent=None, date_from=None, date_to=None, config_id=None, **_kw):
    today = fields.Date.context_today(env.user)
    d_to = _parse_date(date_to, 'date_to') or today
    d_from = _parse_date(date_from, 'date_from') or d_to
    if d_from > d_to:
        raise UserError(_("date_from must be on or before date_to."))
    start, end = _utc_bounds(env, d_from, d_to)
    domain = [('payment_date', '>=', start), ('payment_date', '<', end)] + _company_domain(env)
    if config_id:
        domain.append(('session_id.config_id', '=', int(config_id)))
    groups = env['pos.payment']._read_group(
        domain, ['payment_method_id'], ['amount:sum', '__count'],
        order='amount:sum desc', limit=MAX_ROWS)
    rows = [[m.name or '', round(amount or 0.0, 2), n] for m, amount, n in groups]
    return {
        'date_from': d_from.isoformat(),
        'date_to': d_to.isoformat(),
        'headers': ['Payment method', 'Amount', 'Payments'],
        'rows': rows,
        'total': round(sum(r[1] for r in rows), 2),
        'total_rows': len(rows),
    }


for _code, _fn in (('pos_session_status', pos_session_status),
                   ('top_cashiers', top_cashiers),
                   ('pos_shift_summary', pos_shift_summary),
                   ('pos_payment_mix', pos_payment_mix)):
    tool_dispatcher.register(_code, _fn)
