# -*- coding: utf-8 -*-
"""One assistant, one memory, whichever surface you came in through.

There used to be three doors onto the same agent — the "Ask AI" menu,
the floating bubble and this console — and the console alone kept no
history at all. Same user, same assistant, two different memories
depending on which one they clicked.

These pin the seam that fixed it. They skip cleanly when ab_ai_chatbot
is absent: ab_ai_agent ships in saas-share and must still install on a
database that has no chat history model at all.
"""
import json

from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestSharedHistory(HttpCase):

    def setUp(self):
        super().setUp()
        if self.env.get('ai.chat.conversation') is None:
            self.skipTest('ab_ai_chatbot not installed')
        # Own user with a known password rather than assuming admin/admin
        # — these run against whatever database is to hand, and the real
        # tenants do not use the default credentials.
        self.chat_user = self.env['res.users'].create({
            'name': 'Shared History User',
            'login': 'shared-history-test',
            'password': 'shared-history-test-pw',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.env = self.env(user=self.chat_user)
        self.authenticate('shared-history-test', 'shared-history-test-pw')

    def _call(self, route, **params):
        res = self.url_open(
            route,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'},
        )
        return res.json().get('result') or {}

    # ── open ──────────────────────────────────────────────────────
    def test_open_resumes_rather_than_starting_blank(self):
        """Reopening must land on the last chat, not a blank screen.

        Arriving at an empty console when the bubble beside it still
        remembered the thread is precisely what made the two feel like
        different products.
        """
        conv = self.env['ai.chat.conversation'].create({'name': 'Resume me'})
        self.env['ai.chat.message'].create({
            'conversation_id': conv.id, 'role': 'user', 'content': 'hello'})
        res = self._call('/ai_agent/conversation/open')
        self.assertTrue(res.get('available'))
        self.assertEqual(res['conversation_id'], conv.id)
        self.assertTrue(res['messages'])

    def test_open_honours_an_explicit_id(self):
        """The bubble's expand button passes the chat it was showing.

        Ignoring it and opening "the most recent" instead would drop the
        user into a different thread than the one they were reading.
        """
        Conv = self.env['ai.chat.conversation']
        older = Conv.create({'name': 'The one being read'})
        Conv.create({'name': 'A newer chat'})       # would win by default
        res = self._call('/ai_agent/conversation/open',
                         conversation_id=older.id)
        self.assertEqual(res['conversation_id'], older.id)

    def test_open_creates_one_when_there_is_nothing_to_resume(self):
        self.env['ai.chat.conversation'].search(
            [('user_id', '=', self.chat_user.id)]).unlink()
        res = self._call('/ai_agent/conversation/open')
        self.assertTrue(res.get('conversation_id'))

    # ── messages ──────────────────────────────────────────────────
    def test_stored_envelope_survives_a_reload(self):
        """A reopened chart must still be a chart.

        Without envelope_json a stored KPI grid degrades to the sentence
        beside it, so yesterday's answer looks poorer than it was when
        it arrived — which makes history not worth reopening.
        """
        conv = self.env['ai.chat.conversation'].create({'name': 'With blocks'})
        envelope = {'response': 'Sales are up',
                    'blocks': [{'type': 'kpi_grid', 'items': []}]}
        self.env['ai.chat.message'].create({
            'conversation_id': conv.id, 'role': 'assistant',
            'content': 'Sales are up', 'envelope_json': json.dumps(envelope)})
        res = self._call('/ai_agent/conversation/messages',
                         conversation_id=conv.id)
        msg = res['messages'][-1]
        self.assertEqual(msg['envelope']['blocks'][0]['type'], 'kpi_grid')

    def test_broken_envelope_falls_back_to_text(self):
        """Bad JSON must not blank the whole turn."""
        conv = self.env['ai.chat.conversation'].create({'name': 'Broken'})
        self.env['ai.chat.message'].create({
            'conversation_id': conv.id, 'role': 'assistant',
            'content': 'still readable', 'envelope_json': '{not json'})
        res = self._call('/ai_agent/conversation/messages',
                         conversation_id=conv.id)
        msg = res['messages'][-1]
        self.assertIsNone(msg['envelope'])
        self.assertEqual(msg['text'], 'still readable')

    # ── isolation ─────────────────────────────────────────────────
    def test_list_shows_only_standalone_chats(self):
        """Record-anchored chats belong to their record's chatter.

        Mixing them into the console's list would offer to reopen a
        conversation about one specific invoice as if it were a general
        one, with none of that context on screen.
        """
        Conv = self.env['ai.chat.conversation']
        # sudo: an ordinary internal user cannot create contacts, and
        # who owns the anchor is irrelevant to what is being tested.
        partner = self.env['res.partner'].sudo().create({'name': 'Anchor'})
        anchored = Conv.create({'name': 'On a record',
                                'record_ref': f'res.partner,{partner.id}'})
        plain = Conv.create({'name': 'Standalone'})
        ids = [c['id'] for c in self._call(
            '/ai_agent/conversation/list').get('conversations', [])]
        self.assertIn(plain.id, ids)
        self.assertNotIn(anchored.id, ids)

    def test_another_users_chat_is_not_readable(self):
        other = self.env['res.users'].sudo().create({
            'name': 'Someone Else', 'login': 'history-isolation-other',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        theirs = self.env['ai.chat.conversation'].sudo().with_user(
            other).create({'name': 'Private'})
        self.env['ai.chat.message'].sudo().with_user(other).create({
            'conversation_id': theirs.id, 'role': 'user',
            'content': 'SECRET-CONTENT-MARKER'})
        raw = self.url_open(
            '/ai_agent/conversation/messages',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': {'conversation_id': theirs.id}}),
            headers={'Content-Type': 'application/json'},
        ).text
        # Raising or refusing are both fine; leaking is not. Assert on the
        # payload rather than the shape so either outcome passes for the
        # right reason.
        self.assertNotIn('SECRET-CONTENT-MARKER', raw)


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestShare(HttpCase):
    """A shared link is a capability: revoking must be as easy as making."""

    def setUp(self):
        super().setUp()
        if self.env.get('ai.chat.conversation') is None:
            self.skipTest('ab_ai_chatbot not installed')
        self.owner = self.env['res.users'].create({
            'name': 'Share Owner', 'login': 'share-owner-test',
            'password': 'share-owner-test-pw',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.env = self.env(user=self.owner)
        self.authenticate('share-owner-test', 'share-owner-test-pw')
        self.conv = self.env['ai.chat.conversation'].create({'name': 'To share'})

    def _share(self, **params):
        return self.url_open(
            '/ai_agent/conversation/share',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'},
        ).json().get('result') or {}

    def test_share_mints_a_link(self):
        res = self._share(conversation_id=self.conv.id)
        self.assertTrue(res.get('shared'))
        self.assertIn('/ai_chat/shared/', res.get('share_url', ''))

    def test_revoke_clears_the_token(self):
        self._share(conversation_id=self.conv.id)
        res = self._share(conversation_id=self.conv.id, revoke=True)
        self.assertFalse(res.get('shared'))
        self.assertFalse(self.conv.share_token)
        self.assertFalse(self.conv.is_shared)

    def test_cannot_publish_someone_elses_chat(self):
        """Read access is not permission to publish."""
        other = self.env['res.users'].sudo().create({
            'name': 'Not The Owner', 'login': 'share-nonowner-test',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        theirs = self.env['ai.chat.conversation'].sudo().with_user(
            other).create({'name': 'Theirs'})
        res = self._share(conversation_id=theirs.id)
        self.assertFalse(res.get('shared'))
        self.assertFalse(theirs.sudo().is_shared)
