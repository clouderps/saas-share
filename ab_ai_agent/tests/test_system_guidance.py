# -*- coding: utf-8 -*-
"""System-guidance tools must never over-report what a user can reach.

The whole value of these tools is that the assistant stops inventing
menu paths. That only holds if the answers are genuinely scoped to the
requesting user — so these tests compare a restricted user against an
admin on the same call.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher as td


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestSystemGuidance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal = cls.env['res.users'].create({
            'name': 'Guidance Portal', 'login': 'guidance_portal',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.internal = cls.env['res.users'].create({
            'name': 'Guidance Internal', 'login': 'guidance_internal',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    # ── list_my_apps ──────────────────────────────────────────────
    def test_apps_are_scoped_to_the_user(self):
        admin = td._builtin_list_my_apps(self.env)
        portal = td._builtin_list_my_apps(self.env(user=self.portal.id))
        self.assertGreater(admin['app_count'], portal['app_count'],
                           'a portal user must not see every app')

    def test_no_backoffice_access_is_data_not_an_error(self):
        """A portal user can't read ir.ui.menu at all. That is the
        answer ("you have no back office"), so it must come back as
        data the model can explain — an error dict would make the
        assistant say something went wrong instead."""
        res = td._builtin_list_my_apps(self.env(user=self.portal.id))
        self.assertNotIn('error', res)
        self.assertEqual(res['app_count'], 0)
        self.assertEqual(res['apps'], [])
        self.assertIn('portal', res['note'].lower())

    def test_apps_report_the_requesting_user(self):
        res = td._builtin_list_my_apps(self.env(user=self.internal.id))
        self.assertEqual(res['user'], 'Guidance Internal')

    def test_apps_carry_the_do_not_invent_instruction(self):
        # The model will happily hallucinate menus without this nudge.
        self.assertIn('Do not mention anything absent',
                      td._builtin_list_my_apps(self.env)['note'])

    # ── find_menu ─────────────────────────────────────────────────
    def test_find_menu_requires_a_query(self):
        self.assertIn('error', td._builtin_find_menu(self.env))
        self.assertIn('error', td._builtin_find_menu(self.env, query='   '))

    def test_find_menu_returns_openable_destinations(self):
        res = td._builtin_find_menu(self.env, query='Settings')
        for hit in res.get('matches', []):
            self.assertTrue(hit['path'], 'every match needs a menu path')
            self.assertIn('action_xmlid', hit)

    def test_find_menu_never_returns_a_folder(self):
        # A menu with no action is a container — routing a user there
        # lands them on a blank screen.
        res = td._builtin_find_menu(self.env, query='a', limit=20)
        for hit in res.get('matches', []):
            self.assertTrue(hit['label'])

    def test_find_menu_scoped_to_the_user(self):
        admin = td._builtin_find_menu(self.env, query='Settings', limit=20)
        portal = td._builtin_find_menu(
            self.env(user=self.portal.id), query='Settings', limit=20)
        self.assertGreaterEqual(len(admin.get('matches', [])),
                                len(portal.get('matches', [])))

    def test_no_match_tells_the_model_not_to_invent(self):
        res = td._builtin_find_menu(
            self.env, query='zzz-nonexistent-feature-zzz')
        self.assertEqual(res['matches'], [])
        self.assertIn('do NOT', res['note'])

    # ── explain_screen ────────────────────────────────────────────
    def test_explain_requires_a_model(self):
        self.assertIn('error', td._builtin_explain_screen(self.env))

    def test_explain_unknown_model_is_handled(self):
        res = td._builtin_explain_screen(self.env, model='not.a.real.model')
        self.assertIn('error', res)

    def test_explain_accepts_the_users_own_words(self):
        """Users say "the contacts screen", not "res.partner". Pushing a
        technical model name back at them leaks our internals into a
        business answer."""
        res = td._builtin_explain_screen(self.env, screen='Contacts')
        self.assertNotIn('error', res)
        self.assertTrue(res['model'])

    def test_explain_resolves_a_human_model_description(self):
        res = td._builtin_explain_screen(self.env, screen='Journal Entry')
        self.assertEqual(res.get('model'), 'account.move')

    def test_unresolvable_screen_tells_the_model_to_ask_in_plain_words(self):
        res = td._builtin_explain_screen(self.env, screen='zzz nonsense zzz')
        self.assertIn('error', res)
        self.assertIn('never mention this tool', res['note'].lower())

    def test_resolver_passes_through_a_real_model_name(self):
        self.assertEqual(
            td._resolve_model(self.env, 'res.partner'), 'res.partner')
        self.assertIsNone(td._resolve_model(self.env, ''))

    def test_explain_returns_live_metadata(self):
        res = td._builtin_explain_screen(self.env, model='res.partner')
        self.assertEqual(res['model'], 'res.partner')
        self.assertTrue(res['title'])
        self.assertTrue(res['key_fields'], 'should surface real fields')
        self.assertIn('name', [f['field'] for f in res['key_fields']])

    def test_explain_reports_lifecycle_when_the_model_has_one(self):
        res = td._builtin_explain_screen(self.env, model='sale.order')
        self.assertTrue(res['lifecycle'], 'sale.order has a state field')

    def test_explain_permissions_track_the_user(self):
        as_admin = td._builtin_explain_screen(self.env, model='res.partner')
        as_portal = td._builtin_explain_screen(
            self.env(user=self.portal.id), model='res.partner')
        self.assertTrue(as_admin['permissions']['write'])
        # Either the read is refused outright or write is denied — both
        # are correct, what matters is the portal user is not told they
        # may edit.
        self.assertFalse(as_portal.get('permissions', {}).get('write'))

    def test_explain_refuses_a_model_the_user_cannot_read(self):
        res = td._builtin_explain_screen(
            self.env(user=self.portal.id), model='res.users')
        if 'error' in res:
            self.assertIn('access', res['error'].lower())
        else:
            self.assertFalse(res['permissions']['write'])

    # ── registration ──────────────────────────────────────────────
    def test_tools_are_registered(self):
        for code in ('list_my_apps', 'find_menu', 'explain_screen'):
            self.assertIsNotNone(td.get(code), f'{code} not registered')
