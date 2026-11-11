# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.mcp_token import CLIENT_SELECTION, PRESET_SELECTION


class McpConnectWizard(models.TransientModel):
    _name = 'mcp.connect.wizard'
    _description = 'Ghaima MCP — Connect an AI app'
    # The plaintext token is NEVER written to the row: token / snippet are
    # non-stored and only travel in the context of the "result" dialog
    # (a new, unsaved record), so closing it by any means leaves nothing.
    _transient_max_hours = 0.25

    client = fields.Selection(CLIENT_SELECTION, required=True, default='claude_desktop')
    name = fields.Char(required=True, default=lambda self: _('My AI app'))
    expiry_days = fields.Selection([('30', '30 days'), ('90', '90 days'), ('365', '1 year')],
                                   string='Expires after', required=True, default='90')
    preset = fields.Selection(PRESET_SELECTION, required=True, default='readonly')
    tool_ids = fields.Many2many('ai.agent.tool', string='Tools', domain=[('mcp_enabled', '=', True)])
    allow_write = fields.Boolean(string='Allow write tools')
    write_available = fields.Boolean(compute='_compute_write_available')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft')
    token = fields.Char(readonly=True, store=False)
    mcp_url = fields.Char(string='MCP URL', readonly=True, default=lambda self: self._mcp_url())
    config_snippet = fields.Text(string='Configuration', readonly=True, store=False)

    @api.model
    def _mcp_url(self):
        return self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/') + '/mcp'

    @api.depends('preset')
    def _compute_write_available(self):
        allowed = bool(self.env['ai.feature.policy'].get('mcp.write_tools'))
        for w in self:
            w.write_available = allowed

    @api.model
    def _snippet(self, client, url, token):
        if client == 'claude_code':
            return ('claude mcp add --transport http ghaima %s '
                    '--header "Authorization: Bearer %s"') % (url, token)
        if client == 'claude_desktop':
            # claude_desktop_config.json only runs stdio servers: bridge the
            # remote endpoint through mcp-remote. The bearer value goes via
            # env so the space in "Bearer <token>" survives arg splitting.
            return json.dumps({'mcpServers': {'ghaima': {
                'command': 'npx',
                'args': ['-y', 'mcp-remote', url, '--header', 'Authorization:${GHAIMA_AUTH}'],
                'env': {'GHAIMA_AUTH': 'Bearer %s' % token},
            }}}, indent=2)
        server = {'url': url, 'headers': {'Authorization': 'Bearer %s' % token}}
        if client == 'vscode':
            return json.dumps({'servers': {'ghaima': dict(server, type='http')}}, indent=2)
        return json.dumps({'mcpServers': {'ghaima': server}}, indent=2)

    def action_generate(self):
        self.ensure_one()
        if not self.env['ai.feature.policy'].get('mcp.enabled'):
            raise UserError(_('MCP access is turned off or not included in your plan.'))
        Token = self.env['mcp.token']
        _rec, plain = Token._generate({
            'name': self.name, 'client': self.client, 'preset': self.preset,
            'tool_ids': [(6, 0, self.tool_ids.ids)],
            'allow_write': self.allow_write and self.write_available,
            'expires_at': Token.default_expiry(self.expiry_days),
        })
        url = self._mcp_url()
        # Result dialog = a NEW unsaved record filled from defaults: the
        # secret lives only in this action's context / the browser.
        ctx = {k: v for k, v in self.env.context.items() if not k.startswith('default_')}
        ctx.update({
            'default_state': 'done', 'default_client': self.client, 'default_name': self.name,
            'default_preset': self.preset, 'default_expiry_days': self.expiry_days,
            'default_mcp_url': url, 'default_token': plain,
            'default_config_snippet': self._snippet(self.client, url, plain),
        })
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'new',
                'name': _('Connect an AI app'), 'context': ctx}

    def action_done(self):
        """Close the dialog (kept for old clients; nothing secret is stored)."""
        return {'type': 'ir.actions.act_window_close'}
