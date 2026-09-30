# -*- coding: utf-8 -*-
"""Phase 2 — the Screen Context Engine trusts nothing from the browser."""
from odoo import fields
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestScreenContext(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        own = 'sales_team.group_sale_salesman'          # "own documents only"
        cls.alice = new_test_user(cls.env, login='ai_ctx_alice',
                                  groups=f'base.group_user,{own}')
        cls.bob = new_test_user(cls.env, login='ai_ctx_bob',
                                groups=f'base.group_user,{own}')
        partner = cls.env['res.partner'].create({'name': 'Screen Co'})
        cls.mine = cls.env['sale.order'].create(
            {'partner_id': partner.id, 'user_id': cls.alice.id})
        cls.theirs = cls.env['sale.order'].create(
            {'partner_id': partner.id, 'user_id': cls.bob.id})
        cls.SC = cls.env['ai.screen.context']

    def _ctx(self, user, raw):
        return self.SC.with_user(user).normalize(raw)

    def test_counts_follow_record_rules(self):
        raw = {'model': 'sale.order', 'view_type': 'list', 'domain': []}
        alice = self.SC.with_user(self.alice)
        facts = alice.facts(alice.normalize(raw))
        visible = self.env['sale.order'].with_user(self.alice).search_count([])
        self.assertEqual(facts['count'], visible)
        self.assertLess(facts['count'], self.env['sale.order'].search_count([]))

    def test_browser_ids_are_intersected_with_access(self):
        ctx = self._ctx(self.alice, {
            'model': 'sale.order', 'view_type': 'list',
            'visible_ids': [self.theirs.id, self.mine.id],
            'selected_ids': [self.theirs.id]})
        self.assertEqual(ctx['visible_ids'], [self.mine.id])
        self.assertEqual(ctx['selected_ids'], [])

    def test_unreadable_record_is_dropped(self):
        ctx = self._ctx(self.alice, {'model': 'sale.order', 'view_type': 'form',
                                     'res_id': self.theirs.id})
        self.assertNotIn('res_id', ctx)

    def test_unreadable_model_gives_no_context(self):
        ctx = self._ctx(self.alice, {'model': 'ir.config_parameter', 'view_type': 'list'})
        self.assertFalse(ctx and ctx.get('model'))

    def test_malformed_or_hostile_domains_are_dropped(self):
        for domain in (["DROP TABLE"], [('nope_field', '=', 1)],
                       [('name', '=', 'x', 'extra')], "[('id','>',0)]"):
            ctx = self._ctx(self.alice, {'model': 'sale.order', 'domain': domain})
            self.assertEqual(ctx['domain'], [], domain)

    def test_forbidden_action_gives_no_context(self):
        action = self.env['ir.actions.act_window'].create({
            'name': 'Admins only', 'res_model': 'sale.order',
            'groups_id': [(6, 0, [self.env.ref('base.group_system').id])]})
        self.assertIsNone(self._ctx(self.alice, {'action': {'id': action.id},
                                                 'model': 'sale.order'}))

    def test_prompt_block_lists_rows_in_order(self):
        block = self.SC.with_user(self.alice).prompt_block({
            'model': 'sale.order', 'view_type': 'list',
            'visible_ids': [self.mine.id]})
        self.assertIn('Current screen', block)
        self.assertIn(f'#1 {self.mine.display_name} (id {self.mine.id})', block)
        self.assertNotIn(self.theirs.display_name + ' (id', block)

    def test_group_by_only_real_fields(self):
        ctx = self._ctx(self.alice, {'model': 'sale.order',
                                     'group_by': ['state', 'x;drop', 'date_order:month']})
        self.assertEqual(ctx['group_by'], ['state', 'date_order:month'])


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestScreenInsight(TransactionCase):

    def test_insight_numbers_are_the_users_own_counts(self):
        if 'sale.order' not in self.env:
            self.skipTest('sale not installed')
        user = new_test_user(self.env, login='ai_tip_user',
                             groups='base.group_user,sales_team.group_sale_salesman')
        SC = self.env['ai.screen.context'].with_user(user).with_context(lang='en_US')
        res = SC.insight({'model': 'sale.order', 'view_type': 'list'})
        n = self.env['sale.order'].with_user(user).search_count([])
        self.assertTrue(res['lines'])
        self.assertIn(str(n), res['lines'][0])

    def test_insight_is_cached_and_never_raises(self):
        SC = self.env['ai.screen.context']
        a = SC.insight({'model': 'res.partner', 'view_type': 'list'})
        b = SC.insight({'model': 'res.partner', 'view_type': 'list'})
        self.assertIs(a, b)
        self.assertEqual(SC.insight({'model': 'no.such.model'}), {'lines': []})
        self.assertEqual(SC.insight('garbage'), {'lines': []})

    def test_session_info_exposes_assistant_flags(self):
        info = self.env.user._ai_assistant_info()
        self.assertIn(info['proactive'], ('off', 'quiet', 'on'))
        self.env['ir.config_parameter'].set_param('ab_ai_agent.proactive_enabled', 'False')
        self.assertEqual(self.env.user._ai_assistant_info()['proactive'], 'off')

    def test_insight_carries_the_screen_card(self):
        SC = self.env['ai.screen.context'].with_context(lang='en_US')
        res = SC.insight({'model': 'res.partner', 'view_type': 'list',
                          'visible_ids': self.env['res.partner'].search([], limit=2).ids})
        self.assertTrue(res['title'])
        self.assertIn('Explain this screen', res['suggestions'])
        self.assertIn('Open the first one', res['suggestions'])
        partner = self.env['res.partner'].search([], limit=1)
        res = SC.insight({'model': 'res.partner', 'view_type': 'form', 'res_id': partner.id})
        self.assertEqual(res['title'], partner.display_name)
        self.assertIn('Explain this record', res['suggestions'])

    def test_tips_default_to_on(self):
        user = new_test_user(self.env, login='ai_tip_default', groups='base.group_user')
        self.assertEqual(user.ai_proactive_mode, 'on')

    def test_briefing_is_counts_for_the_user_cached_per_day(self):
        user = new_test_user(self.env, login='ai_brief_user', groups='base.group_user')
        partner = self.env['res.partner'].create({'name': 'Brief Co'})
        partner.activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                  date_deadline='2000-01-01', summary='late one')
        text = user._ai_briefing()
        self.assertIn('1', text)
        self.assertEqual(user.ai_briefing_date, fields.Date.context_today(user))
        partner.activity_schedule('mail.mail_activity_data_todo', user_id=user.id,
                                  date_deadline='2000-01-02', summary='late two')
        self.assertEqual(user._ai_briefing(), text)          # cached for today
