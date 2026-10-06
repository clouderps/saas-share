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
            'job_id': {
                'aliases': ['job', 'position', 'job position', 'وظيفة', 'الوظيفة',
                            'المسمى الوظيفي'],
                'resolver': 'many2one', 'fallback_text': 'job_title',
            },
            'job_title': {
                'aliases': ['title', 'job title', 'role', 'المسمى'],
                'resolver': 'text',
            },
            'department_id': {
                'aliases': ['department', 'dept', 'قسم', 'القسم', 'الإدارة', 'ادارة'],
                'resolver': 'many2one',
            },
            'parent_id': {
                'aliases': ['manager', 'reports to', 'مدير', 'المدير', 'المدير المباشر'],
                'resolver': 'many2one',
            },
            'work_location_id': {
                'aliases': ['location', 'work location', 'موقع', 'موقع العمل', 'مكان العمل'],
                'resolver': 'many2one',
            },
            'private_phone': {
                'aliases': ['private phone', 'personal phone', 'جوال شخصي', 'الجوال الشخصي'],
                'resolver': 'text',
            },
        }
