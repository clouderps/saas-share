# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher
from odoo.addons.ab_ai_agent_cache.services import answer_cache as ac


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestAnswerCache(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='ac_user',
                                 groups='base.group_user,ab_ai_agent.group_ai_agent_user')
        cls.other = new_test_user(cls.env, login='ac_other',
                                  groups='base.group_user,base.group_partner_manager,'
                                         'ab_ai_agent.group_ai_agent_user')
        cls.agent = cls.env['ai.agent'].search([('code', '=', 'ghaima_assistant')], limit=1) \
            or cls.env['ai.agent'].search([], limit=1)
        cls.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.answer_cache', 'True')

    def test_normalize_arabic(self):
        self.assertEqual(ac.normalize('أَيْنَ الفاتورةُ ٣؟'), ac.normalize('اين الفاتوره 3'))
        self.assertEqual(ac.normalize('Where  is  it?'), 'where is it')

    def _howto(self, env, q='Where do I create a vendor bill?'):
        env_ = {'response': 'Accounting > Vendors > Bills', 'render': None, 'action': None}
        return ac.store(env, agent=self.agent, question=q, locale='en', envelope=env_,
                        tool_plan=[{'tool': 'find_menu', 'args': {'query': 'vendor bill'}}],
                        tool_calls=[{'tool': 'find_menu', 'ok': True, 'result': {'matches': []}}])

    def test_howto_hit_same_rights_only(self):
        env = self.env(user=self.user)
        self.assertTrue(self._howto(env))
        hit = ac.lookup(env, agent=self.agent, question='where do i create a vendor bill',
                        locale='en')
        self.assertEqual(hit['response'], 'Accounting > Vendors > Bills')
        self.assertTrue(hit['cache']['hit'])
        # different groups → different key → miss
        self.assertIsNone(ac.lookup(self.env(user=self.other), agent=self.agent,
                                    question='Where do I create a vendor bill?', locale='en'))

    def test_never_cache_writes_failures_or_ungrounded(self):
        env = self.env(user=self.user)
        base = dict(agent=self.agent, locale='en', envelope={'response': 'x'})
        self.assertFalse(ac.store(env, question='q1', tool_plan=[], tool_calls=[], **base))
        self.assertFalse(ac.store(env, question='q2',
                                  tool_plan=[{'tool': 'create_record', 'args': {}}],
                                  tool_calls=[{'ok': True, 'result': {}}], **base))
        self.assertFalse(ac.store(env, question='q3',
                                  tool_plan=[{'tool': 'find_menu', 'args': {}}],
                                  tool_calls=[{'ok': False}], **base))
        self.assertFalse(ac.store(env, question='q4',
                                  tool_plan=[{'tool': 'query_data', 'args': {}}],
                                  tool_calls=[{'ok': True, 'result': {'rows': []}}], **base))

    def test_data_plan_replayed_fresh(self):
        calls = []

        def fake(env, agent=None, **kw):
            calls.append(kw)
            return {'render': {'layout': 'report', 'title': 'T',
                               'blocks': [{'type': 'text', 'text': str(len(calls))}]},
                    'summary': f'run {len(calls)}'}
        old = tool_dispatcher.get('recent_records')
        tool_dispatcher.register('recent_records', fake)
        try:
            tool = self.env['ai.agent.tool'].search([('code', '=', 'recent_records')], limit=1)
            if not tool or tool not in self.agent.all_tool_ids:
                self.skipTest('recent_records not on the agent')
            env = self.env(user=self.user)
            first = fake(env)
            self.assertTrue(ac.store(env, agent=self.agent, question='latest invoices',
                                     locale='en', envelope={'response': 'run 1'},
                                     tool_plan=[{'tool': 'recent_records',
                                                 'args': {'model': 'account.move'}}],
                                     tool_calls=[{'ok': True, 'result': first}]))
            hit = ac.lookup(env, agent=self.agent, question='Latest invoices', locale='en')
            self.assertEqual(hit['response'], 'run 2')            # re-ran, not reused
        finally:
            tool_dispatcher.register('recent_records', old)

    def test_switch_off(self):
        env = self.env(user=self.user)
        self._howto(env, 'q switch')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.answer_cache', 'False')
        self.assertIsNone(ac.lookup(env, agent=self.agent, question='q switch', locale='en'))
