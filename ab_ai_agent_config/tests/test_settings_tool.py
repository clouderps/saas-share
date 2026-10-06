# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ab_ai_agent_config.services.settings_tool import update_settings


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestSettingsTool(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, login='st_admin',
                                  groups='base.group_user,base.group_system,'
                                         'ab_ai_agent.group_ai_agent_user')
        cls.plain = new_test_user(cls.env, login='st_plain', groups='base.group_user')

    def test_plain_user_refused(self):
        res = update_settings(self.env(user=self.plain), settings={'multi_currency': True})
        self.assertEqual(res.get('error'), 'not permitted')

    def test_list_and_unknown_code(self):
        env = self.env(user=self.admin)
        listed = update_settings(env)
        codes = [o['code'] for o in listed['options']]
        self.assertIn('multi_currency', codes)
        self.assertNotIn('lock_date', codes) if 'fiscalyear_lock_date' not in \
            self.env['res.config.settings']._fields else None
        res = update_settings(env, settings={'web_base_url': 'x'})
        self.assertIn('error', res)

    def test_toggle_multi_currency_confirm_first(self):
        env = self.env(user=self.admin)
        group = self.env.ref('base.group_multi_currency')
        was = group in self.env.ref('base.group_user').implied_ids
        res = update_settings(env, settings={'multi_currency': not was})
        self.assertTrue(res.get('requires_confirmation'), res)
        self.assertIn('→', '\n'.join(res['confirmation']['details']))
        self.assertEqual(group in self.env.ref('base.group_user').implied_ids, was)  # unchanged
        out = env['ai.agent.pending.action'].resolve(res['confirmation']['key'], True)
        self.assertTrue(out['ok'], out)
        self.assertEqual(group in self.env.ref('base.group_user').implied_ids, not was)
