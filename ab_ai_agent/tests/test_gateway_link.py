# -*- coding: utf-8 -*-
"""Tenant ↔ central gateway: native tools pass through, the gateway is
skipped for a while when unreachable, and the plan is a ceiling."""
from unittest.mock import patch

import requests

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_agent.services import llm_adapter

TOOLS = [{'name': 'query_data', 'description': 'd',
          'parameters': {'type': 'object', 'properties': {}}}]


class FakeGateway:
    def __init__(self, caps=('native_tools',), policy=None, fail=None):
        self.caps, self.policy, self.fail, self.calls = caps, policy or {}, fail, []

    def has_capability(self, name):
        return name in self.caps

    def get_policy(self):
        return self.policy

    def call_ai(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return '', {'total_tokens': 5, 'tool_calls': [
            {'name': 'query_data', 'arguments': {}, 'id': 'g-0'}]}


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestGatewayLink(TransactionCase):

    def setUp(self):
        super().setUp()
        llm_adapter._gateway_down_until.clear()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.icp.set_param('ab_ai_agent.llm_mode', 'auto')
        self.icp.set_param('ab_ai_agent.native_tools_enabled', 'True')

    def _with(self, gw):
        return patch.object(llm_adapter, '_try_get_gateway', return_value=gw)

    def test_native_tools_travel_through_a_capable_gateway(self):
        gw = FakeGateway()
        with self._with(gw):
            self.assertTrue(llm_adapter.native_tools_active(self.env))
            _text, usage, via = llm_adapter.call_llm(
                self.env, None, system_prompt='s', user_prompt='u', tools=TOOLS)
        self.assertEqual(via, 'gateway')
        self.assertEqual(gw.calls[0]['tool_schemas'], TOOLS)
        self.assertNotIn('tools', gw.calls[0])
        self.assertEqual(usage['tool_calls'][0]['name'], 'query_data')
        self.assertEqual(gw.calls[0]['request_id'], usage['request_id'])

    def test_older_gateway_gets_tool_names_and_text_protocol(self):
        gw = FakeGateway(caps=())
        with self._with(gw):
            self.assertFalse(llm_adapter.native_tools_active(self.env))
            llm_adapter.call_llm(self.env, None, system_prompt='s', user_prompt='u', tools=TOOLS)
        self.assertEqual(gw.calls[0]['tools'], ['query_data'])

    def test_unreachable_gateway_is_skipped_for_a_while(self):
        gw = FakeGateway(fail=requests.exceptions.ConnectionError('refused'))
        direct = (lambda _s, *a, **k: ('ok', {'provider': 'google'}))
        with self._with(gw), \
                patch.object(type(self.env['ai.provider.service']), 'call', direct), \
                patch.object(llm_adapter, '_has_active_provider', return_value=True):
            _t, _u, via1 = llm_adapter.call_llm(self.env, None, system_prompt='s', user_prompt='u')
            _t, _u, via2 = llm_adapter.call_llm(self.env, None, system_prompt='s', user_prompt='u')
        self.assertEqual((via1, via2), ('direct', 'direct'))
        self.assertEqual(len(gw.calls), 1, 'second turn must not pay the failed round-trip')

    def test_gateway_mode_never_falls_back_to_a_local_key(self):
        self.icp.set_param('ab_ai_agent.llm_mode', 'gateway')
        gw = FakeGateway(fail=requests.exceptions.ConnectionError('refused'))
        with self._with(gw), self.assertRaises(llm_adapter.AiProviderError):
            llm_adapter.call_llm(self.env, None, system_prompt='s', user_prompt='u')

    def test_direct_mode_ignores_the_gateway(self):
        self.icp.set_param('ab_ai_agent.llm_mode', 'direct')
        with self._with(FakeGateway()):
            self.assertIsNone(llm_adapter.gateway_for_turn(self.env))
            self.assertEqual(llm_adapter.gateway_policy(self.env), {})

    def test_plan_is_a_ceiling_for_actions_and_voice(self):
        from odoo.addons.ab_ai_agent.services.runtime import ACTION_TOOLS, _resolve_tools
        self.icp.set_param('ab_ai_agent.actions_enabled', 'True')
        self.icp.set_param('ab_ai_agent.voice_enabled', 'True')
        agent = self.env['ai.agent'].sudo().search([], limit=1)
        with self._with(FakeGateway(policy={'actions': False, 'voice': False})):
            codes = set(_resolve_tools(self.env, agent).mapped('code')) if agent else set()
            self.assertFalse(codes & set(ACTION_TOOLS))
            self.assertFalse(self.env.user._ai_assistant_info()['voice'])
        with self._with(FakeGateway(policy={})):
            self.assertTrue(self.env.user._ai_assistant_info()['voice'])
