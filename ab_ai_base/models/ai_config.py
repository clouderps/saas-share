# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AIProviderConfig(models.Model):
    _name = 'ai.provider.config'
    _description = 'AI Provider Configuration'
    _order = 'sequence, id'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Default AI Config'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    active = fields.Boolean(
        default=True
    )
    
    # AI Provider Settings
    ai_provider = fields.Selection(
        [
            ('openai', 'OpenAI (ChatGPT)'),
            ('google', 'Google Gemini'),
            ('anthropic', 'Anthropic Claude'),
            ('local', 'Local LLM'),
        ],
        string='AI Provider',
        required=True,
        default='openai'
    )
    
    # OpenAI Settings
    openai_model = fields.Selection(
        [
            ('gpt-4o', 'GPT-4o (Latest)'),
            ('gpt-4o-mini', 'GPT-4o Mini'),
            ('gpt-4-turbo', 'GPT-4 Turbo'),
            ('gpt-4', 'GPT-4'),
            ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
        ],
        string='OpenAI Model',
        default='gpt-4o-mini'
    )
    
    openai_api_key = fields.Char(
        string='OpenAI API Key',
        help='Your OpenAI API key from https://platform.openai.com/api-keys'
    )
    
    # Google Gemini Settings
    gemini_model = fields.Selection(
        [
            ('gemini-2.5-flash', 'Gemini 2.5 Flash'),
            ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
            ('gemini-2.0-flash-001', 'Gemini 2.0 Flash'),
            ('gemini-2.0-flash-lite-001', 'Gemini 2.0 Flash Lite'),
        ],
        string='Gemini Model',
        default='gemini-2.5-flash'
    )
    
    gemini_api_key = fields.Char(
        string='Google AI API Key',
        help='Your Google AI API key from https://makersuite.google.com/app/apikey'
    )
    
    # Anthropic Claude Settings
    claude_model = fields.Selection(
        [
            ('claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet (Latest)'),
            ('claude-3-5-haiku-20241022', 'Claude 3.5 Haiku'),
            ('claude-3-opus-20240229', 'Claude 3 Opus'),
            ('claude-3-sonnet-20240229', 'Claude 3 Sonnet'),
            ('claude-3-haiku-20240307', 'Claude 3 Haiku'),
        ],
        string='Claude Model',
        default='claude-3-5-sonnet-20241022'
    )
    
    claude_api_key = fields.Char(
        string='Anthropic API Key',
        help='Your Anthropic API key from https://console.anthropic.com/'
    )
    
    # Local LLM Settings
    local_llm_endpoint = fields.Char(
        string='Local LLM Endpoint',
        default='http://localhost:11434/api/generate',
        help='Ollama or other local LLM endpoint'
    )
    
    local_llm_model = fields.Char(
        string='Local Model Name',
        default='llama2',
        help='Model name (e.g., llama2, mistral, codellama)'
    )
    
    # Generation Settings
    temperature = fields.Float(
        string='Temperature',
        default=0.7,
        help='Controls randomness (0.0 = deterministic, 1.0 = creative)'
    )
    
    max_tokens = fields.Integer(
        string='Max Tokens',
        default=2000,
        help='Maximum length of generated response'
    )
    
    timeout = fields.Integer(
        string='Request Timeout (seconds)',
        default=30,
        help='Maximum time to wait for AI response'
    )
    
    # Usage Tracking
    total_requests = fields.Integer(
        string='Total Requests',
        readonly=True,
        default=0
    )
    
    total_tokens = fields.Integer(
        string='Total Tokens Used',
        readonly=True,
        default=0
    )
    
    last_used = fields.Datetime(
        string='Last Used',
        readonly=True
    )
    
    # System Prompt
    system_prompt = fields.Text(
        string='Default System Prompt',
        default='You are a helpful AI assistant. Return structured JSON when asked for configurations.'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.constrains('ai_provider', 'openai_api_key', 'gemini_api_key', 'claude_api_key')
    def _check_api_key(self):
        """Validate that API key is provided for selected provider"""
        for config in self:
            if config.ai_provider == 'openai' and not config.openai_api_key:
                raise ValidationError(_('OpenAI API Key is required when using OpenAI provider'))
            elif config.ai_provider == 'google' and not config.gemini_api_key:
                raise ValidationError(_('Google AI API Key is required when using Gemini provider'))
            elif config.ai_provider == 'anthropic' and not config.claude_api_key:
                raise ValidationError(_('Anthropic API Key is required when using Claude provider'))

    def get_active_config(self):
        """Get the active AI configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(_('No active AI configuration found. Please configure AI settings first.'))
        return config
    
    def increment_usage(self, tokens=0):
        """Track AI usage"""
        self.ensure_one()
        self.write({
            'total_requests': self.total_requests + 1,
            'total_tokens': self.total_tokens + tokens,
            'last_used': fields.Datetime.now(),
        })
    
    def action_test_connection(self):
        """Test AI connection"""
        self.ensure_one()
        try:
            ai_service = self.env['ai.provider.service']
            result = ai_service.test_connection(self)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': result.get('message', 'Connection successful!'),
                    'type': 'success' if result.get('success') else 'danger',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

