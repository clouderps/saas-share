# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class AiAgentAnswerCache(models.Model):
    """One remembered answer. Read and written with sudo by the cache
    service only; the key already embeds company, groups and language,
    so a row can only ever be served to a user with the same rights."""
    _name = 'ai.agent.answer.cache'
    _description = 'AI Agent Answer Cache'
    _order = 'last_hit desc, id desc'

    key = fields.Char(required=True, index=True)
    agent_id = fields.Many2one('ai.agent', ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', ondelete='cascade')
    lang = fields.Char()
    question = fields.Char()
    kind = fields.Selection([('data', 'Data (tool plan replayed)'),
                             ('howto', 'Navigation / how-to (answer reused)')], required=True)
    plan_json = fields.Text()
    envelope_json = fields.Text()
    models_touched = fields.Char()
    expires_at = fields.Datetime(required=True, index=True)
    hit_count = fields.Integer(default=0)
    last_hit = fields.Datetime()

    _sql_constraints = [('key_unique', 'unique(key)', 'One cached answer per key.')]

    @api.autovacuum
    def _gc_expired(self):
        self.sudo().search([('expires_at', '<', fields.Datetime.now() - timedelta(hours=1))]).unlink()
