# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td
from odoo.addons.ab_ai_tools_sale.services.sale_tools import TOOL_CODES


@tagged('post_install', '-at_install', 'ab_ai_tools_sale')
class TestSaleTools(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co_a = cls.env.company
        cls.co_b = cls.env['res.company'].create({'name': 'Pack Sale Co B'})
        cls.product = cls.env['product.product'].create(
            {'name': 'Pack Widget', 'list_price': 100.0, 'taxes_id': [Command.clear()]})
        cls.partner = cls.env['res.partner'].create({'name': 'Pack Customer'})
        groups = [cls.env.ref('base.group_user').id]
        cls.salesman = cls.env['res.users'].create({
            'name': 'Pack Salesman', 'login': 'pack_salesman',
            'company_id': cls.co_a.id, 'company_ids': [Command.set([cls.co_a.id, cls.co_b.id])],
            'groups_id': [Command.set(groups + [cls.env.ref('sales_team.group_sale_salesman_all_leads').id])]})
        cls.plain = cls.env['res.users'].create({
            'name': 'Pack Plain', 'login': 'pack_plain',
            'company_id': cls.co_a.id, 'company_ids': [Command.set([cls.co_a.id])],
            'groups_id': [Command.set(groups)]})
        for company, qty in ((cls.co_a, 2), (cls.co_b, 3)):
            so = cls.env['sale.order'].with_company(company).create({
                'partner_id': cls.partner.id, 'company_id': company.id,
                'order_line': [Command.create({'product_id': cls.product.id,
                                               'product_uom_qty': qty, 'price_unit': 100.0,
                                               'tax_id': [Command.clear()]})]})
            so.action_confirm()
        cls.policy = td.ToolPolicy(allow_write_actions=False, allow_pii=True, name='test')

    def _call(self, user, code, companies, **args):
        env = self.env(user=user, context=dict(self.env.context,
                                               allowed_company_ids=companies.ids))
        tool = env['ai.agent.tool'].search([('code', '=', code)])
        return td.dispatch(env, tool, args, policy=self.policy)

    def test_records_and_registry(self):
        Tool = self.env['ai.agent.tool']
        grp = self.env.ref('sales_team.group_sale_salesman')
        for code in TOOL_CODES:
            tool = self.env.ref(f'ab_ai_tools_sale.tool_{code}')
            self.assertEqual(tool.code, code)
            self.assertEqual(tool.group_ids, grp)
            self.assertTrue(tool.mcp_enabled)
            self.assertTrue(td.get(code))
            self.assertEqual(Tool.search_count([('code', '=', code)]), 1)

    def test_salesman_gets_data_scoped_to_active_company(self):
        out = self._call(self.salesman, 'sales_totals', self.co_a, period='ytd')
        self.assertTrue(out['ok'], out)
        self.assertEqual(out['result']['rows'], [[200.0, 1, 2.0]])
        both = self._call(self.salesman, 'sales_totals', self.co_a | self.co_b, period='ytd')
        self.assertEqual(both['result']['rows'], [[500.0, 2, 5.0]])

    def test_rankings_and_trend(self):
        top = self._call(self.salesman, 'top_products', self.co_a | self.co_b, period='ytd', limit=3)
        self.assertEqual(top['result']['rows'][0][1:], [500.0, 5.0])
        cust = self._call(self.salesman, 'top_customers', self.co_b, period='ytd')
        self.assertEqual(cust['result']['rows'][0][1:], [300.0, 1])
        trend = self._call(self.salesman, 'sales_trend_monthly', self.co_a, period='ytd')
        self.assertEqual(sum(r[1] for r in trend['result']['rows']), 200.0)

    def test_limit_capped(self):
        out = self._call(self.salesman, 'top_products', self.co_a, period='ytd', limit=100000)
        self.assertTrue(out['ok'])
        self.assertLessEqual(out['result']['total_rows'], 500)

    def test_refused_without_group(self):
        for code in TOOL_CODES:
            out = self._call(self.plain, code, self.co_a)
            self.assertFalse(out['ok'])
            self.assertEqual(out['error'], 'forbidden', out)
