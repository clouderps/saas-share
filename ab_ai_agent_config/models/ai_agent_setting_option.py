# -*- coding: utf-8 -*-
from odoo import api, fields, models

KINDS = ('boolean', 'selection', 'many2one')


class AiAgentSettingOption(models.Model):
    """One setting the assistant may change. The whitelist IS the
    security model: a setting absent from here cannot be reached, however
    the request is phrased."""
    _name = 'ai.agent.setting.option'
    _description = 'AI Agent Setting Option'
    _order = 'sequence, id'

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    field_name = fields.Char(required=True,
                             help='Field on res.config.settings that holds the setting.')
    group_id = fields.Many2one('res.groups',
                               help='Extra group required, on top of Settings administrator.')
    warning = fields.Text(translate=True,
                          help='Shown on the confirmation card, e.g. side effects.')
    available = fields.Boolean(compute='_compute_available')

    _sql_constraints = [('code_unique', 'unique(code)', 'Option codes are unique.')]

    @api.depends('field_name')
    def _compute_available(self):
        Settings = self.env['res.config.settings']
        for opt in self:
            field = Settings._fields.get(opt.field_name or '')
            opt.available = bool(field and field.type in KINDS)

    @api.model
    def options_for_user(self, user=None):
        """Options this user may change on this database."""
        user = user or self.env.user
        if not user.has_group('base.group_system'):
            return self.browse()
        return self.search([]).filtered(
            lambda o: o.available and (not o.group_id or o.group_id in user.groups_id))
