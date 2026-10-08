# -*- coding: utf-8 -*-
"""Make hr.leave requestable by command — for the requester only.

The employee is never taken from the input: a command files time off for
the user's own employee, so "request leave for Ahmed" cannot be used to
book someone else's days. HR officers book for others from the Time Off
screen, where the employee field is in front of them.
"""
from odoo import _, api, models
from odoo.exceptions import UserError


class HrLeave(models.Model):
    _name = 'hr.leave'
    _inherit = ['hr.leave', 'ai.command.mixin']

    @api.model
    def _ai_command_spec(self):
        return {
            'holiday_status_id': {
                'aliases': ['type', 'leave type', 'time off type', 'kind',
                            'نوع', 'النوع', 'نوع الإجازة', 'نوع الاجازة'],
                'resolver': 'many2one', 'required': True, 'label': 'Time Off Type',
            },
            'request_date_from': {
                'aliases': ['from', 'start', 'date', 'on', 'day',
                            'من', 'تاريخ', 'يوم', 'بداية', 'من تاريخ'],
                'resolver': 'date', 'required': True, 'label': 'From',
            },
            'request_date_to': {
                'aliases': ['to', 'until', 'end', 'إلى', 'الى', 'حتى', 'نهاية', 'إلى تاريخ'],
                'resolver': 'date', 'label': 'To',
            },
            'private_name': {
                'aliases': ['reason', 'description', 'note', 'سبب', 'السبب', 'ملاحظة', 'الوصف'],
                'resolver': 'text', 'label': 'Reason',
            },
        }

    @api.model
    def _ai_command_create(self, values):
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_('Your user is not linked to an employee, so time off '
                              'cannot be requested for you. Ask HR to link it.'))
        values = dict(values, employee_id=employee.id)
        values.setdefault('request_date_to', values.get('request_date_from'))
        return super()._ai_command_create(values)

    @api.model
    def _ai_command_preview_fields(self):
        return ['employee_id', 'holiday_status_id', 'request_date_from',
                'request_date_to', 'number_of_days', 'private_name']
