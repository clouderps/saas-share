# -*- coding: utf-8 -*-
"""Read-only exposure of the locked Ghaima base instruction and the
website-reference refresh. The base text itself is file-only (see
services/ghaima_base.py): the field below is computed, not stored and
has no inverse, so no UI, console or RPC write can change it."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..services import ghaima_base


class AIAgentGhaima(models.Model):
    _inherit = 'ai.agent'

    ghaima_base_instruction = fields.Text(
        string='Ghaima Base Instructions',
        compute='_compute_ghaima_base_instruction', store=False, readonly=True,
        help='Set by Ghaima and applied before every agent prompt. '
             'Locked: changes only ship with a module update.')

    def _compute_ghaima_base_instruction(self):
        text = ghaima_base.base_instruction()
        for agent in self:
            agent.ghaima_base_instruction = text

    @api.model
    def _cron_refresh_ghaima_website(self):
        ghaima_base.refresh_website_excerpt(self.env)

    def action_refresh_ghaima_website(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only administrators can refresh the website knowledge.'))
        ok = ghaima_base.refresh_website_excerpt(self.env)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success' if ok else 'warning',
                'message': _('Website knowledge refreshed from ghaima.sa.') if ok else
                _('Could not reach ghaima.sa; the built-in website knowledge is still used.'),
            },
        }
