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
    ai_actions_enabled = fields.Boolean(
        string='Assistant actions', default=True,
        config_parameter='ab_ai_agent.actions_enabled',
        help='Let the assistant create, change, approve, confirm, send and schedule — '
             'always proposed first, run only after the user clicks Confirm, and '
             'limited by that user\'s access rights.')
    ai_tool_routing = fields.Boolean(
        string='Offer only relevant tools', default=True,
        config_parameter='ab_ai_agent.tool_routing',
        help='Faster, cheaper answers: each question is sent with the tools it can use.')
    ai_strong_model = fields.Char(
        string='Model for complex questions',
        config_parameter='ab_ai_agent.strong_model',
        help='Used for analysis / planning / multi-part questions, e.g. gemini-2.5-pro '
             '(must belong to the active AI provider). Empty: always the default model.')
    ai_user_memory = fields.Boolean(
        string='Remember user preferences', default=True,
        config_parameter='ab_ai_agent.user_memory',
        help='Users can ask the assistant to remember preferences; they are used in later chats.')
    ai_daily_briefing = fields.Boolean(
        string='Daily briefing', default=False,
        config_parameter='ab_ai_agent.daily_briefing',
        help='Each morning, a short summary of what needs the user\'s attention, '
             'shown when they open the assistant (no AI cost).')
    ai_voice_conversation = fields.Boolean(
        string='Hands-free voice conversation', default=False,
        config_parameter='ab_ai_agent.voice_conversation',
        help='After a spoken answer the microphone listens again, until the user '
             'stays silent or presses stop.')
    ai_voice_confirm = fields.Boolean(
        string='Confirm by voice', default=False,
        config_parameter='ab_ai_agent.voice_confirm',
        help='In a voice conversation, a proposed action can be confirmed by saying '
             '"yes / confirm" (or cancelled with "no / cancel") instead of clicking. '
             'Same rules as the button: only the user\'s own proposal, within 15 minutes, '
             'with their access rights.')
    ai_llm_mode = fields.Selection(
        [('auto', 'Automatic'), ('gateway', 'Central gateway only'),
         ('direct', 'Own provider key only')],
        string='AI connection', default='auto',
        config_parameter='ab_ai_agent.llm_mode',
        help='Automatic: the central Ghaima AI gateway when this company is linked '
             'to it, otherwise its own provider key. If the gateway cannot be '
             'reached, the own key is used for 5 minutes before trying again.')

