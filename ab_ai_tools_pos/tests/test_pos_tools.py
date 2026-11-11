# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.ab_ai_agent.services import tool_dispatcher
from odoo.addons.ab_ai_agent.services.tool_dispatcher import ToolPolicy

CODES = ('pos_session_status', 'top_cashiers', 'pos_shift_summary', 'pos_payment_mix')


@tagged('post_install', '-at_install', 'ab_ai_tools_pos')
class TestPosTools(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.company_data['company']
        cls.company_b = cls.setup_other_company()['company']
        pos_user = cls.env.ref('point_of_sale.group_pos_user')
        cls.cashier = cls.env['res.users'].create({
            'name': 'AI Cashier', 'login': 'ai_pos_cashier',
            'company_id': cls.company_a.id, 'company_ids': [(6, 0, [cls.company_a.id, cls.company_b.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, pos_user.id])],
        })
        cls.plain = cls.env['res.users'].create({
            'name': 'AI Plain', 'login': 'ai_pos_plain', 'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.sess_a = cls._make_shop(cls.company_a, 'Shop A', [100.0, 50.0])
        cls.sess_b = cls._make_shop(cls.company_b, 'Shop B', [70.0])

    @classmethod
    def _make_shop(cls, company, name, amounts):
        env = cls.env(context=dict(cls.env.context, allowed_company_ids=[company.id]))
        journal = env['account.journal'].create({
            'name': f'{name} Cash', 'code': name[-1] + 'CSH', 'type': 'cash', 'company_id': company.id})
        method = env['pos.payment.method'].create({
            'name': f'{name} Cash', 'journal_id': journal.id, 'company_id': company.id})
        config = env['pos.config'].create({
            'name': name, 'company_id': company.id, 'payment_method_ids': [(6, 0, method.ids)]})
        session = env['pos.session'].create({'config_id': config.id, 'user_id': cls.cashier.id})
        session.state = 'opened'
        for amount in amounts:
            order = env['pos.order'].create({
                'session_id': session.id, 'company_id': company.id, 'user_id': cls.cashier.id,
                'amount_tax': 0.0, 'amount_total': amount, 'amount_paid': amount,
                'amount_return': 0.0, 'date_order': fields.Datetime.now(),
            })
            env['pos.payment'].create({
                'pos_order_id': order.id, 'payment_method_id': method.id, 'amount': amount,
                'payment_date': fields.Datetime.now()})
            order.state = 'paid'
        return session

    def _env(self, user, companies):
        return self.env(user=user, context=dict(self.env.context, allowed_company_ids=companies.ids))

    def _tool(self, code):
        return self.env.ref(f'ab_ai_tools_pos.tool_{code}')

    def test_records_registered(self):
        group = self.env.ref('point_of_sale.group_pos_user')
        for code in CODES:
            tool = self._tool(code)
            self.assertEqual(tool.code, code)
            self.assertEqual(tool.group_ids, group)
            self.assertTrue(tool.mcp_enabled)
            self.assertFalse(tool.is_write_action)
            self.assertTrue(tool_dispatcher.get(code), code)

    def test_user_with_group_gets_data(self):
        env = self._env(self.cashier, self.company_a)
        for code in CODES:
            out = tool_dispatcher.dispatch(env, self._tool(code).with_env(env), {}, policy=ToolPolicy())
            self.assertTrue(out['ok'], (code, out))
        mix = tool_dispatcher.get('pos_payment_mix')(env)
        self.assertEqual(mix['total'], 150.0)
        shift = tool_dispatcher.get('pos_shift_summary')(env)
        self.assertEqual([s['pos'] for s in shift['shifts']], ['Shop A'])
        self.assertEqual(shift['shifts'][0]['orders'], 2)
        self.assertEqual(shift['shifts'][0]['total'], 150.0)
        self.assertEqual(shift['shifts'][0]['payment_mix'][0]['amount'], 150.0)
        top = tool_dispatcher.get('top_cashiers')(env)
        self.assertEqual(top['rows'][0][:2], ['AI Cashier', 150.0])

    def test_refused_without_group(self):
        env = self._env(self.plain, self.company_a)
        for code in CODES:
            out = tool_dispatcher.dispatch(env, self._tool(code).with_env(env), {}, policy=ToolPolicy())
            self.assertFalse(out['ok'])
            self.assertEqual(out['error'], 'forbidden')

    def test_multi_company_scope(self):
        mix = tool_dispatcher.get('pos_payment_mix')
        status = tool_dispatcher.get('pos_session_status')
        both = self._env(self.cashier, self.company_a | self.company_b)
        only_b = self._env(self.cashier, self.company_b)
        self.assertEqual(mix(both)['total'], 220.0)
        self.assertEqual(mix(only_b)['total'], 70.0)
        self.assertEqual([r[0] for r in status(only_b)['rows']], ['Shop B'])
        self.assertEqual(len(tool_dispatcher.get('pos_shift_summary')(both)['shifts']), 2)

    def test_bad_date_is_user_error(self):
        env = self._env(self.cashier, self.company_a)
        out = tool_dispatcher.dispatch(env, self._tool('pos_payment_mix').with_env(env),
                                       {'date_from': 'nope'}, policy=ToolPolicy())
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'user_error')
        self.assertIn('nope', out['message'])
