# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_command_account_entry.services.journal_entry import (
    _amount, create_journal_entry)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestJournalEntry(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='je_user',
                                 groups='base.group_user,account.group_account_user,'
                                        'ab_ai_agent.group_ai_agent_user')
        cls.env_u = cls.env(user=cls.user)
        company = cls.env.company
        cls.expense = cls.env['account.account'].create({
            'name': 'Flow Rent Expense', 'code': '699101', 'account_type': 'expense'})
        cls.bank_acc = cls.env['account.account'].create({
            'name': 'Flow Bank Account', 'code': '199101', 'account_type': 'asset_cash'})
        cls.journal = cls.env['account.journal'].search(
            [('company_id', '=', company.id), ('type', '=', 'general')], limit=1)

    def test_amount_parsing(self):
        self.assertEqual(_amount('5,000 SAR'), 5000.0)
        self.assertEqual(_amount('٥٠٠'), 500.0)
        self.assertIsNone(_amount(''))

    def test_unbalanced_is_need_info(self):
        res = create_journal_entry(self.env_u, lines=[
            {'account': 'Flow Rent Expense', 'debit': 500},
            {'account': '199101', 'credit': 400}])
        self.assertEqual(res.get('status'), 'need_info', res)

    def test_single_line_is_need_info(self):
        res = create_journal_entry(self.env_u, lines=[{'account': '699101', 'debit': 5}])
        self.assertEqual(res.get('status'), 'need_info')

    def test_balanced_draft_created_on_confirm(self):
        if not self.journal:
            self.skipTest('no general journal')
        before = self.env['account.move'].search_count([('move_type', '=', 'entry')])
        res = create_journal_entry(self.env_u, ref='Flow rent', lines=[
            {'account': 'Flow Rent Expense', 'debit': 500, 'label': 'Rent'},
            {'account': '199101', 'credit': '500 SAR'}])
        self.assertTrue(res.get('requires_confirmation'), res)
        self.assertEqual(self.env['account.move'].search_count([('move_type', '=', 'entry')]),
                         before)
        out = self.env_u['ai.agent.pending.action'].resolve(res['confirmation']['key'], True)
        self.assertTrue(out['ok'], out)
        move = self.env['account.move'].browse(out['result']['action']['res_id'])
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.move_type, 'entry')
        self.assertEqual(sorted(move.line_ids.mapped('debit')), [0.0, 500.0])
        self.assertEqual(move.create_uid, self.user)
