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
             image_data=None, image_mimetype=None, model_override=None,
             tools=None):
        """Call AI provider with a prompt, optionally with an image.

        Args:
            prompt: The user prompt text
            config: Optional ai.provider.config record. Uses active config if not provided.
            system_prompt: Optional system prompt override. Uses config default if not provided.
            image_data: Optional base64-encoded image for vision/multimodal requests.
            image_mimetype: MIME type of the image (default: image/png).
            tools: Optional list of unified tool schemas (the dicts produced
                by ``ai.agent.tool.as_llm_schema()``). When supplied AND
                ``ab_ai_agent.native_tools_enabled`` is True, providers
                that support a native ``tools=`` slot receive them there
                and surface back ``usage['tool_calls']`` for the runtime
                to dispatch directly. When the flag is off (or the
                provider doesn't support it) tools are ignored — the
                runtime's legacy JSON-action protocol still works because
                the schemas remain embedded in the system_prompt body.

        Returns:
            tuple: (response_text, usage_dict) where usage_dict has:
                prompt_tokens, completion_tokens, total_tokens, model, provider
                (`provider` is 'simulation' when no real call was made).
                When the model decides to call a tool natively, also:
                ``tool_calls`` = list[{name, arguments(dict), id}].

        Simulation (Phase 2 of SAAS_AI_PLAN.md):
          - If ir.config_parameter `ab_ai_gateway.simulation` is True,
            we short-circuit before any HTTP and return a canned
            placeholder so the downstream pipeline still completes.
          - If no active ai.provider.config exists, we also simulate
            (rather than raising UserError) so a fresh install doesn't
            crash every AI feature.

        Prompt caching (T.1 Day 1, SAAS_AI_TOKEN_REDUCTION_SUMMARY.md):
          - When ir.config_parameter `ab_ai_base.provider_cache_enabled`
            is True, the system_prompt is threaded into the provider's
            native system slot (Anthropic: `system` array w/
            cache_control=ephemeral; OpenAI: `messages[0].role=system`,
            automatic prefix cache when ≥1024 tokens). Saves 50–90 %
            cost on cached tokens. Default off — when off, legacy
            behavior (concatenation into user prompt) is preserved
            byte-for-byte.

        Native tools (T.1 Day 3, SAAS_AI_TOKEN_REDUCTION_SUMMARY.md):
          - When ir.config_parameter `ab_ai_agent.native_tools_enabled`
            is True AND `tools` is non-empty, OpenAI and Anthropic
            receive the schemas in their provider-native slot and we
            parse ``tool_calls`` from the response. Saves 600–1 200
            tokens / turn (no JSON schema in the prompt body) and
            unlocks parallel tool calls on supported providers.
            Default off — when off, ``tools`` is ignored and the
            runtime continues to use the JSON-action text protocol.
        """
        if self._is_simulation_mode():
            return self._simulate_call(reason='explicit_toggle')

        if not config:
            config = self.env['ai.provider.config'].sudo().search(
                [('active', '=', True)], limit=1)
            if not config:
                return self._simulate_call(reason='no_provider_configured')

        effective_system = system_prompt or config.system_prompt or None

        if self._provider_cache_enabled():
            # Cache-friendly path: keep system separate so providers can
            # mark it as a cacheable prefix.
            user_prompt = prompt
            system_for_handler = effective_system
        else:
            # Legacy path: merge into user prompt (byte-for-byte identical
            # to pre-T.1 behavior).
            if effective_system:
                user_prompt = f"{effective_system}\n\n{prompt}"
            else:
                user_prompt = prompt
            system_for_handler = None

        # Native tools slot is engaged only when the flag is on AND the
        # caller passed at least one tool schema. Vision/image path stays
        # text-only — tool use during vision turns is rare and the
        # provider matrix differs.
        use_native_tools = bool(tools) and self._native_tools_enabled()
        tools_for_handler = tools if use_native_tools else None

        if image_data:
            response_text, usage = self._call_ai_api_with_image(
                user_prompt, config, image_data, image_mimetype or 'image/png',
                model_override=model_override,
                system_prompt=system_for_handler,
            )
        else:
            response_text, usage = self._call_ai_api(
                user_prompt, config, model_override=model_override,
                system_prompt=system_for_handler,
                tools=tools_for_handler,
            )
        config.increment_usage(tokens=usage.get('total_tokens', 0))
        return response_text, usage

    def _is_simulation_mode(self):
        """True when the gateway is configured to skip real provider calls."""
        icp = self.env['ir.config_parameter'].sudo()
        return str(icp.get_param('ab_ai_gateway.simulation', 'False')).lower() \
                in ('1', 'true', 'yes')

    def _provider_cache_enabled(self):
        """True when provider-native prompt caching should be engaged.

        Default False — when off, system_prompt is concatenated into the
        user prompt (legacy behavior). When on, providers receive the
        system_prompt in their native system slot and (for Anthropic) the
        block is marked `cache_control: ephemeral` — 5-min TTL, 90 %
        discount on cache reads, 25 % premium on cache writes."""
        icp = self.env['ir.config_parameter'].sudo()
        return str(icp.get_param('ab_ai_base.provider_cache_enabled', 'False')).lower() \
                in ('1', 'true', 'yes')

    def _native_tools_enabled(self):
        """True when the runtime should hand tools to the provider's
        native ``tools=`` slot instead of dumping JSON-schema into the
        system prompt body.

        Default False — when off, ``tools`` passed to ``call()`` is
        ignored and the runtime's JSON-action text protocol continues
        to work because the schemas are still embedded in the prompt.
        When on, OpenAI / Anthropic receive the schemas natively and
        we parse ``tool_calls`` from the response — saves 600–1 200
        tokens / turn and unlocks parallel tool calls."""
        icp = self.env['ir.config_parameter'].sudo()
        return str(icp.get_param('ab_ai_agent.native_tools_enabled', 'False')).lower() \
                in ('1', 'true', 'yes')

    def _cache_min_tokens(self, provider):
        """Per-provider minimum prompt length (chars) before we bother
        marking it cacheable. Anthropic requires ≥1024 tokens (~4096
        chars) for Sonnet/Opus; smaller blocks are rejected silently and
        we'd pay the 25 % write premium for nothing. Conservative."""
        return {
            'anthropic': 4096,   # ~1024 tokens
            'openai':    4096,   # ~1024 tokens (automatic cache threshold)
        }.get(provider, 4096)

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
                    "Authorization": "Bearer %s" % config._get_decrypted_key('openai_api_key'),
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

    def call_with_tools(self, prompt, config=None, system_prompt=None, tools=None,
                        model_override=None):
        """Non-streaming call that surfaces the model's tool_calls when
        the model decides to invoke a tool. Returns
            (response_text, usage_dict, tool_calls_list_or_None).

        ``tool_calls`` is None when the model returned plain text.
        The gateway service handles dispatch + re-call loops on top.
        Only OpenAI is wired today; other providers return tool_calls=None
        and behave like plain call().
        """
        if self._is_simulation_mode() or not tools:
            text, usage = self.call(
                prompt, config=config, system_prompt=system_prompt,
                model_override=model_override,
            )
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
            return self._call_openai_with_tools(
                full_prompt, config, tools, model_override=model_override,
            )

        # Other providers: ignore tools for now.
        _logger.info(
            'call_with_tools: provider %s lacks tool-calling impl — '
            'ignoring tools and doing plain call', config.ai_provider)
        text, usage = self._call_ai_api(
            full_prompt, config, model_override=model_override,
        )
        config.increment_usage(tokens=usage.get('total_tokens', 0))
        return text, usage, None

    def _call_openai_with_tools(self, prompt, config, tools, model_override=None):
        """OpenAI tool-calling. Returns (text, usage, tool_calls|None)."""
        model = model_override or config.openai_model
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config._get_decrypted_key('openai_api_key'),
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
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
                'model': model, 'provider': 'openai',
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

    def _call_ai_api(self, prompt, config, model_override=None,
                     system_prompt=None, tools=None):
        """Route to the appropriate provider API.

        ``model_override`` (Phase G.2): when non-empty, overrides the
        per-provider default model for this call only. Used by the
        gateway's class→model routing — the underlying provider config
        keeps its default for everything else.

        ``system_prompt`` (T.1): when non-None, the caller has opted into
        cache-friendly mode (see `_provider_cache_enabled`). Handlers
        that support a native system slot use it directly; handlers
        that don't fall back to internal concatenation so no content
        is dropped.

        ``tools`` (T.1/3): when non-None, the unified tool schemas (as
        produced by ``ai.agent.tool.as_llm_schema``) are translated to
        the provider's native ``tools=`` format. Providers that lack a
        native tool slot (gemini text, local) silently ignore the
        argument — the runtime's JSON-action text protocol still works
        because the schemas remain embedded in the prompt body.

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
        return handler(prompt, config, model_override=model_override,
                       system_prompt=system_prompt, tools=tools)

    def _call_ai_api_with_image(self, prompt, config, image_data, image_mimetype,
                                model_override=None, system_prompt=None):
        """Route to the appropriate provider with multimodal image support."""
        provider = config.ai_provider
        if provider == 'openai':
            return self._call_openai_vision(
                prompt, config, image_data, image_mimetype,
                model_override=model_override, system_prompt=system_prompt)
        elif provider == 'anthropic':
            return self._call_claude_vision(
                prompt, config, image_data, image_mimetype,
                model_override=model_override, system_prompt=system_prompt)
        elif provider == 'google':
            return self._call_gemini_vision(
                prompt, config, image_data, image_mimetype,
                model_override=model_override, system_prompt=system_prompt)
        else:
            _logger.warning('Provider %s does not support vision, falling back to text', provider)
            return self._call_ai_api(prompt, config, model_override=model_override,
                                     system_prompt=system_prompt)

    def _call_openai(self, prompt, config, model_override=None,
                     system_prompt=None, tools=None):
        """Call OpenAI API. Returns (text, usage_dict).

        T.1: when ``system_prompt`` is provided we put it in the system
        role message; OpenAI's automatic prefix cache then kicks in once
        the prefix ≥1024 tokens and is stable across requests (no opt-in
        flag needed — usage response surfaces `cached_tokens`).

        T.1/3: when ``tools`` is provided, translate the unified schemas
        to OpenAI's ``[{type:"function", function:{name, description,
        parameters}}]`` form and surface ``tool_calls`` in the usage
        dict (list of {name, arguments(dict), id}). The model can
        parallel-call multiple tools per response."""
        model = model_override or config.openai_model
        system_content = system_prompt or (
            "You are a helpful assistant that returns only valid JSON."
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if tools:
            body["tools"] = _tools_for_openai(tools)
            # ``auto`` is OpenAI's default; we set it explicitly so the
            # intent is auditable in HTTP traces. The model still picks
            # whether to call a tool or answer in plain text.
            body["tool_choice"] = "auto"
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config._get_decrypted_key('openai_api_key'),
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choice = data['choices'][0]['message']
            text = (choice.get('content') or '').strip()
            api_usage = data.get('usage', {})
            usage = {
                'prompt_tokens': api_usage.get('prompt_tokens', 0),
                'completion_tokens': api_usage.get('completion_tokens', 0),
                'total_tokens': api_usage.get('total_tokens', 0),
                'model': model,
                'provider': 'openai',
            }
            details = api_usage.get('prompt_tokens_details') or {}
            if details.get('cached_tokens'):
                usage['cache_read_tokens'] = details['cached_tokens']
                # The runtime reads 'cached_tokens'; writing only
                # 'cache_read_tokens' made the meter read 0 for
                # every provider even when caching worked.
                usage['cached_tokens'] = details['cached_tokens']
            raw_calls = choice.get('tool_calls') or []
            if raw_calls:
                usage['tool_calls'] = _parse_openai_tool_calls(raw_calls)
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI API error: %s", e)
            raise UserError(_('OpenAI API Error: %s') % e)

    def _call_gemini(self, prompt, config, model_override=None,
                     system_prompt=None, tools=None):
        """Call Google Gemini API. Returns (text, usage_dict).

        T.1: Gemini supports a native ``systemInstruction`` slot — we
        route ``system_prompt`` there when provided so the model treats
        it correctly. (Gemini's explicit context caching is a separate
        endpoint — not wired here; the system slot alone is the right
        first step.)"""
        model = model_override or config.gemini_model
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (
                model, config._get_decrypted_key('gemini_api_key')
            )
            generation_config = {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            }
            # Gemini 2.5 family enables "thinking" by default, which silently
            # eats most of maxOutputTokens before the visible reply starts.
            # Disable it for structured replies — we want the full budget on
            # the JSON envelope, not hidden chain-of-thought.
            if (model or '').startswith('gemini-2.5'):
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
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
                # Gemini 2.5 caches a stable prefix implicitly — no
                # explicit cachedContent needed — but it only reports it
                # here. Not reading it meant the meter showed 0% forever
                # and there was no way to tell whether caching worked.
                'cached_tokens': api_usage.get('cachedContentTokenCount', 0),
                'model': model,
                'provider': 'google',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Gemini API error: %s", e)
            raise UserError(_('Gemini API Error: %s') % e)

    def _call_claude(self, prompt, config, model_override=None,
                     system_prompt=None, tools=None):
        """Call Anthropic Claude API. Returns (text, usage_dict).

        T.1 prompt caching: when ``system_prompt`` is supplied AND is
        large enough to amortise the 25 % write premium, we send it as
        a top-level `system` content array with ``cache_control:
        ephemeral`` (5-min TTL). Subsequent calls with the same prefix
        within the TTL window read at a 90 % discount — see
        ``cache_read_input_tokens`` in the usage dict.

        T.1/3 native tools: when ``tools`` is supplied, translate to
        Anthropic's ``[{name, description, input_schema}]`` form and
        parse ``content[type=tool_use]`` blocks into
        ``usage['tool_calls']``. The visible text is the
        ``content[type=text]`` block (may be empty when the model goes
        straight to a tool call).
        """
        model = model_override or config.claude_model
        min_chars = self._cache_min_tokens('anthropic')
        try:
            payload = {
                "model": model,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                if len(system_prompt) >= min_chars and self._provider_cache_enabled():
                    # Cache-friendly path — system is an array of content
                    # blocks; the last block carries the cache_control
                    # marker. Anthropic caches the longest cacheable
                    # prefix that matches a prior request.
                    payload["system"] = [{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }]
                else:
                    # Below cache threshold (or flag off): use the plain
                    # string form — still gets the proper system role,
                    # just no caching.
                    payload["system"] = system_prompt
            if tools:
                payload["tools"] = _tools_for_anthropic(tools)
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config._get_decrypted_key('claude_api_key'),
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get('content') or []
            text_parts = []
            tool_uses = []
            for block in content_blocks:
                btype = block.get('type')
                if btype == 'text':
                    text_parts.append(block.get('text') or '')
                elif btype == 'tool_use':
                    tool_uses.append(block)
            text = ''.join(text_parts).strip()
            api_usage = data.get('usage', {})
            input_t = api_usage.get('input_tokens', 0)
            output_t = api_usage.get('output_tokens', 0)
            cache_write = api_usage.get('cache_creation_input_tokens', 0) or 0
            cache_read = api_usage.get('cache_read_input_tokens', 0) or 0
            usage = {
                # Anthropic excludes cache reads/writes from input_tokens
                # in the API response — fold them back in so the
                # tenant-side meter still sees a true input total.
                'prompt_tokens': input_t + cache_write + cache_read,
                'completion_tokens': output_t,
                'total_tokens': input_t + cache_write + cache_read + output_t,
                'model': model,
                'provider': 'anthropic',
            }
            if cache_write:
                usage['cache_write_tokens'] = cache_write
            if cache_read:
                usage['cache_read_tokens'] = cache_read
                usage['cached_tokens'] = cache_read
            if tool_uses:
                usage['tool_calls'] = _parse_anthropic_tool_uses(tool_uses)
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Claude API error: %s", e)
            raise UserError(_('Claude API Error: %s') % e)

    # ── Vision / Multimodal methods ──

    def _call_openai_vision(self, prompt, config, image_data, image_mimetype,
                            model_override=None, system_prompt=None):
        """Call OpenAI with image (GPT-4o vision). Returns (text, usage_dict)."""
        model = model_override or config.openai_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:{image_mimetype};base64,{image_data}",
            }},
        ]})
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer %s" % config._get_decrypted_key('openai_api_key'),
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
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
                'model': model, 'provider': 'openai',
            }
            details = api_usage.get('prompt_tokens_details') or {}
            if details.get('cached_tokens'):
                usage['cache_read_tokens'] = details['cached_tokens']
                # The runtime reads 'cached_tokens'; writing only
                # 'cache_read_tokens' made the meter read 0 for
                # every provider even when caching worked.
                usage['cached_tokens'] = details['cached_tokens']
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("OpenAI Vision error: %s", e)
            raise UserError(_('OpenAI Vision Error: %s') % e)

    def _call_claude_vision(self, prompt, config, image_data, image_mimetype,
                            model_override=None, system_prompt=None):
        """Call Claude with image (multimodal). Returns (text, usage_dict)."""
        model = model_override or config.claude_model
        media_type = image_mimetype
        if media_type == 'image/jpg':
            media_type = 'image/jpeg'
        min_chars = self._cache_min_tokens('anthropic')
        try:
            payload = {
                "model": model,
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
            }
            if system_prompt:
                if len(system_prompt) >= min_chars and self._provider_cache_enabled():
                    payload["system"] = [{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }]
                else:
                    payload["system"] = system_prompt
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config._get_decrypted_key('claude_api_key'),
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = data['content'][0]['text'].strip()
            api_usage = data.get('usage', {})
            input_t = api_usage.get('input_tokens', 0)
            output_t = api_usage.get('output_tokens', 0)
            cache_write = api_usage.get('cache_creation_input_tokens', 0) or 0
            cache_read = api_usage.get('cache_read_input_tokens', 0) or 0
            usage = {
                'prompt_tokens': input_t + cache_write + cache_read,
                'completion_tokens': output_t,
                'total_tokens': input_t + cache_write + cache_read + output_t,
                'model': model, 'provider': 'anthropic',
            }
            if cache_write:
                usage['cache_write_tokens'] = cache_write
            if cache_read:
                usage['cache_read_tokens'] = cache_read
                usage['cached_tokens'] = cache_read
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Claude Vision error: %s", e)
            raise UserError(_('Claude Vision Error: %s') % e)

    def _call_gemini_vision(self, prompt, config, image_data, image_mimetype,
                            model_override=None, system_prompt=None):
        """Call Gemini with image (multimodal). Returns (text, usage_dict)."""
        model = model_override or config.gemini_model
        try:
            url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (
                model, config._get_decrypted_key('gemini_api_key')
            )
            generation_config = {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
            }
            if (model or '').startswith('gemini-2.5'):
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {
                "contents": [{"parts": [
                    {"text": prompt},
                    {"inline_data": {
                        "mime_type": image_mimetype,
                        "data": image_data,
                    }},
                ]}],
                "generationConfig": generation_config,
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
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
                'cached_tokens': api_usage.get('cachedContentTokenCount', 0),
                'model': model, 'provider': 'google',
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
        # Simulation answers even with no provider row — same contract as
        # call()/stream_call(), which fall back to simulation instead of
        # erroring when nothing is configured.
        if self._is_simulation_mode() or not config:
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
            "%s:embedContent?key=%s" % (model, config._get_decrypted_key('gemini_api_key'))
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

    def _call_local_llm(self, prompt, config, model_override=None,
                         system_prompt=None, tools=None):
        """Call local LLM (Ollama or similar). Returns (text, usage_dict).

        Ollama accepts a top-level ``system`` field — we route
        ``system_prompt`` there when supplied so the model template
        applies it correctly."""
        model = model_override or config.local_llm_model
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": config.temperature},
            }
            if system_prompt:
                payload["system"] = system_prompt
            response = requests.post(
                config.local_llm_endpoint,
                json=payload,
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
                'model': model,
                'provider': 'local',
            }
            return text, usage
        except requests.exceptions.RequestException as e:
            _logger.error("Local LLM API error: %s", e)
            raise UserError(_('Local LLM Error: %s') % e)


# ─── Native tools — schema translation + response parsing (T.1/3) ─────
# Helpers live at module level so vision/streaming paths can reuse them
# without re-pulling the AbstractModel record. They take the unified
# tool-schema dict that ``ai.agent.tool.as_llm_schema()`` produces:
#   {'name', 'description', 'parameters', 'is_write_action',
#    'allow_end_message'}

def _tools_for_openai(tools):
    """Translate unified schemas → OpenAI ``tools=`` payload.

    OpenAI: ``[{type:"function", function:{name, description, parameters}}]``.
    Empty list when input is empty (caller should treat that as
    "no tools" and omit the key entirely).
    """
    out = []
    for t in (tools or []):
        name = t.get('name')
        if not name:
            continue
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": (t.get('description') or '')[:1024],
                "parameters": t.get('parameters') or {
                    "type": "object", "properties": {}, "required": [],
                },
            },
        })
    return out


def _tools_for_anthropic(tools):
    """Translate unified schemas → Anthropic ``tools=`` payload.

    Anthropic: ``[{name, description, input_schema}]``. Note that
    Anthropic calls the parameters field ``input_schema`` (not
    ``parameters``).
    """
    out = []
    for t in (tools or []):
        name = t.get('name')
        if not name:
            continue
        out.append({
            "name": name,
            "description": (t.get('description') or '')[:1024],
            "input_schema": t.get('parameters') or {
                "type": "object", "properties": {}, "required": [],
            },
        })
    return out


def _parse_openai_tool_calls(raw_calls):
    """Normalise OpenAI ``message.tool_calls`` → unified shape:
    list of ``{id, name, arguments(dict)}``.

    OpenAI sends arguments as a JSON STRING — we decode here so the
    runtime dispatcher doesn't have to know which provider produced
    the call. Malformed JSON degrades to ``{}`` (the dispatcher will
    surface a tool error to the LLM).
    """
    out = []
    for rc in raw_calls or []:
        fn = rc.get('function') or {}
        name = fn.get('name')
        if not name:
            continue
        raw_args = fn.get('arguments')
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except (ValueError, TypeError):
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        out.append({
            'id': rc.get('id') or '',
            'name': name,
            'arguments': args,
        })
    return out


def _parse_anthropic_tool_uses(blocks):
    """Normalise Anthropic ``tool_use`` content blocks → unified shape.

    Anthropic already returns ``input`` as a dict, so no JSON-string
    decode is needed. ``id`` is the ``tool_use_id`` the API expects
    in a follow-up tool_result block (we don't use that pattern yet —
    the agent runtime does a transcript-based re-prompt — but we keep
    it for the future native-conversation refactor).
    """
    out = []
    for b in blocks or []:
        if b.get('type') != 'tool_use':
            continue
        name = b.get('name')
        if not name:
            continue
        out.append({
            'id': b.get('id') or '',
            'name': name,
            'arguments': b.get('input') or {},
        })
    return out
