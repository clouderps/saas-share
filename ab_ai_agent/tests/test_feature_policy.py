# -*- coding: utf-8 -*-
"""Phase 1 (MCP + AI plan v2): feature policy + per-user activation."""
import importlib.util
import json
import os
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.ab_ai_agent.tests.common import new_test_user

from odoo.addons.ab_ai_agent.models import ai_feature_policy as fp


def ceiling(env, value):
    """Stand-in for a SaaS bridge overriding ai.feature.policy._ceiling."""
    return patch.object(type(env['ai.feature.policy']), '_ceiling', lambda self: value)
from odoo.addons.ab_ai_agent.services import tool_dispatcher as td

_spec = importlib.util.spec_from_file_location('ab_ai_agent_mig_1_20', os.path.join(
    os.path.dirname(__file__), '..', 'migrations', '18.0.1.20.0', 'post-migrate.py'))
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)



@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestPolicyMath(TransactionCase):

    def setUp(self):
        super().setUp()
        self.P = self.env['ai.feature.policy']
        self.ICP = self.env['ir.config_parameter'].sudo()

    def test_combine_rules(self):
        self.assertEqual(fp.combine('limit', 0, 5), 5)
        self.assertEqual(fp.combine('limit', 3, 5), 3)
        self.assertEqual(fp.combine('limit', 0, 0), 0)
        self.assertEqual(fp.combine('list', None, frozenset('ab')), frozenset('ab'))
        self.assertEqual(fp.combine('list', frozenset('abc'), frozenset('bcd')), frozenset('bc'))
        self.assertTrue(fp.combine('bool', True, True))
        self.assertFalse(fp.combine('bool', True, False))
        self.assertTrue(fp.combine('kill', False, True))
        self.assertEqual(fp.combine('enum', 'self', 'admin', ('admin', 'self')), 'admin')
        self.assertEqual(fp.combine('enum', 'catalog_byok', 'catalog',
                                    ('none', 'catalog', 'catalog_byok')), 'catalog')

    def test_no_ceiling_uses_local_settings(self):
        self.assertIsNone(self.P._ceiling())
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '7')
        self.assertEqual(self.P.get('assistant.max_users'), 7)
        self.assertEqual(self.P.get('assistant.activation'), 'self')
        self.assertTrue(self.P.get('assistant.enabled'))
        self.assertFalse(self.P.get('kill'))

    def test_ceiling_override(self):
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '0')
        self.ICP.set_param('ab_ai_agent.feature.model.tiers', 'fast,balanced')
        cap = {'assistant.max_users': 3, 'assistant.voice': False,
                   'model.tiers': ['balanced', 'premium'], 'assistant.activation': 'admin'}
        with ceiling(self.env, cap):
            self.assertEqual(self.P.get('assistant.max_users'), 3)
            self.assertFalse(self.P.get('assistant.voice'))
            self.assertEqual(self.P.get('model.tiers'), frozenset({'balanced'}))
            self.assertEqual(self.P.get('assistant.activation'), 'admin')
            self.assertTrue(self.P.get('assistant.actions'))  # not capped

    def test_agents_max_reads_old_param(self):
        self.ICP.set_param('ab_ai_agent.max_agents', '4')
        self.assertEqual(self.env['ai.agent']._agent_limit(), 4)
        with ceiling(self.env, {'agents.max': 2}):
            self.assertEqual(self.env['ai.agent']._agent_limit(), 2)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestActivation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '0')
        self.ICP.set_param('ab_ai_agent.assistant_activation', 'self')

    def _user(self, login):
        return new_test_user(self.env, login=login,
                             groups='base.group_user,ab_ai_agent.group_ai_agent_user')

    def test_self_activation_default_on_and_self_writeable(self):
        u = self._user('fp_self')
        self.assertTrue(u.ai_assistant_active)
        self.assertTrue(u._ai_assistant_allowed())
        u.with_user(u).write({'ai_assistant_active': False})
        self.assertFalse(u.ai_assistant_active)
        self.assertFalse(u.with_user(u)._ai_assistant_info()['enabled'])

    def test_admin_activation_default_off_and_not_self_writeable(self):
        self.ICP.set_param('ab_ai_agent.assistant_activation', 'admin')
        u = self._user('fp_admin')
        self.assertFalse(u.ai_assistant_active)
        with self.assertRaises(AccessError):
            u.with_user(u).write({'ai_assistant_active': True})
        u.write({'ai_assistant_active': True})  # an administrator can
        self.assertTrue(u._ai_assistant_allowed())

    def test_seat_limit(self):
        used = self.env['res.users']._ai_seats_used()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', str(used + 1))
        a = self._user('fp_seat_a')
        self.assertTrue(a.ai_assistant_active)
        b = self._user('fp_seat_b')        # no seat free: created inactive
        self.assertFalse(b.ai_assistant_active)
        with self.assertRaises(ValidationError):
            b.write({'ai_assistant_active': True})

    def test_downgrade_keeps_earliest_activations(self):
        a = self._user('fp_dn_a')
        b = self._user('fp_dn_b')
        b.ai_assistant_activated_on = '2999-01-01 00:00:00'   # latest activation
        used = self.env['res.users']._ai_seats_used()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', str(used - 1))
        self.assertTrue(a._ai_assistant_allowed())
        self.assertEqual(b._ai_assistant_block_reason(), 'no_seat')
        self.assertTrue(b.ai_assistant_active)   # flag kept, just inert

    def test_kill_switch_and_disabled(self):
        u = self._user('fp_kill')
        self.ICP.set_param('ab_ai_agent.kill_switch', 'True')
        self.assertEqual(u._ai_assistant_block_reason(), 'killed')
        self.assertFalse(u._ai_assistant_info()['enabled'])
        self.ICP.set_param('ab_ai_agent.kill_switch', 'False')
        self.ICP.set_param('ab_ai_agent.assistant_enabled', 'False')
        self.assertEqual(u._ai_assistant_block_reason(), 'disabled')

    def test_voice_gate(self):
        u = self._user('fp_voice')
        self.ICP.set_param('ab_ai_agent.voice_enabled', 'True')
        self.assertTrue(u._ai_assistant_info()['voice'])
        with ceiling(self.env, {'assistant.voice': False}):
            self.assertFalse(u._ai_assistant_info()['voice'])
        u.ai_assistant_active = False
        self.assertFalse(u._ai_assistant_info()['voice'])

    def test_migration_activates_internal_users(self):
        u = self._user('fp_mig')
        self.env.cr.execute("UPDATE res_users SET ai_assistant_active = FALSE WHERE id = %s", (u.id,))
        _mig.migrate(self.env.cr, '18.0.1.19.0')
        u.invalidate_recordset()
        self.assertTrue(u.ai_assistant_active)
        self.assertTrue(u._ai_assistant_allowed())


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestDispatchGates(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '0')
        self.user = new_test_user(self.env, login='fp_disp',
                                  groups='base.group_user,ab_ai_agent.group_ai_agent_user')
        self.env_u = self.env(user=self.user)
        self.agent = self.env['ai.agent'].get_default().with_env(self.env_u)
        self.read_tool = self.env_u['ai.agent.tool'].search([('code', '=', 'date_reference')], limit=1)

    def test_kill_blocks_dispatch_and_confirm(self):
        self.assertTrue(td.dispatch(self.env_u, self.read_tool, {}, agent=self.agent)['ok'])
        self.ICP.set_param('ab_ai_agent.kill_switch', 'True')
        out = td.dispatch(self.env_u, self.read_tool, {}, agent=self.agent)
        self.assertEqual(out['error'], 'assistant_off')
        out = td.dispatch_confirmed(self.env_u, 'create_record', {}, agent=self.agent)
        self.assertFalse(out['ok'])
        self.assertEqual(out['error'], 'assistant_off')

    def test_inactive_user_blocked(self):
        self.user.ai_assistant_active = False
        out = td.dispatch(self.env_u, self.read_tool, {}, agent=self.agent)
        self.assertEqual(out['error'], 'assistant_off')

    def test_actions_policy_blocks_confirm(self):
        with ceiling(self.env, {'assistant.actions': False}):
            out = td.dispatch_confirmed(self.env_u, 'create_record', {}, agent=self.agent)
        self.assertEqual(out['error'], 'actions_off')


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestRunRoute(HttpCase):

    def _post(self, url, params):
        res = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                                                  'params': params}),
                            headers={'Content-Type': 'application/json'})
        return res.json()['result']

    def test_run_refused_when_inactive_or_killed(self):
        u = new_test_user(self.env, login='fp_run', password='fp_run_pw',
                          groups='base.group_user,ab_ai_agent.group_ai_agent_user')
        u.ai_assistant_active = False
        self.authenticate('fp_run', 'fp_run_pw')
        res = self._post('/ai_agent/run', {'message': 'hi'})
        self.assertEqual(res.get('error'), 'assistant_unavailable')
        self.assertEqual(res.get('reason'), 'inactive')
        u.ai_assistant_active = True
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.kill_switch', 'True')
        res = self._post('/ai_agent/run', {'message': 'hi'})
        self.assertEqual(res.get('reason'), 'killed')
        res = self._post('/ai_agent/voice/transcribe', {'audio': 'x'})
        self.assertFalse(res.get('ok'))


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestReviewFixes(TransactionCase):
    """Planner flow review of Phase 0 + 1 (F1, F2, F3, F5, F8, F9, settings)."""

    def setUp(self):
        super().setUp()
        self.P = self.env['ai.feature.policy']
        self.ICP = self.env['ir.config_parameter'].sudo()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '0')
        self.ICP.set_param('ab_ai_agent.assistant_activation', 'self')

    def _user(self, login):
        return new_test_user(self.env, login=login,
                             groups='base.group_user,ab_ai_agent.group_ai_agent_user')

    def test_user_can_switch_back_on_in_self_mode(self):
        u = self._user('rf_self')
        u.with_user(u).write({'ai_assistant_active': False})
        u.ai_assistant_activated_on = False
        u.with_user(u).write({'ai_assistant_active': True})     # F1: was AccessError
        self.assertTrue(u.ai_assistant_active)
        self.assertTrue(u.ai_assistant_activated_on)
        with self.assertRaises(AccessError):                    # the date stays admin-only
            u.with_user(u).write({'ai_assistant_activated_on': '2000-01-01 00:00:00'})

    def test_runtime_run_spends_nothing_when_blocked(self):
        from odoo.addons.ab_ai_agent.services import llm_adapter, runtime
        u = self._user('rf_run')
        env_u = self.env(user=u)
        agent = self.env['ai.agent'].get_default().with_env(env_u)
        for setup, reason in ((lambda: u.write({'ai_assistant_active': False}), 'inactive'),
                              (lambda: self.ICP.set_param('ab_ai_agent.kill_switch', 'True'),
                               'killed')):
            setup()
            with patch.object(llm_adapter, 'call_llm') as llm:
                text, run, envelope = runtime.run(env_u, agent=agent, user_question='hi')
            llm.assert_not_called()
            self.assertEqual(envelope['error'], 'ASSISTANT_UNAVAILABLE')
            self.assertEqual(envelope['reason'], reason)
            self.assertEqual(run.state, 'cancelled')
            self.assertTrue(text)

    def test_confirm_after_kill_says_not_allowed(self):
        u = self._user('rf_kill')
        Pending = self.env(user=u, context={'lang': 'en_US'})['ai.agent.pending.action']
        key = Pending.propose('create_record', {})['confirmation']['key']
        self.ICP.set_param('ab_ai_agent.kill_switch', 'True')
        res = Pending.resolve(key, True)
        self.assertFalse(res['ok'])
        self.assertEqual(res['message'], 'That action is not allowed any more.')

    def test_user_cannot_forge_a_pending_action(self):
        u = self._user('rf_forge')
        Pending = self.env(user=u)['ai.agent.pending.action']
        with self.assertRaises(AccessError):
            Pending.create({'key': 'forged', 'tool_code': 'create_record', 'args_json': '{}'})
        out = Pending.propose('create_record', {})              # the tool path still works
        row = Pending.search([('key', '=', out['confirmation']['key'])])
        self.assertEqual(row.user_id, u)

    def test_unreadable_ceiling_fails_closed(self):
        self.ICP.set_param('ab_ai_agent.assistant_max_users', '4')
        self.ICP.set_param('ab_ai_agent.feature.model.tiers', 'fast')
        cap = {'assistant.activation': 'bogus', 'assistant.max_users': 'many',
               'model.tiers': '', 'model.regions': [], 'model.choice': 'everything'}
        with ceiling(self.env, cap):
            self.assertEqual(self.P.get('assistant.activation'), 'admin')
            self.assertEqual(self.P.get('assistant.max_users'), 4)      # local kept
            self.assertEqual(self.P.get('model.tiers'), frozenset())
            self.assertEqual(self.P.get('model.regions'), frozenset())
            self.assertEqual(self.P.get('model.choice'), 'none')

    def test_batch_create_fills_free_seats_only(self):
        used = self.env['res.users']._ai_seats_used()
        self.ICP.set_param('ab_ai_agent.assistant_max_users', str(used + 2))
        group = self.env.ref('base.group_user').id
        users = self.env['res.users'].create([
            {'name': 'RF %s' % i, 'login': 'rf_batch_%s' % i, 'groups_id': [(6, 0, [group])]}
            for i in range(4)])
        self.assertEqual(users.mapped('ai_assistant_active'), [True, True, False, False])

    def test_settings_can_switch_default_on_flags_off(self):
        self.env['res.config.settings'].create({
            'ai_assistant_enabled': False, 'ai_actions_enabled': False,
            'ai_voice_enabled': False}).set_values()
        self.assertFalse(self.P.get('assistant.enabled'))
        self.assertFalse(self.P.get('assistant.actions'))
        self.assertFalse(self.P.get('assistant.voice'))
        self.env['res.config.settings'].create({
            'ai_assistant_enabled': True, 'ai_actions_enabled': True,
            'ai_voice_enabled': True}).set_values()
        self.assertTrue(self.P.get('assistant.enabled'))
