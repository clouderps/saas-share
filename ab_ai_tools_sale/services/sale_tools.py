# -*- coding: utf-8 -*-
"""Sales tools for the shared ab_ai_agent registry.

Moved from ab_ai_chatbot (services/tools/sales.py). The chatbot versions
read the ``fact_sales`` materialized view with raw SQL; these aggregate
through ``_read_group`` as the calling user, so ACLs, record rules, the
branch ``_search`` filter and the company switcher (``env.companies``)
apply exactly as in a list view. Same codes, arguments and result shape
(``headers`` / ``rows`` / ``total_rows`` / ``fact``), so prompts and
golden sets keep working.

Channels: confirmed sales orders, plus Point of Sale orders when
``pos.order`` is installed and readable by the user (the old view was a
union of both). Amounts are tax-included order totals, as before.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from odoo import fields

from odoo.addons.ab_ai_agent.services import tool_dispatcher

MAX_ROWS = 500

TOOL_CODES = ('sales_totals', 'top_products', 'top_customers',
              'sales_by_branch', 'sales_trend_monthly')

PERIODS = ('today', 'yesterday', 'this_week', 'last_week', 'this_month',
           'last_month', 'this_quarter', 'ytd', 'last_year')

# channel -> order model, line model, order domain, order amount,
#            line amount, line qty
_CHANNELS = (
    ('sale_order', 'sale.order', 'sale.order.line',
     [('state', 'in', ('sale', 'done'))], 'amount_total',
     'price_total', 'product_uom_qty'),
    ('pos_order', 'pos.order', 'pos.order.line',
     [('state', 'in', ('paid', 'done', 'invoiced'))], 'amount_total',
     'price_subtotal_incl', 'qty'),
)


def _resolve_period(label, today):
    """Relative period label -> (date_from, date_to) inclusive, or None."""
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
    return None


def _sources(env):
    """Channels installed on this DB and readable by the user."""
    out = []
    for channel, order_m, line_m, dom, o_amt, l_amt, l_qty in _CHANNELS:
        Order, Line = env.get(order_m), env.get(line_m)
        if Order is None or Line is None:
            continue
        if not (Order.has_access('read') and Line.has_access('read')):
            continue
        out.append({'channel': channel, 'Order': Order, 'Line': Line,
                    'domain': list(dom), 'o_amt': o_amt, 'l_amt': l_amt,
                    'l_qty': l_qty})
    return out


def _order_domain(env, src, period, branch_id=None):
    domain = src['domain'] + [('company_id', 'in', env.companies.ids)]
    rng = _resolve_period(period, fields.Date.context_today(env.user)) if period else None
    if rng:
        domain += [('date_order', '>=', datetime.combine(rng[0], time.min)),
                   ('date_order', '<', datetime.combine(rng[1] + timedelta(days=1), time.min))]
    if branch_id and 'branch_id' in src['Order']._fields:
        domain.append(('branch_id', '=', int(branch_id)))
    return domain


def _line_domain(env, src, period, branch_id=None):
    domain = [('order_id', 'any', _order_domain(env, src, period, branch_id))]
    if 'display_type' in src['Line']._fields:
        domain.append(('display_type', '=', False))
    return domain


def _cap(limit, default):
    try:
        return max(1, min(MAX_ROWS, int(limit)))
    except (TypeError, ValueError):
        return default


def _result(headers, rows):
    return {'headers': headers, 'rows': rows, 'total_rows': len(rows), 'fact': 'fact_sales'}


def _grouped(env, period, groupby, level, measures, extra_domain=(), branch_id=None):
    """Sum ``measures`` per ``groupby`` key across every readable channel.

    ``level`` is 'order' or 'line'; measures are logical names
    ('amount', 'count', 'qty'). Returns {key: [values...]}.
    """
    acc = {}
    for src in _sources(env):
        if level == 'order':
            Model = src['Order']
            domain = _order_domain(env, src, period, branch_id)
            spec = {'amount': f"{src['o_amt']}:sum", 'count': '__count'}
        else:
            Model = src['Line']
            domain = _line_domain(env, src, period, branch_id)
            spec = {'amount': f"{src['l_amt']}:sum", 'qty': f"{src['l_qty']}:sum",
                    'count': 'order_id:count_distinct'}
        groups = Model._read_group(domain + list(extra_domain),
                                   groupby=[groupby] if groupby else [],
                                   aggregates=[spec[m] for m in measures])
        for row in groups:
            key, values = (row[0], row[1:]) if groupby else (None, row)
            slot = acc.setdefault(key, [0.0] * len(measures))
            for i, v in enumerate(values):
                slot[i] += float(v or 0)
    return acc


def _label(key):
    if hasattr(key, 'display_name'):
        return key.display_name if key else None
    if isinstance(key, (datetime, date)):
        return key.strftime('%Y-%m')
    return key


def _ranked_rows(acc, limit, n_int=()):
    items = sorted(((k, v) for k, v in acc.items() if k), key=lambda kv: kv[1][0], reverse=True)
    rows = []
    for key, vals in items[:limit]:
        vals = [int(v) if i in n_int else round(v, 2) for i, v in enumerate(vals)]
        rows.append([_label(key)] + vals)
    return rows


# A ranking over an empty window answers nothing although the question
# ("who are my top customers?") has an answer: short windows widen until
# there is data, and the result says which window it used.
_WIDEN = {'today': ['this_month', 'ytd', None], 'yesterday': ['this_month', 'ytd', None],
          'this_week': ['this_month', 'ytd', None], 'last_week': ['ytd', None],
          'this_month': ['ytd', None], 'last_month': ['ytd', None],
          'this_quarter': ['ytd', None], 'ytd': [None]}


def _widened(period, run):
    result = run(period)
    if result['rows'] or period not in _WIDEN:
        return result
    for wider in _WIDEN[period]:
        widened = run(wider)
        if widened['rows']:
            widened['period_used'] = wider or 'all_time'
            widened['note'] = ('No sales in %s; showing %s instead.' % (
                period, 'year to date' if wider == 'ytd'
                else 'this month' if wider == 'this_month' else 'all time'))
            return widened
    return result


# ── Tools ────────────────────────────────────────────────────────────

def sales_totals(env, agent=None, period='this_month', branch_id=None, **_kw):
    acc = _grouped(env, period, None, 'order', ['amount', 'count'], branch_id=branch_id)
    qty = _grouped(env, period, None, 'line', ['qty'], branch_id=branch_id)
    amount, count = acc.get(None, [0.0, 0.0])
    return _result(['Total Sales', 'Orders', 'Units Sold'],
                   [[round(amount, 2), int(count), round(qty.get(None, [0.0])[0], 2)]])


def top_products(env, agent=None, period='this_month', limit=5, **_kw):
    limit = _cap(limit, 5)

    def run(p):
        acc = _grouped(env, p, 'product_id', 'line', ['amount', 'qty'])
        return _result(['Product', 'Total Sales', 'Units Sold'], _ranked_rows(acc, limit))
    return _widened(period, run)


def top_customers(env, agent=None, period='this_month', limit=5, **_kw):
    limit = _cap(limit, 5)

    def run(p):
        acc = _grouped(env, p, 'partner_id', 'order', ['amount', 'count'],
                       extra_domain=[('partner_id', '!=', False)])
        return _result(['Customer', 'Total Sales', 'Orders'], _ranked_rows(acc, limit, n_int=(1,)))
    return _widened(period, run)


def sales_by_branch(env, agent=None, period='this_month', **_kw):
    headers = ['Branch', 'Total Sales', 'Orders']
    if 'ab.branch' not in env.registry.models:
        return _result([], [])
    acc = {}
    for src in _sources(env):
        if 'branch_id' not in src['Order']._fields:
            continue
        for branch, amount, count in src['Order']._read_group(
                _order_domain(env, src, period) + [('branch_id', '!=', False)],
                groupby=['branch_id'], aggregates=[f"{src['o_amt']}:sum", '__count']):
            slot = acc.setdefault(branch, [0.0, 0.0])
            slot[0] += float(amount or 0)
            slot[1] += float(count or 0)
    return _result(headers, _ranked_rows(acc, 50, n_int=(1,)))


def sales_trend_monthly(env, agent=None, period='ytd', **_kw):
    acc = _grouped(env, period, 'date_order:month', 'order', ['amount', 'count'])
    rows = [[_label(k), round(v[0], 2), int(v[1])]
            for k, v in sorted(((k, v) for k, v in acc.items() if k), key=lambda kv: kv[0])]
    return _result(['Month', 'Total Sales', 'Orders'], rows[-24:])


for _code in TOOL_CODES:
    tool_dispatcher.register(_code, globals()[_code])
