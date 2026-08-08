# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

from ..lib import fernet as fernet_lib

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
    
    # Write-only plaintext input. Encrypted into *_encrypted on write and
    # then blanked at rest — see create()/write(). "Leave empty to keep the
    # stored key" is the intended UX (mirrors ab_aws_saas_dns.aws.config).
    openai_api_key = fields.Char(
        string='OpenAI API Key',
        help='Your OpenAI API key from https://platform.openai.com/api-keys. '
             'Stored encrypted — leave empty to keep the existing key.'
    )
    openai_api_key_encrypted = fields.Text(
        string='OpenAI API Key (encrypted)', readonly=True, copy=False,
        help='Fernet-encrypted OpenAI API key. Decrypted only when calling '
             'the provider.'
    )
    has_openai_key = fields.Boolean(compute='_compute_has_keys')
    
    # Google Gemini Settings
    # 2.0 variants ('gemini-2.0-flash-001' / 'gemini-2.0-flash-lite-001')
    # were dropped on 2026-05-13 after Google's API responded
    # `404 "This model is no longer available to new users"` against a
    # fresh key. The replacements below were smoke-tested live against
    # generativelanguage.googleapis.com/v1beta on the same date.
    gemini_model = fields.Selection(
        [
            ('gemini-2.5-flash', 'Gemini 2.5 Flash'),
            ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
            ('gemini-2.5-flash-lite', 'Gemini 2.5 Flash Lite'),
            ('gemini-flash-latest', 'Gemini Flash (latest)'),
        ],
        string='Gemini Model',
        default='gemini-2.5-flash'
    )
    
    gemini_api_key = fields.Char(
        string='Google AI API Key',
        help='Your Google AI API key from https://makersuite.google.com/app/apikey. '
             'Stored encrypted — leave empty to keep the existing key.'
    )
    gemini_api_key_encrypted = fields.Text(
        string='Google AI API Key (encrypted)', readonly=True, copy=False,
        help='Fernet-encrypted Google AI key. Decrypted only when calling '
             'the provider.'
    )
    has_gemini_key = fields.Boolean(compute='_compute_has_keys')
    
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
        help='Your Anthropic API key from https://console.anthropic.com/. '
             'Stored encrypted — leave empty to keep the existing key.'
    )
    claude_api_key_encrypted = fields.Text(
        string='Anthropic API Key (encrypted)', readonly=True, copy=False,
        help='Fernet-encrypted Anthropic key. Decrypted only when calling '
             'the provider.'
    )
    has_claude_key = fields.Boolean(compute='_compute_has_keys')
    
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

    # Fallback chain (Phase 2 of SAAS_AI_PLAN.md)
    fallback_provider_id = fields.Many2one(
        'ai.provider.config',
        string='Fallback provider',
        ondelete='set null',
        help='Engaged once if the primary provider returns a transport '
             'error or 5xx. Both attempts are audited as separate '
             'ai.usage.log rows linked via parent_log_id.',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.constrains(
        'ai_provider', 'openai_api_key', 'gemini_api_key', 'claude_api_key',
        'openai_api_key_encrypted', 'gemini_api_key_encrypted',
        'claude_api_key_encrypted',
    )
    def _check_api_key(self):
        """Validate that API key is provided for selected provider.

        create()/write() blank the plaintext input after encrypting it, so
        the check must accept either a pending plaintext value or a stored
        ciphertext."""
        # Bypass key validation when global simulation toggle is on —
        # ops may want to save a config skeleton with empty keys for
        # later, and simulation mode never hits the provider anyway.
        icp = self.env['ir.config_parameter'].sudo()
        if str(icp.get_param('ab_ai_gateway.simulation', 'False')).lower() \
                in ('1', 'true', 'yes'):
            return
        for config in self:
            if config.ai_provider == 'openai' and not (
                    config.openai_api_key or config.openai_api_key_encrypted):
                raise ValidationError(_('OpenAI API Key is required when using OpenAI provider'))
            elif config.ai_provider == 'google' and not (
                    config.gemini_api_key or config.gemini_api_key_encrypted):
                raise ValidationError(_('Google AI API Key is required when using Gemini provider'))
            elif config.ai_provider == 'anthropic' and not (
                    config.claude_api_key or config.claude_api_key_encrypted):
                raise ValidationError(_('Anthropic API Key is required when using Claude provider'))

    # ------------------------------------------------------------------
    # Encryption at rest — provider keys are Fernet-encrypted on write and
    # decrypted only at the point of a provider call. Pattern mirrors
    # ab_aws_saas_dns.aws.config.
    # ------------------------------------------------------------------

    # Plaintext input field -> encrypted storage column.
    _ENCRYPTED_KEY_FIELDS = {
        'openai_api_key': 'openai_api_key_encrypted',
        'gemini_api_key': 'gemini_api_key_encrypted',
        'claude_api_key': 'claude_api_key_encrypted',
    }

    @api.depends('openai_api_key_encrypted', 'gemini_api_key_encrypted',
                 'claude_api_key_encrypted')
    def _compute_has_keys(self):
        for record in self:
            record.has_openai_key = bool(record.openai_api_key_encrypted)
            record.has_gemini_key = bool(record.gemini_api_key_encrypted)
            record.has_claude_key = bool(record.claude_api_key_encrypted)

    def _encrypt_key_vals(self, vals):
        """Move any *non-empty* plaintext key in ``vals`` into its encrypted
        column and blank the plaintext so it never lands in the DB.

        An absent or empty value leaves the stored (encrypted) key untouched
        — this is the 'leave empty to keep the existing key' UX and mirrors
        ab_aws_saas_dns.aws.config. It deliberately does not offer a
        clear-via-blank path (which would risk wiping a key if a client ever
        re-sent an empty value for an untouched field)."""
        for plain_field, enc_field in self._ENCRYPTED_KEY_FIELDS.items():
            if vals.get(plain_field):
                vals[enc_field] = fernet_lib.encrypt(self.env, vals[plain_field])
                # Never persist the plaintext.
                vals[plain_field] = ''
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._encrypt_key_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._encrypt_key_vals(vals)
        return super().write(vals)

    def _get_decrypted_key(self, plain_field):
        """Return the decrypted provider key for ``plain_field``
        (one of openai_api_key / gemini_api_key / claude_api_key).

        Falls back to any legacy plaintext still sitting in the column so
        the switch is seamless even before the migration runs."""
        self.ensure_one()
        enc_field = self._ENCRYPTED_KEY_FIELDS[plain_field]
        ciphertext = self[enc_field]
        if ciphertext:
            return fernet_lib.decrypt(self.env, ciphertext)
        # Legacy / pre-migration plaintext fallback.
        return self[plain_field] or ''

    @api.constrains('fallback_provider_id')
    def _check_no_fallback_loop(self):
        """Prevent fallback chains > 1 hop and self-references."""
        for cfg in self:
            if cfg.fallback_provider_id == cfg:
                raise ValidationError(_(
                    'A config cannot be its own fallback.'))
            if cfg.fallback_provider_id \
                    and cfg.fallback_provider_id.fallback_provider_id:
                raise ValidationError(_(
                    'Fallback chains are limited to one hop. '
                    '%s already has its own fallback configured.'
                ) % cfg.fallback_provider_id.name)

    def get_active_config(self):
        """Get the active AI configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise UserError(_('No active AI configuration found. Please configure AI settings first.'))
        return config
    
    def increment_usage(self, tokens=0):
        """Track AI usage on the single active provider row.

        This is the request hot path (called on every gateway call). A
        read-modify-write here — total_requests = self.total_requests + 1 —
        serialization-fails under concurrency (Odoo runs REPEATABLE READ, the
        DBCLOUD gateway runs 2 prefork workers): two requests read the same
        counter, both write +1, the loser gets SQLSTATE 40001 which aborts the
        WHOLE request transaction (it can't be caught with a savepoint). That
        was 77 failed requests / 3 days at the 2026-08-08 review.

        Do the increment in an autonomous cursor with an atomic in-place UPDATE:
        its failure can never poison the caller's transaction, and the counters
        are a soft metric (the authoritative per-request data is ai.usage.log).
        ponytail: under extreme concurrency an autonomous increment may still
        40001 and be dropped — acceptable for a soft counter; the swallow keeps
        the request itself safe."""
        self.ensure_one()
        try:
            with self.pool.cursor() as cr:
                cr.execute(
                    "UPDATE ai_provider_config SET "
                    "total_requests = COALESCE(total_requests, 0) + 1, "
                    "total_tokens = COALESCE(total_tokens, 0) + %s, "
                    "last_used = now() WHERE id = %s",
                    (tokens or 0, self.id))
                cr.commit()
        except Exception:
            _logger.warning("ai.provider.config.increment_usage failed (id=%s)",
                            self.id, exc_info=True)
    
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

