# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.ab_ai_agent.services import tool_dispatcher
from odoo.addons.ab_ai_agent.tests.common import new_test_user

SECRET = 'Traceback-SECRET-xyz'


def _boom(env, agent=None, **kw):
    raise RuntimeError(SECRET)


def _partial_then_boom(env, agent=None, **kw):
    env['res.partner'].create({'name': 'MCP partial write'})
    raise RuntimeError(SECRET)


def _memory_write(env, agent=None, **kw):
    env['res.partner'].create({'name': 'MCP memory write'})
    return {'ok': True}


def _direct_write(env, agent=None, **kw):
    env['res.partner'].create({'name': 'MCP direct write'})
    return {'ok': True}


def _admin_only(env, agent=None, **kw):
    return {'answer': 42}


@tagged('post_install', '-at_install', 'ab_mcp')
class TestMcp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('ab_ai_agent.feature.mcp.enabled', 'True')
        icp.set_param('ab_ai_agent.feature.mcp.write_tools', 'True')
        icp.set_param('ab_ai_agent.actions_enabled', 'True')
        icp.set_param('ab_ai_agent.kill_switch', 'False')
        icp.set_param('ab_ai_agent.feature.mcp.max_calls_day', '0')
        tool_dispatcher.register('mcp_test_boom', _boom)
        tool_dispatcher.register('mcp_test_admin', _admin_only)
        Tool = cls.env['ai.agent.tool'].sudo()
        Tool.create({'name': 'Boom', 'description': 'x', 'code': 'mcp_test_boom', 'dispatch_kind': 'python',
                     'mcp_enabled': True, 'schema': '{"type": "object", "properties": {}}'})
        Tool.create({'name': 'Admin only', 'description': 'x', 'code': 'mcp_test_admin', 'dispatch_kind': 'python',
                     'mcp_enabled': True, 'schema': '{"type": "object", "properties": {}}',
                     'group_ids': [(6, 0, [cls.env.ref('base.group_system').id])]})
        tool_dispatcher.register('mcp_test_partial', _partial_then_boom)
        tool_dispatcher.register('mcp_test_memory', _memory_write)
        tool_dispatcher.register('mcp_test_direct_write', _direct_write)
        empty = '{"type": "object", "properties": {}}'
        Tool.create({'name': 'Partial', 'description': 'x', 'code': 'mcp_test_partial',
                     'dispatch_kind': 'python', 'mcp_enabled': True, 'schema': empty})
        Tool.create({'name': 'Memory', 'description': 'x', 'code': 'mcp_test_memory',
                     'dispatch_kind': 'python', 'category': 'memory', 'is_write_action': True,
                     'mcp_enabled': True, 'schema': empty})
        Tool.create({'name': 'Direct write', 'description': 'x', 'code': 'mcp_test_direct_write',
                     'dispatch_kind': 'python', 'is_write_action': True,
                     'mcp_enabled': True, 'schema': empty})
        server_action = cls.env['ir.actions.server'].sudo().create({
            'name': 'MCP test SA', 'model_id': cls.env.ref('base.model_res_partner').id,
            'state': 'code', 'code': "env['res.partner'].create({'name': 'MCP server action write'})"})
        Tool.create({'name': 'Server action', 'description': 'x', 'code': 'mcp_test_sa',
                     'dispatch_kind': 'server_action', 'server_action_id': server_action.id,
                     'is_write_action': False, 'mcp_enabled': True, 'schema': empty})
        Tool.search([('code', 'in', ('date_reference', 'create_record', 'open_list'))]).write(
            {'mcp_enabled': True})
        cls.user = new_test_user(cls.env, login='mcp_user', groups='base.group_user,base.group_partner_manager')
        cls.admin_user = new_test_user(cls.env, login='mcp_admin', groups='base.group_user,base.group_system')
        (cls.user | cls.admin_user).sudo().write({'ai_assistant_active': True})

    def _token(self, user, **vals):
        vals = dict({'name': 't', 'client': 'claude_code', 'preset': 'manager', 'allow_write': True,
                     'expires_at': fields.Datetime.now() + timedelta(days=30)}, **vals)
        rec, plain = self.env['mcp.token'].with_user(user)._generate(vals)
        return rec, plain

    def _rpc(self, method, params=None, token=None, rid=1, raw=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer %s' % token
        body = raw if raw is not None else json.dumps(
            {'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params or {}})
        return self.url_open('/mcp', data=body, headers=headers)

    def _names(self, token):
        r = self._rpc('tools/list', token=token)
        self.assertEqual(r.status_code, 200, r.text)
        return {t['name'] for t in r.json()['result']['tools']}

    def test_initialize(self):
        _r, tok = self._token(self.user)
        r = self._rpc('initialize', {'protocolVersion': '2025-06-18',
                                     'clientInfo': {'name': 'test-client'}}, token=tok)
        res = r.json()['result']
        self.assertEqual(res['protocolVersion'], '2025-06-18')
        self.assertEqual(res['serverInfo']['name'], 'ghaima')
        self.assertEqual(res['capabilities'], {'tools': {'listChanged': False}})
        r = self._rpc('initialize', {'protocolVersion': '1999-01-01'}, token=tok)
        self.assertEqual(r.json()['result']['protocolVersion'], '2025-11-25')
        r = self._rpc(None, token=tok, raw=json.dumps(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        self.assertEqual(r.status_code, 202)
        self.assertEqual(self._rpc('ping', token=tok).json()['result'], {})
        r = self._rpc(None, token=tok, raw=json.dumps([{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.url_open('/mcp').status_code, 405)

    def test_401(self):
        r = self._rpc('ping')
        self.assertEqual(r.status_code, 401)
        self.assertIn('Bearer', r.headers.get('WWW-Authenticate', ''))
        self.assertEqual(self._rpc('ping', token='gmcp_nope').status_code, 401)

    def test_expired_and_revoked(self):
        rec, tok = self._token(self.user)
        rec.with_user(self.user).action_revoke()
        self.assertEqual(self._rpc('ping', token=tok).status_code, 401)
        rec2, tok2 = self._token(self.user)
        rec2.sudo().write({'expires_at': fields.Datetime.now() - timedelta(minutes=1)})
        self.assertEqual(self._rpc('ping', token=tok2).status_code, 401)

    def test_list_per_group_and_screen_only(self):
        _r, tok_u = self._token(self.user)
        _r, tok_a = self._token(self.admin_user)
        users, admins = self._names(tok_u), self._names(tok_a)
        self.assertIn('date_reference', users)
        self.assertIn('get_proposal_status', users)
        self.assertNotIn('mcp_test_admin', users)
        self.assertIn('mcp_test_admin', admins)
        self.assertNotIn('open_list', users | admins)

    def test_readonly_preset_hides_write(self):
        _r, tok = self._token(self.user, preset='readonly')
        names = self._names(tok)
        self.assertNotIn('create_record', names)
        self.assertIn('date_reference', names)
        _r, tok_m = self._token(self.user)
        self.assertIn('create_record', self._names(tok_m))
        _r, tok_c = self._token(self.user, preset='custom', tool_ids=[(6, 0, self.env['ai.agent.tool'].search(
            [('code', '=', 'date_reference')]).ids)])
        self.assertEqual(self._names(tok_c), {'date_reference'})

    def test_write_call_proposes_only(self):
        _r, tok = self._token(self.user)
        Partner = self.env['res.partner'].sudo()
        before = Partner.search_count([('name', '=', 'MCP Partner X')])
        r = self._rpc('tools/call', {'name': 'create_record', 'arguments': {
            'model': 'res.partner', 'values': {'name': 'MCP Partner X'},
            '_ai_confirmed': True}}, token=tok)
        res = r.json()['result']
        self.assertFalse(res['isError'], res)
        self.assertEqual(res['structuredContent']['status'], 'proposed')
        self.assertIn('15 minutes', res['content'][0]['text'])
        self.assertEqual(Partner.search_count([('name', '=', 'MCP Partner X')]), before)
        row = self.env['ai.agent.pending.action'].sudo().search(
            [('key', '=', res['structuredContent']['key'])])
        self.assertEqual(row.origin, 'mcp')
        self.assertEqual(row.state, 'proposed')
        self.assertEqual(row.target_model, 'res.partner')
        self.assertIn('values / name: MCP Partner X', row.details_text)
        st = self._rpc('tools/call', {'name': 'get_proposal_status',
                                      'arguments': {'key': row.key}}, token=tok).json()['result']
        self.assertEqual(st['structuredContent']['state'], 'proposed')

    def test_kill_switch(self):
        _r, tok = self._token(self.user)
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.kill_switch', 'True')
        r = self._rpc('tools/list', token=tok)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['data']['code'], 'killed')

    def test_mcp_disabled(self):
        _r, tok = self._token(self.user)
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.feature.mcp.enabled', 'False')
        r = self._rpc('tools/list', token=tok)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['data']['code'], 'mcp_disabled')

    def test_quota(self):
        _r, tok = self._token(self.user)
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.feature.mcp.max_calls_day', '2')
        call = {'name': 'date_reference', 'arguments': {}}
        used = self.env['mcp.usage.day'].calls_today()
        for _i in range(max(0, 2 - used)):
            self.assertEqual(self._rpc('tools/call', call, token=tok).status_code, 200)
        r = self._rpc('tools/call', call, token=tok)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()['error']['data']['code'], 'limit_reached')

    def test_no_exception_leak(self):
        _r, tok = self._token(self.user)
        r = self._rpc('tools/call', {'name': 'mcp_test_boom', 'arguments': {}}, token=tok)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(SECRET, r.text)
        self.assertNotIn('RuntimeError', r.text)
        res = r.json()['result']
        self.assertTrue(res['isError'])
        self.assertTrue(res['structuredContent']['request_id'])
        log = self.env['mcp.call.log'].sudo().search([('tool_code', '=', 'mcp_test_boom')], limit=1)
        self.assertFalse(log.ok)

    def test_unconfirmed_writers_never_listed_or_called(self):
        _r, tok = self._token(self.admin_user)
        names = self._names(tok)
        Partner = self.env['res.partner'].sudo()
        for code, pname in (('mcp_test_sa', 'MCP server action write'),
                            ('mcp_test_memory', 'MCP memory write'),
                            ('mcp_test_direct_write', 'MCP direct write')):
            self.assertNotIn(code, names)
            r = self._rpc('tools/call', {'name': code, 'arguments': {}}, token=tok)
            self.assertEqual(r.json()['error']['code'], -32602, r.text)
            self.assertFalse(Partner.search_count([('name', '=', pname)]))
        self.assertIn('create_record', names)  # confirm-first stays

    def test_write_off_hides_write_tools(self):
        _r, tok = self._token(self.user, allow_write=False)
        names = self._names(tok)
        self.assertNotIn('mcp_test_memory', names)
        self.assertNotIn('create_record', names)

    def test_failing_tool_leaves_no_partial_write(self):
        _r, tok = self._token(self.user)
        r = self._rpc('tools/call', {'name': 'mcp_test_partial', 'arguments': {}}, token=tok)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['result']['isError'])
        self.assertFalse(self.env['res.partner'].sudo().search_count(
            [('name', '=', 'MCP partial write')]))
        self.assertTrue(self.env['mcp.call.log'].sudo().search_count(
            [('tool_code', '=', 'mcp_test_partial'), ('ok', '=', False)]))

    def test_archived_user_frees_seat(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param('ab_ai_agent.feature.mcp.max_users', '1')
        self.env['mcp.token'].sudo().search([]).write({'revoked_at': fields.Datetime.now()})
        rec, tok = self._token(self.user)
        other = new_test_user(self.env, login='mcp_other', groups='base.group_user')
        other.sudo().write({'ai_assistant_active': True})
        with self.assertRaises(Exception):
            self._token(other)
        self.user.sudo().write({'active': False})
        self.assertTrue(rec.sudo().revoked_at)
        self.assertNotIn(self.user.id, self.env['mcp.token']._seat_holder_ids())
        self.assertEqual(self._rpc('ping', token=tok).status_code, 401)
        self._token(other)  # seat is free again

    def test_confirm_refused_after_mcp_off(self):
        _r, tok = self._token(self.user)
        r = self._rpc('tools/call', {'name': 'create_record', 'arguments': {
            'model': 'res.partner', 'values': {'name': 'MCP Partner Late'}}}, token=tok)
        key = r.json()['result']['structuredContent']['key']
        self.assertTrue(key)
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.feature.mcp.enabled', 'False')
        out = self.env['ai.agent.pending.action'].with_user(self.user).resolve(key, True)
        self.assertFalse(out['ok'])
        self.assertFalse(self.env['res.partner'].sudo().search_count(
            [('name', '=', 'MCP Partner Late')]))

    def test_confirm_refused_after_token_revoked(self):
        rec, tok = self._token(self.user)
        r = self._rpc('tools/call', {'name': 'create_record', 'arguments': {
            'model': 'res.partner', 'values': {'name': 'MCP Partner Revoked'}}}, token=tok)
        key = r.json()['result']['structuredContent']['key']
        rec.with_user(self.user).action_revoke()
        out = self.env['ai.agent.pending.action'].with_user(self.user).resolve(key, True)
        self.assertFalse(out['ok'])

    def test_wizard_never_stores_token(self):
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.feature.mcp.max_users', '0')
        Wiz = self.env['mcp.connect.wizard'].with_user(self.user)
        wiz = Wiz.create({'name': 'w', 'client': 'claude_desktop'})
        action = wiz.action_generate()
        self.assertFalse(action.get('res_id'))
        plain = action['context']['default_token']
        self.assertTrue(plain.startswith('gmcp_'))
        # The result dialog is a new record built from the context...
        shown = Wiz.with_context(action['context']).new({})
        self.assertEqual(shown.token, plain)
        self.assertIn(plain, shown.config_snippet)
        # ...and nothing secret ever reaches the database.
        self.assertFalse(Wiz._fields['token'].store)
        self.assertFalse(Wiz._fields['config_snippet'].store)
        wiz.invalidate_recordset()
        self.assertFalse(wiz.read(['token', 'config_snippet'])[0]['token'])
        self.env.cr.execute("SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'mcp_connect_wizard'")
        cols = {r[0] for r in self.env.cr.fetchall()}
        self.assertFalse({'token', 'config_snippet'} & cols)

    def test_snippets(self):
        Wiz = self.env['mcp.connect.wizard']
        url, tok = 'https://x.example/mcp', 'gmcp_abc'
        desk = json.loads(Wiz._snippet('claude_desktop', url, tok))['mcpServers']['ghaima']
        self.assertEqual(desk['command'], 'npx')
        self.assertEqual(desk['args'], ['-y', 'mcp-remote', url, '--header', 'Authorization:${GHAIMA_AUTH}'])
        self.assertEqual(desk['env'], {'GHAIMA_AUTH': 'Bearer gmcp_abc'})
        self.assertEqual(Wiz._snippet('claude_code', url, tok),
                         'claude mcp add --transport http ghaima %s '
                         '--header "Authorization: Bearer gmcp_abc"' % url)
        cur = json.loads(Wiz._snippet('cursor', url, tok))['mcpServers']['ghaima']
        self.assertEqual(cur, {'url': url, 'headers': {'Authorization': 'Bearer gmcp_abc'}})

    def test_token_state_searchable(self):
        rec, _tok = self._token(self.user)
        rec = rec.sudo()
        Token = self.env['mcp.token'].sudo()
        self.assertIn(rec, Token.search([('state', '=', 'active')]))
        rec.write({'revoked_at': fields.Datetime.now()})
        self.assertIn(rec, Token.search([('state', '=', 'revoked')]))
        self.assertNotIn(rec, Token.search([('state', '!=', 'revoked')]))
        self.assertNotIn(rec, Token.search([('state', 'in', ['active', 'expired'])]))

    def test_exposed_tools_hide_never_offered(self):
        Tool = self.env['ai.agent.tool'].sudo()
        avail = Tool.search([('mcp_available', '=', True)])
        self.assertTrue(avail)
        self.assertFalse(avail.filtered(lambda t: t.category in ('memory', 'navigation')
                                        or t.dispatch_kind == 'server_action'))
        self.assertIn('create_record', avail.mapped('code'))
