# -*- coding: utf-8 -*-
"""Phase H — ai.agent persona.

An agent is the user-facing personality + the operator-tuneable
behaviour bundle. The runtime (services/runtime.py) reads its
system_prompt, topic_ids, tool_ids, source_ids, and cost guardrails
on every invocation. Vertical modules (CRM, accounting, POS) seed
their own agents via data XML.
"""
from __future__ import annotations

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


PERSONA_SELECTION = [
    ('assistant', 'Assistant'),
    ('analyst',   'Analyst'),
    ('coach',     'Coach'),
    ('bot',       'Bot'),
    ('extractor', 'Extractor'),
]

RESPONSE_STYLE_SELECTION = [
    ('analytical', 'Analytical (low temperature)'),
    ('balanced',   'Balanced (default)'),
    ('creative',   'Creative (high temperature)'),
]

# Maps style → temperature. Mirrors Odoo 19 native conventions.
TEMPERATURE_MAP = {
    'analytical': 0.2,
    'balanced':   0.5,
    'creative':   0.8,
}

MODEL_CLASS_SELECTION = [
    ('cheap',    'Cheap (lite — short replies)'),
    ('fast',     'Fast (default for chat)'),
    ('balanced', 'Balanced (compare / forecast / report)'),
]


class AIAgent(models.Model):
    _name = 'ai.agent'
    _description = 'Ghaima AI — Agent persona'
    _order = 'sequence, name'
    _rec_name = 'name'

    # ── Identity ───────────────────────────────────────────────
    name = fields.Char(required=True, translate=True, index=True)
    code = fields.Char(
        required=True, index=True, copy=False,
        help='Stable identifier (e.g. ghaima_assistant). Used by the '
             'runtime to look up the agent and by data XML to seed personas.')
    persona = fields.Selection(PERSONA_SELECTION, default='assistant', required=True)
    description = fields.Text(translate=True)
    avatar = fields.Image(max_width=256, max_height=256)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, index=True)

    # ── Behaviour ──────────────────────────────────────────────
    system_prompt = fields.Text(translate=True, required=True)
    locale = fields.Selection([
        ('ar', 'Arabic'),
        ('en', 'English'),
        ('both', 'Both / auto-detect'),
    ], default='both', required=True)
    response_style = fields.Selection(
        RESPONSE_STYLE_SELECTION, default='balanced', required=True)
    model_class = fields.Selection(
        MODEL_CLASS_SELECTION, default='fast', required=True,
        help='Hint passed to the gateway. Cheap/fast/balanced maps to '
             'provider-specific models (Gemini: flash-lite / 2.5-flash / 2.5-pro).')
    max_hops = fields.Integer(
        default=6,
        help='Hard cap on tool-calling rounds per run. Prevents infinite '
             'loops when the model misuses tools.')
    max_cost_usd = fields.Float(
        digits=(10, 4), default=0.10,
        help='Per-run USD ceiling. Run aborts with cost_capped state once '
             'accumulated usage exceeds this value. 0 = unlimited.')
    allow_pii = fields.Boolean(
        default=False,
        help='When True, the guardrails service skips PII redaction for '
             'this agent. Required for agents that must see real customer '
             'data (e.g. AR Chaser drafting personalised emails).')
    allow_write_actions = fields.Boolean(
        default=False,
        help='Required for tools that mutate data. The chip-driven '
             'two-phase confirmation flow still applies on top.')
    allow_web_grounding = fields.Boolean(
        default=False,
        help='Allow the agent to use provider web-search tools (OpenAI '
             'web_search_preview / Gemini google_search). Adds cost.')
    is_system = fields.Boolean(
        default=False, readonly=True,
        help='System agents cannot be deleted from the UI — only ops '
             'with super-user rights can remove them.')

    # ── Capability bundles ─────────────────────────────────────
    topic_ids = fields.Many2many(
        'ai.agent.topic', 'ai_agent_topic_rel', 'agent_id', 'topic_id',
        string='Topics',
        help='A topic bundles related instructions and tools. The agent '
             'receives the union of every selected topic.')
    tool_ids = fields.Many2many(
        'ai.agent.tool', 'ai_agent_tool_rel', 'agent_id', 'tool_id',
        string='Direct Tools',
        help='Tools attached directly to this agent (outside of any topic).')
    all_tool_ids = fields.Many2many(
        'ai.agent.tool', compute='_compute_all_tool_ids',
        help='Direct tools + every tool reachable via topics. The runtime '
             'consults this set, not tool_ids alone.')
    skill_ids = fields.One2many(
        'ai.agent.skill', 'agent_id', string='Skills',
        help='User-facing actions: "Qualify this lead", "Draft reply", '
             '"Compare to last quarter". Shown in the chat skill panel.')

    # ── Distribution / surfaces ────────────────────────────────
    surface_ids = fields.Selection([
        ('chat',     'Chatbot (Discuss)'),
        ('chatter',  'Chatter (record forms)'),
        ('composer', 'Mail / HTML composer'),
        ('website',  'Public website'),
        ('cron',     'Cron / background'),
        ('all',      'All surfaces'),
    ], string='Primary Surface', default='chat')
    is_public = fields.Boolean(
        default=False,
        help='Exposed on the public website widget. Public agents have '
             'their cost charged to the company and runs go through a '
             'dedicated rate-limited code path.')
    company_ids = fields.Many2many(
        'res.company', 'ai_agent_company_rel', 'agent_id', 'company_id',
        default=lambda self: self.env.companies,
        string='Allowed Companies',
        help='Empty = available to every company; restricted otherwise.')
    user_group_ids = fields.Many2many(
        'res.groups', 'ai_agent_group_rel', 'agent_id', 'group_id',
        string='Allowed User Groups',
        help='Empty = every internal user can invoke this agent.')

    # ── Stats (computed by daily cron) ─────────────────────────
    run_count = fields.Integer(readonly=True, default=0)
    last_run_at = fields.Datetime(readonly=True)
    success_rate = fields.Float(
        readonly=True, digits=(5, 2),
        help='% of runs in the last 30 days that ended in state=done.')
    avg_cost_usd = fields.Float(
        readonly=True, digits=(10, 6),
        help='Average cost per successful run, last 30 days.')
    total_cost_30d_usd = fields.Float(readonly=True, digits=(10, 6))

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)',
         'Agent code must be unique across the database.'),
    ]

    # ── Compute ────────────────────────────────────────────────

    @api.depends('topic_ids.tool_ids', 'tool_ids')
    def _compute_all_tool_ids(self):
        for agent in self:
            tools = agent.tool_ids
            for topic in agent.topic_ids:
                tools |= topic.tool_ids
            agent.all_tool_ids = tools

    @api.model
    def _heal_core_topics(self):
        """Attach topics the assistant must always have, on every -u.

        The seed file declares ``noupdate="0"``, but the deployed
        ir_model_data row for agent_ghaima_assistant carries
        noupdate=True — so an upgrade silently skips the agent record
        and a newly-shipped topic never reaches existing tenants. That
        is invisible: the tools install fine, the topic installs fine,
        and the assistant just never gains the capability.

        Adding the link here instead of fighting the flag keeps
        ops-level edits to the prompt intact (the reason the flag was
        set) while still guaranteeing capability rollout. Purely
        additive and idempotent — it never removes a topic an operator
        attached by hand.
        """
        agent = self.search([('code', '=', 'ghaima_assistant')], limit=1)
        if not agent:
            return False
        # Any module can opt a topic in by setting auto_attach — the core
        # does not need to know the topic exists. That is what lets a
        # bridge (ab_ai_command, and whatever ships next) deliver a
        # capability to tenants that already exist.
        wanted = self.env['ai.agent.topic'].search([
            '|', ('auto_attach', '=', True),
            ('code', 'in', ['system_guidance'])])
        missing = wanted - agent.topic_ids
        if missing:
            agent.topic_ids = [(4, t.id) for t in missing]
            _logger.info(
                "ai.agent: attached %s to %s",
                ', '.join(missing.mapped('code')), agent.code)
        return True

    # ── Constraints ────────────────────────────────────────────

    @api.constrains('max_hops')
    def _check_max_hops(self):
        for agent in self:
            if agent.max_hops < 1 or agent.max_hops > 20:
                raise ValidationError(_(
                    'max_hops must be between 1 and 20 (got %s).'
                ) % agent.max_hops)

    @api.constrains('active')
    def _check_single_active_chat_default(self):
        """Business rule (refined):

        Tenants can have many active agents — one per persona/surface
        (Chatbot Assistant, Manager Bot, Document Extractor, …).
        What CAN'T coexist is two active agents with the same `code`
        prefix targeting the same default chat surface — that would
        be ambiguous when ai.chat.conversation._default_agent_id()
        runs. The seeded system agent (code='ghaima_assistant') is
        always the chat-surface default; everything else uses
        explicit surface targeting.

        Central (DBCLOUD): unconstrained — any number of agents in
        any combination.
        """
        if 'ai.gateway.service' in self.env:
            return
        # Allow many actives. The legacy strict rule blocked vertical
        # agent modules (ab_manager_agents, ab_crm_agents, …) from
        # ever being active on a tenant. Replaced with a soft rule
        # below — no error, just keep the chat-surface default unique.
        for agent in self:
            if not agent.active or agent.surface_ids != 'chat' or agent.code == 'ghaima_assistant':
                continue
            # Non-system agent claiming the chat surface — that's fine
            # as long as it doesn't share the system agent's code.
            if agent.code == 'ghaima_assistant':
                raise ValidationError(_(
                    "The code 'ghaima_assistant' is reserved for the system agent."
                ))

    @api.ondelete(at_uninstall=False)
    def _unlink_system(self):
        if any(agent.is_system for agent in self):
            raise UserError(_(
                'System agents cannot be deleted. Archive them instead by '
                'unchecking the Active field.'
            ))

    # ── Helpers used by the runtime ────────────────────────────

    @api.model
    def get_default(self):
        """Return the catch-all system agent (Ghaima Assistant).

        Falls back to the first active agent when the seed is missing
        (defensive — never raises). The runtime calls this when a
        consumer doesn't pin a specific agent."""
        ref = self.env.ref('ab_ai_agent.agent_ghaima_assistant',
                           raise_if_not_found=False)
        if ref and ref.active:
            return ref
        return self.search([('active', '=', True)], limit=1)

    @api.model
    def get_by_code(self, code):
        """Resolve agent by stable code. Returns empty recordset when
        the code is unknown — caller decides whether to fall back."""
        if not code:
            return self.browse()
        return self.search([('code', '=', code), ('active', '=', True)], limit=1)

    def temperature(self):
        """Map response_style → numeric temperature for the LLM call."""
        self.ensure_one()
        return TEMPERATURE_MAP.get(self.response_style, 0.5)

    def is_visible_to(self, user):
        """Per-agent visibility check used by the chat picker. Returns
        True when the agent is in scope for the given user (company +
        group membership)."""
        self.ensure_one()
        if self.company_ids and user.company_id not in self.company_ids:
            return False
        if self.user_group_ids and not (self.user_group_ids & user.groups_id):
            return False
        return True

    def open_chat(self):
        """Action: open the agent's chat surface (used by the agent
        list view 'Open' button). The OWL service intercepts."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'ab_ai_agent.open_chat',
            'params': {'agent_id': self.id, 'agent_code': self.code},
        }

    # ── Stats refresh (cron-driven) ────────────────────────────

    @api.model
    def _cron_refresh_stats(self):
        """Aggregate ai.agent.run rows from the last 30 days into the
        denormalised stats fields. Called once per day."""
        cr = self.env.cr
        cr.execute("""
            SELECT agent_id,
                   COUNT(*) AS runs,
                   COUNT(*) FILTER (WHERE state = 'done') AS done,
                   MAX(finished_at) AS last,
                   AVG(cost_usd) FILTER (WHERE state = 'done') AS avg_cost,
                   SUM(cost_usd) AS total_cost
              FROM ai_agent_run
             WHERE create_date > (NOW() AT TIME ZONE 'UTC') - INTERVAL '30 days'
               AND agent_id IS NOT NULL
          GROUP BY agent_id
        """)
        for agent_id, runs, done, last, avg_cost, total_cost in cr.fetchall():
            agent = self.browse(agent_id)
            if not agent.exists():
                continue
            agent.sudo().write({
                'run_count': runs,
                'last_run_at': last,
                'success_rate': round((done / runs) * 100, 2) if runs else 0,
                'avg_cost_usd': avg_cost or 0.0,
                'total_cost_30d_usd': total_cost or 0.0,
            })
