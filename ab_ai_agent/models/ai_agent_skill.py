# -*- coding: utf-8 -*-
"""Phase H — ai.agent.skill.

A skill is the user-facing unit of work the agent advertises:
"Qualify this lead", "Summarise this chatter", "Compare to last
quarter". The chat UI renders skills as launcher cards; clicking
one fires the agent runtime with a templated prompt.

Skills are intentionally separate from tools — a skill can be a
zero-tool prompt ("summarise"), a one-tool prompt ("call qualifier"),
or a multi-tool plan. The agent's run loop decides the path.
"""
from __future__ import annotations

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


SURFACE_SELECTION = [
    ('chat',     'Chat (Discuss + systray)'),
    ('chatter',  'Record chatter button'),
    ('compose',  'Mail / HTML composer'),
    ('website',  'Public website'),
    ('cron',     'Background cron'),
]


class AIAgentSkill(models.Model):
    _name = 'ai.agent.skill'
    _description = 'Ghaima AI — Agent skill (user-facing action)'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True, index=True)
    code = fields.Char(required=True, index=True, copy=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    icon = fields.Char(
        default='fa-magic',
        help='FontAwesome icon code without the fa- prefix is fine too.')
    accent = fields.Selection([
        ('blue',   'Ghaima Blue'),
        ('navy',   'Ghaima Navy'),
        ('cyan',   'Ghaima Cyan'),
        ('gold',   'Gold'),
        ('green',  'Green (positive)'),
        ('rose',   'Rose (caution)'),
    ], default='blue',
        help='Accent colour for the launcher card. Pulled from Ghaima '
             'design tokens, no hex codes in templates.')

    agent_id = fields.Many2one(
        'ai.agent', ondelete='cascade', index=True,
        help='Owning agent. Empty for a shared (global) skill.')
    is_global = fields.Boolean(
        string='Shared with every agent', default=False, index=True,
        help='Offered by every agent, not only the owner.')
    is_custom = fields.Boolean(
        default=False, readonly=True, copy=False,
        help='Created from the Agent Console builder (editable / removable '
             'there). Module-shipped skills are protected.')
    context_model = fields.Char(
        help='Technical model this skill is about (optional). Passed to the '
             'prompt as {model} when no record is open.')
    surfaces = fields.Selection(
        SURFACE_SELECTION, default='chat',
        help='Where this skill appears. Chatter skills require '
             'requires_record_context.')

    # ── Prompt template ────────────────────────────────────────
    user_prompt_template = fields.Text(
        required=True, translate=True,
        help='str.format template with named placeholders. Example: '
             '"Qualify lead {lead_id}: produce a 1-100 score and a '
             '2-sentence rationale based on the partner + recent activities."')
    requires_record_context = fields.Boolean(
        default=False,
        help='When True, the skill expects {model} + {id} placeholders. '
             'The chatter button populates them; standalone chat surfaces '
             'fall back to selecting a record first.')

    # ── KPI linkage ────────────────────────────────────────────
    kpi_label = fields.Char(
        translate=True,
        help='Short label of the business KPI this skill contributes to '
             '(e.g. "Lead response time", "DSO"). Shown in the cost-center '
             'dashboard alongside the skill spend.')
    kpi_target_text = fields.Char(
        translate=True,
        help='Target description, e.g. "< 24h", "< 35 days". Operator-readable.')

    # ── Stats ──────────────────────────────────────────────────
    run_count = fields.Integer(readonly=True, default=0)
    avg_cost_usd = fields.Float(readonly=True, digits=(10, 6))
    last_run_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ('unique_code_per_agent', 'UNIQUE(agent_id, code)',
         'Skill code must be unique within an agent.'),
    ]

    @api.constrains('agent_id', 'is_global', 'code')
    def _check_owner(self):
        for skill in self:
            if not skill.agent_id and not skill.is_global:
                raise ValidationError(_(
                    "Skill '%(name)s' needs an agent or must be shared with every agent.",
                    name=skill.name))
            if skill.is_global and self.search_count([
                    ('id', '!=', skill.id), ('is_global', '=', True),
                    ('agent_id', '=', False), ('code', '=', skill.code)]):
                raise ValidationError(_(
                    "A shared skill with the code '%(code)s' already exists.",
                    code=skill.code))

    def render_prompt(self, context):
        """Apply str.format to user_prompt_template with the given
        context dict. Returns the rendered prompt. Missing placeholders
        raise UserError so the UI can surface a clear error to the
        operator."""
        self.ensure_one()
        from odoo.exceptions import UserError
        try:
            return self.user_prompt_template.format_map(_SafeDict(context or {}))
        except KeyError as e:
            raise UserError(_(
                "Skill '%(name)s' needs placeholder value: %(key)s",
                name=self.name, key=str(e),
            ))


class _SafeDict(dict):
    """KeyError-raising dict for str.format_map so missing placeholders
    surface a useful error instead of silent substitution."""
    def __missing__(self, key):
        raise KeyError(key)
