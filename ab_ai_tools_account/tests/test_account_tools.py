# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td
from odoo.addons.ab_ai_tools_account.services.account_tools import TOOLS

CODES = sorted(TOOLS)


@tagged('post_install', '-at_install', 'ab_ai_tools_account')
class TestAccountTools(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env['res.company'].create({'name': 'Pack Co B'})
        if not cls.env['account.account'].search_count(
                [('company_ids', 'in', cls.company_a.id)]):
            cls.env['account.chart.template'].try_loading(
                'generic_coa', cls.company_a, install_demo=False)
        cls.env['account.chart.template'].try_loading(
            'generic_coa', cls.company_b, install_demo=False)
        cls.accountant = new_test_user(
            cls.env, 'pack_acc', groups='base.group_user,account.group_account_invoice',
            company_id=cls.company_a.id, company_ids=[cls.company_a.id])
        cls.plain = new_test_user(cls.env, 'pack_plain', groups='base.group_user',
                                  company_id=cls.company_a.id)
        cls.partner_a = cls.env['res.partner'].create({'name': 'Debtor A'})
        cls.partner_b = cls.env['res.partner'].create({'name': 'Debtor B'})
        past = fields.Date.today() - timedelta(days=45)
        cls.inv_a = cls._invoice(cls.company_a, cls.partner_a, 100.0, past)
        cls.inv_b = cls._invoice(cls.company_b, cls.partner_b, 777.0, past)

    @classmethod
    def _invoice(cls, company, partner, price, due):
        env = cls.env(context=dict(cls.env.context, allowed_company_ids=[company.id]))
        move = env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id,
            'company_id': company.id, 'invoice_date': fields.Date.today(),
            'invoice_date_due': due,
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1,
                                         'price_unit': price, 'tax_ids': [(5,)]})],
        })
        move.action_post()
        move.invoice_date_due = due
        return move

    def _tool(self, code):
        return self.env['ai.agent.tool'].search([('code', '=', code)])

    def test_records_registered(self):
        for code in CODES:
            tool = self._tool(code)
            self.assertEqual(len(tool), 1, code)
            self.assertIs(td.get(code), TOOLS[code])
            self.assertEqual(tool.group_ids, self.env.ref('account.group_account_invoice'))
            self.assertTrue(tool.mcp_enabled)
            self.assertFalse(tool._is_mutating())
            self.assertTrue(self.env.ref(f'ab_ai_tools_account.tool_{code}'))

    def test_all_tools_run_as_accountant(self):
        env = self.env(user=self.accountant)
        for code in CODES:
            out = td.dispatch(env, self._tool(code).with_user(self.accountant), {},
                              policy=td.ToolPolicy(allow_pii=True))
            self.assertTrue(out['ok'], (code, out))

    def test_refused_without_group(self):
        env = self.env(user=self.plain)
        for code in CODES:
            out = td.dispatch(env, self._tool(code).with_user(self.plain), {},
                              policy=td.ToolPolicy())
            self.assertFalse(out['ok'], code)
            self.assertEqual(out['error'], 'forbidden', code)
            with self.assertRaises(AccessError):
                TOOLS[code](env)

    def test_multi_company_scope(self):
        env_a = self.env(user=self.accountant)
        names = [r[0] for r in TOOLS['top_overdue_partners'](env_a)['rows']]
        self.assertIn('Debtor A', names)
        self.assertNotIn('Debtor B', names)
        aging = TOOLS['ar_aging'](env_a)
        self.assertEqual(aging['total'], 100.0)
        self.assertEqual(aging['rows'], [['31-60', 100.0, 1, 45.0]])
        # Superuser with both companies allowed sees both.
        env_ab = self.env(context=dict(self.env.context, allowed_company_ids=[
            self.company_a.id, self.company_b.id]))
        names = [r[0] for r in TOOLS['top_overdue_partners'](env_ab)['rows']]
        self.assertIn('Debtor B', names)
        # Even an explicit allowed_company_ids can't reach a company the user lacks.
        self.assertNotIn(self.company_b, env_a.companies)

    def test_pl_summary_and_cap(self):
        env_a = self.env(user=self.accountant)
        pl = TOOLS['pl_summary'](env_a, period='this_month')
        self.assertEqual(pl['revenue'], 100.0)
        out = TOOLS['top_overdue_partners'](env_a, limit=100000)
        self.assertLessEqual(out['total_rows'], 500)

    def test_pre_init_hook_adopts_existing_rows(self):
        from odoo.addons.ab_ai_tools_account.hooks import pre_init_hook, MODULE
        Imd = self.env['ir.model.data']
        imd = Imd.search([('module', '=', MODULE), ('name', '=', 'tool_pl_summary')])
        res_id = imd.res_id
        imd.unlink()
        pre_init_hook(self.env)
        imd = Imd.search([('module', '=', MODULE), ('name', '=', 'tool_pl_summary')])
        self.assertEqual(imd.res_id, res_id)
        self.assertFalse(imd.noupdate)
        pre_init_hook(self.env)  # idempotent
        self.assertEqual(Imd.search_count([('module', '=', MODULE),
                                           ('name', '=', 'tool_pl_summary')]), 1)
