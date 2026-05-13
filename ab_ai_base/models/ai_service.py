# -*- coding: utf-8 -*-

from odoo import models, api, _
from odoo.exceptions import UserError
import json
import logging
import time
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
                (`provider` is 'simulation' when no real call was made).

        Simulation (Phase 2 of SAAS_AI_PLAN.md):
          - If ir.config_parameter `ab_ai_gateway.simulation` is True,
            we short-circuit before any HTTP and return a canned
            placeholder so the downstream pipeline still completes.
          - If no active ai.provider.config exists, we also simulate
            (rather than raising UserError) so a fresh install doesn't
            crash every AI feature.
        """
        if self._is_simulation_mode():
            return self._simulate_call(reason='explicit_toggle')

        if not config:
            config = self.env['ai.provider.config'].sudo().search(
                [('active', '=', True)], limit=1)
            if not config:
                return self._simulate_call(reason='no_provider_configured')

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

    def _is_simulation_mode(self):
        """True when the gateway is configured to skip real provider calls."""
        icp = self.env['ir.config_parameter'].sudo()
        return str(icp.get_param('ab_ai_gateway.simulation', 'False')).lower() \
                in ('1', 'true', 'yes')

    def _simulate_call(self, reason='explicit_toggle'):
        """Return a placeholder response without hitting any provider.

        The placeholder is a plain string with a clear marker so the
        consumer can either:
          - parse as JSON (daily report does; its parser falls through
            to wrapping as `<p>{text}</p>` because the keys don't match);
          - render as text (chatbot, chatter — they just paint the
            response).

        Either way the pipeline completes cleanly and audit logs show
        zero-token rows tagged with provider='simulation'.
        """
        _logger.info('ai.provider.service: simulation mode (%s)', reason)
        text = (
            '[Simulated AI output — gateway running in simulation mode. '
            'Configure an active ai.provider.config and set '
            'ir.config_parameter ab_ai_gateway.simulation=False to '
            'enable real LLM responses. Reason: %s]'
        ) % reason
        usage = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'model': 'simulation',
            'provider': 'simulation',
            'simulated_reason': reason,
        }
        return text, usage

    # ------------------------------------------------------------------
    # Phase 6 of SAAS_AI_PLAN.md — streaming (Server-Sent Events).
    # ------------------------------------------------------------------

    def stream_call(self, prompt, config=None, system_prompt=None,
                    tools=None):
        """Generator-style streaming variant of ``call()``.

        Yields a sequence of dicts:
            {'delta': '...', 'done': False, 'usage': None, 'tool_calls': None}
            ...
            {'delta': '',    'done': True,  'usage': {...}, 'tool_calls': [...]}

        The final dict's ``usage`` is populated when the provider supplies
        it; ``tool_calls`` is populated when the model decided to invoke
        a tool (Phase 7 — the gateway dispatcher consumes it).

        Providers without real streaming fall through to the non-streaming
        ``call()`` and yield the whole response as a single delta plus a
        terminating done dict — keeps the consumer code shape identical
        across providers.
        """
        if self._is_simulation_mode():
            yield from self._simulate_stream(reason='explicit_toggle')
            return

        if not config:
            config = self.env['ai.provider.config'].sudo().search(
                [('active', '=', True)], limit=1)
            if not config:
                yield from self._simulate_stream(reason='no_provider_configured')
                return

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        elif config.system_prompt:
            full_prompt = f"{config.system_prompt}\n\n{prompt}"

        provider = config.ai_provider
        if provider == 'openai':
            yield from self._stream_openai(full_prompt, config, tools=tools)
        else:
            # No real-streaming implementation for this provider yet —
            # do a regular call and emit a single chunk + done so the
            # consumer's protocol stays uniform.
            _logger.info(
                'stream_call: provider %s lacks streaming impl — '
                'using non-streaming fallback', provider)
            text, usage = self._call_ai_api(full_prompt, config)
            config.increment_usage(tokens=usage.get('total_tokens', 0))
            yield {'delta': text, 'done': False, 'usage': None, 'tool_calls': None}
            yield {'delta': '', 'done': True, 'usage': usage, 'tool_calls': None}

    def _simulate_stream(self, reason='explicit_toggle'):
        """Yield the simulation placeholder text as 4 chunks so the
        consumer's streaming UI exercises the partial-paint path."""
        _logger.info('ai.provider.service: stream simulation (%s)', reason)
        text = (
            '[Simulated AI stream — gateway running in simulation mode. '
            'Configure an active ai.provider.config and set '
            'ir.config_parameter ab_ai_gateway.simulation=False to '
            'enable real LLM responses. Reason: %s]'
        ) % reason
        chunks = [text[i:i + max(1, len(text) // 4)]
                  for i in range(0, len(text), max(1, len(text) // 4))]
        for chunk in chunks:
            yield {'delta': chunk, 'done': False, 'usage': None, 'tool_calls': None}
            time.sleep(0.05)
        yield {
            'delta': '',
            'done': True,
            'usage': {
                'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0,
                'model': 'simulation', 'provider': 'simulation',
                'simulated_reason': reason,
            },
            'tool_calls': None,
        }

    def _stream_openai(self, prompt, config, tools=None):
        """Real OpenAI streaming via SSE. Yields the same dict shape as
        ``stream_call``. Token usage arrives in the final chunk when
        ``stream_options.include_usage`` is on."""
        messages = [
            {"role": "system",
             "content": "You are a helpful assistant that returns only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        payload = {
            "model": config.openai_model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools

        try:
            with requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config.openai_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                aggregated = []
                final_usage = None
                tool_calls_acc = {}  # index → partial tool_call dict

                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    if not raw_line.startswith("data:"):
                        continue
                    data_str = raw_line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except ValueError:
                        continue
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            aggregated.append(content)
                            yield {
                                'delta': content, 'done': False,
                                'usage': None, 'tool_calls': None,
                            }
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            slot = tool_calls_acc.setdefault(idx, {
                                'id': tc.get('id'),
                                'type': tc.get('type', 'function'),
                                'function': {'name': '', 'arguments': ''},
                            })
                            fn = tc.get('function') or {}
                            if fn.get('name'):
                                slot['function']['name'] = fn['name']
                            if fn.get('arguments'):
                                slot['function']['arguments'] += fn['arguments']
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        final_usage = {
                            'prompt_tokens': u.get('prompt_tokens', 0),
                            'completion_tokens': u.get('completion_tokens', 0),
                            'total_tokens': u.get('total_tokens', 0),
                            'model': config.openai_model, 'provider': 'openai',
                        }

                if final_usage is None:
                    # Approximate when the provider didn't supply usage
                    full_text = ''.join(aggregated)
                    final_usage = {
                        'prompt_tokens': max(1, len(prompt) // 4),
                        'completion_tokens': max(1, len(full_text) // 4),
                        'total_tokens': max(2, (len(prompt) + len(full_text)) // 4),
                        'model': config.openai_model, 'provider': 'openai',
                    }
                config.increment_usage(tokens=final_usage.get('total_tokens', 0))
                tool_calls = list(tool_calls_acc.values()) if tool_calls_acc else None
                yield {
                    'delta': '', 'done': True,
                    'usage': final_usage, 'tool_calls': tool_calls,
                }
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI stream error: %s", e)
            yield {
                'delta': '', 'done': True,
                'usage': {
                    'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0,
                    'model': config.openai_model, 'provider': 'openai',
                    'error': str(e),
                },
                'tool_calls': None,
            }

    # ------------------------------------------------------------------
    # Phase 7 — tool calling (non-streaming variant).
    # ------------------------------------------------------------------

    def call_with_tools(self, prompt, config=None, system_prompt=None, tools=None):
        """Non-streaming call that surfaces the model's tool_calls when
        the model decides to invoke a tool. Returns
            (response_text, usage_dict, tool_calls_list_or_None).

        ``tool_calls`` is None when the model returned plain text.
        The gateway service handles dispatch + re-call loops on top.
        Only OpenAI is wired today; other providers return tool_calls=None
        and behave like plain call().
        """
        if self._is_simulation_mode() or not tools:
            text, usage = self.call(prompt, config=config, system_prompt=system_prompt)
            return text, usage, None

        if not config:
            config = self.env['ai.provider.config'].sudo().search(
                [('active', '=', True)], limit=1)
            if not config:
                text, usage = self._simulate_call(reason='no_provider_configured')
                return text, usage, None

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        elif config.system_prompt:
            full_prompt = f"{config.system_prompt}\n\n{prompt}"

        if config.ai_provider == 'openai':
            return self._call_openai_with_tools(full_prompt, config, tools)

        # Other providers: ignore tools for now.
        _logger.info(
            'call_with_tools: provider %s lacks tool-calling impl — '
            'ignoring tools and doing plain call', config.ai_provider)
        text, usage = self._call_ai_api(full_prompt, config)
        config.increment_usage(tokens=usage.get('total_tokens', 0))
        return text, usage, None

    def _call_openai_with_tools(self, prompt, config, tools):
        """OpenAI tool-calling. Returns (text, usage, tool_calls|None)."""
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
                        {"role": "system",
                         "content": "You are a helpful assistant. Call tools when appropriate."},
                        {"role": "user", "content": prompt},
                    ],
                    "tools": tools,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = data['choices'][0]['message']
            text = (choice.get('content') or '').strip()
            tool_calls = choice.get('tool_calls') or None
            api_usage = data.get('usage', {})
            usage = {
                'prompt_tokens': api_usage.get('prompt_tokens', 0),
                'completion_tokens': api_usage.get('completion_tokens', 0),
                'total_tokens': api_usage.get('total_tokens', 0),
                'model': config.openai_model, 'provider': 'openai',
            }
            config.increment_usage(tokens=usage.get('total_tokens', 0))
            return text, usage, tool_calls
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI tools API error: %s", e)
            raise UserError(_('OpenAI Tools Error: %s') % e)

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
            generation_config = {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            }
            # Gemini 2.5 family enables "thinking" by default, which silently
            # eats most of maxOutputTokens before the visible reply starts.
            # Disable it for structured replies — we want the full budget on
            # the JSON envelope, not hidden chain-of-thought.
            if (config.gemini_model or '').startswith('gemini-2.5'):
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": generation_config,
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
            generation_config = {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            }
            if (config.gemini_model or '').startswith('gemini-2.5'):
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
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
                    "generationConfig": generation_config,
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

    # ------------------------------------------------------------------
    # Embeddings (Phase B — semantic retrieval).
    # ------------------------------------------------------------------
    def call_embedding(self, texts, config=None):
        """Embed a list of strings. Returns (vectors, usage_dict).

        ``vectors`` is a list[list[float]] with one row per input. We
        dispatch by provider so adding OpenAI / Ollama embeddings is a
        single function. Today only Google's text-embedding-004 is
        wired — others raise gracefully.

        Empty input → ([], {}). Single-string input is auto-wrapped.
        """
        if not texts:
            return [], {}
        if isinstance(texts, str):
            texts = [texts]
        config = config or self.env['ai.provider.config'].search(
            [('active', '=', True)], limit=1,
        )
        if not config:
            raise UserError(_('No active AI provider configured.'))
        if self._is_simulation_mode():
            # Deterministic pseudo-vectors so tests / dev flows still work.
            import hashlib
            vectors = []
            for t in texts:
                h = hashlib.sha256((t or '').encode('utf-8')).digest()
                # 32 bytes -> 32 normalised floats. Repeat to 768 dims so
                # downstream code that hard-codes the dim still works.
                base = [(b - 128) / 128.0 for b in h]
                vec = (base * 24)[:768]
                vectors.append(vec)
            return vectors, {'provider': 'simulation', 'model': 'sim-embed', 'total_tokens': 0}
        if config.ai_provider == 'google':
            return self._call_gemini_embed(texts, config)
        # Fallthrough — providers without an embedding impl yet.
        raise UserError(_(
            "Embedding not implemented for provider '%s'. "
            "Switch to Google (gemini text-embedding-004) or add a wrapper."
        ) % config.ai_provider)

    def _call_gemini_embed(self, texts, config):
        """Call Gemini's embedContent endpoint, looping per-text.

        gemini-embedding-001 supports only the single-text
        embedContent method (no synchronous batch). It returns 3072
        dims by default; we request outputDimensionality=768 via
        Matryoshka so the resulting vectors fit our pgvector(768)
        column and stay compact.

        Returns (vectors, usage). Vectors are 1:1 with `texts`. If a
        single call fails the loop still returns an empty vector for
        that slot so the caller's indexing stays aligned."""
        model = "gemini-embedding-001"
        base_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "%s:embedContent?key=%s" % (model, config.gemini_api_key)
        )
        if len(texts) > 100:
            raise UserError(_('Embedding batch too large (max 100 per call).'))

        vectors: list[list[float]] = []
        ok = 0
        for t in texts:
            text = (t or '')[:8000]
            if not text.strip():
                vectors.append([])
                continue
            try:
                response = requests.post(
                    base_url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": text}]},
                        # Matryoshka — request a smaller vector that
                        # still preserves most of the semantic signal.
                        # Fits our pgvector(768) column.
                        "outputDimensionality": 768,
                    },
                    timeout=config.timeout,
                )
                response.raise_for_status()
                data = response.json()
                values = (data.get('embedding') or {}).get('values') or []
                vectors.append([float(x) for x in values])
                if values:
                    ok += 1
            except requests.exceptions.RequestException as e:
                _logger.warning("Gemini embed call failed for one text: %s", e)
                vectors.append([])
        return vectors, {
            'provider': 'google',
            'model': model,
            'total_tokens': sum(len((t or '').split()) for t in texts),
            'count_ok': ok,
        }

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
