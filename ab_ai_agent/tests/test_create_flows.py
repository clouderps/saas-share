# -*- coding: utf-8 -*-
"""create_record: one need_info question instead of a failing card,
defaults on the card, draft guard, spec-driven resolution."""
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import agent_actions as aa


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestCreateFlows(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = ['base.group_user', 'ab_ai_agent.group_ai_agent_user']
        if 'hr.employee' in cls.env:
            groups.append('hr.group_hr_user')
        if 'account.move' in cls.env:
            groups.append('account.group_account_invoice')
        cls.user = new_test_user(cls.env, login='cf_user', groups=','.join(groups))
        cls.env_u = cls.env(user=cls.user)
        cls.Pending = cls.env_u['ai.agent.pending.action']
        cls.partner = cls.env['res.partner'].create({'name': 'Flow Partner Unique',
                                                     'customer_rank': 1})
        cls.product = cls.env['product.product'].create({'name': 'Flow Product Unique',
                                                         'list_price': 10})

    def confirm(self, res):
        self.assertTrue(res.get('requires_confirmation'), res)
        return self.Pending.resolve(res['confirmation']['key'], True)

    def test_employee_missing_name_asks_once(self):
        if 'hr.employee' not in self.env:
            self.skipTest('hr not installed')
        res = aa.create_record(self.env_u, model='hr.employee', values={})
        self.assertEqual(res.get('status'), 'need_info', res)
        self.assertIn('name', [m['field'] for m in res['missing']])

    def test_employee_department_resolved_and_created(self):
        if 'hr.employee' not in self.env:
            self.skipTest('hr not installed')
        dep = self.env['hr.department'].create({'name': 'Flow Sales Dept'})
        res = aa.create_record(self.env_u, model='hr.employee',
                               values={'name': 'Ahmed Ali Flow', 'department_id': 'Flow Sales Dept'})
        self.assertIn('Flow Sales Dept', res['message'])
        self.assertTrue(any('(default)' in d for d in res['confirmation']['details']), res)
        out = self.confirm(res)
        self.assertTrue(out['ok'], out)
        emp = self.env['hr.employee'].browse(out['result']['action']['res_id'])
        self.assertEqual(emp.department_id, dep)
        self.assertTrue(out['result']['url'].startswith('/odoo/hr.employee/'))

    def test_employee_unknown_department_is_a_question(self):
        if 'hr.employee' not in self.env:
            self.skipTest('hr not installed')
        res = aa.create_record(self.env_u, model='hr.employee',
                               values={'name': 'X', 'department_id': 'No Such Dept Zz'})
        self.assertEqual(res.get('status'), 'need_info', res)

    def test_invoice_draft_and_guard(self):
        if 'account.move' not in self.env:
            self.skipTest('account not installed')
        for bad in ({'state': 'posted'}, {'name': 'INV/X'}, {'posted_before': True},
                    {'auto_post': 'at_date'}, {'auto_post_until': '2030-01-01'}):
            res = aa.create_record(self.env_u, model='account.move',
                                   values=dict(bad, move_type='out_invoice',
                                               partner_id='Flow Partner Unique'))
            self.assertIn('error', res, bad)
        res = aa.create_record(self.env_u, model='account.move',
                               values={'move_type': 'out_invoice'},
                               lines=[{'product': 'Flow Product Unique', 'quantity': 2}])
        self.assertEqual(res.get('status'), 'need_info', res)          # no customer
        res = aa.create_record(self.env_u, model='account.move',
                               values={'move_type': 'out_invoice',
                                       'partner_id': 'Flow Partner Unique'},
                               lines=[{'product': 'Flow Product Unique', 'quantity': 2}])
        self.assertIn('Invoice', res['confirmation']['summary'])     # not "Journal Entry"
        self.assertFalse(any(d.startswith('Status') for d in res['confirmation']['details']))
        out = self.confirm(res)
        self.assertTrue(out['ok'], out)
        move = self.env['account.move'].browse(out['result']['action']['res_id'])
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.partner_id, self.partner)
        self.assertEqual(move.invoice_line_ids.quantity, 2)

    def test_invoice_tax_uses_sale_side(self):
        if 'account.move' not in self.env:
            self.skipTest('account not installed')
        company = self.env.company
        sale = self.env['account.tax'].create({'name': 'FlowVAT 17%', 'amount': 17,
                                               'type_tax_use': 'sale', 'company_id': company.id})
        self.env['account.tax'].create({'name': 'FlowVAT 17% P', 'amount': 17,
                                        'type_tax_use': 'purchase', 'company_id': company.id})
        tax_id, err = aa._invoice_tax(self.env_u, 'FlowVAT', 'out_invoice')
        self.assertEqual((tax_id, err), (sale.id, None))
        tax_id, err = aa._invoice_tax(self.env_u, 'FlowVAT', 'in_invoice')
        self.assertNotEqual(tax_id, sale.id)

    def test_digest_hides_sections_without_rights(self):
        Digest = self.env['ai.agent.knowledge.digest']
        content = '### Journals\n- Bank (bank, BNK1)\n\n### Installed apps\n- Sales'
        basic = new_test_user(self.env, login='cf_basic', groups='base.group_user')
        out = Digest._filter_for_user(self.env(user=basic), content)
        self.assertNotIn('Journals', out)
        self.assertIn('Installed apps', out)

    def test_company_must_be_users(self):
        other = self.env['res.company'].create({'name': 'Flow Other Co'})
        res = aa.create_record(self.env_u, model='res.partner',
                               values={'name': 'P', 'company_id': other.id})
        self.assertIn('error', res)

    def test_posting_needs_accounting_manager(self):
        if 'account.move' not in self.env:
            self.skipTest('account not installed')
        from odoo.addons.ab_ai_agent.services.tool_dispatcher import _builtin_record_action
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id, 'ref': 'FLOWPOST1',
            'invoice_line_ids': [(0, 0, {'product_id': self.product.id, 'quantity': 1})]})
        res = _builtin_record_action(self.env_u, reference='FLOWPOST1')
        self.assertIn('error', res)
        self.assertEqual(move.state, 'draft')


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestKnowledgeDigest(TransactionCase):

    def test_digest_in_cached_prefix(self):
        from odoo.addons.ab_ai_agent.services import runtime
        from odoo.addons.ab_ai_base.models.ai_service import CACHE_BREAK
        Digest = self.env['ai.agent.knowledge.digest']
        Digest._rebuild()
        block = Digest.prompt_block(self.env)
        self.assertIn('This ERP', block)
        self.assertNotIn('amount', block.lower())
        before = Digest.search([]).mapped('built_at')
        Digest._rebuild()                               # no-op: byte-stable
        self.assertEqual(Digest.search([]).mapped('built_at'), before)
        agent = self.env['ai.agent'].search([], limit=1)
        prompt = runtime._compose_system_prompt(self.env, agent)
        self.assertLess(prompt.index('This ERP'), prompt.index(CACHE_BREAK))
