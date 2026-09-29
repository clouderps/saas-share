# -*- coding: utf-8 -*-
"""Phase 6/7 — voice is an interface: validated input, no stored audio."""
import base64
import json
from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

WAV = base64.b64encode(b'RIFF' + b'\0' * 64).decode()


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestVoiceService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.svc = self.env['ai.provider.service'].sudo()

    def test_rejects_empty_oversized_and_unknown_audio(self):
        with self.assertRaises(UserError):
            self.svc.call_transcription('', 'audio/wav')
        with self.assertRaises(UserError):
            self.svc.call_transcription('A' * (self.svc.AUDIO_MAX_B64 + 1), 'audio/wav')
        with self.assertRaises(UserError):
            self.svc.call_transcription(WAV, 'application/x-sh')

    def test_simulation_transcribes_to_nothing(self):
        with patch.object(type(self.svc), '_is_simulation_mode', return_value=True):
            text, usage = self.svc.call_transcription(WAV, 'audio/wav', 'ar')
        self.assertEqual(text, '')
        self.assertEqual(usage['provider'], 'simulation')

    def test_gemini_request_shape(self):
        config = MagicMock(ai_provider='google', gemini_model='gemini-2.5-flash', timeout=5)
        config._get_decrypted_key.return_value = 'k'
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, headers=headers, json=json)
            resp = MagicMock()
            resp.json.return_value = {'candidates': [{'content': {'parts': [{'text': ' مرحبا '}]}}]}
            return resp
        with patch('odoo.addons.ab_ai_base.models.ai_service.requests.post', fake_post), \
                patch.object(type(self.svc), '_is_simulation_mode', return_value=False):
            text, _usage = self.svc.call_transcription(WAV, 'audio/wav', 'ar', config=config)
        self.assertEqual(text, 'مرحبا')
        # The key travels in a header, never in the URL (URLs get logged).
        self.assertNotIn('key=', captured['url'])
        self.assertEqual(captured['headers']['x-goog-api-key'], 'k')
        part = captured['json']['contents'][0]['parts'][0]['inline_data']
        self.assertEqual(part['mime_type'], 'audio/wav')


@tagged('post_install', '-at_install', 'ghaima_ai_agent')
class TestVoiceRoutes(HttpCase):

    def _post(self, url, params):
        res = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                                                  'params': params}),
                            headers={'Content-Type': 'application/json'})
        return res.json()['result']

    def test_transcribe_respects_the_company_switch_and_stores_no_audio(self):
        new_test_user(self.env, login='ai_voice_user', password='ai_voice_user_pw',
                      groups='base.group_user,ab_ai_agent.group_ai_agent_user')
        self.authenticate('ai_voice_user', 'ai_voice_user_pw')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.voice_enabled', 'False')
        res = self._post('/ai_agent/voice/transcribe', {'audio': WAV, 'mimetype': 'audio/wav'})
        self.assertEqual(res['error'], 'voice_disabled')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_agent.voice_enabled', 'True')
        self.env['ir.config_parameter'].sudo().set_param('ab_ai_gateway.simulation', 'True')
        before = self.env['ir.attachment'].sudo().search_count([])
        res = self._post('/ai_agent/voice/transcribe', {'audio': WAV, 'mimetype': 'audio/wav',
                                                        'seconds': 1.5})
        self.assertFalse(res['ok'])                    # simulation hears nothing
        self.assertEqual(res['error'], 'empty')
        self.assertEqual(self.env['ir.attachment'].sudo().search_count([]), before)
        log = self.env['ai.usage.local.log'].sudo().search(
            [('feature', '=', 'voice')], order='id desc', limit=1)
        self.assertAlmostEqual(log.audio_seconds, 1.5)
