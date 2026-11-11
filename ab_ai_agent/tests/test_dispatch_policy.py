# -*- coding: utf-8 -*-
"""Phase 0 agent-hardening (MCP + AI plan v2).

* data_analysis aggregates as the user: no other company's totals.
* A confirmed proposal re-runs every dispatch gate with the proposing
  agent: group removed, kill switch on or plan ceiling lowered → refused.
* tool_spec / as_mcp_schema shape.
* dispatch works with a policy object instead of an agent, and its
  sanitised-error mode hides exception text.
"""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.tests.common import new_test_user

from odoo.addons.ab_ai_agent.services import agent_actions as aa
from odoo.addons.ab_ai_agent.services import llm_adapter
from odoo.addons.ab_ai_agent.services import tool_dispatcher as td


class _Gateway:
    def __init__(self, policy):
        self.policy = policy

    def has_capability(self, name):
        return False

    def get_policy(self):
        return self.policy


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestDataAnalysisCompanies(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'DA Foreign Co'})
        cls.user = new_test_user(
            cls.env, login='da_mc_user', company_id=cls.company_a.id,
            company_ids=[(6, 0, [cls.company_a.id, cls.company_b.id])],
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                   'ab_ai_agent.group_ai_agent_user')
        partner = cls.env['res.partner'].create({'name': 'DA Partner'})
        product = cls.env['product.product'].create({'name': 'DA Product', 'list_price': 100})
        when = fields.Datetime.now() - timedelta(days=2)
        for company, qty in ((cls.company_a, 1), (cls.company_b, 50)):
            so = cls.env['sale.order'].with_company(company).create({
                'partner_id': partner.id, 'company_id': company.id,
                'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty,
                                       'price_unit': 100, 'tax_id': [(6, 0, [])]})],
            })
            so.write({'state': 'sale', 'date_order': when})
        cls.foreign_total = sum(cls.env['sale.order'].search(
            [('company_id', '=', cls.company_b.id)]).mapped('amount_total'))

    def _total(self, env):
        out = td._builtin_data_analysis(env, metric='sale_orders', period_days=7)
        self.assertIn('render', out, out)
        return out

    def test_only_active_company_totals(self):
        env = self.env(user=self.user, context={'allowed_company_ids': [self.company_a.id]})
        out = self._total(env)
        own = sum(self.env['sale.order'].search(
            [('company_id', '=', self.company_a.id), ('state', '=', 'sale'),
             ('date_order', '>=', fields.Date.today() - timedelta(days=7)),
             ('date_order', '<', fields.Date.today())]).mapped('amount_total'))
        self.assertIn(f'{own:,.0f}', out['summary'])
        self.assertNotIn(f'{own + self.foreign_total:,.0f}', out['summary'])

    def test_user_outside_company_gets_no_foreign_totals(self):
        self.user.write({'company_ids': [(6, 0, [self.company_a.id])]})
        env = self.env(user=self.user)
        out = self._total(env)
        self.assertNotIn(f'{self.foreign_total:,.0f}', out['summary'])

    def test_no_read_access_is_refused(self):
        plain = new_test_user(self.env, login='da_plain', groups='base.group_user')
        out = td._builtin_data_analysis(self.env(user=plain), metric='sale_orders')
        self.assertIn('error', out)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestConfirmedDispatchGates(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        cls.user = new_test_user(
            cls.env, login='cdg_sales',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                   'ab_ai_agent.group_ai_agent_user')
        cls.partner = cls.env['res.partner'].create({'name': 'Gate Partner Unique'})
        cls.agent = cls.env['ai.agent'].get_default()
        cls.agent.sudo().allow_write_actions = True
        cls.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'True')
        cls.tool = cls.env['ai.agent.tool'].search([('code', '=', 'create_record')], limit=1)

    def setUp(self):
        super().setUp()
        self.env_u = self.env(user=self.user)
        self.Pending = self.env_u['ai.agent.pending.action']

    def _propose(self):
        """Propose through the dispatcher so the agent is recorded."""
        out = td.dispatch(self.env_u, self.tool.with_env(self.env_u),
                          {'model': 'sale.order', 'values': {'partner_id': 'Gate Partner Unique'}},
                          agent=self.agent.with_env(self.env_u))
        self.assertTrue(out['ok'], out)
        res = out['result']
        self.assertTrue(res.get('requires_confirmation'), res)
        row = self.Pending.search([('key', '=', res['confirmation']['key'])])
        self.assertEqual(row.agent_id, self.agent)
        return res['confirmation']['key']

    def _created(self):
        return self.env['sale.order'].search_count([('partner_id', '=', self.partner.id)])

    def test_confirm_runs_when_gates_hold(self):
        out = self.Pending.resolve(self._propose(), True)
        self.assertTrue(out['ok'], out)
        self.assertEqual(self._created(), 1)

    def test_refused_after_group_removed(self):
        key = self._propose()
        self.tool.sudo().group_ids = [(6, 0, [self.env.ref('base.group_system').id])]
        out = self.Pending.resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertEqual(self._created(), 0)

    def test_refused_when_kill_switch_on(self):
        key = self._propose()
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.actions_enabled', 'False')
        out = self.Pending.resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertEqual(self._created(), 0)

    def test_refused_when_plan_ceiling_lowered(self):
        key = self._propose()
        with patch.object(llm_adapter, 'llm_mode', return_value='auto'), \
                patch.object(llm_adapter, '_try_get_gateway',
                             return_value=_Gateway({'actions': False})):
            out = self.Pending.resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertEqual(self._created(), 0)

    def test_refused_when_agent_loses_write_permission(self):
        key = self._propose()
        self.agent.sudo().allow_write_actions = False
        out = self.Pending.resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertEqual(self._created(), 0)

    def test_direct_proposal_falls_back_to_default_agent(self):
        res = aa.create_record(self.env_u, model='sale.order',
                               values={'partner_id': 'Gate Partner Unique'})
        self.agent.sudo().allow_write_actions = False
        self.assertFalse(self.Pending.resolve(res['confirmation']['key'], True)['ok'])
        self.assertEqual(self._created(), 0)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestToolSpecAndPolicy(TransactionCase):

    def test_tool_spec_shape(self):
        Tool = self.env['ai.agent.tool']
        read = Tool.search([('code', '=', 'date_reference')], limit=1)
        write = Tool.search([('code', '=', 'record_action')], limit=1)
        spec = read.tool_spec()
        self.assertEqual(spec['name'], 'date_reference')
        self.assertEqual(spec['inputSchema']['type'], 'object')
        self.assertNotIn('__end_message', spec['inputSchema']['properties'])
        self.assertTrue(spec['annotations']['readOnlyHint'])
        self.assertFalse(spec['annotations']['destructiveHint'])
        self.assertIsInstance(spec['groups'], list)
        self.assertFalse(read.mcp_enabled)
        wspec = write.as_mcp_schema()
        self.assertTrue(wspec['annotations']['destructiveHint'])
        self.assertFalse(wspec['annotations']['readOnlyHint'])
        self.assertNotIn('groups', wspec)
        read.output_schema = '{"type": "object"}'
        self.assertEqual(read.tool_spec()['outputSchema'], {'type': 'object'})

    def test_dispatch_with_policy_object(self):
        tool = self.env['ai.agent.tool'].search([('code', '=', 'date_reference')], limit=1)
        out = td.dispatch(self.env, tool, {}, policy=td.ToolPolicy())
        self.assertTrue(out['ok'], out)

    def test_policy_without_write_is_refused_write_tools(self):
        tool = self.env['ai.agent.tool'].search([('code', '=', 'record_action')], limit=1)
        out = td.dispatch(self.env, tool, {'reference': 'x'}, policy=td.ToolPolicy())
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'write_blocked')
        create = self.env['ai.agent.tool'].search([('code', '=', 'create_record')], limit=1)
        out = td.dispatch(self.env, create, {}, policy=td.ToolPolicy())
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'not_offered')

    def test_offered_to_policy(self):
        Tool = self.env['ai.agent.tool'].search([])
        codes = set(Tool._offered_to(self.env.user, td.ToolPolicy()).mapped('code'))
        self.assertFalse(codes & td.ACTION_TOOLS)
        self.assertIn('date_reference', codes)

    def test_sanitised_errors_hide_exception_text(self):
        tool = self.env['ai.agent.tool'].search([('code', '=', 'date_reference')], limit=1)

        def boom(env, agent=None, **kw):
            raise RuntimeError('secret-db-detail')
        with patch.dict(td._REGISTRY, {'date_reference': boom}):
            out = td.dispatch(self.env, tool, {}, policy=td.ToolPolicy())
            self.assertFalse(out['ok'])
            self.assertNotIn('secret-db-detail', out['message'])
            self.assertIn(out['request_id'], out['message'])
            agent = self.env['ai.agent'].get_default()
            out = td.dispatch(self.env, tool, {}, agent=agent)
            self.assertIn('secret-db-detail', out['message'])
