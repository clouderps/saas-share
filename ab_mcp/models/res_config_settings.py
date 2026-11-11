# -*- coding: utf-8 -*-
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.http import request


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mcp_enabled = fields.Boolean(string='MCP access',
                                 config_parameter='ab_ai_agent.feature.mcp.enabled')
    mcp_write_tools = fields.Boolean(string='MCP write tools',
                                     config_parameter='ab_ai_agent.feature.mcp.write_tools')
    mcp_max_calls_day = fields.Integer(string='MCP calls per day',
                                       config_parameter='ab_ai_agent.feature.mcp.max_calls_day')
    mcp_max_users = fields.Integer(string='MCP users',
                                   config_parameter='ab_ai_agent.feature.mcp.max_users')
    mcp_url = fields.Char(string='MCP URL', compute='_compute_mcp_info')
    mcp_in_plan = fields.Boolean(compute='_compute_mcp_info')
    mcp_write_in_plan = fields.Boolean(compute='_compute_mcp_info')
    mcp_effective_calls_day = fields.Integer(string='Effective daily limit', compute='_compute_mcp_info')
    mcp_status = fields.Char(string='MCP status', compute='_compute_mcp_info')
    mcp_url_host_mismatch = fields.Char(compute='_compute_mcp_info')

    @api.depends('mcp_enabled', 'mcp_write_tools', 'mcp_max_calls_day', 'mcp_max_users')
    def _compute_mcp_info(self):
        Policy = self.env['ai.feature.policy']
        ceiling = Policy._ceiling() or {}
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        seats = len(self.env['mcp.token']._seat_holder_ids())
        max_users = Policy.get('mcp.max_users')
        limit = Policy.get('mcp.max_calls_day')
        calls = self.env['mcp.usage.day'].calls_today()
        mismatch = False
        base_host = (urlsplit(base).netloc or '').lower()
        req_host = (request.httprequest.host or '').lower() if request else ''
        if req_host and base_host != req_host:
            mismatch = _('The MCP URL uses %(base)s (web.base.url) but you opened Ghaima at %(here)s. '
                         'Copied snippets will point to %(base)s.', base=base_host or '?', here=req_host)
        for s in self:
            s.mcp_url = base.rstrip('/') + '/mcp'
            s.mcp_in_plan = ceiling.get('mcp.enabled') is not False
            s.mcp_write_in_plan = ceiling.get('mcp.write_tools') is not False
            s.mcp_effective_calls_day = limit
            s.mcp_url_host_mismatch = mismatch
            s.mcp_status = _(
                'Seats used: %(seats)s / %(max)s · Calls today: %(calls)s / %(limit)s',
                seats=seats, max=max_users or _('unlimited'),
                calls=calls, limit=limit or _('unlimited'))
