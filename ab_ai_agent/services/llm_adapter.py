# -*- coding: utf-8 -*-
"""Phase H — gateway-optional LLM adapter.

Single seam between the agent runtime and the LLM call. Tries the
central gateway first (inherits budgets / cache / fallback /
guardrails / model routing); falls back to a direct provider call
when no ai.client.config exists (development / central diagnostics /
disaster recovery); simulation as last resort.

Removing the gateway leaves the runtime functional via path #2.
The agent module never imports ab_ai_gateway directly.
"""
from __future__ import annotations

import logging
import time
import uuid

_logger = logging.getLogger(__name__)


class AiProviderError(Exception):
    """A *configured* AI provider/gateway call failed.

    Raised so the runtime finalizes the run as ``state='error'`` (visible to
    monitoring) instead of silently degrading a real outage to the canned
    simulation string and reporting it as a successful ``done`` answer.
    """


NATIVE_TOOL_PROVIDERS = ('openai', 'anthropic', 'google')

# ``ab_ai_agent.llm_mode``:
#   auto    — the central gateway when this tenant is linked, else its own
#             provider key (default; the historical behaviour)
#   gateway — always the gateway; no silent fallback to a local key
#   direct  — always the tenant's own provider key; the gateway is ignored
LLM_MODES = ('auto', 'gateway', 'direct')

# Gateway unreachable (DNS, refused, 5xx, bad URL) in auto mode: skip it
# for this long instead of paying a failed round-trip on every step.
_BREAKER_SECONDS = 300
_gateway_down_until = {}      # dbname → epoch seconds


def llm_mode(env):
    mode = env['ir.config_parameter'].sudo().get_param('ab_ai_agent.llm_mode', 'auto')
    return mode if mode in LLM_MODES else 'auto'


def gateway_for_turn(env):
    """The gateway link this turn will use, or None. One answer shared by
    the prompt builder (native or text protocol) and call_llm, so the two
    always agree."""
    mode = llm_mode(env)
    if mode == 'direct':
        return None
    if mode == 'auto' and _gateway_down_until.get(env.cr.dbname, 0) > time.time():
        return None
    return _try_get_gateway(env)


def _trip_breaker(env, error):
    _gateway_down_until[env.cr.dbname] = time.time() + _BREAKER_SECONDS
    _logger.warning('AI gateway unreachable (%s) — using the direct provider '
                    'for %d s', error, _BREAKER_SECONDS)


def _is_transport_error(error):
    """Unreachable / broken gateway, as opposed to an answer from it
    (quota exceeded, plan refuses the feature) that must be respected."""
    try:
        import requests
    except ImportError:            # pragma: no cover
        return False
    return isinstance(error, (requests.exceptions.ConnectionError,
                              requests.exceptions.Timeout,
                              requests.exceptions.HTTPError,
                              requests.exceptions.InvalidURL,
                              requests.exceptions.MissingSchema,
                              ValueError))      # non-JSON reply


def gateway_policy(env):
    """The plan's ceiling for the assistant, as last reported by central
    ({'actions': bool, 'voice': bool}); {} when not linked / not reported."""
    gw = _try_get_gateway(env) if llm_mode(env) != 'direct' else None
    if not gw or not hasattr(gw, 'get_policy'):
        return {}
    try:
        return gw.get_policy()
    except Exception:
        return {}


def native_tools_active(env):
    """True when this turn's tool calls will travel as provider-native
    function calls: the flag is on, and either the gateway this turn uses
    passes native tools through, or the active local provider implements
    them. The prompt then asks for plain answers instead of the JSON text
    protocol."""
    icp = env['ir.config_parameter'].sudo()
    if str(icp.get_param('ab_ai_agent.native_tools_enabled', 'True')).lower() not in ('1', 'true', 'yes'):
        return False
    gateway = gateway_for_turn(env)
    if gateway:
        return bool(getattr(gateway, 'has_capability', None)
                    and gateway.has_capability('native_tools'))
    if llm_mode(env) == 'gateway':
        return False
    Cfg = env.get('ai.provider.config')
    if Cfg is None:
        return False
    cfg = Cfg.sudo().search([('active', '=', True)], limit=1)
    return bool(cfg) and cfg.ai_provider in NATIVE_TOOL_PROVIDERS


def _has_active_provider(env):
    """True iff a real provider config is active — i.e. a failure is an
    OUTAGE, not just an unconfigured dev box that should simulate."""
    Cfg = env.get('ai.provider.config')
    if Cfg is None:
        return False
    try:
        return bool(Cfg.sudo().search_count([('active', '=', True)]))
    except Exception:
        return False


def _configured_max_tokens(env, fallback=2000):
    """Output ceiling from the active provider config.

    The gateway path used to receive a hard-coded 2000 while the direct
    path quietly used the config, so raising ai.provider.config.max_tokens
    changed the answer length on a tenant talking to a provider directly
    and did nothing at all on one routed through the central gateway.
    Same setting, same screen, two different behaviours.
    """
    Config = env.get('ai.provider.config')
    if Config is None:
        return fallback
    try:
        cfg = Config.sudo().search([('max_tokens', '>', 0)], limit=1)
        return int(cfg.max_tokens) if cfg else fallback
    except Exception:
        return fallback


def call_llm(env, agent, *, system_prompt, user_prompt, tools=None,
             temperature=None, max_tokens=None, image_data=None,
             image_mimetype=None, model_class_hint=None, model_override=None):
    """Resolve the LLM call path + execute.

    Returns:
        (response_text, usage_dict, routed_via)
        routed_via ∈ {'gateway', 'direct', 'sim'}

    Tools convention — provider-agnostic. The runtime serialises
    each tool with `ai.agent.tool.as_llm_schema()` and passes the
    list of dicts here; we adapt to the actual provider on the way out.
    """
    request_id = str(uuid.uuid4())
    if max_tokens is None:
        max_tokens = _configured_max_tokens(env)
    temperature = temperature if temperature is not None else (
        agent.temperature() if agent else 0.3)
    model_class_hint = model_class_hint or (agent.model_class if agent else 'fast')

    last_error = None

    mode = llm_mode(env)

    # ── Path 1: central gateway via ab_ai_client ──────────────
    gateway = gateway_for_turn(env)
    if mode == 'gateway' and not gateway:
        raise AiProviderError('LLM mode is "gateway" but this company is not '
                              'linked to the central AI gateway.')
    if gateway:
        native = bool(tools) and native_tools_active(env)
        try:
            tool_codes = [t.get('name') for t in (tools or []) if t.get('name')]
            response, usage = gateway.call_ai(
                feature=_feature_for(agent),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                model_class=model_class_hint,
                **({'model_override': model_override} if model_override else {}),
                image_data=image_data,
                image_mimetype=image_mimetype,
                request_id=request_id,
                # Native: full schemas travel, tool calls come back, tools
                # run here as the user. Otherwise the legacy name list.
                **({'tool_schemas': tools} if native else
                   {'tools': tool_codes} if tool_codes else {}),
            )
            usage = dict(usage or {})
            if not usage.get('tool_calls'):
                usage.pop('tool_calls', None)
            usage.setdefault('request_id', request_id)
            usage.setdefault('routed_via', 'gateway')
            return response, usage, 'gateway'
        except Exception as e:
            last_error = e
            if mode == 'gateway':
                raise AiProviderError(str(e))
            if _is_transport_error(e):
                _trip_breaker(env, e)
            elif not _has_active_provider(env):
                # The gateway ANSWERED with a refusal (quota, plan) and
                # there is no own key to fall back to: say so.
                raise AiProviderError(str(e))
            else:
                _logger.warning('Gateway call failed (%s) — trying direct provider', e)

    # ── Path 2: direct provider via ab_ai_base ────────────────
    # T.1/3 native tools: pass full unified schemas through. The provider
    # service decides whether to use them — gated on
    # ``ab_ai_agent.native_tools_enabled`` AND provider support. When
    # the flag is off, ai_service ignores ``tools`` and the runtime's
    # JSON-action text protocol stays in effect.
    Provider = env.get('ai.provider.service')
    if Provider is not None:
        try:
            response, usage = Provider.sudo().call(
                user_prompt,
                config=None,            # auto-pick active config
                system_prompt=system_prompt,
                image_data=image_data,
                image_mimetype=image_mimetype,
                # the stronger model for complex questions (runtime._route_model)
                model_override=model_override,
                tools=tools or None,
            )
            usage = dict(usage or {})
            usage.setdefault('request_id', request_id)
            usage['routed_via'] = 'direct'
            return response, usage, 'direct'
        except Exception as e:
            _logger.warning('Direct provider call failed (%s)', e)
            last_error = e

    # A *configured* path failed (tenant gateway present, or an active
    # ai.provider.config exists) — surface it as an error instead of
    # masking a live outage as a successful simulated answer.
    if last_error is not None and (gateway or _has_active_provider(env)):
        raise AiProviderError(str(last_error))

    # ── Path 3: simulation (nothing configured — dev / staging) ─
    response = (
        '[Simulated AI output — no gateway, no provider, simulation mode.] '
        'Configure ai.client.config (tenant) or ai.provider.config (central) '
        'to enable real LLM responses.'
    )
    usage = {
        'request_id': request_id,
        'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0,
        'cost_usd': 0.0, 'model': 'simulation', 'provider': 'simulation',
        'simulated': True, 'routed_via': 'sim',
    }
    return response, usage, 'sim'


def _try_get_gateway(env):
    """Return an active ai.client.config or None — never raises.

    Probes whether ab_ai_client is *really* installed by checking for
    its table: when saas-ai is on the addons_path but ab_ai_client isn't
    installed, the model class loads but the table is absent, and reading
    it pollutes the log with "relation does not exist" lines. Probe result is cached on the registry per
    process so the SQL only fires once after a restart.
    """
    Cfg = env.get('ai.client.config')
    if Cfg is None:
        return None

    registry = env.registry
    cached = getattr(registry, '_aigent_gateway_installed', None)
    if cached is None:
        cached = _probe_gateway_installed(env)
        try:
            registry._aigent_gateway_installed = cached
        except Exception:
            pass
    if not cached:
        return None

    try:
        return Cfg.sudo().get_config()
    except Exception:
        return None


def _probe_gateway_installed(env):
    """True iff the gateway *client* table exists on this DB.

    Cheap one-shot SQL — runs once per process. It must probe
    ab_ai_client's own ``ai_client_config`` (the model read next), not
    the gateway server's tables: ab_ai_gateway lives only on the
    management DB while this agent runs on tenants, so probing
    ``ai_tenant_budget`` failed on every tenant and sent all agent
    answers to simulation ("no gateway, no provider") even with a
    valid, active gateway config."""
    try:
        env.cr.execute("SELECT to_regclass('public.ai_client_config') IS NOT NULL")
        return bool(env.cr.fetchone()[0])
    except Exception:
        return False


def _feature_for(agent):
    """Map agent surface → gateway feature code so the analytics
    line up with existing dashboards."""
    if not agent:
        return 'chat'
    return {
        'chat':     'chat',
        'chatter':  'chat',
        'composer': 'chat',
        'website':  'website_chatbot',
        'cron':     'custom',
    }.get(agent.surface_ids or 'chat', 'chat')
