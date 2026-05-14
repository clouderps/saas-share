# -*- coding: utf-8 -*-
"""Phase H Part 12 — tenant-side budget mirror.

Pre-call guard. The runtime checks the relevant budget row BEFORE
calling the LLM; if the scope is exhausted the call short-circuits
with a BUDGET_EXCEEDED_LOCAL envelope. Saves a round-trip and
gives the user a clear error chip with a CTA.

Central `ai.tenant.budget` (ab_ai_gateway) stays as the canonical
limit; this is a UX speed layer.
"""
from __future__ import annotations

from datetime import date

from odoo import api, fields, models


SCOPE_SELECTION = [
    ('company', 'Company-wide'),
    ('user',    'Per user'),
    ('agent',   'Per agent'),
    ('surface', 'Per surface'),
]


class AIUsageLocalBudget(models.Model):
    _name = 'ai.usage.local.budget'
    _description = 'Ghaima AI — Local pre-call budget guard'
    _order = 'scope, sequence'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        'res.company', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env.company)

    scope = fields.Selection(SCOPE_SELECTION, default='company', required=True)
    user_id = fields.Many2one('res.users', ondelete='cascade')
    agent_id = fields.Many2one('ai.agent', ondelete='cascade')
    surface = fields.Char()

    daily_sar = fields.Float(digits=(10, 4), default=0.0,
                             help='0 = unlimited')
    monthly_sar = fields.Float(digits=(10, 4), default=0.0,
                               help='0 = unlimited')
    warn_at = fields.Float(default=0.8,
                           help='Warning threshold as a fraction (0.8 = 80%).')
    enforce = fields.Boolean(default=True,
                             help='False = soft-warn only; True = block at 100%.')

    used_today_sar = fields.Float(compute='_compute_used',
                                  digits=(10, 4))
    used_month_sar = fields.Float(compute='_compute_used',
                                  digits=(10, 4))
    remaining_daily_sar = fields.Float(compute='_compute_remaining',
                                       digits=(10, 4))
    remaining_monthly_sar = fields.Float(compute='_compute_remaining',
                                         digits=(10, 4))
    state = fields.Selection([
        ('ok',      'OK'),
        ('warn',    'Warn'),
        ('blocked', 'Blocked'),
    ], compute='_compute_remaining', store=False)

    # ── Compute ────────────────────────────────────────────────

    def _compute_used(self):
        for b in self:
            domain = [('company_id', '=', b.company_id.id)]
            if b.scope == 'user' and b.user_id:
                domain.append(('user_id', '=', b.user_id.id))
            elif b.scope == 'agent' and b.agent_id:
                domain.append(('agent_id', '=', b.agent_id.id))
            elif b.scope == 'surface' and b.surface:
                domain.append(('surface', '=', b.surface))
            today = fields.Date.context_today(b)
            month_start = today.replace(day=1)
            Log = b.env['ai.usage.local.log'].sudo()
            day_rows = Log.search(domain + [('timestamp', '>=', str(today))])
            month_rows = Log.search(domain + [('timestamp', '>=', str(month_start))])
            b.used_today_sar = sum(day_rows.mapped('est_cost_billable'))
            b.used_month_sar = sum(month_rows.mapped('est_cost_billable'))

    def _compute_remaining(self):
        for b in self:
            daily_left = (b.daily_sar - b.used_today_sar) if b.daily_sar else 10**9
            monthly_left = (b.monthly_sar - b.used_month_sar) if b.monthly_sar else 10**9
            b.remaining_daily_sar = max(0, daily_left)
            b.remaining_monthly_sar = max(0, monthly_left)
            tightest = min(daily_left, monthly_left)
            tightest_cap = min(b.daily_sar or 10**9, b.monthly_sar or 10**9)
            ratio = 1 - (tightest / tightest_cap) if tightest_cap else 0
            if tightest <= 0:
                b.state = 'blocked'
            elif ratio >= b.warn_at:
                b.state = 'warn'
            else:
                b.state = 'ok'

    # ── Pre-call check used by the runtime ─────────────────────

    @api.model
    def check(self, env, agent=None, surface=None, user=None):
        """Aggregate every applicable budget row into a single decision.

        Returns ``{'allow': bool, 'state': 'ok'|'warn'|'blocked',
        'reason': str, 'remaining_sar': float}``."""
        company = env.company
        user = user or env.user
        domain = [
            ('active', '=', True),
            ('company_id', '=', company.id),
            ('enforce', '=', True),
            '|', '|', '|',
                ('scope', '=', 'company'),
                '&', ('scope', '=', 'user'), ('user_id', '=', user.id),
                '&', ('scope', '=', 'agent'), ('agent_id', '=', agent.id if agent else 0),
                '&', ('scope', '=', 'surface'), ('surface', '=', surface or ''),
        ]
        budgets = self.search(domain)
        if not budgets:
            return {'allow': True, 'state': 'ok', 'reason': '', 'remaining_sar': -1}
        worst = 'ok'
        worst_reason = ''
        worst_remaining = 10**9
        for b in budgets:
            if b.state == 'blocked':
                return {
                    'allow': False, 'state': 'blocked',
                    'reason': 'Budget exhausted for scope %s' % b.scope,
                    'remaining_sar': 0,
                }
            if b.state == 'warn' and worst != 'warn':
                worst = 'warn'
                worst_reason = 'Approaching limit on scope %s' % b.scope
            worst_remaining = min(worst_remaining, b.remaining_daily_sar)
        return {
            'allow': True, 'state': worst, 'reason': worst_reason,
            'remaining_sar': worst_remaining if worst_remaining < 10**9 else -1,
        }
