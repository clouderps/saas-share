# -*- coding: utf-8 -*-
"""query_data — the assistant's generic, safe "ask the data" tool.

Replaces guessing among a few fixed metrics with an aggregation over ANY
model the user can read: measures (sum/avg/min/max/count), group-by
(fields, or dates by day/week/month/quarter/year), filters, a date range,
and an optional comparison with the previous period of the same length.

Safety:
  * runs as the user through read_group — ACL, record rules and
    multi-company apply; no SQL is built from model input;
  * every field name must be a stored, readable field (field-level
    groups honoured through fields_get as the user);
  * filters go through the same validation as the screen engine;
  * bounded: ≤5 measures, ≤2 group-bys, ≤50 groups, 8 s statement timeout.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from odoo import fields as ofields

_logger = logging.getLogger(__name__)

NUMERIC = ('integer', 'float', 'monetary')
GROUPABLE = ('many2one', 'selection', 'char', 'boolean', 'date', 'datetime', 'integer')
DATE_GRAINS = ('day', 'week', 'month', 'quarter', 'year')
OPS = ('sum', 'avg', 'min', 'max', 'count')
PREFERRED_DATES = ('date_order', 'invoice_date', 'date', 'date_planned', 'scheduled_date',
                   'request_date', 'date_from', 'create_date')


def _as_list(v):
    if v in (None, False, ''):
        return []
    return v if isinstance(v, list) else [v]


def _resolve_model(env, name):
    from .tool_dispatcher import _resolve_model as resolve
    screen = env.context.get('ai_screen') or {}
    return resolve(env, name) if name else screen.get('model')


def query_data(env, agent=None, model=None, measures=None, group_by=None,
               domain=None, date_field=None, date_from=None, date_to=None,
               compare_previous=False, limit=10, order='desc', **_kw):
    _ = env._
    model = _resolve_model(env, model)
    Model = env.get(model) if model else None
    if Model is None:
        return {'error': 'unknown model', 'note': 'Ask which records the user means, in their words.'}
    if not Model.has_access('read'):
        return {'error': 'not permitted', 'note': 'Tell the user they cannot see these records.'}
    info = Model.fields_get(attributes=['type', 'string', 'store', 'selection', 'groupable'])

    # Measures: [{"field": "amount_total", "op": "sum"}] or "amount_total:sum"
    specs = []
    for m in _as_list(measures)[:5]:
        if isinstance(m, str):
            f, _sep, op = m.partition(':')
        else:
            f, op = (m or {}).get('field'), (m or {}).get('op') or 'sum'
        op = (op or 'sum').lower()
        if f in ('id', '__count', 'count', None, '') or op == 'count':
            specs.append(('__count', 'count'))
        elif f in info and info[f]['type'] in NUMERIC and info[f].get('store') and op in OPS:
            specs.append((f, op))
    if not specs:
        specs = [('__count', 'count')]

    # Group-bys: "partner_id", "date_order:month"
    groups = []
    for g in _as_list(group_by)[:2]:
        f, _sep, grain = str(g).partition(':')
        if f not in info or not info[f].get('store') or info[f]['type'] not in GROUPABLE:
            continue
        if info[f]['type'] in ('date', 'datetime'):
            groups.append(f"{f}:{grain if grain in DATE_GRAINS else 'month'}")
        else:
            groups.append(f)

    # Filters (validated like the screen engine) + date range
    dom = domain if isinstance(domain, list) else []
    if dom and not env['ai.screen.context']._domain_ok(Model, dom, info):
        return {'error': 'invalid filter',
                'note': 'Use only real fields of this model in the filter.'}
    dfield = date_field if date_field in info and info[date_field]['type'] in ('date', 'datetime') \
        else next((f for f in PREFERRED_DATES if f in info and info[f]['type'] in ('date', 'datetime')
                   and info[f].get('store')), None)
    d_from = ofields.Date.to_date(date_from) if date_from else None
    d_to = ofields.Date.to_date(date_to) if date_to else None

    def with_period(start, end):
        extra = []
        if dfield and start:
            extra.append((dfield, '>=', start))
        if dfield and end:
            extra.append((dfield, '<=', end))
        return list(dom) + extra

    aggregates = ['__count' if f == '__count' else f'{f}:{op}' for f, op in specs]
    limit = max(1, min(int(limit or 10), 50))

    def run(dm):
        cr = env.cr
        cr.execute("SHOW statement_timeout")
        before = cr.fetchone()[0]
        cr.execute("SET LOCAL statement_timeout = '8s'")
        try:
            order_by = None
            if groups:
                order_by = f"{aggregates[0]} {'asc' if order == 'asc' else 'desc'}"
                if groups[0].split(':')[0] in info and info[groups[0].split(':')[0]]['type'] in ('date', 'datetime'):
                    order_by = f"{groups[0]} asc"
            return Model._read_group(dm, groups, aggregates, order=order_by,
                                     limit=limit if groups else None)
        finally:
            cr.execute("SET LOCAL statement_timeout = %s", (before,))

    try:
        with env.cr.savepoint():
            rows = run(with_period(d_from, d_to))
            prev_rows = None
            if compare_previous and d_from and d_to and not groups:
                span = (d_to - d_from).days + 1
                prev_rows = run(with_period(d_from - timedelta(days=span), d_from - timedelta(days=1)))
    except Exception as e:
        _logger.info('query_data failed on %s: %s', model, e)
        return {'error': 'the query could not run', 'note': 'Try fewer filters or another grouping.'}

    def mlabel(f, op):
        if f == '__count':
            return _('Count')
        return f"{info[f]['string']} ({ {'sum': _('total'), 'avg': _('average'), 'min': _('minimum'), 'max': _('maximum')}[op] })"

    def fmt(v):
        if isinstance(v, float):
            return f'{v:,.2f}'
        if isinstance(v, int):
            return f'{v:,}'
        return str(v)

    def glabel(g, v):
        f = g.split(':')[0]
        if hasattr(v, 'display_name'):
            return v.display_name or _('(none)')
        if info[f]['type'] == 'selection':
            return dict(info[f].get('selection') or []).get(v, v) or _('(none)')
        if isinstance(v, date):
            grain = g.split(':')[1] if ':' in g else 'day'
            d = v.date() if hasattr(v, 'date') and callable(v.date) else v
            if grain == 'year':
                return str(d.year)
            if grain == 'quarter':
                return f'{d.year} Q{(d.month - 1) // 3 + 1}'
            if grain == 'month':
                return f'{d.year}-{d.month:02d}'
            return d.isoformat()
        return _('(none)') if v in (False, None) else str(v)

    # The model's name in the user's language (ir.model is translated;
    # _description is the untranslated Python string).
    title = env['ir.model']._get(model).name or Model._description or model
    period = ''
    if d_from or d_to:
        period = f" ({d_from or '…'} → {d_to or '…'})"

    if not groups:
        vals = rows[0] if rows else tuple(0 for _s in specs)
        items = []
        summary = []
        for (f, op), v in zip(specs, vals):
            item = {'label': mlabel(f, op), 'value': fmt(v or 0)}
            if prev_rows:
                pv = prev_rows[0][specs.index((f, op))] or 0
                if pv:
                    delta = ((v or 0) - pv) / pv * 100
                    item['delta_pct'] = f'{delta:+.1f}%'
                    item['tone'] = 'good' if delta >= 0 else 'bad'
                    summary.append(f'{f}:{op}={v} (previous period {pv}, {delta:+.1f}%)')
                else:
                    summary.append(f'{f}:{op}={v} (previous period 0)')
            else:
                summary.append(f'{f}:{op}={v}')
            items.append(item)
        return {
            'render': {'layout': 'report', 'title': f'{title}{period}',
                       'blocks': [{'type': 'kpi_grid', 'items': items}]},
            'summary': f'{model}{period}: ' + '; '.join(summary),
        }

    grain_label = {'day': _('day'), 'week': _('week'), 'month': _('month'),
                   'quarter': _('quarter'), 'year': _('year')}
    headers = [info[g.split(':')[0]]['string']
               + (f" ({grain_label.get(g.split(':')[1], g.split(':')[1])})" if ':' in g else '')
               for g in groups] + [mlabel(f, op) for f, op in specs]
    table = []
    csv = []
    for row in rows:
        keys, vals = row[:len(groups)], row[len(groups):]
        cells = [glabel(g, k) for g, k in zip(groups, keys)] + [fmt(v or 0) for v in vals]
        table.append(cells)
        csv.append(' | '.join(cells))
    blocks = [{'type': 'data_table', 'title': f'{title}{period}', 'headers': headers, 'rows': table}]
    if len(groups) == 1 and table and all(isinstance(r[len(groups)], (int, float)) for r in rows):
        blocks.append({
            'type': 'chart', 'chart': 'area' if ':' in groups[0] else 'bar',
            'title': headers[1], 'x': [r[0] for r in table],
            'series': [{'name': headers[1], 'data': [round(float(r[1] or 0), 2) for r in rows]}],
        })
    return {
        'render': {'layout': 'report', 'title': f'{title}{period}', 'blocks': blocks},
        'summary': f'{model}{period} grouped by {", ".join(groups)} ({len(table)} groups): '
                   + ' || '.join(csv[:20]),
    }
