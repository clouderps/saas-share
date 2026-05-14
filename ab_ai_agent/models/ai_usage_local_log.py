# -*- coding: utf-8 -*-
"""Phase H Part 12 — per-instance token meter.

Every LLM call funnels through services.llm_adapter.call_llm(); that
function writes one row here in its own savepoint so a downstream
failure (validator reject, parse error) does not lose the cost record.

This is the tenant-side billing audit. Central DBCLOUD has its own
`ai.usage.log` (source of truth); the nightly reconcile() cron
compares the two and raises an ops alert on drift > 1%.
"""
from __future__ import annotations

import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


SURFACE_SELECTION = [
    ('chat',      'Chatbot'),
    ('chatter',   'Record chatter'),
    ('composer',  'Mail / HTML composer'),
    ('scan',      'Document Scanner'),
    ('report',    'Daily Report'),
    ('dashboard', 'Dashboard'),
    ('agent',     'Agent runtime'),
    ('cron',      'Cron / background'),
    ('api',       'External API'),
    ('skill',     'Skill launcher'),
]

STATUS_SELECTION = [
    ('ok',           'OK'),
    ('error',        'Error'),
    ('quota',        'Quota exceeded'),
    ('budget',       'Local budget capped'),
    ('cost_capped',  'Per-run cost capped'),
    ('rate_limited', 'Rate limited'),
    ('sim',          'Simulation'),
]


class AIUsageLocalLog(models.Model):
    _name = 'ai.usage.local.log'
    _description = 'Ghaima AI — Per-instance LLM call audit + meter'
    _order = 'timestamp desc, id desc'
    _rec_name = 'request_id'

    # ── Correlation ────────────────────────────────────────────
    request_id = fields.Char(
        required=True, index=True, copy=False,
        help='Generated locally per call; sent to central — joins '
             'ai.usage.log.request_id on the gateway for reconciliation.')
    surface = fields.Selection(SURFACE_SELECTION, required=True, index=True)
    feature = fields.Char(index=True,
                          help='Logical feature name (e.g. "chat", "daily_report").')
    agent_id = fields.Many2one('ai.agent', ondelete='set null', index=True)
    agent_skill_id = fields.Many2one('ai.agent.skill', ondelete='set null', index=True)
    agent_run_id = fields.Many2one('ai.agent.run', ondelete='set null', index=True)
    user_id = fields.Many2one(
        'res.users', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', required=True, ondelete='restrict', index=True,
        default=lambda self: self.env.company)
    record_ref = fields.Reference(
        selection='_referenceable_models',
        help='Optional — which record the call was about.')

    # ── Provider / model ───────────────────────────────────────
    provider = fields.Char(index=True)         # 'google', 'openai', …
    model_used = fields.Char(index=True)
    model_class = fields.Char()                 # 'cheap'|'fast'|'balanced'
    routed_via = fields.Selection([
        ('gateway',  'Gateway'),
        ('direct',   'Direct'),
        ('sim',      'Simulation'),
        ('cache',    'Response cache hit'),
    ], index=True)
    cache_hit = fields.Boolean(
        index=True,
        help='G.1 cache short-circuited this call — tokens and cost are 0.')

    # ── Tokens ─────────────────────────────────────────────────
    prompt_tokens = fields.Integer(default=0)
    completion_tokens = fields.Integer(default=0)
    cached_tokens = fields.Integer(
        default=0,
        help='Provider prompt-cache (Anthropic cache_control / Gemini '
             'cachedContent) — billed cheaper than prompt_tokens.')
    web_grounding_calls = fields.Integer(
        default=0,
        help='Provider web-search tool invocations on this call.')
    audio_seconds = fields.Float(
        digits=(10, 2), default=0.0,
        help='Audio billed (Whisper / realtime sessions).')
    total_tokens = fields.Integer(compute='_compute_total', store=True)

    # ── Cost ───────────────────────────────────────────────────
    est_cost_usd = fields.Float(
        digits=(10, 6), default=0.0,
        help='Computed from local price book at request time.')
    est_cost_sar = fields.Float(
        digits=(10, 4), default=0.0,
        help='USD × FX × markup; shown to the operator in the UI.')
    est_cost_billable = fields.Float(
        digits=(10, 4), default=0.0,
        help='What the tenant pays. 0 when cache_hit or simulation.')

    # ── Timing ─────────────────────────────────────────────────
    timestamp = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True)
    duration_ms = fields.Integer()
    status = fields.Selection(
        STATUS_SELECTION, default='ok', required=True, index=True)
    error_message = fields.Text()

    # ── Reconciliation ─────────────────────────────────────────
    reconciled_with_central = fields.Boolean(index=True, default=False)
    reconciled_at = fields.Datetime()
    central_audit_id_remote = fields.Integer(
        help='ai.usage.log.id on DBCLOUD after a successful reconcile.')

    # ── Sample (PII-safe excerpt) ──────────────────────────────
    prompt_excerpt = fields.Char(
        size=200,
        help='Truncated, PII-redacted excerpt of the user prompt. For '
             'audit only — never the full prompt.')

    @api.model
    def _referenceable_models(self):
        candidates = [
            ('sale.order',     'Sale Order'),
            ('account.move',   'Invoice'),
            ('crm.lead',       'CRM Lead'),
            ('hr.employee',    'Employee'),
            ('pos.order',      'POS Order'),
            ('purchase.order', 'Purchase Order'),
            ('stock.picking',  'Stock Picking'),
        ]
        return [(m, label) for m, label in candidates if m in self.env]

    @api.depends('prompt_tokens', 'completion_tokens', 'cached_tokens')
    def _compute_total(self):
        for r in self:
            r.total_tokens = (r.prompt_tokens or 0) + \
                             (r.completion_tokens or 0) + \
                             (r.cached_tokens or 0)

    # ── Reconciliation cron ────────────────────────────────────

    @api.model
    def _cron_reconcile(self):
        """Send unreconciled rows to /api/v1/ai/usage/reconcile and
        mark each one as matched. Drift > 1 % raises an ops signal."""
        rows = self.search([('reconciled_with_central', '=', False)], limit=500)
        if not rows:
            return
        try:
            config = self.env['ai.client.config'].sudo().get_config()
        except Exception:
            _logger.info('reconcile cron skipped — gateway client unavailable')
            return
        payload = {
            'rows': [{
                'request_id': r.request_id,
                'total_tokens': r.total_tokens,
                'est_cost_usd': r.est_cost_usd,
                'feature': r.feature or '',
                'surface': r.surface,
                'timestamp': fields.Datetime.to_string(r.timestamp),
            } for r in rows],
        }
        try:
            response = config._gateway_call('/api/v1/ai/usage/reconcile', payload)
        except Exception as e:
            _logger.warning('reconcile cron call failed: %s', e)
            return
        if not response or not response.get('success'):
            return
        matched = {m['request_id']: m for m in response.get('matched', [])}
        for r in rows:
            if r.request_id in matched:
                r.sudo().write({
                    'reconciled_with_central': True,
                    'reconciled_at': fields.Datetime.now(),
                    'central_audit_id_remote': matched[r.request_id].get('central_id', 0),
                })
        drift_pct = response.get('drift_pct', 0)
        if drift_pct and drift_pct > 0.01:
            _logger.warning('AI usage drift %.2f%% — investigate', drift_pct * 100)

    # ── Local aggregates for the cost-center dashboard ─────────

    @api.model
    def usage_summary(self, period='today'):
        """Compact totals for the cost-center widget. Bypasses ORM
        for cheap aggregates — used by the live meter chip too."""
        cr = self.env.cr
        if period == 'today':
            where = "DATE(timestamp AT TIME ZONE 'UTC') = (CURRENT_DATE AT TIME ZONE 'UTC')"
        elif period == 'week':
            where = "timestamp >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '7 days'"
        elif period == 'month':
            where = "DATE_TRUNC('month', timestamp AT TIME ZONE 'UTC') = DATE_TRUNC('month', (NOW() AT TIME ZONE 'UTC'))"
        else:
            where = "TRUE"
        cr.execute(f"""
            SELECT COUNT(*) AS calls,
                   COALESCE(SUM(total_tokens), 0) AS tokens,
                   COALESCE(SUM(est_cost_usd), 0)::float AS cost_usd,
                   COALESCE(SUM(est_cost_billable), 0)::float AS cost_sar,
                   COUNT(*) FILTER (WHERE cache_hit) AS cache_hits,
                   COALESCE(SUM(est_cost_billable) FILTER (WHERE NOT cache_hit), 0)::float AS billed_sar
              FROM ai_usage_local_log
             WHERE company_id = %s
               AND {where}
        """, (self.env.company.id,))
        row = cr.fetchone() or (0, 0, 0.0, 0.0, 0, 0.0)
        return {
            'calls': int(row[0] or 0),
            'tokens': int(row[1] or 0),
            'cost_usd': float(row[2] or 0),
            'cost_sar': float(row[3] or 0),
            'cache_hits': int(row[4] or 0),
            'billed_sar': float(row[5] or 0),
            'cache_hit_rate': round(row[4] / row[0], 3) if row[0] else 0,
        }
