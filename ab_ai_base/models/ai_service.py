# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError
import logging
import requests

_logger = logging.getLogger(__name__)


class AIProviderService(models.AbstractModel):
    _name = 'ai.provider.service'
    _description = 'AI Provider Service'

    def call(self, prompt, config=None, system_prompt=None,
             image_data=None, image_mimetype=None):
        """Call AI provider with a prompt, optionally with an image.

        Args:
            prompt: The user prompt text
            config: Optional ai.provider.config record. Uses active config if not provided.
            system_prompt: Optional system prompt override. Uses config default if not provided.
            image_data: Optional base64-encoded image for vision/multimodal requests.
            image_mimetype: MIME type of the image (default: image/png).

        Returns:
            tuple: (response_text, usage_dict) where usage_dict has:
                prompt_tokens, completion_tokens, total_tokens, model, provider
        """
        if not config:
            config = self.env['ai.provider.config'].get_active_config()

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        elif config.system_prompt:
            full_prompt = f"{config.system_prompt}\n\n{prompt}"

        if image_data:
            response_text, usage = self._call_ai_api_with_image(
                full_prompt, config, image_data, image_mimetype or 'image/png',
            )
        else:
            response_text, usage = self._call_ai_api(full_prompt, config)
        config.increment_usage(tokens=usage.get('total_tokens', 0))
        return response_text, usage

    def test_connection(self, config):
        """Test AI API connection."""
        try:
            response_text, usage = self._call_ai_api(
                "Say 'Connection successful' in JSON: {'status': 'ok'}",
                config,
            )
            return {
                'success': True,
                'message': _('AI connection successful!'),
                'response': response_text[:200],
                'usage': usage,
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def _call_ai_api(self, prompt, config):
        """Route to the appropriate provider API.

        Returns:
            tuple: (response_text, usage_dict)
        """
        providers = {
            'openai': self._call_openai,
            'google': self._call_gemini,
            'anthropic': self._call_claude,
            'local': self._call_local_llm,
        }
        handler = providers.get(config.ai_provider)
        if not handler:
            raise UserError(_('Unsupported AI provider: %s') % config.ai_provider)
        return handler(prompt, config)

    def _call_ai_api_with_image(self, prompt, config, image_data, image_mimetype):
        """Route to the appropriate provider with multimodal image support."""
        provider = config.ai_provider
        if provider == 'openai':
            return self._call_openai_vision(prompt, config, image_data, image_mimetype)
        elif provider == 'anthropic':
            return self._call_claude_vision(prompt, config, image_data, image_mimetype)
        elif provider == 'google':
            return self._call_gemini_vision(prompt, config, image_data, image_mimetype)
        else:
            _logger.warning('Provider %s does not support vision, falling back to text', provider)
            return self._call_ai_api(prompt, config)

    def _call_openai(self, prompt, config):
        """Call OpenAI API. Returns (text, usage_dict)."""
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config.openai_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.openai_model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that returns only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['choices'][0]['message']['content'].strip()
            api_usage = data.get('usage', {})
            usage = {
                'prompt_tokens': api_usage.get('prompt_tokens', 0),
                'completion_tokens': api_usage.get('completion_tokens', 0),
                'total_tokens': api_usage.get('total_tokens', 0),
                'model': config.openai_model,
                'provider': 'openai',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI API error: %s", e)
            raise UserError(_('OpenAI API Error: %s') % e)

    def _call_gemini(self, prompt, config):
        """Call Google Gemini API. Returns (text, usage_dict)."""
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (
                config.gemini_model, config.gemini_api_key
            )
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": config.temperature,
                        "maxOutputTokens": config.max_tokens,
                    },
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            api_usage = data.get('usageMetadata', {})
            usage = {
                'prompt_tokens': api_usage.get('promptTokenCount', 0),
                'completion_tokens': api_usage.get('candidatesTokenCount', 0),
                'total_tokens': api_usage.get('totalTokenCount', 0),
                'model': config.gemini_model,
                'provider': 'google',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Gemini API error: %s", e)
            raise UserError(_('Gemini API Error: %s') % e)

    def _call_claude(self, prompt, config):
        """Call Anthropic Claude API. Returns (text, usage_dict)."""
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.claude_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.claude_model,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['content'][0]['text'].strip()
            api_usage = data.get('usage', {})
            usage = {
                'prompt_tokens': api_usage.get('input_tokens', 0),
                'completion_tokens': api_usage.get('output_tokens', 0),
                'total_tokens': api_usage.get('input_tokens', 0) + api_usage.get('output_tokens', 0),
                'model': config.claude_model,
                'provider': 'anthropic',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Claude API error: %s", e)
            raise UserError(_('Claude API Error: %s') % e)

    # ── Vision / Multimodal methods ──

    def _call_openai_vision(self, prompt, config, image_data, image_mimetype):
        """Call OpenAI with image (GPT-4o vision). Returns (text, usage_dict)."""
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config.openai_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.openai_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:{image_mimetype};base64,{image_data}",
                        }},
                    ]}],
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['choices'][0]['message']['content'].strip()
            api_usage = data.get('usage', {})
            return text, {
                'prompt_tokens': api_usage.get('prompt_tokens', 0),
                'completion_tokens': api_usage.get('completion_tokens', 0),
                'total_tokens': api_usage.get('total_tokens', 0),
                'model': config.openai_model, 'provider': 'openai',
            }
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI Vision error: %s", e)
            raise UserError(_('OpenAI Vision Error: %s') % e)

    def _call_claude_vision(self, prompt, config, image_data, image_mimetype):
        """Call Claude with image (multimodal). Returns (text, usage_dict)."""
        media_type = image_mimetype
        if media_type == 'image/jpg':
            media_type = 'image/jpeg'
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.claude_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.claude_model,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": [{"role": "user", "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        }},
                        {"type": "text", "text": prompt},
                    ]}],
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['content'][0]['text'].strip()
            api_usage = data.get('usage', {})
            return text, {
                'prompt_tokens': api_usage.get('input_tokens', 0),
                'completion_tokens': api_usage.get('output_tokens', 0),
                'total_tokens': api_usage.get('input_tokens', 0) + api_usage.get('output_tokens', 0),
                'model': config.claude_model, 'provider': 'anthropic',
            }
        except requests.exceptions.RequestException as e:
            _logger.error("Claude Vision error: %s", e)
            raise UserError(_('Claude Vision Error: %s') % e)

    def _call_gemini_vision(self, prompt, config, image_data, image_mimetype):
        """Call Gemini with image (multimodal). Returns (text, usage_dict)."""
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (
                config.gemini_model, config.gemini_api_key
            )
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [
                        {"text": prompt},
                        {"inline_data": {
                            "mime_type": image_mimetype,
                            "data": image_data,
                        }},
                    ]}],
                    "generationConfig": {
                        "temperature": config.temperature,
                        "maxOutputTokens": config.max_tokens,
                    },
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['candidates'][0]['content']['parts'][0]['text'].strip()
            api_usage = data.get('usageMetadata', {})
            return text, {
                'prompt_tokens': api_usage.get('promptTokenCount', 0),
                'completion_tokens': api_usage.get('candidatesTokenCount', 0),
                'total_tokens': api_usage.get('totalTokenCount', 0),
                'model': config.gemini_model, 'provider': 'google',
            }
        except requests.exceptions.RequestException as e:
            _logger.error("Gemini Vision error: %s", e)
            raise UserError(_('Gemini Vision Error: %s') % e)

    def _call_local_llm(self, prompt, config):
        """Call local LLM (Ollama or similar). Returns (text, usage_dict)."""
        try:
            response = requests.post(
                config.local_llm_endpoint,
                json={
                    "model": config.local_llm_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": config.temperature},
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data.get('response', '').strip()
            # Ollama provides token counts; estimate if not available
            prompt_tokens = data.get('prompt_eval_count', len(prompt.split()))
            completion_tokens = data.get('eval_count', len(text.split()))
            usage = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens,
                'model': config.local_llm_model,
                'provider': 'local',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Local LLM API error: %s", e)
            raise UserError(_('Local LLM Error: %s') % e)
