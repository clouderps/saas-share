# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    mcp_token_count = fields.Integer(compute='_compute_mcp_token_count', string='Connected AI apps')

    def _compute_mcp_token_count(self):
        Token = self.env['mcp.token']
        for user in self:
            user.mcp_token_count = Token.search_count([('user_id', '=', user.id)] + Token._live_domain())

    def write(self, vals):
        res = super().write(vals)
        if 'active' in vals and not vals['active']:
            self.env['mcp.token']._revoke_for_users(self.ids)
        return res

    def action_mcp_connect(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'mcp.connect.wizard',
            'view_mode': 'form', 'target': 'new', 'name': _('Connect an AI app'),
        }

    def action_mcp_tokens(self):
        action = self.env['ir.actions.act_window']._for_xml_id('ab_mcp.action_mcp_token_mine')
        return action

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['mcp_token_count']
