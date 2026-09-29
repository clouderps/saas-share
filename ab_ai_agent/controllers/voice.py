# -*- coding: utf-8 -*-
"""Voice for the assistant — an interface, not a second AI.

/ai_agent/voice/transcribe turns a push-to-talk recording into text; the
browser then sends that text through the normal /ai_agent/run, so a
spoken question gets exactly the same context, permissions, tools,
confirmation rules and history as a typed one.

/ai_agent/voice/speak turns an answer into audio (optional; the text
answer is always shown first and stays).

Audio is never stored: only the transcript lands in the conversation,
and ai.usage.local.log records the seconds for billing.
"""
import logging
import time

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from ..services import meter as meter_svc

_logger = logging.getLogger(__name__)

MAX_SECONDS = 70


def _voice_enabled():
    return request.env.user._ai_assistant_info().get('voice')


class AIVoiceController(http.Controller):

    @http.route('/ai_agent/voice/transcribe', type='json', auth='user', methods=['POST'])
    def transcribe(self, audio=None, mimetype='audio/wav', lang=None, seconds=0, **_kw):
        if not _voice_enabled():
            return {'ok': False, 'error': 'voice_disabled',
                    'message': _('Voice is turned off for this company.')}
        try:
            seconds = min(float(seconds or 0), MAX_SECONDS)
        except (TypeError, ValueError):
            seconds = 0.0
        started = time.perf_counter()
        try:
            # sudo: reads the provider configuration (keys) to make the
            # call on the user's behalf; the user only receives the text.
            text, usage = request.env['ai.provider.service'].sudo().call_transcription(
                audio, mimetype, lang)
        except UserError as e:
            return {'ok': False, 'error': 'stt_failed', 'message': str(e)}
        except Exception:
            _logger.exception('voice transcription failed')
            return {'ok': False, 'error': 'stt_failed',
                    'message': _('Speech recognition is unavailable right now.')}
        usage = usage or {}
        meter_svc.record(
            request.env, request_id='', surface='chat', feature='voice',
            provider=usage.get('provider', ''), model_used=usage.get('model', ''),
            model_class='', routed_via='gateway' if usage.get('provider') == 'gateway' else 'direct',
            prompt_tokens=int(usage.get('prompt_tokens') or 0),
            completion_tokens=int(usage.get('completion_tokens') or 0),
            audio_seconds=seconds,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status='sim' if usage.get('provider') == 'simulation' else 'ok')
        text = (text or '').strip()
        if not text:
            return {'ok': False, 'error': 'empty',
                    'message': _("I didn't catch that. Try again, a little closer to the microphone.")}
        return {'ok': True, 'text': text}

    @http.route('/ai_agent/voice/speak', type='json', auth='user', methods=['POST'])
    def speak(self, text=None, lang=None, **_kw):
        if not _voice_enabled():
            return {'ok': False, 'error': 'voice_disabled'}
        try:
            audio, mimetype, usage = request.env['ai.provider.service'].sudo().call_speech(
                text, lang)
        except UserError as e:
            return {'ok': False, 'error': 'tts_failed', 'message': str(e)}
        except Exception:
            _logger.exception('voice speech failed')
            return {'ok': False, 'error': 'tts_failed'}
        usage = usage or {}
        meter_svc.record(
            request.env, request_id='', surface='chat', feature='voice_out',
            provider=usage.get('provider', ''), model_used=usage.get('model', ''),
            model_class='', routed_via='direct', status='ok')
        return {'ok': True, 'audio': audio, 'mimetype': mimetype}
