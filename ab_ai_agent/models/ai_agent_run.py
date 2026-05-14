# -*- coding: utf-8 -*-
"""Phase H — ai.agent.run.

One row per agent invocation. Immutable after `state` moves to a
terminal value (done / error / cost_capped / maxhops). The runtime
writes this row at the start of the run, updates state as it
progresses, and stamps the final outcome.

This is the audit + replay + cost-charge-back source of truth on the
tenant side. `ai.usage.local.log` stores the lower-level per-call
metering rows (one ai.agent.run can have several local-log rows).
"""
from __future__ import annotations

import json

from odoo import api, fields, models, _


STATE_SELECTION = [
    ('planning',     'Planning'),
    ('tool',         'Running tool'),
    ('reflect',      'Reflecting'),
    ('done',         'Done'),
    ('maxhops',      'Max hops reached'),
    ('cost_capped',  'Cost cap hit'),
    ('budget',       'Budget exceeded'),
    ('error',        'Error'),
    ('cancelled',    'Cancelled'),
]


class AIAgentRun(models.Model):
    _name = 'ai.agent.run'
    _description = 'Ghaima AI — Agent invocation audit row'
    _order = 'started_at desc, id desc'
    _rec_name = 'question'

    # Identity
    # ondelete='restrict' because audit rows must outlive agent deletes —
    # operators archive an agent (active=False) instead of removing it
    # so its run history stays auditable. Skill is optional; setting
    # set null is fine since the run can survive without it.
    agent_id = fields.Many2one(
        'ai.agent', required=True, ondelete='restrict', index=True)
    skill_id = fields.Many2one('ai.agent.skill', ondelete='set null', index=True)
    user_id = fields.Many2one(
        'res.users', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env.company)

    # Context
    surface = fields.Selection([
        ('chat',     'Chat'),
        ('chatter',  'Record chatter'),
        ('compose',  'Composer'),
        ('skill',    'Skill launcher'),
        ('website',  'Public website'),
        ('cron',     'Cron'),
        ('api',      'External API'),
    ], default='chat', required=True, index=True)
    record_ref = fields.Reference(
        selection=lambda self: self._referenceable_models(),
        help='Optional record the agent was working on.')
    conversation_id = fields.Char(
        index=True,
        help='Loose pointer (model+id or chat conv id). String so this '
             'module has no hard dep on ab_ai_chatbot.')

    # Conversation
    question = fields.Text(required=True)
    response = fields.Text()
    state = fields.Selection(STATE_SELECTION, default='planning', required=True, index=True)
    error_message = fields.Text()

    # Execution stats
    hops = fields.Integer(default=0)
    tool_calls_json = fields.Text(
        help='Truncated JSON: list of {tool, args, ok, duration_ms}.')
    cost_usd = fields.Float(digits=(10, 6), default=0.0)
    cost_sar = fields.Float(digits=(10, 4), default=0.0)
    prompt_tokens = fields.Integer(default=0)
    completion_tokens = fields.Integer(default=0)
    cached_tokens = fields.Integer(default=0)
    total_tokens = fields.Integer(compute='_compute_total', store=True)
    model_used = fields.Char()
    provider_used = fields.Char()
    routed_via = fields.Selection([
        ('gateway', 'Central Gateway'),
        ('direct',  'Direct Provider'),
        ('sim',     'Simulation'),
        ('cache',   'Response Cache (G.1)'),
    ])

    # Quality
    verdict = fields.Selection([
        ('verified',         'Verified'),
        ('partial',          'Partial'),
        ('unverified',       'Unverified'),
        ('policy_violation', 'Policy Violation'),
    ], help='Output from the validator (no-apology rule, citation check, etc.).')
    feedback = fields.Selection([
        ('up',   'Thumbs up'),
        ('down', 'Thumbs down'),
    ], help='User-supplied rating after the run.')
    feedback_note = fields.Text()

    # Timing
    started_at = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True)
    finished_at = fields.Datetime()
    latency_ms = fields.Integer()

    # ── Compute ────────────────────────────────────────────────

    @api.depends('prompt_tokens', 'completion_tokens', 'cached_tokens')
    def _compute_total(self):
        for run in self:
            run.total_tokens = (run.prompt_tokens or 0) + \
                               (run.completion_tokens or 0) + \
                               (run.cached_tokens or 0)

    @api.model
    def _referenceable_models(self):
        """Models that can be a record_ref target. Defensive — only
        return models the tenant actually has installed."""
        candidates = [
            ('sale.order',         'Sale Order'),
            ('account.move',       'Invoice / Journal'),
            ('crm.lead',           'CRM Lead'),
            ('hr.employee',        'Employee'),
            ('pos.order',          'POS Order'),
            ('purchase.order',     'Purchase Order'),
            ('stock.picking',      'Stock Picking'),
            ('mail.thread',        'Discussion'),
        ]
        return [(m, label) for m, label in candidates if m in self.env]

    # ── State helpers ──────────────────────────────────────────

    def finalize(self, *, state, response=None, error=None, latency_ms=None,
                 tool_calls=None):
        """Move the run to a terminal state. Best-effort — never raises."""
        self.ensure_one()
        vals = {'state': state, 'finished_at': fields.Datetime.now()}
        if response is not None:
            vals['response'] = response
        if error is not None:
            vals['error_message'] = error
        if latency_ms is not None:
            vals['latency_ms'] = latency_ms
        if tool_calls is not None:
            try:
                vals['tool_calls_json'] = json.dumps(tool_calls, default=str)[:50000]
            except Exception:
                pass
        try:
            self.sudo().write(vals)
        except Exception:
            pass
        return self

    def rate(self, feedback, note=None):
        """User rating from the chat UI. -1 / +1 maps to down / up."""
        self.ensure_one()
        rating = 'up' if (feedback in (1, '1', 'up', True)) else 'down'
        self.sudo().write({'feedback': rating, 'feedback_note': note or ''})
        return True

    # ── ACL ────────────────────────────────────────────────────
    # Regular users see their own runs; AI managers see company-wide.
    # Enforced via record rules in security.xml.
