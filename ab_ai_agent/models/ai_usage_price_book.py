# -*- coding: utf-8 -*-
"""Phase H Part 12 — published rate book.

Local copy of what YOU charge per 1k tokens. Refreshed nightly from
the central /api/v1/ai/pricebook endpoint (when the gateway is
present). On central DBCLOUD this is the source of truth — ops
publishes rates here, the cron pushes them to every tenant.
"""
from __future__ import annotations

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AIUsagePriceBook(models.Model):
    _name = 'ai.usage.price.book'
    _description = 'Ghaima AI — Per-model pricing (provider cost + tenant-billed)'
    _order = 'effective_from desc, provider, model_name'
    _rec_name = 'model_name'

    provider = fields.Selection([
        ('openai',    'OpenAI'),
        ('google',    'Google'),
        ('anthropic', 'Anthropic'),
        ('local',     'Local'),
    ], required=True, index=True)
    model_name = fields.Char(required=True, index=True)
    model_class = fields.Selection([
        ('cheap',    'Cheap'),
        ('fast',     'Fast'),
        ('balanced', 'Balanced'),
    ], help='Routing class. The runtime uses this to translate '
            "an agent's model_class hint into a model name.")

    # Provider raw cost (what YOU pay, in USD per 1k tokens)
    provider_input_per_1k_usd = fields.Float(digits=(10, 6))
    provider_output_per_1k_usd = fields.Float(digits=(10, 6))
    provider_cached_per_1k_usd = fields.Float(digits=(10, 6))

    # Tenant-billed cost (what the tenant pays, in SAR per 1k tokens)
    billed_input_per_1k_sar = fields.Float(digits=(10, 4))
    billed_output_per_1k_sar = fields.Float(digits=(10, 4))
    billed_cached_per_1k_sar = fields.Float(digits=(10, 4))

    # Reference exchange rate at publication time (frozen, for audit)
    fx_usd_to_sar = fields.Float(
        digits=(10, 4), default=3.75,
        help='USD → SAR conversion rate used when computing billed_*. '
             'Frozen at publish time so historical rows stay consistent.')
    markup_pct = fields.Float(
        compute='_compute_markup', store=True, digits=(6, 2),
        help='(billed − provider×FX) / provider×FX × 100')

    effective_from = fields.Date(
        required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date()
    is_published = fields.Boolean(default=True, index=True)
    notes = fields.Char()

    _sql_constraints = [
        ('unique_model_effective',
         'UNIQUE(provider, model_name, effective_from)',
         "Only one price row per (provider, model, effective date)."),
    ]

    @api.depends('provider_output_per_1k_usd', 'billed_output_per_1k_sar', 'fx_usd_to_sar')
    def _compute_markup(self):
        for r in self:
            prov_sar = (r.provider_output_per_1k_usd or 0) * (r.fx_usd_to_sar or 1)
            billed = r.billed_output_per_1k_sar or 0
            r.markup_pct = round(((billed - prov_sar) / prov_sar) * 100, 2) if prov_sar else 0.0

    # ── Lookup ─────────────────────────────────────────────────

    @api.model
    def get_for(self, provider, model_name, at_date=None):
        """Return the active price row for (provider, model) at the
        given date (defaults to today). Returns an empty recordset
        when no row matches — caller is responsible for the fallback."""
        domain = [
            ('provider', '=', provider),
            ('model_name', '=', model_name),
            ('is_published', '=', True),
            ('effective_from', '<=', at_date or fields.Date.context_today(self)),
        ]
        rows = self.search(domain, order='effective_from desc', limit=1)
        return rows

    @api.model
    def estimate_cost(self, provider, model, prompt_tokens, completion_tokens,
                      cached_tokens=0):
        """Compute (USD, SAR_billable) for a call. Falls back to zero
        when no price row exists — never raises, never blocks."""
        row = self.get_for(provider, model)
        if not row:
            return 0.0, 0.0
        usd = (
            (prompt_tokens / 1000.0) * (row.provider_input_per_1k_usd or 0) +
            (completion_tokens / 1000.0) * (row.provider_output_per_1k_usd or 0) +
            (cached_tokens / 1000.0) * (row.provider_cached_per_1k_usd or 0)
        )
        sar = (
            (prompt_tokens / 1000.0) * (row.billed_input_per_1k_sar or 0) +
            (completion_tokens / 1000.0) * (row.billed_output_per_1k_sar or 0) +
            (cached_tokens / 1000.0) * (row.billed_cached_per_1k_sar or 0)
        )
        return round(usd, 6), round(sar, 4)

    # ── Nightly sync from central ──────────────────────────────

    @api.model
    def _cron_sync_pricebook(self):
        """Pull the latest published price rows from DBCLOUD. Idempotent.

        Skipped silently when no ai.client.config exists — central is
        itself responsible for editing its own rows, no sync needed."""
        try:
            config = self.env['ai.client.config'].sudo().get_config()
        except Exception:
            return
        try:
            response = config._gateway_call('/api/v1/ai/pricebook', {})
        except Exception as e:
            _logger.info('pricebook sync skipped: %s', e)
            return
        if not response or not response.get('success'):
            return
        for row in response.get('rows', []):
            existing = self.search([
                ('provider', '=', row.get('provider')),
                ('model_name', '=', row.get('model_name')),
                ('effective_from', '=', row.get('effective_from')),
            ], limit=1)
            vals = {k: row.get(k) for k in (
                'provider', 'model_name', 'model_class',
                'provider_input_per_1k_usd', 'provider_output_per_1k_usd',
                'provider_cached_per_1k_usd',
                'billed_input_per_1k_sar', 'billed_output_per_1k_sar',
                'billed_cached_per_1k_sar',
                'fx_usd_to_sar', 'effective_from', 'effective_to',
                'is_published',
            ) if k in row}
            if existing:
                existing.sudo().write(vals)
            else:
                self.sudo().create(vals)
