# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAgentConsole(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env['ai.agent'].create({
            'name': 'Console Test', 'code': 'console_test_agent',
            'system_prompt': 'Be brief.', 'company_ids': [(5, 0, 0)],
        })
        cls.user = cls.env['res.users'].create({
            'name': 'Console User', 'login': 'console_user_t',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_payload_and_kpis(self):
        Run = self.env['ai.agent.run'].sudo()
        for state, cost in (('done', 0.02), ('done', 0.04), ('error', 0.0)):
            Run.create({'agent_id': self.agent.id, 'user_id': self.env.uid,
                        'question': 'q', 'state': state, 'cost_usd': cost})
        k = self.agent.console_payload()['kpis']
        self.assertEqual(k['runs'], 3)
        self.assertEqual(k['done'], 2)
        self.assertAlmostEqual(k['avg_cost_usd'], 0.03)
        self.assertAlmostEqual(k['success_rate'], 66.7)

    def test_plain_user_reads_but_cannot_save(self):
        agent = self.agent.with_user(self.user)
        payload = agent.console_payload()
        self.assertFalse(payload['can_edit'])
        with self.assertRaises(AccessError):
            agent.console_save({'max_hops': 2})

    def test_save_whitelist(self):
        self.agent.console_save({'max_hops': 4, 'is_system': True,
                                 'run_count': 99})
        self.assertEqual(self.agent.max_hops, 4)
        self.assertFalse(self.agent.is_system)
        self.assertEqual(self.agent.run_count, 0)

    def test_run_rows_read_only_for_users(self):
        with self.assertRaises(AccessError):
            self.env['ai.agent.run'].with_user(self.user).create({
                'agent_id': self.agent.id, 'user_id': self.user.id,
                'question': 'forged'})
