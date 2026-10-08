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


class TestGeminiContextCache(TransactionCase):
    """Explicit cachedContents: stable prefix + tools cached once, reused."""

    def setUp(self):
        super().setUp()
        from odoo.addons.ab_ai_base.models import ai_service
        self.svc_mod = ai_service
        ai_service._GEMINI_CACHE.clear()
        self.addCleanup(ai_service._GEMINI_CACHE.clear)
        self.config = MagicMock(gemini_model='gemini-2.5-flash', temperature=0,
                                max_tokens=100, timeout=5)
        self.config._get_decrypted_key.return_value = 'SECRET'
        self.tools = [{'name': 'find_menu', 'description': 'd',
                       'parameters': {'type': 'object', 'properties': {}}}]
        self.system = 'S' * 5000 + ai_service.CACHE_BREAK + 'VOLATILE'

    def _post(self, calls, gen_status=200):
        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, json))
            resp = MagicMock()
            if url.endswith('/cachedContents'):
                resp.json.return_value = {'name': 'cachedContents/abc'}
            else:
                resp.status_code = gen_status if json.get('cachedContent') else 200
                resp.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'ok'}]}}],
                                          'usageMetadata': {'cachedContentTokenCount': 1300}}
            return resp
        return fake_post

    def _call(self, calls, gen_status=200):
        with patch.object(self.svc_mod.requests, 'post', self._post(calls, gen_status)):
            return self.env['ai.provider.service'].sudo()._call_gemini(
                'q', self.config, system_prompt=self.system, tools=self.tools)

    def test_cache_created_once_and_volatile_part_moves_to_contents(self):
        calls = []
        self._call(calls)
        text, usage = self._call(calls)
        creates = [c for c in calls if c[0].endswith('/cachedContents')]
        self.assertEqual(len(creates), 1)
        self.assertNotIn('VOLATILE', str(creates[0][1]))
        self.assertIn('functionDeclarations', creates[0][1]['tools'][0])
        gen = calls[-1][1]
        self.assertEqual(gen['cachedContent'], 'cachedContents/abc')
        self.assertNotIn('systemInstruction', gen)
        self.assertNotIn('tools', gen)
        self.assertTrue(gen['contents'][0]['parts'][0]['text'].startswith('VOLATILE'))
        self.assertEqual((text, usage['cached_tokens']), ('ok', 1300))

    def test_expired_cache_falls_back_uncached_without_marker(self):
        calls = []
        text, _usage = self._call(calls, gen_status=404)
        last = calls[-1][1]
        self.assertNotIn('cachedContent', last)
        self.assertNotIn(self.svc_mod.CACHE_BREAK, last['systemInstruction']['parts'][0]['text'])
        self.assertEqual(text, 'ok')
        self.assertEqual(self.svc_mod._GEMINI_CACHE, {})

    def test_small_prompt_is_not_cached(self):
        calls = []
        self.system = 'short' + self.svc_mod.CACHE_BREAK + 'v'
        self._call(calls)
        self.assertFalse([c for c in calls if c[0].endswith('/cachedContents')])
        self.assertNotIn(self.svc_mod.CACHE_BREAK, calls[0][1]['systemInstruction']['parts'][0]['text'])
