# -*- coding: utf-8 -*-
"""Answer cache hooks for ``ab_ai_agent.services.runtime``.

Two kinds of entry:

* ``data`` — "sales this month", "who is absent today". The answer is
  numbers, so it is never reused; the TOOL PLAN is. A hit re-runs the
  same read tools as the requesting user (ACL, record rules, branch
  scope all apply) and renders their own output: fresh figures, no LLM
  hop. Kept only when every tool rendered its own result, so nothing
  depended on the model's prose. TTL 10 minutes.
* ``howto`` — "where do I create a vendor bill". Navigation and
  knowledge-base answers do not move with the data, so the stored
  envelope is reused. TTL 24 hours.

Never cached: a turn that proposed or executed any change, a turn with a
failed tool, and a turn that used no tool (ungrounded).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import timedelta

from odoo import fields

from odoo.addons.ab_ai_agent.services import runtime, tool_dispatcher

_logger = logging.getLogger(__name__)

DATA_TOOLS = frozenset({'query_data', 'data_analysis', 'recent_records',
                        'hr_attendance_missing_today', 'hr_leave_pending',
                        'hr_attendance_open_shifts'})
HOWTO_TOOLS = frozenset({'find_menu', 'list_my_apps', 'kb_search', 'kb_read', 'open_action',
                         'open_list', 'open_pivot', 'open_graph'})
# Allowed inside a data plan, never on its own (answers move with the clock).
NEUTRAL_TOOLS = frozenset({'date_reference'})
TTL = {'data': timedelta(minutes=10), 'howto': timedelta(hours=24)}

_TASHKEEL = re.compile('[ؐ-ًؚ-ٰٟۖ-ۭ]')
_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
_FOLD = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي', 'ة': 'ه',
                       'ؤ': 'و', 'ئ': 'ي'})


def normalize(text):
    """Same question, same key: case, punctuation, tashkeel, tatweel,
    alef / ya / ta-marbuta forms and Arabic-Indic digits do not count."""
    text = (text or '').strip().lower()
    text = _TASHKEEL.sub('', text).replace('ـ', '')
    text = text.translate(_FOLD).translate(_DIGITS)
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _enabled(env):
    if env.get('ai.agent.answer.cache') is None:
        return False          # code loaded, module not installed on this db
    val = env['ir.config_parameter'].sudo().get_param('ab_ai_agent.answer_cache', 'True')
    return str(val).lower() in ('1', 'true', 'yes')


def cache_key(env, agent, question, locale):
    parts = [normalize(question), str(agent.id if agent else 0), str(env.company.id),
             ','.join(map(str, sorted(env.user.groups_id.ids))), env.lang or '',
             locale or '', ','.join(map(str, sorted(env.companies.ids)))]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()


def _replay(env, agent, plan):
    """Re-run a cached read-only plan as the user → envelope or None."""
    tools = runtime._resolve_tools(env, agent)
    renders, summaries, action = [], [], None
    for step in plan:
        if step['tool'] in NEUTRAL_TOOLS:
            continue                       # its result is already baked into later args
        tool = tools.filtered(lambda t, c=step['tool']: t.code == c)[:1]
        if not tool:
            return None                    # rights changed: let the LLM answer
        out = tool_dispatcher.dispatch(env, tool, dict(step.get('args') or {}), agent=agent)
        res = out.get('result') if out.get('ok') else None
        if not isinstance(res, dict) or not (res.get('render') or {}).get('blocks'):
            return None
        renders.append(res['render'])
        if res.get('summary'):
            summaries.append(res['summary'])
        action = res.get('action') or action
    if len(renders) == 1:
        render = renders[0]
    else:
        blocks = []
        for r in renders:
            if r.get('title'):
                blocks.append({'type': 'text', 'text': f'### {r["title"]}'})
            blocks.extend(r.get('blocks') or [])
        render = {'layout': 'report', 'title': env._('Results'), 'blocks': blocks}
    return {'response': ' '.join(summaries)[:600] or render.get('title') or '',
            'render': render, 'action': action}


def lookup(env, agent=None, question=None, locale=None):
    if not question or not _enabled(env):
        return None
    Cache = env['ai.agent.answer.cache'].sudo()
    row = Cache.search([('key', '=', cache_key(env, agent, question, locale))], limit=1)
    if not row:
        return None
    now = fields.Datetime.now()
    if row.expires_at < now:
        row.unlink()
        return None
    if row.kind == 'data':
        envelope = _replay(env, agent, json.loads(row.plan_json or '[]'))
    else:
        envelope = json.loads(row.envelope_json or 'null')
    if not envelope:
        row.unlink()
        return None
    row.write({'hit_count': row.hit_count + 1, 'last_hit': now})
    envelope['cache'] = {'hit': True, 'kind': row.kind}
    envelope.setdefault('usage', {}).update({'prompt_tokens': 0, 'completion_tokens': 0,
                                             'cached_tokens': 0, 'total_tokens': 0,
                                             'cost_usd': 0.0, 'model': '', 'provider': 'cache'})
    return envelope


def store(env, agent=None, question=None, locale=None, envelope=None, tool_plan=None,
          tool_calls=None):
    if not question or not envelope or not _enabled(env):
        return False
    plan = list(tool_plan or [])
    calls = list(tool_calls or [])
    if not plan or len(plan) != len(calls) or not all(c.get('ok') for c in calls):
        return False
    codes = {s['tool'] for s in plan}
    if not codes <= (DATA_TOOLS | HOWTO_TOOLS | NEUTRAL_TOOLS):
        return False                       # anything that writes / proposes / is unknown
    if not codes - NEUTRAL_TOOLS:
        return False
    if codes & NEUTRAL_TOOLS and not codes & DATA_TOOLS:
        return False                       # a dated how-to answer goes stale at midnight
    if any(isinstance(c.get('result'), dict) and c['result'].get('requires_confirmation')
           for c in calls):
        return False
    kind = 'data' if codes & DATA_TOOLS else 'howto'
    if kind == 'data' and not all(
            isinstance(c.get('result'), dict) and (c['result'].get('render') or {}).get('blocks')
            for c, s in zip(calls, plan) if s['tool'] in DATA_TOOLS):
        return False                       # the answer lives in the model's prose
    vals = {
        'key': cache_key(env, agent, question, locale),
        'agent_id': agent.id if agent else False,
        'company_id': env.company.id,
        'lang': env.lang,
        'question': (question or '')[:250],
        'kind': kind,
        'plan_json': json.dumps(plan, default=str),
        'envelope_json': json.dumps({k: envelope.get(k) for k in ('response', 'render', 'action')},
                                    default=str) if kind == 'howto' else False,
        'models_touched': ','.join(sorted({str((s.get('args') or {}).get('model'))
                                           for s in plan if (s.get('args') or {}).get('model')})),
        'expires_at': fields.Datetime.now() + TTL[kind],
    }
    Cache = env['ai.agent.answer.cache'].sudo()
    row = Cache.search([('key', '=', vals['key'])], limit=1)
    if row:
        row.write(vals)
    else:
        Cache.create(vals)
    return True


runtime.ANSWER_CACHE.update({'lookup': lookup, 'store': store})
