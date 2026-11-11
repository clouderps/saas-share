# -*- coding: utf-8 -*-
"""Accounting tools — P&L, cash, VAT, receivables.

Each callable runs as the calling user through ``_read_group``: model ACLs,
record rules and the allowed companies (``env.companies``) all apply. No
raw SQL. Amounts are company-currency balances; rows are capped at 500.
"""
from __future__ import annotations

from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError

from odoo.addons.ab_ai_agent.services import tool_dispatcher

ACL_GROUP = 'account.group_account_invoice'
MAX_ROWS = 500
OPEN_STATES = ('not_paid', 'partial', 'in_payment')
BUCKETS = ('not_due', '0-30', '31-60', '61-90', '90+')


# ── helpers ────────────────────────────────────────────────────────

def resolve_period(label, today=None):
    """Relative period label → (date_from, date_to), inclusive; (None, None)
    for an unknown label. Same labels as the chatbot intent router."""
    today = today or date.today()
    if label == 'today':
        return today, today
    if label == 'yesterday':
        d = today - timedelta(days=1)
        return d, d
    if label == 'this_week':
        return today - timedelta(days=today.weekday()), today
    if label == 'last_week':
        end = today - timedelta(days=today.weekday() + 1)
        return end - timedelta(days=6), end
    if label == 'this_month':
        return today.replace(day=1), today
    if label == 'last_month':
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if label == 'this_quarter':
        q = (today.month - 1) // 3
        return today.replace(month=q * 3 + 1, day=1), today
    if label == 'ytd':
        return today.replace(month=1, day=1), today
    if label == 'last_year':
        return (today.replace(year=today.year - 1, month=1, day=1),
                today.replace(year=today.year - 1, month=12, day=31))
    return None, None


def _check(env):
    if not env.user.has_group(ACL_GROUP):
        raise AccessError(env._("permission_denied: this tool needs the group %s", ACL_GROUP))


def _cap(limit, default):
    try:
        n = int(limit) if limit is not None else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_ROWS))


def _currency(env):
    return env.company.currency_id.name or ''


def _today(env):
    return fields.Date.context_today(env['account.move'])


def _date_domain(period, field='date'):
    d_from, d_to = resolve_period(period) if period else (None, None)
    dom = []
    if d_from:
        dom.append((field, '>=', d_from))
    if d_to:
        dom.append((field, '<=', d_to))
    return dom


def _aml_base(env):
    return [('parent_state', '=', 'posted'), ('company_id', 'in', env.companies.ids)]


def _open_invoices(env):
    return [('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('payment_state', 'in', OPEN_STATES),
            ('company_id', 'in', env.companies.ids)]


def _table(env, headers, rows, **extra):
    rows = rows[:MAX_ROWS]
    return {'currency': _currency(env), 'headers': headers, 'rows': rows,
            'total_rows': len(rows), **extra}


def _cashflow_domain(env, period):
    return (_aml_base(env)
            + [('journal_id.type', 'in', ('cash', 'bank')),
               ('account_id.account_type', '=', 'asset_cash')]
            + _date_domain(period))


def _cashflow(env, period, groupby, limit):
    """inflow / outflow / net / line count per ``groupby`` key."""
    Aml = env['account.move.line']
    base = _cashflow_domain(env, period)
    acc = {}
    for sign, extra in (('in', [('balance', '>', 0)]), ('out', [('balance', '<', 0)])):
        for key, bal, cnt in Aml._read_group(base + extra, [groupby],
                                             ['balance:sum', '__count']):
            row = acc.setdefault(key, {'in': 0.0, 'out': 0.0, 'n': 0})
            row[sign] += bal or 0.0
            row['n'] += cnt
    return acc


# ── tools ──────────────────────────────────────────────────────────

def ar_aging(env, agent=None, **_kw):
    _check(env)
    today = _today(env)
    groups = env['account.move']._read_group(
        _open_invoices(env), ['invoice_date_due:day'],
        ['amount_residual_signed:sum', '__count'])
    acc = {b: [0.0, 0, 0] for b in BUCKETS}  # outstanding, count, overdue-days*count
    for due, amount, count in groups:
        days = (today - due).days if due else 0
        bucket = ('not_due' if days <= 0 else '0-30' if days <= 30 else
                  '31-60' if days <= 60 else '61-90' if days <= 90 else '90+')
        acc[bucket][0] += amount or 0.0
        acc[bucket][1] += count
        acc[bucket][2] += max(days, 0) * count
    rows = [[b, round(v[0], 2), v[1], round(v[2] / v[1], 1) if v[1] else 0.0]
            for b, v in acc.items() if v[1]]
    return _table(env, ['Aging bucket', 'Outstanding', 'Invoices', 'Avg days overdue'],
                  rows, total=round(sum(v[0] for v in acc.values()), 2))


def top_overdue_partners(env, agent=None, limit=10, **_kw):
    _check(env)
    groups = env['account.move']._read_group(
        _open_invoices(env) + [('partner_id', '!=', False)], ['partner_id'],
        ['amount_residual_signed:sum', '__count', 'invoice_date_due:min'],
        order='amount_residual_signed:sum desc', limit=_cap(limit, 10))
    today = _today(env)
    rows = [[p.display_name, round(amount or 0.0, 2), count,
             max((today - oldest).days, 0) if oldest else 0]
            for p, amount, count, oldest in groups]
    return _table(env, ['Customer', 'Outstanding', 'Invoices', 'Oldest days overdue'], rows)


def _pl(env, domain, groupby):
    Aml = env['account.move.line']
    out = {}
    for kind, op in (('revenue', 'income'), ('expenses', 'expense')):
        dom = domain + [('account_id.account_type', '=like', f'{op}%')]
        for *key, bal in Aml._read_group(dom, groupby, ['balance:sum']):
            key = tuple(key)
            # income is credited (negative balance); expense debited
            out.setdefault(key, {'revenue': 0.0, 'expenses': 0.0})[kind] += (
                -(bal or 0.0) if kind == 'revenue' else (bal or 0.0))
    return out


def pl_summary(env, agent=None, period='this_month', **_kw):
    _check(env)
    totals = _pl(env, _aml_base(env) + _date_domain(period), []).get((), {})
    revenue, expenses = totals.get('revenue', 0.0), totals.get('expenses', 0.0)
    return {'period': period, 'currency': _currency(env),
            'revenue': round(revenue, 2), 'expenses': round(expenses, 2),
            'net_profit': round(revenue - expenses, 2)}


def pl_trend(env, agent=None, period='ytd', **_kw):
    _check(env)
    d_from, d_to = resolve_period(period or 'ytd')
    dom = _aml_base(env)
    if d_from:
        dom.append(('date', '>=', d_from.replace(day=1)))
    if d_to:
        dom.append(('date', '<=', d_to))
    data = _pl(env, dom, ['date:month'])
    rows = []
    for (month,), v in sorted(data.items(), key=lambda kv: kv[0][0] or date.min):
        rows.append([month.isoformat() if month else '', round(v['revenue'], 2),
                     round(v['expenses'], 2), round(v['revenue'] - v['expenses'], 2)])
    return _table(env, ['Month', 'Revenue', 'Expenses', 'Net profit'], rows[-24:],
                  period=period)


def cashflow_daily(env, agent=None, period='this_month', **_kw):
    _check(env)
    acc = _cashflow(env, period, 'date:day', 62)
    rows = [[d.isoformat(), round(v['in'], 2), round(-v['out'], 2),
             round(v['in'] + v['out'], 2)]
            for d, v in sorted(acc.items(), key=lambda kv: kv[0])]
    return _table(env, ['Date', 'Inflow', 'Outflow', 'Net'], rows[-62:], period=period)


def cashflow_by_journal(env, agent=None, period='this_month', **_kw):
    _check(env)
    acc = _cashflow(env, period, 'journal_id', 20)
    rows = sorted(([j.display_name, round(v['in'], 2), round(-v['out'], 2),
                    round(v['in'] + v['out'], 2), v['n']] for j, v in acc.items()),
                  key=lambda r: r[3], reverse=True)
    return _table(env, ['Journal', 'Inflow', 'Outflow', 'Net', 'Lines'], rows[:20],
                  period=period)


def cash_position(env, agent=None, **_kw):
    _check(env)
    journals = env['account.journal'].search(
        [('type', 'in', ('cash', 'bank')), ('company_id', 'in', env.companies.ids)],
        limit=MAX_ROWS)
    accounts = journals.default_account_id
    balances = dict(env['account.move.line']._read_group(
        _aml_base(env) + [('account_id', 'in', accounts.ids)],
        ['account_id'], ['balance:sum'])) if accounts else {}
    rows, total = [], 0.0
    for j in journals:
        bal = (balances.get(j.default_account_id) or 0.0) if j.default_account_id else 0.0
        rows.append([j.display_name, j.type, round(bal, 2)])
        total += bal
    return _table(env, ['Journal', 'Type', 'Balance'], rows, total=round(total, 2))


def tax_summary(env, agent=None, period='this_month', **_kw):
    _check(env)
    Aml = env['account.move.line']
    dom = _aml_base(env) + [('tax_line_id', '!=', False)] + _date_domain(period)
    [[out_bal]] = Aml._read_group(dom + [('balance', '<', 0)], [], ['balance:sum'])
    [[in_bal]] = Aml._read_group(dom + [('balance', '>', 0)], [], ['balance:sum'])
    output_tax, input_tax = -(out_bal or 0.0), in_bal or 0.0
    return {'period': period, 'currency': _currency(env),
            'output_tax': round(output_tax, 2), 'input_tax': round(input_tax, 2),
            'net_payable': round(output_tax - input_tax, 2)}


TOOLS = {
    'ar_aging': ar_aging,
    'top_overdue_partners': top_overdue_partners,
    'pl_trend': pl_trend,
    'cashflow_daily': cashflow_daily,
    'cashflow_by_journal': cashflow_by_journal,
    'pl_summary': pl_summary,
    'cash_position': cash_position,
    'tax_summary': tax_summary,
}

for _code, _fn in TOOLS.items():
    tool_dispatcher.register(_code, _fn)
