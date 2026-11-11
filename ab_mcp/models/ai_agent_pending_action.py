# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import _, api, fields, models

TTL = timedelta(minutes=15)


class AIAgentPendingAction(models.Model):
    _inherit = 'ai.agent.pending.action'

    expires_at = fields.Datetime(compute='_compute_expires_at')
    target_model_display = fields.Char(string='Target model', compute='_compute_details')
    details_text = fields.Text(string='Details', compute='_compute_details')

    @api.model_create_multi
    def create(self, vals_list):
        # create_record proposals have no target yet: record the model the
        # record WILL be created in, so the inbox can show it.
        for vals in vals_list:
            if not vals.get('target_model') and vals.get('args_json'):
                model = self._args(vals['args_json']).get('model')
                if isinstance(model, str) and model in self.env:
                    vals['target_model'] = model
        return super().create(vals_list)

    @api.model
    def _args(self, raw):
        try:
            data = json.loads(raw or '{}')
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @api.model
    def _details_lines(self, data, prefix=''):
        lines = []
        for key, value in data.items():
            label = '%s%s' % (prefix, key)
            if isinstance(value, dict):
                lines += self._details_lines(value, label + ' / ')
            elif isinstance(value, list):
                if value and all(isinstance(v, dict) for v in value):
                    for i, item in enumerate(value, 1):
                        lines.append('%s %s: %s' % (label, i, ', '.join(
                            '%s: %s' % (k, v) for k, v in item.items())))
                else:
                    lines.append('%s: %s' % (label, ', '.join(str(v) for v in value)))
            else:
                lines.append('%s: %s' % (label, '' if value is None else value))
        return lines

    @api.depends('args_json', 'target_model')
    def _compute_details(self):
        for row in self:
            model = row.target_model or ''
            if model and model in self.env:
                model = self.env['ir.model']._get(model).name or model
            row.target_model_display = model
            row.details_text = '\n'.join(self._details_lines(self._args(row.args_json)))

    @api.depends('create_date')
    def _compute_expires_at(self):
        for row in self:
            row.expires_at = row.create_date and row.create_date + TTL

    @api.model
    def _mcp_origin_allowed(self, row):
        if not super()._mcp_origin_allowed(row):
            return False
        Token = self.env['mcp.token']
        # sudo: token rows are the caller's own; existence check only.
        return bool(Token.sudo().search_count(
            [('user_id', '=', self.env.uid), ('allow_write', '=', True)] + Token._live_domain(),
            limit=1))

    def _mcp_decide(self, confirm):
        self.ensure_one()
        out = self.resolve(self.key, confirm)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if out.get('ok') else 'warning',
                'message': str(out.get('message') or ''),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_mcp_confirm(self):
        return self._mcp_decide(True)

    def action_mcp_reject(self):
        return self._mcp_decide(False)

    def _mcp_status(self):
        self.ensure_one()
        state = self.state
        if state == 'proposed' and self.create_date and fields.Datetime.now() - self.create_date > TTL:
            state = 'expired'
        return {
            'key': self.key,
            'state': state,
            'summary': self.summary or '',
            'tool': self.tool_code,
            'origin': self.origin,
            'expires_at': fields.Datetime.to_string(self.expires_at) if self.expires_at else None,
            'error': self.error or None,
        }
