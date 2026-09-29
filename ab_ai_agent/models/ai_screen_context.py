# -*- coding: utf-8 -*-
"""Screen Context Engine — what the user is looking at, as facts.

The browser (``aiScreenContext`` service) sends a *descriptor* of the
current screen: action, model, view type, open record, search domain,
group-by, facets, selected / visible ids, visible header buttons. Nothing
in it is trusted. Everything is re-derived here AS THE USER:

* the model must be readable by them, the action must be one their groups
  can open, the record must pass their record rules;
* counts are ``search_count`` / ``read_group`` under their rules, so two
  users on "the same" screen get their own numbers;
* ids from the browser are intersected with what they can read;
* no field the user cannot read (field ``groups``) is ever named or valued.

Only aggregates and a handful of display names leave this module — never
row dumps. The result feeds two consumers:

* ``prompt_block()`` — a compact section of the agent's system prompt;
* ``facts()`` — the same facts as data, for the proactive insight
  (``/ai_agent/screen/insight``), which costs no AI tokens at all.

Extension points (inherit this AbstractModel):
* ``_ai_screen_guide(ctx)``  — a short "what this screen is for" text
  (the knowledge-base bridge fills it from kb.article);
* ``_ai_attention_domain(Model)`` — what "needs attention" means for a
  model (default: overdue activities / past deadline).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time

from odoo import api, fields, models
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

VIEW_TYPES = {'list', 'form', 'kanban', 'pivot', 'graph', 'calendar',
              'activity', 'map', 'gantt', 'cohort', 'hierarchy'}
MAX_IDS = 50
MAX_DOMAIN_CHARS = 6000
STATE_FIELDS = ('state', 'stage_id', 'status', 'kanban_state', 'priority')
_FIELD_RE = re.compile(r'^[a-z_][a-z0-9_]{0,62}$')

# Per-worker insight cache: (uid, companies, lang, context hash) ->
# (expires_at, payload). Small and short-lived on purpose — the numbers
# are live data, a tip is only worth re-computing when the screen or the
# data may have changed.
_INSIGHT_CACHE: dict = {}
_INSIGHT_CACHE_MAX = 512


class AiScreenContext(models.AbstractModel):
    _name = 'ai.screen.context'
    _description = 'AI Screen Context Engine'

    # ── Normalise (trust nothing) ──────────────────────────────

    @api.model
    def normalize(self, raw):
        """Validate a browser descriptor. Returns a clean dict or None."""
        if not isinstance(raw, dict):
            return None
        env = self.env
        ctx = {}

        action = self._resolve_action(raw.get('action') or {})
        if action is False:                      # exists but forbidden
            return None
        if action:
            ctx['action'] = action

        model = raw.get('model') or (action or {}).get('res_model')
        if model:
            Model = env.get(model) if isinstance(model, str) else None
            if Model is None or Model._abstract or not Model.has_access('read'):
                return ctx or None
            ctx['model'] = model
            ctx['model_label'] = Model._description or model
        else:
            return ctx or None

        vt = raw.get('view_type')
        ctx['view_type'] = vt if vt in VIEW_TYPES else ''

        Model = env[model]
        readable = Model.fields_get(attributes=['type', 'string', 'selection',
                                                'relation', 'store'])
        ctx['_readable'] = readable

        # Open record
        res_id = raw.get('res_id')
        if isinstance(res_id, int) and res_id > 0:
            rec = Model.browse(res_id).exists()
            if rec and self._can_read(rec):
                ctx['res_id'] = rec.id

        # Domain / group by / order — only well-formed, readable fields
        domain = raw.get('domain')
        if isinstance(domain, list) and len(str(domain)) <= MAX_DOMAIN_CHARS \
                and self._domain_ok(Model, domain, readable):
            ctx['domain'] = domain
        else:
            ctx['domain'] = []
        ctx['group_by'] = [g for g in (raw.get('group_by') or [])[:3]
                           if isinstance(g, str)
                           and g.split(':')[0] in readable
                           and _FIELD_RE.match(g.split(':')[0])]
        ctx['facets'] = [str(f)[:80] for f in (raw.get('facets') or [])[:10]
                         if isinstance(f, str) and f.strip()]

        # Ids from the browser ∩ what the user can read, order preserved
        for key in ('selected_ids', 'visible_ids'):
            ids = [i for i in (raw.get(key) or [])[:MAX_IDS]
                   if isinstance(i, int) and i > 0]
            if ids:
                ok = set(Model.search([('id', 'in', ids)]).ids)
                ids = [i for i in ids if i in ok]
            ctx[key] = ids

        # Header buttons the UI shows (labels only; the executable
        # decision is made again at click time by the confirm flow)
        ctx['buttons'] = [
            {'name': str(b.get('name') or '')[:64],
             'string': str(b.get('string') or '')[:60],
             'type': b.get('type') if b.get('type') in ('object', 'action') else ''}
            for b in (raw.get('buttons') or [])[:15]
            if isinstance(b, dict) and (b.get('string') or '').strip()
        ]
        return ctx

    def _resolve_action(self, raw_action):
        """{} when absent, False when present but not openable by the user."""
        act_id = raw_action.get('id') if isinstance(raw_action, dict) else None
        if not isinstance(act_id, int) or act_id <= 0:
            return {}
        Action = self.env['ir.actions.actions']
        base = Action.sudo().browse(act_id).exists()
        if not base:
            return {}
        action = self.env[base.type].sudo().browse(act_id)
        groups = action.groups_id if 'groups_id' in action._fields else False
        if groups and not (groups & self.env.user.groups_id):
            return False
        out = {'id': action.id, 'name': action.with_context(
            lang=self.env.lang).name or '', 'type': base.type}
        if base.type == 'ir.actions.act_window':
            out['res_model'] = action.res_model
            if action.help:
                out['help'] = html2plaintext(action.help or '').strip()[:400]
        # Menu path, walked as the user (hidden ancestors truncate it)
        menu = self.env['ir.ui.menu'].search(
            [('action', '=', f'{base.type},{act_id}')], limit=1)
        if menu:
            parts, node = [], menu
            while node:
                parts.append(node.name)
                node = node.parent_id
            out['menu_path'] = ' / '.join(reversed(parts))
        return out

    def _domain_ok(self, Model, domain, readable):
        """Every leaf must be a (field, op, value) on a readable field."""
        for leaf in domain:
            if isinstance(leaf, str):
                if leaf not in ('&', '|', '!'):
                    return False
                continue
            if not isinstance(leaf, (list, tuple)) or len(leaf) != 3:
                return False
            path = leaf[0]
            if path in (0, 1):                   # TRUE_LEAF / FALSE_LEAF
                continue
            if not isinstance(path, str):
                return False
            head = path.split('.')[0]
            if head != 'id' and head not in readable:
                return False
        try:
            Model.search_count(domain, limit=1)
        except Exception:
            return False
        return True

    def _can_read(self, record):
        try:
            record.check_access('read')
            return True
        except Exception:
            return False

    # ── Facts (shared by the prompt block and the insight) ─────

    @api.model
    def facts(self, ctx):
        """Aggregates for a normalised context. Cheap: ≤4 queries."""
        if not ctx or not ctx.get('model'):
            return {}
        Model = self.env[ctx['model']]
        readable = ctx.get('_readable') or {}
        domain = ctx.get('domain') or []
        out = {}
        try:
            out['count'] = Model.search_count(domain)
        except Exception:
            out['count'] = None

        # Breakdown by the model's lifecycle field
        state_field = next((f for f in STATE_FIELDS
                            if f in readable and readable[f].get('store')
                            and readable[f]['type'] in ('selection', 'many2one')), None)
        if state_field and out.get('count'):
            try:
                groups = Model._read_group(domain, [state_field], ['__count'],
                                           order='__count desc', limit=6)
                labels = dict(readable[state_field].get('selection') or [])
                out['by_state'] = [{
                    'label': (labels.get(val, val) if readable[state_field]['type'] == 'selection'
                              else (val.display_name if val else '')) or '—',
                    'count': cnt,
                } for val, cnt in groups]
                out['state_field'] = readable[state_field].get('string') or state_field
            except Exception:
                _logger.debug('screen facts: by_state failed', exc_info=True)

        att = self._ai_attention_domain(Model, readable)
        if att and out.get('count'):
            try:
                out['attention'] = Model.search_count(domain + att)
            except Exception:
                pass

        if ctx.get('res_id'):
            out['record'] = self._record_facts(Model.browse(ctx['res_id']), readable)
        if ctx.get('visible_ids'):
            recs = Model.browse(ctx['visible_ids'][:10])
            out['visible'] = [{'id': r.id, 'name': r.display_name} for r in recs]
        if ctx.get('selected_ids'):
            out['selected'] = len(ctx['selected_ids'])
        return out

    def _ai_attention_domain(self, Model, readable):
        """What "needs attention" means for this model. Extension point."""
        today = fields.Date.context_today(self)
        if 'activity_date_deadline' in Model._fields and 'activity_ids' in readable:
            return [('activity_date_deadline', '<', today)]
        for f in ('date_deadline', 'invoice_date_due', 'date_due'):
            if f in readable and readable[f].get('store'):
                dom = [(f, '<', today)]
                if 'state' in readable and readable['state'].get('store'):
                    dom.append(('state', 'not in', ('done', 'cancel', 'posted', 'paid')))
                return dom
        return []

    def _record_facts(self, rec, readable):
        """A few identifying values of the open record (never all fields)."""
        out = {'id': rec.id, 'name': rec.display_name}
        for f in ('state', 'stage_id', 'partner_id', 'user_id', 'amount_total',
                  'date', 'date_order', 'invoice_date', 'date_deadline'):
            if f not in readable:
                continue
            val = rec[f]
            if not val and val != 0:
                continue
            ftype = readable[f]['type']
            if ftype == 'selection':
                val = dict(readable[f].get('selection') or []).get(val, val)
            elif ftype == 'many2one':
                val = val.display_name
            out[readable[f].get('string') or f] = str(val)
        return out

    def _ai_screen_guide(self, ctx):
        """Short "what this screen is for". Extension point: the knowledge
        base bridge returns the linked article's summary. Default: the
        action's own help text (Odoo's empty-state copy — a weak seed)."""
        return (ctx.get('action') or {}).get('help') or ''

    # ── Prompt block ───────────────────────────────────────────

    @api.model
    def prompt_block(self, raw):
        ctx = self.normalize(raw)
        if not ctx or not ctx.get('model'):
            return ''
        facts = self.facts(ctx)
        action = ctx.get('action') or {}
        lines = ['## Current screen (live, as this user sees it)']
        title = action.get('name') or ctx.get('model_label')
        lines.append(f'- Screen: {title} ({ctx["model_label"]}, `{ctx["model"]}`)')
        if action.get('menu_path'):
            lines.append(f'- Menu: {action["menu_path"]}')
        if ctx.get('view_type'):
            lines.append(f'- View: {ctx["view_type"]}')
        if ctx.get('facets'):
            lines.append(f'- Active filters: {"; ".join(ctx["facets"])}')
        if ctx.get('group_by'):
            lines.append(f'- Grouped by: {", ".join(ctx["group_by"])}')
        if facts.get('count') is not None and not ctx.get('res_id'):
            lines.append(f'- Records matching the current filters: {facts["count"]}')
        if facts.get('by_state'):
            parts = ', '.join(f'{s["label"]}: {s["count"]}' for s in facts['by_state'])
            lines.append(f'- By {facts.get("state_field")}: {parts}')
        if facts.get('attention'):
            lines.append(f'- Overdue / needing attention: {facts["attention"]}')
        if facts.get('selected'):
            lines.append(f'- Selected by the user: {facts["selected"]} record(s)')
        if facts.get('visible'):
            rows = '; '.join(f'#{i + 1} {v["name"]} (id {v["id"]})'
                             for i, v in enumerate(facts['visible']))
            lines.append(f'- Rows on screen, in order: {rows}')
        if facts.get('record'):
            rec = facts['record']
            vals = ', '.join(f'{k}: {v}' for k, v in rec.items() if k not in ('id', 'name'))
            lines.append(f'- Open record: {rec["name"]} (id {rec["id"]})'
                         + (f' — {vals}' if vals else ''))
        if ctx.get('buttons'):
            lines.append('- Buttons visible on screen: ' + ', '.join(
                f"{b['string']} [{b['name']}]" if b.get('name') and b.get('type') == 'object'
                else b['string'] for b in ctx['buttons']))
        guide = self._ai_screen_guide(ctx)
        if guide:
            lines.append(f'- About this screen: {guide[:500]}')
        lines.append(
            'Use ONLY these facts for questions about "this page/screen/record". '
            '"The first one" means row #1 above. Numbers here are exact; do not '
            'invent others — call a tool for anything not listed. A button '
            'being visible does not mean you may press it: any change needs '
            'the user\'s confirmation.')
        return '\n'.join(lines)

    # ── Proactive insight (no AI tokens) ──────────────────────

    @api.model
    def insight(self, raw):
        """0-2 short, templated lines about the current screen.

        Deterministic, from facts() only — no LLM call, so a tip costs a
        count and a group-by, never tokens, and can never invent a number.
        """
        ctx = self.normalize(raw)
        if not ctx or not ctx.get('model'):
            return {'lines': []}
        public = {k: v for k, v in ctx.items() if not k.startswith('_')}
        key_src = json.dumps(public, sort_keys=True, default=str)
        key = (self.env.uid, tuple(self.env.companies.ids), self.env.lang,
               hashlib.sha1(key_src.encode()).hexdigest())
        now = time.monotonic()
        hit = _INSIGHT_CACHE.get(key)
        if hit and hit[0] > now:
            return hit[1]

        facts = self.facts(ctx)
        _ = self.env._
        lines = []
        if ctx.get('res_id') and facts.get('record'):
            rec = facts['record']
            state = next((v for k, v in rec.items()
                          if k not in ('id', 'name') and k.lower() in ('status', 'state', 'stage')), None)
            if state:
                lines.append(_('%(name)s is at: %(state)s.', name=rec['name'], state=state))
        else:
            count = facts.get('count')
            if count is not None:
                lines.append(_('%(count)s records match your current filters.', count=count)
                             if ctx.get('facets') else _('%(count)s records on this screen.', count=count))
            if facts.get('attention'):
                lines.append(_('%(n)s need attention (overdue).', n=facts['attention']))
            elif facts.get('by_state') and count:
                top = facts['by_state'][0]
                lines.append(_('Most are "%(label)s" (%(n)s).', label=top['label'], n=top['count']))
        # What the panel shows the moment it opens, without being asked:
        # which screen this is, what it is for, and the questions worth
        # one tap here. Suggestions are sent as ordinary questions.
        action = ctx.get('action') or {}
        about = (self._ai_screen_guide(ctx) or '').strip()
        if ctx.get('res_id'):
            suggestions = [
                _('Explain this record'),
                _('What should I do next with it?'),
            ]
            if ctx.get('buttons'):
                suggestions.append(_('What can I do on this screen?'))
        else:
            suggestions = [_('Explain this screen')]
            if facts.get('attention'):
                suggestions.append(_('Which records need attention?'))
            if facts.get('count'):
                suggestions.append(_('Summarise what is shown here'))
            if ctx.get('visible_ids'):
                suggestions.append(_('Open the first one'))
        payload = {
            'lines': lines[:2],
            'attention': facts.get('attention') or 0,
            'title': (facts.get('record') or {}).get('name') if ctx.get('res_id')
                     else (action.get('name') or ctx.get('model_label') or ''),
            'subtitle': ctx.get('model_label') if ctx.get('res_id') else (action.get('menu_path') or ''),
            'about': about[:280],
            'suggestions': suggestions[:4],
        }

        ttl = int(self.env['ir.config_parameter'].sudo().get_param(
            'ab_ai_agent.insight_cache_seconds', 30) or 0)
        if ttl > 0:
            if len(_INSIGHT_CACHE) >= _INSIGHT_CACHE_MAX:
                for k in [k for k, v in _INSIGHT_CACHE.items() if v[0] <= now] or \
                        list(_INSIGHT_CACHE)[:_INSIGHT_CACHE_MAX // 4]:
                    _INSIGHT_CACHE.pop(k, None)
            _INSIGHT_CACHE[key] = (now + ttl, payload)
        return payload

