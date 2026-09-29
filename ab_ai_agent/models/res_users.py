# -*- coding: utf-8 -*-
from odoo import api, fields, models

PROACTIVE_MODES = [
    ('off', 'Off'),
    ('quiet', 'Quiet: a dot on the assistant'),
    ('on', 'On: short tips as I move between screens'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    ai_proactive_mode = fields.Selection(
        PROACTIVE_MODES, string='Ghaima AI tips', default='on', required=True,
        # 'on' by default (owner 2026-09-29): the hint for the current
        # screen must appear without asking. Users can lower it.
        help='How much Ghaima AI tells you on its own when you open a screen. '
             'It never interrupts: tips are one or two lines from your own '
             'data and disappear by themselves.')
    ai_voice_autoplay = fields.Boolean(
        string='Read answers aloud',
        help='Speak every answer automatically. Off: press Listen on an answer.')

    def _ai_assistant_info(self):
        """Assistant flags for the web client (company settings AND the
        user's own preference)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()

        def flag(key, default='True'):
            return str(icp.get_param(key, default)).lower() in ('true', '1', 'yes')

        return {
            'enabled': flag('ab_ai_agent.assistant_enabled'),
            'proactive': (self.ai_proactive_mode
                          if flag('ab_ai_agent.proactive_enabled') else 'off'),
            'voice': flag('ab_ai_agent.voice_enabled'),
            'stt': icp.get_param('ab_ai_agent.stt_provider', 'browser'),
            'tts': icp.get_param('ab_ai_agent.tts_provider', 'browser'),
            'autoplay': bool(self.ai_voice_autoplay),
        }

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['ai_proactive_mode', 'ai_voice_autoplay']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['ai_proactive_mode', 'ai_voice_autoplay']
