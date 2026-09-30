# -*- coding: utf-8 -*-
"""Agent actions: propose first, run on Confirm, as the user, validated."""
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import agent_actions as aa


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestAgentActions(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        cls.user = new_test_user(cls.env, login='aa_sales',
                                 groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                                        'ab_ai_agent.group_ai_agent_user')
        cls.plain = new_test_user(cls.env, login='aa_plain', groups='base.group_user')
        cls.partner = cls.env['res.partner'].create({'name': 'Action Partner Unique'})
        cls.product = cls.env['product.product'].create({'name': 'Action Product Unique',
                                                         'list_price': 25})
        cls.env_u = cls.env(user=cls.user)
        cls.Pending = cls.env_u['ai.agent.pending.action']

    def confirm(self, res):
        self.assertTrue(res.get('requires_confirmation'), res)
        return self.Pending.resolve(res['confirmation']['key'], True)

    def test_create_quotation_with_lines(self):
        before = self.env['sale.order'].search_count([])
        res = aa.create_record(self.env_u, model='sale.order',
                               values={'partner_id': 'Action Partner Unique'},
                               lines=[{'product': 'Action Product Unique', 'quantity': 3}])
        self.assertEqual(self.env['sale.order'].search_count([]), before)   # nothing yet
        self.assertIn('Action Product Unique × 3', res['message'])
        out = self.confirm(res)
        self.assertTrue(out['ok'], out)
        so = self.env['sale.order'].browse(out['result']['action']['res_id'])
        self.assertEqual(so.partner_id, self.partner)
        self.assertEqual(so.order_line.product_uom_qty, 3)
        self.assertEqual(so.create_uid, self.user)                           # ran as the user

    def test_values_are_validated(self):
        for values in ({'company_id': 1}, {'nope': 1}, {'partner_id': 'No Such Partner Xyz'},
                       {'state': 'teleported'}):
            res = aa.create_record(self.env_u, model='sale.order', values=values)
            self.assertIn('error', res, values)

    def test_update_post_and_schedule(self):
        so = self.env['sale.order'].create({'partner_id': self.partner.id})
        out = self.confirm(aa.update_record(self.env_u, model='sale.order', record=so.name,
                                            values='{"client_order_ref": "PO-77"}'))
        self.assertTrue(out['ok'], out)
        self.assertEqual(so.client_order_ref, 'PO-77')
        out = self.confirm(aa.post_message(self.env_u, model='sale.order', record=so.id,
                                           body='Call the customer'))
        self.assertTrue(out['ok'], out)
        self.assertIn('Call the customer', so.message_ids[0].body)
        out = self.confirm(aa.schedule_activity(self.env_u, model='sale.order', record=so.id,
                                                summary='Follow up', date_deadline='2031-01-05'))
        self.assertTrue(out['ok'], out)
        self.assertEqual(so.activity_ids[:1].summary, 'Follow up')

    def test_act_on_named_record(self):
        so = self.env['sale.order'].create({'partner_id': self.partner.id, 'order_line': [
            (0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})]})
        out = self.confirm(aa.act_on_record(self.env_u, model='sale.order', record=so.name,
                                            button='Confirm'))
        self.assertTrue(out['ok'], out)
        self.assertEqual(so.state, 'sale')

    def test_no_rights_no_proposal(self):
        env_p = self.env(user=self.plain)
        res = aa.create_record(env_p, model='sale.order', values={'partner_id': self.partner.id})
        self.assertEqual(res.get('error'), 'not permitted')

    def test_action_tools_follow_the_switch(self):
        from odoo.addons.ab_ai_agent.services.runtime import _resolve_tools
        agent = self.env['ai.agent'].search([('code', '=', 'ghaima_assistant')], limit=1)
        if not agent:
            self.skipTest('no default assistant')
        agent._heal_core_topics()
        self.assertIn('create_record', _resolve_tools(self.env_u, agent).mapped('code'))
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'False')
        self.assertNotIn('create_record', _resolve_tools(self.env_u, agent).mapped('code'))


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestRouting(TransactionCase):

    def test_tool_routing_trims_and_falls_back(self):
        from odoo.addons.ab_ai_agent.services.runtime import _route_tools, _resolve_tools
        agent = self.env['ai.agent'].search([('code', '=', 'ghaima_assistant')], limit=1)
        if not agent:
            self.skipTest('no default assistant')
        agent._heal_core_topics()
        tools = _resolve_tools(self.env, agent)
        stock = _route_tools(self.env, tools, 'what is low in stock?')
        self.assertLess(len(stock), len(tools))
        self.assertIn('query_data', stock.mapped('code'))
        self.assertNotIn('create_record', stock.mapped('code'))
        act = _route_tools(self.env, tools, 'أنشئ عرض سعر لأحمد')
        self.assertIn('create_record', act.mapped('code'))
        self.assertEqual(len(_route_tools(self.env, tools, 'hello there')), len(tools))

    def test_model_routing_only_when_configured(self):
        from odoo.addons.ab_ai_agent.services.runtime import _route_model
        self.assertIsNone(_route_model(self.env, 'حلل المبيعات'))
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.strong_model', 'gemini-2.5-pro')
        self.assertEqual(_route_model(self.env, 'حلل المبيعات ولماذا انخفضت'), 'gemini-2.5-pro')
        self.assertIsNone(_route_model(self.env, 'افتح أول سجل'))
