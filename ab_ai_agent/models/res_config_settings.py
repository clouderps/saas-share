# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_assistant_enabled = fields.Boolean(
        string='Floating assistant', default=True,
        config_parameter='ab_ai_agent.assistant_enabled')
    ai_proactive_enabled = fields.Boolean(
        string='Proactive tips', default=True,
        config_parameter='ab_ai_agent.proactive_enabled',
        help='Allow short, data-based tips when users open a screen. Each '
             'user can still turn them off in their preferences.')
    ai_voice_enabled = fields.Boolean(
        string='Voice', default=True,
        config_parameter='ab_ai_agent.voice_enabled',
        help='Microphone (push to talk) and "Listen" in the assistant.')
    ai_stt_provider = fields.Selection(
        [('browser', 'Browser (free, no audio leaves the browser via Ghaima)'),
         ('server', 'Ghaima AI service (metered, consistent Arabic quality)')],
        string='Speech to text', default='browser',
        config_parameter='ab_ai_agent.stt_provider')
    ai_tts_provider = fields.Selection(
        [('browser', 'Browser voices'),
         ('server', 'Ghaima AI service (metered)')],
        string='Text to speech', default='browser',
        config_parameter='ab_ai_agent.tts_provider')
    ai_insight_cache_seconds = fields.Integer(
        string='Tip cache (seconds)', default=30,
        config_parameter='ab_ai_agent.insight_cache_seconds')
