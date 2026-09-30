# -*- coding: utf-8 -*-
"""Gemini native function calling: schema translation + response parsing."""
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ab_ai_base.models.ai_service import _gemini_schema, _tools_for_gemini


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestGeminiNativeTools(TransactionCase):

    def test_schema_is_reduced_to_what_gemini_accepts(self):
        out = _gemini_schema({'type': 'object', 'additionalProperties': False,
                              'properties': {'a': {'type': ['string', 'null'], 'default': 'x'},
                                             'b': {'type': 'array', 'items': {'type': 'integer'}}},
                              'required': ['a', 'zz']})
        self.assertNotIn('additionalProperties', out)
        self.assertEqual(out['properties']['a'], {'type': 'string', 'nullable': True})
        self.assertEqual(out['required'], ['a'])
        self.assertEqual(out['properties']['b']['items'], {'type': 'integer'})

    def test_tools_without_arguments_have_no_parameters(self):
        decl = _tools_for_gemini([{'name': 'list_my_apps', 'description': 'd',
                                   'parameters': {'type': 'object', 'properties': {}}}])
        self.assertEqual(decl, [{'name': 'list_my_apps', 'description': 'd'}])

    def test_function_calls_come_back_as_tool_calls_and_key_stays_out_of_url(self):
        svc = self.env['ai.provider.service'].sudo()
        config = MagicMock(gemini_model='gemini-2.5-flash', temperature=0, max_tokens=100, timeout=5)
        config._get_decrypted_key.return_value = 'SECRET'
        seen = {}
        resp = MagicMock()
        resp.json.return_value = {'candidates': [{'content': {'parts': [
            {'functionCall': {'name': 'find_menu', 'args': {'query': 'invoice'}}}]}}],
            'usageMetadata': {}}

        def fake_post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, headers=headers, json=json)
            return resp
        with patch('odoo.addons.ab_ai_base.models.ai_service.requests.post', fake_post):
            text, usage = svc._call_gemini('q', config, tools=[
                {'name': 'find_menu', 'description': 'd',
                 'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}}}])
        self.assertEqual(text, '')
        self.assertEqual(usage['tool_calls'][0]['name'], 'find_menu')
        self.assertEqual(usage['tool_calls'][0]['arguments'], {'query': 'invoice'})
        self.assertNotIn('SECRET', seen['url'])
        self.assertEqual(seen['headers']['x-goog-api-key'], 'SECRET')
        self.assertIn('functionDeclarations', seen['json']['tools'][0])
