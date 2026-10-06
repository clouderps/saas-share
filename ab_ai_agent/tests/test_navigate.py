# -*- coding: utf-8 -*-
"""`navigate` resolver: everything as the user, typed directives only."""
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher
from odoo.addons.ab_ai_agent.services.navigate import navigate


@tagged('post_install', '-at_install', 'ghaima_ai_agent', 'ai_navigate')
class TestNavigate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plain = new_test_user(cls.env, login='nav_plain', groups='base.group_user')
        groups = 'base.group_user,base.group_partner_manager'
        if cls.env.ref('account.group_account_invoice', raise_if_not_found=False):
            groups += ',account.group_account_invoice'
        cls.billing = new_test_user(cls.env, login='nav_billing', groups=groups)
        Partner = cls.env['res.partner']
        cls.zubair = Partner.create({'name': 'Zubairqx Navtest Trading'})
        cls.twin_a = Partner.create({'name': 'Twinqx Navtest North'})
        cls.twin_b = Partner.create({'name': 'Twinqx Navtest South'})

    def _as(self, user, **kw):
        return navigate(self.env(user=user), **kw)

    def test_registered_and_core(self):
        from odoo.addons.ab_ai_agent.services.runtime import _CORE_TOOLS
        self.assertIs(tool_dispatcher.get('navigate'), navigate)
        self.assertIn('navigate', _CORE_TOOLS)
        self.assertTrue(self.env.ref('ab_ai_agent.tool_navigate').active)

    def test_partner_by_name(self):
        res = self._as(self.billing, kind='record', target='contact', query='zubairqx navtest')
        self.assertTrue(res['found'])
        nav = res['navigate']
        self.assertEqual((nav['type'], nav['model'], nav['res_id']),
                         ('record', 'res.partner', self.zubair.id))
        self.assertEqual(res['action']['type'], 'ir.actions.act_window')

    def test_arabic_target_word(self):
        res = self._as(self.billing, kind='record', target='العميل', query='Zubairqx')
        self.assertEqual(res['navigate']['res_id'], self.zubair.id)

    def test_ambiguous_returns_choices_not_a_guess(self):
        res = self._as(self.billing, kind='record', target='customer', query='Twinqx Navtest')
        self.assertTrue(res.get('ambiguous'))
        self.assertNotIn('navigate', res)
        self.assertEqual({c['res_id'] for c in res['choices']}, {self.twin_a.id, self.twin_b.id})
        self.assertTrue(all(c['type'] == 'record' for c in res['choices']))

    def test_exact_name_wins_over_partial_hits(self):
        exact = self.env['res.partner'].create({'name': 'Twinqx Navtest'})
        res = self._as(self.billing, kind='record', target='contact', query='twinqx navtest')
        self.assertEqual(res['navigate']['res_id'], exact.id)

    def test_not_found(self):
        res = self._as(self.billing, kind='record', target='contact', query='Nobodyqx Zzz 4711')
        self.assertFalse(res['found'])
        self.assertNotIn('navigate', res)

    def test_invoice_by_number(self):
        if 'account.move' not in self.env or not self.env['account.journal'].search(
                [('type', '=', 'sale')], limit=1):
            self.skipTest('accounting not set up')
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.zubair.id,
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 10})]})
        move.action_post()
        self.assertTrue(move.name and move.name != '/')
        user = self.billing if self.billing.has_group('account.group_account_invoice') else self.env.user
        res = self._as(user, kind='record', target='invoice', query=move.name)
        self.assertEqual(res['navigate']['res_id'], move.id)
        # same number but asked as a vendor bill: not in that scope
        res = self._as(user, kind='record', target='bill', query=move.name)
        self.assertNotEqual((res.get('navigate') or {}).get('res_id'), move.id)

    def test_record_rules_hide_records(self):
        # A company the user is not in: record rules hide its partner.
        other = self.env['res.company'].create({'name': 'Navtest Other Co'})
        hidden = self.env['res.partner'].create({'name': 'Hiddenqx Navtest', 'company_id': other.id})
        res = self._as(self.billing, kind='record', target='contact', query='Hiddenqx Navtest')
        self.assertFalse(res['found'])
        self.assertNotIn(str(hidden.id), str(res))

    def test_model_without_read_access_is_not_available(self):
        if 'account.move' not in self.env:
            self.skipTest('account not installed')
        if self.env['account.move'].with_user(self.plain).has_access('read'):
            self.skipTest('internal users can read account.move here')
        res = self._as(self.plain, kind='record', target='invoice', query='INV')
        self.assertFalse(res['found'])
        self.assertIn('not available', res['error'])
        self.assertNotIn('navigate', res)
        self.assertNotIn('choices', res)
        res = self._as(self.plain, kind='list', preset='unpaid_invoices')
        self.assertIn('not available', res['error'])

    def test_unknown_target_is_rejected(self):
        res = self._as(self.billing, kind='record', target='res.users', query='admin')
        self.assertFalse(res['found'])

    def test_list_preset_ignores_model_domain(self):
        user = self.env.user
        res = self._as(user, kind='list', preset='customers', domain="[('id','>',0)]",
                       filter="[('active','=',False)]")
        self.assertTrue(res['found'])
        nav = res['navigate']
        self.assertEqual((nav['type'], nav['model']), ('list', 'res.partner'))
        self.assertEqual(nav['domain'], [('customer_rank', '>', 0)])
        res = self._as(user, kind='list', preset="[('id','>',0)]")
        self.assertFalse(res['found'])

    def test_menu_by_name(self):
        if not self.env.ref('hr.menu_hr_root', raise_if_not_found=False):
            self.skipTest('hr not installed')
        user = new_test_user(self.env, login='nav_hr', groups='base.group_user,hr.group_hr_user')
        res = self._as(user, kind='menu', query='employees')
        self.assertTrue(res['found'], res)
        nav = res['navigate']
        self.assertEqual(nav['type'], 'menu')
        menu = self.env['ir.ui.menu'].browse(nav['menu_id'])
        self.assertTrue(menu.exists())
        self.assertIn(menu, self.env['ir.ui.menu'].with_user(user).search([]))

    def test_menu_not_found(self):
        res = self._as(self.plain, kind='menu', query='zzqx nonexistent screen')
        self.assertFalse(res['found'])
        self.assertNotIn('navigate', res)
