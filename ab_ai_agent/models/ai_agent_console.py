# -*- coding: utf-8 -*-
"""Agent Console data layer.

The full-page console (OWL client action ``ab_ai_agent.console``) reads
and edits one agent's configuration in place: prompt, tools, skills,
scope, behaviour, permissions and 30-day performance. These methods are
the whole contract — the controller is a thin JSON shim over them.

Access model: everything runs as the calling user, never sudo. Reading
needs ``ai.agent`` read (every internal user has it) plus the agent being
visible to them; editing needs ``ai.agent`` write, i.e. the Agent
Designer group — the same rule the backend form applies.
"""
from __future__ import annotations

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

# Fields the console may write. Anything else in the payload is ignored,
# so a crafted request cannot touch is_system, stats or distribution.
CONSOLE_WRITABLE = (
    'system_prompt', 'persona', 'locale', 'response_style', 'model_class',
    'max_hops', 'max_cost_usd', 'allow_pii', 'allow_write_actions',
    'allow_web_grounding', 'is_public', 'description', 'use_all_capabilities',
)


class AIAgentConsole(models.Model):
    _inherit = 'ai.agent'

    # ── KPIs ───────────────────────────────────────────────────

    def _console_kpis(self, days=30):
        """Live 30-day performance for every agent in ``self`` in ONE
        aggregate query (the denormalised cron fields are up to a day
        stale, which is wrong for a console someone just ran).

        Runs as the caller: record rules on ai.agent.run apply, so a
        plain user sees their own runs and an AI manager the company's.
        """
        result = {a.id: {'runs': 0, 'done': 0, 'success_rate': 0.0,
                         'avg_cost_usd': 0.0, 'total_cost_usd': 0.0,
                         'total_tokens': 0, 'last_run_at': False}
                  for a in self}
        if not self:
            return result
        since = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        Run = self.env['ai.agent.run']
        domain = [('agent_id', 'in', self.ids), ('started_at', '>=', since)]
        for agent, count, cost, tokens, last in Run._read_group(
                domain, ['agent_id'],
                ['__count', 'cost_usd:sum', 'total_tokens:sum',
                 'started_at:max']):
            row = result[agent.id]
            row.update(runs=count, total_cost_usd=cost or 0.0,
                       total_tokens=tokens or 0, last_run_at=last)
        for agent, count, cost in Run._read_group(
                domain + [('state', '=', 'done')], ['agent_id'],
                ['__count', 'cost_usd:sum']):
            row = result[agent.id]
            row['done'] = count
            row['avg_cost_usd'] = (cost or 0.0) / count if count else 0.0
            row['success_rate'] = round(count * 100.0 / row['runs'], 1) \
                if row['runs'] else 0.0
        for row in result.values():
            if row['last_run_at']:
                row['last_run_at'] = fields.Datetime.to_string(row['last_run_at'])
        return result

    # ── Read ───────────────────────────────────────────────────

    def _console_check_visible(self):
        self.ensure_one()
        user = self.env.user
        if not self.active or not self.is_visible_to(user):
            raise AccessError(_('This agent is not available to you.'))

    @api.model
    def _console_can_edit(self):
        return self.env['ai.agent'].has_access('write')

    def console_payload(self):
        """Everything the console panels render for one agent."""
        self._console_check_visible()
        can_edit = self._console_can_edit()
        # Cost / spend is operator data: only system admins see it.
        show_cost = self.env.user.has_group('base.group_system')
        sel = dict
        persona_sel = sel(self._fields['persona']._description_selection(self.env))
        style_sel = sel(self._fields['response_style']._description_selection(self.env))
        model_sel = sel(self._fields['model_class']._description_selection(self.env))
        locale_sel = sel(self._fields['locale']._description_selection(self.env))
        surface_sel = sel(self._fields['surface_ids']._description_selection(self.env))

        full = self.use_all_capabilities
        direct = self.tool_ids
        via_topic = self.topic_ids.tool_ids - direct
        Tool = self.env['ai.agent.tool']
        # Designers toggle any tool; others see the effective set. A
        # full-access agent has every active tool, so nothing to toggle.
        if full:
            catalog = Tool.search([]) if can_edit else self._effective_tools()
        else:
            catalog = Tool.search([]) if can_edit else (direct | via_topic)
        cat_sel = sel(Tool._fields['category']._description_selection(self.env))
        tools = [{
            'id': t.id, 'name': t.name, 'code': t.code,
            'description': t.description or '',
            'category': cat_sel.get(t.category, t.category or ''),
            'is_write_action': t.is_write_action,
            'requires_pii': t.requires_pii,
            'enabled': (full and t.active) or t in direct or t in via_topic,
            'via_topic': not full and t in via_topic,
            'is_custom': t.is_custom,
            'active': t.active,
            'preset_model': t.preset_model or '',
            'preset_op': t.preset_op or '',
            **(t._builder_edit_payload() if t.is_custom and t.preset_json else {}),
        } for t in catalog.sorted(lambda t: (not t.is_custom, t not in direct and t not in via_topic,
                                             t.sequence, t.name))]
        topics = self._effective_topics()
        if can_edit and not full:
            topics |= self.env['ai.agent.topic'].search([('is_custom', '=', True)])

        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description or '',
            'avatar_url': f'/web/image/ai.agent/{self.id}/avatar' if self.avatar else '',
            'is_system': self.is_system,
            'can_edit': can_edit,
            'show_cost': show_cost,
            'system_prompt': self.system_prompt or '',
            'ghaima_base_instruction': self.ghaima_base_instruction or '',
            'persona': self.persona, 'persona_label': persona_sel.get(self.persona, ''),
            'locale': self.locale,
            'response_style': self.response_style,
            'model_class': self.model_class,
            'max_hops': self.max_hops,
            'max_cost_usd': self.max_cost_usd if show_cost else False,
            'allow_pii': self.allow_pii,
            'allow_write_actions': self.allow_write_actions,
            'allow_web_grounding': self.allow_web_grounding,
            'is_public': self.is_public,
            'options': {
                'persona': list(persona_sel.items()),
                'response_style': list(style_sel.items()),
                'model_class': list(model_sel.items()),
                'locale': list(locale_sel.items()),
            },
            'tools': tools,
            'skills': [{
                'id': s.id, 'name': s.name, 'icon': s.icon or 'fa-magic',
                'description': s.description or '',
                'accent': s.accent or 'blue',
                'requires_record_context': s.requires_record_context,
                'kpi_label': s.kpi_label or '',
                'code': s.code,
                'is_custom': s.is_custom,
                'is_global': s.is_global,
                'template': s.user_prompt_template or '' if can_edit else '',
                'context_model': s.context_model or '',
            } for s in self._effective_skills()],
            'full_access': full,
            'scope': {
                'surface': surface_sel.get(self.surface_ids, ''),
                'topics': [{'id': t.id, 'name': t.name, 'code': t.code,
                            'description': t.description or '',
                            'instructions': (t.instructions or '') if can_edit else '',
                            'tool_ids': t.tool_ids.ids,
                            'is_custom': t.is_custom,
                            'attached': full or t in self.topic_ids} for t in topics],
                'companies': [c.name for c in self.company_ids],
                'groups': [g.full_name for g in self.user_group_ids],
            },
            'kpis': self._console_kpis_public(show_cost),
        }

    def _console_kpis_public(self, show_cost):
        kpis = dict(self._console_kpis()[self.id])
        if not show_cost:
            for key in ('avg_cost_usd', 'total_cost_usd', 'total_tokens'):
                kpis.pop(key, None)
        return kpis

    # ── Write ──────────────────────────────────────────────────

    def console_save(self, values):
        """Apply a console edit. Whitelisted fields only; ACL enforced by
        the ORM (no sudo), so a non-designer gets an AccessError."""
        self._console_check_visible()
        if not self._console_can_edit():
            raise AccessError(_('Only AI agent designers can change agents.'))
        values = values or {}
        vals = {k: values[k] for k in CONSOLE_WRITABLE if k in values}
        if 'system_prompt' in vals and not (vals['system_prompt'] or '').strip():
            raise UserError(_('The system prompt cannot be empty.'))
        if 'max_hops' in vals:
            vals['max_hops'] = int(vals['max_hops'] or 0)
        if 'max_cost_usd' in vals and not self.env.user.has_group('base.group_system'):
            vals.pop('max_cost_usd')
        if 'max_cost_usd' in vals:
            vals['max_cost_usd'] = max(0.0, float(vals['max_cost_usd'] or 0))
        if 'tool_ids' in values:
            ids = [int(i) for i in (values.get('tool_ids') or [])]
            vals['tool_ids'] = [fields.Command.set(
                self.env['ai.agent.tool'].browse(ids).exists().ids)]
        if vals:
            self.write(vals)
        return self.console_payload()

    def open_console(self):
        """Form button: open this agent in the console."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'ab_ai_agent.console',
            'name': self.name,
            'params': {'agent_id': self.id, 'agent_code': self.code},
        }
