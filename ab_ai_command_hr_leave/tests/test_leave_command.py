# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'ghaima_ai_command')
class TestLeaveCommand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='leave_cmd_user', groups='base.group_user')
        cls.me = cls.env['hr.employee'].create({'name': 'Leave Me', 'user_id': cls.user.id})
        cls.other = cls.env['hr.employee'].create({'name': 'Someone Else'})
        cls.ltype = cls.env['hr.leave.type'].create({
            'name': 'AI Test Leave', 'requires_allocation': 'no', 'request_unit': 'day'})
        cls.command = cls.env['ai.agent.command'].search([('code', '=', 'create_leave')])

    def test_requests_for_self_only_and_one_day_by_default(self):
        out = self.command.with_user(self.user).run({
            'holiday_status_id': 'AI Test Leave', 'request_date_from': '2030-01-07',
            'employee_id': self.other.name})
        self.assertEqual(out['status'], 'created', out)
        leave = self.env['hr.leave'].browse(out['id'])
        self.assertEqual(leave.employee_id, self.me)
        self.assertEqual(leave.request_date_to, leave.request_date_from)

    def test_unknown_type_offers_the_types(self):
        out = self.command.with_user(self.user).run({
            'holiday_status_id': 'zz-annual', 'request_date_from': '2030-01-07'})
        self.assertEqual(out['status'], 'needs_input')
        names = [o['name'] for o in out['questions'][0]['options']]
        self.assertIn('AI Test Leave', names)
