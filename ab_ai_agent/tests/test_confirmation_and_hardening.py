# -*- coding: utf-8 -*-
"""Phase 0 of docs/ghaima-ai/IMPLEMENTATION_PLAN.md.

* A state change proposed by the assistant never runs until the user who
  saw it clicks Confirm (and only once, only by them, only while fresh).
* The model cannot smuggle the server-side confirmation flag.
* open_action is not a side door to group-restricted screens.
* HR tools need an HR role and honour record rules.
* semantic_search cannot inject SQL through column names.
* The system prompt carries exactly one cache boundary, after the
  invariant blocks.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td
from odoo.addons.ab_ai_agent.services.runtime import (
    _compose_system_prompt, _confirmation_chips, _proposal_of)
from odoo.addons.ab_ai_base.models.ai_service import CACHE_BREAK


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestConfirmation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        cls.salesman = new_test_user(
            cls.env, login='ai_confirm_sales',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                   'ab_ai_agent.group_ai_agent_user')
        cls.other = new_test_user(
            cls.env, login='ai_confirm_other',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                   'ab_ai_agent.group_ai_agent_user')
        partner = cls.env['res.partner'].create({'name': 'Confirm Co'})
        product = cls.env['product.product'].create({'name': 'Confirm Product'})
        cls.so = cls.env['sale.order'].create({
            'partner_id': partner.id, 'client_order_ref': 'CONFIRMREF-777',
            'user_id': cls.salesman.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })

    def _propose(self, user):
        env = self.env(user=user)
        res = td._builtin_record_action(env, reference='CONFIRMREF-777')
        self.assertTrue(res.get('requires_confirmation'), res)
        return env, res['confirmation']['key']

    def test_proposal_changes_nothing(self):
        self._propose(self.salesman)
        self.assertEqual(self.so.state, 'draft')

    def test_confirm_runs_once(self):
        env, key = self._propose(self.salesman)
        Pending = env['ai.agent.pending.action']
        first = Pending.resolve(key, True)
        self.assertTrue(first['ok'] and first.get('executed'), first)
        self.assertEqual(self.so.state, 'sale')
        again = Pending.resolve(key, True)
        self.assertTrue(again.get('replayed'))

    def test_cancel_changes_nothing(self):
        env, key = self._propose(self.salesman)
        out = env['ai.agent.pending.action'].resolve(key, False)
        self.assertTrue(out.get('cancelled'))
        self.assertEqual(self.so.state, 'draft')
        self.assertFalse(env['ai.agent.pending.action'].resolve(key, True)['ok'])

    def test_other_user_cannot_confirm(self):
        _env, key = self._propose(self.salesman)
        out = self.env(user=self.other)['ai.agent.pending.action'].resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertEqual(self.so.state, 'draft')

    def test_expired_proposal_does_not_run(self):
        env, key = self._propose(self.salesman)
        row = env['ai.agent.pending.action'].search([('key', '=', key)])
        self.env.cr.execute(
            "UPDATE ai_agent_pending_action SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(hours=1), row.id))
        row.invalidate_recordset()
        self.assertFalse(env['ai.agent.pending.action'].resolve(key, True)['ok'])
        self.assertEqual(self.so.state, 'draft')

    def test_model_cannot_pass_the_confirmed_flag(self):
        """Arguments starting with _ai_ are server-only: the dispatcher
        drops them, so the call still only proposes."""
        env = self.env(user=self.salesman)
        tool = env['ai.agent.tool'].search([('code', '=', 'record_action')], limit=1)
        agent = env['ai.agent'].sudo().search([], limit=1)
        agent.allow_write_actions = True
        out = td.dispatch(env, tool, {'reference': 'CONFIRMREF-777',
                                      '_ai_confirmed': True}, agent=agent)
        self.assertTrue(out['ok'], out)
        self.assertTrue(out['result'].get('requires_confirmation'))
        self.assertEqual(self.so.state, 'draft')

    def test_runtime_turns_proposal_into_chips(self):
        env, key = self._propose(self.salesman)
        conf = _proposal_of({'ok': True, 'result': {
            'requires_confirmation': True, 'confirmation': {'key': key}}})
        chips = _confirmation_chips(conf, 'ar')
        self.assertEqual(chips['type'], 'suggestion_chips')
        self.assertEqual([i['action']['type'] for i in chips['items']],
                         ['confirm_pending', 'cancel_pending'])
        # The chip carries the key only — never the tool or its arguments.
        self.assertEqual(set(chips['items'][0]['action']), {'type', 'key'})


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestHardening(TransactionCase):

    def test_open_action_respects_action_groups(self):
        user = new_test_user(self.env, login='ai_plain_user',
                             groups='base.group_user')
        action = self.env['ir.actions.act_window'].create({
            'name': 'Admins only', 'res_model': 'res.partner',
            'groups_id': [(6, 0, [self.env.ref('base.group_system').id])],
        })
        self.env['ir.model.data'].create({
            'module': 'ab_ai_agent_test', 'name': 'admins_only_action',
            'model': action._name, 'res_id': action.id})
        res = td._builtin_open_action(
            self.env(user=user), xmlid='ab_ai_agent_test.admins_only_action')
        self.assertIn('error', res)
        self.assertNotIn('action', res)
        ok = td._builtin_open_action(
            self.env, xmlid='ab_ai_agent_test.admins_only_action')
        self.assertIn('action', ok)

    def test_hr_tools_need_an_hr_role(self):
        if 'hr.leave' not in self.env or 'hr.attendance' not in self.env:
            self.skipTest('hr_holidays / hr_attendance not installed')
        user = new_test_user(self.env, login='ai_no_hr', groups='base.group_user')
        env = self.env(user=user)
        for fn in (td._builtin_hr_leave_pending,
                   td._builtin_hr_attendance_open_shifts,
                   td._builtin_hr_attendance_missing_today):
            res = fn(env)
            self.assertEqual(res.get('error'), 'not permitted', fn.__name__)

    def test_semantic_search_rejects_injected_columns(self):
        Index = self.env.get('ai.semantic.index')
        if Index is None:
            self.skipTest('no semantic index')
        rows = Index.search('res.partner', 'anything',
                            hint_fields=['name" FROM res_users --'])
        self.assertEqual(rows, [])
        res = td._builtin_semantic_search(
            self.env, model='res.partner', query='x', vector_col='x; drop')
        self.assertIn('error', res)

    def test_single_cache_break_after_invariant_blocks(self):
        agent = self.env['ai.agent'].search([], limit=1)
        prompt = _compose_system_prompt(self.env, agent, locale='en',
                                        user_question='hello')
        self.assertEqual(prompt.count(CACHE_BREAK), 1)
        stable = prompt.split(CACHE_BREAK)[0]
        self.assertNotIn('## Today', stable)
        if agent.all_tool_ids:
            self.assertIn('## Tool', stable)

    def test_claude_payload_caches_only_the_stable_block(self):
        from unittest.mock import patch, MagicMock
        Service = self.env['ai.provider.service']
        config = MagicMock(claude_model='claude-x', max_tokens=10,
                           temperature=0, timeout=5)
        config._get_decrypted_key.return_value = 'k'
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(json)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {
                'content': [{'type': 'text', 'text': 'hi'}],
                'usage': {'input_tokens': 1, 'output_tokens': 1}}
            return resp
        stable = 'S' * 9000
        with patch.object(type(Service), '_provider_cache_enabled', return_value=True), \
                patch('odoo.addons.ab_ai_base.models.ai_service.requests.post', fake_post):
            try:
                Service._call_claude('q', config,
                                     system_prompt=f'{stable}\n\n{CACHE_BREAK}\n\nvolatile')
            except Exception:
                pass    # response parsing details don't matter here
        system = captured.get('system')
        self.assertIsInstance(system, list)
        self.assertEqual(system[0]['text'].strip(), stable)
        self.assertIn('cache_control', system[0])
        self.assertEqual(system[1]['text'], 'volatile')
        self.assertNotIn('cache_control', system[1])


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestScreenButton(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env:
            cls.skipTest(cls, 'sale not installed')
        cls.user = new_test_user(
            cls.env, login='ai_btn_user',
            groups='base.group_user,sales_team.group_sale_salesman_all_leads,'
                   'ab_ai_agent.group_ai_agent_user')
        partner = cls.env['res.partner'].create({'name': 'Button Co'})
        product = cls.env['product.product'].create({'name': 'Button Product'})
        cls.so = cls.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})]})

    def _call(self, button, confirmed=False):
        return td._builtin_screen_button(
            self.env(user=self.user), model='sale.order', record_id=self.so.id,
            button=button, _ai_confirmed=confirmed)

    def test_visible_header_button_is_proposed_then_confirmed(self):
        res = self._call('action_confirm')
        self.assertTrue(res.get('requires_confirmation'), res)
        self.assertEqual(self.so.state, 'draft')
        out = self.env(user=self.user)['ai.agent.pending.action'].resolve(
            res['confirmation']['key'], True)
        self.assertTrue(out['ok'], out)
        self.assertEqual(self.so.state, 'sale')

    def test_button_can_be_named_by_its_label(self):
        res = self._call('Confirm')
        self.assertTrue(res.get('requires_confirmation'), res)

    def test_methods_not_in_the_users_header_are_refused(self):
        for name in ('unlink', 'write', 'copy', '_action_confirm', 'action_nonexistent'):
            res = self._call(name)
            self.assertIn('error', res, name)
            self.assertFalse(res.get('requires_confirmation'), name)
        self.assertEqual(self.so.state, 'draft')

    def test_screen_topic_reaches_the_default_assistant(self):
        agent = self.env['ai.agent'].search([('code', '=', 'ghaima_assistant')], limit=1)
        if not agent:
            self.skipTest('no default assistant')
        agent._heal_core_topics()
        self.assertIn('screen_button', agent.all_tool_ids.mapped('code'))
