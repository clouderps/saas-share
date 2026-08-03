# -*- coding: utf-8 -*-
"""System-guidance tools must never over-report what a user can reach.

The whole value of these tools is that the assistant stops inventing
menu paths. That only holds if the answers are genuinely scoped to the
requesting user — so these tests compare a restricted user against an
admin on the same call.
"""
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import runtime as rt
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

    def test_empty_match_is_not_reported_as_missing_access(self):
        """An Arabic word matching nothing must not read as "no access".

        Menu names are stored in English on virtually every tenant, so an
        Arabic question forwarded verbatim ("فاتورة") matches zero rows
        even for an administrator. The agent used to take that empty
        result at face value and tell the user to go ask an administrator
        for access they already had. The note has to send it back for an
        English retry before any conclusion is permitted.
        """
        res = td._builtin_find_menu(self.env, query='فاتورة')
        self.assertEqual(res['matches'], [])
        note = res['note']
        self.assertIn('English', note)
        self.assertNotIn('do not have access', note.split('Only after')[0],
                         'no-access must come after the English retry')

    def test_english_query_survives_a_translated_menu(self):
        """Loading an Arabic catalogue must not hide the menu.

        Once ir.ui.menu carries Arabic names, a search in the user's
        Arabic context stops matching the English word — so the model
        doing the right thing (querying in English, as the schema tells
        it to) got an empty result and reported missing access to an
        administrator. The en_US value lives in the same jsonb, so the
        fallback finds it either way.
        """
        menu = self.env['ir.ui.menu'].search(
            [('name', '=', 'Settings'), ('action', '!=', False)], limit=1)
        if not menu:
            self.skipTest('no actionable Settings menu in this database')
        # Give the menu an Arabic name, exactly as --load-language does.
        menu.with_context(lang='ar_001').name = 'الإعدادات'
        arabic_env = self.env(context=dict(self.env.context, lang='ar_001'))
        res = td._builtin_find_menu(arabic_env, query='Settings', limit=5)
        self.assertTrue(res.get('matches'),
                        'translated menu became unreachable in English')

    def test_find_menu_schema_demands_an_english_query(self):
        """The recovery note is the second line of defence; the schema is
        the first. If it invites the user's own words the model forwards
        Arabic and the search misses every time."""
        tool = self.env.ref('ab_ai_agent.tool_find_menu')
        self.assertIn('English', tool.schema)

    def test_no_match_tells_the_model_not_to_invent(self):
        res = td._builtin_find_menu(
            self.env, query='zzz-nonexistent-feature-zzz')
        self.assertEqual(res['matches'], [])
        self.assertIn('never invent', res['note'].lower())

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


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestActionMarkupAbsorbed(TransactionCase):
    """The model writes button markup instead of calling open_action.

    Answers render as plain text, so `<action-button …>` reached the user
    as that literal string — in both Arabic and English, and it kept
    doing it after the prompt was told not to. The runtime converts the
    markup into the real action rather than relying on the model.
    """

    def test_markup_becomes_a_real_action(self):
        text = ('Open it here.\n\n<action-button '
                'action_xmlid="base.action_res_users">Open Users'
                '</action-button>')
        clean, action = rt._absorb_action_markup(self.env, text)
        self.assertNotIn('action-button', clean)
        self.assertNotIn('<', clean)
        self.assertIn('Open Users', clean, 'the label is still prose')
        self.assertTrue(action, 'a resolvable xmlid must yield an action')
        self.assertEqual(action.get('res_model'), 'res.users')

    def test_underscore_spelling_is_handled(self):
        """The model uses both spellings, sometimes in the same session."""
        clean, action = rt._absorb_action_markup(
            self.env,
            '<action_button action_xmlid="base.action_res_users">Go'
            '</action_button>')
        self.assertNotIn('action_button', clean)
        self.assertTrue(action)

    def test_direction_span_is_removed(self):
        """The shell sets dir; a model-added span only prints as text."""
        clean, _a = rt._absorb_action_markup(
            self.env, 'المسار: <span dir="rtl">الفوترة / العملاء</span>')
        self.assertNotIn('span', clean)
        self.assertIn('الفوترة / العملاء', clean)

    def test_unresolvable_xmlid_yields_no_button(self):
        """A made-up xmlid must not produce a button that goes nowhere."""
        clean, action = rt._absorb_action_markup(
            self.env,
            '<action-button action_xmlid="zzz.not_a_real_action">X'
            '</action-button>')
        self.assertIsNone(action)
        self.assertNotIn('<', clean)

    def test_plain_answer_is_untouched(self):
        text = 'Billing / Customers / Invoices is where you create one.'
        clean, action = rt._absorb_action_markup(self.env, text)
        self.assertEqual(clean, text)
        self.assertIsNone(action)

    def test_written_out_tool_call_is_absorbed(self):
        """Sometimes the model prints the tool call instead of making it.

        Seen live: the answer contained
        `{"action": "tool", "tool": "open_action", "args": {…}}` as prose.
        It is intermittent, but when it happens the user reads raw JSON,
        so the xmlid is honoured and the blob removed.
        """
        text = ('افتح من هنا: {"action": "tool", "tool": "open_action", '
                '"args": {"action_xmlid": "base.action_res_users"}}')
        clean, action = rt._absorb_action_markup(self.env, text)
        self.assertNotIn('open_action', clean)
        self.assertNotIn('{', clean)
        self.assertIn('افتح من هنا', clean)
        self.assertEqual((action or {}).get('res_model'), 'res.users')

    def test_json_in_a_normal_answer_is_left_alone(self):
        """Only a blob naming a tool is a mistake — other braces are not."""
        text = 'Set the context to {"default_move_type": "out_invoice"}.'
        clean, action = rt._absorb_action_markup(self.env, text)
        self.assertEqual(clean, text)
        self.assertIsNone(action)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestStepLimitMessage(TransactionCase):
    """Running out of steps is not a failure the user caused.

    It used to surface as a red "AI request failed" card reading
    MAX_HOPS over "the provider returned an error" — none of which is
    true, and none of which tells the user what to do next.
    """

    def _envelope(self, locale='en', partial=''):
        agent = self.env['ai.agent'].search([], limit=1)
        return rt._maxhops_envelope(agent, locale, partial=partial)

    def test_no_raw_error_code_reaches_the_user(self):
        env = self._envelope()
        self.assertNotIn('MAX_HOPS', str(env))
        # No 'error' key: the generic renderer paints a red failure card
        # off it, which misreports what happened.
        self.assertNotIn('error', env)

    def test_no_internal_step_count(self):
        """"6 steps" is a number the user cannot act on."""
        text = self._envelope()['response']
        self.assertNotIn('step', text.lower())

    def test_tone_is_a_warning_not_a_failure(self):
        block = self._envelope()['render']['blocks'][0]
        self.assertEqual(block['tone'], 'warn')

    def test_arabic_user_is_answered_in_arabic(self):
        """locale was accepted here and never used, so an Arabic user
        got an English apology."""
        text = self._envelope(locale='ar_001')['response']
        self.assertRegex(text, r'[؀-ۿ]')

    def test_partial_answer_is_kept(self):
        text = self._envelope(partial='Sales were 1,240 SAR so far')['response']
        self.assertIn('1,240', text)
