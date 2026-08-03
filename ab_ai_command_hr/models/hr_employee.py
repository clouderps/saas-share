# -*- coding: utf-8 -*-
"""Make hr.employee creatable by command.

Scope is deliberately narrow: identity and placement only. Contract,
salary and payroll fields are absent from the spec — a mis-extracted
wage is not something a preview card should be trusted to catch, and
those records carry legal weight.
"""
from odoo import api, models


class HrEmployee(models.Model):
    _name = 'hr.employee'
    _inherit = ['hr.employee', 'ai.command.mixin']

    @api.model
    def _ai_command_spec(self):
        return {
            'name': {
                'aliases': ['name', 'employee', 'full name', 'اسم',
                            'الاسم', 'الموظف'],
                'resolver': 'text', 'required': True, 'label': 'Name',
            },
            'work_email': {
                'aliases': ['email', 'mail', 'بريد', 'الايميل'],
                'resolver': 'text',
            },
            'work_phone': {
                'aliases': ['phone', 'mobile', 'جوال', 'هاتف'],
                'resolver': 'text',
            },
            'job_title': {
                'aliases': ['job', 'title', 'position', 'role', 'وظيفة',
                            'المسمى الوظيفي'],
                'resolver': 'text',
            },
        }
