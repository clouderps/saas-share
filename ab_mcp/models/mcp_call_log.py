# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class McpCallLog(models.Model):
    _name = 'mcp.call.log'
    _description = 'Ghaima MCP — Call log (no content)'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', readonly=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', readonly=True, index=True)
    token_id = fields.Many2one('mcp.token', readonly=True, ondelete='set null')
    tool_code = fields.Char(readonly=True, index=True)
    client = fields.Char(readonly=True)
    ok = fields.Boolean(readonly=True)
    error_kind = fields.Char(readonly=True)
    duration_ms = fields.Integer(readonly=True)
    request_id = fields.Char(readonly=True)
    args_hash = fields.Char(readonly=True, help='SHA-256 of the arguments; the arguments are not stored.')

    @api.autovacuum
    def _gc_old_calls(self):
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=90))]).unlink()
