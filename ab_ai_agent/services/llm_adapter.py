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
import uuid

_logger = logging.getLogger(__name__)


def call_llm(env, agent, *, system_prompt, user_prompt, tools=None,
             temperature=None, max_tokens=2000, image_data=None,
             image_mimetype=None, model_class_hint=None):
    """Resolve the LLM call path + execute.

    Returns:
        (response_text, usage_dict, routed_via)
        routed_via ∈ {'gateway', 'direct', 'sim'}

    Tools convention — provider-agnostic. The runtime serialises
    each tool with `ai.agent.tool.as_llm_schema()` and passes the
    list of dicts here; we adapt to the actual provider on the way out.
    """
    request_id = str(uuid.uuid4())
    temperature = temperature if temperature is not None else (
        agent.temperature() if agent else 0.3)
    model_class_hint = model_class_hint or (agent.model_class if agent else 'fast')

    # ── Path 1: central gateway via ab_ai_client ──────────────
    gateway = _try_get_gateway(env)
    if gateway:
        try:
            tool_codes = [t.get('name') for t in (tools or []) if t.get('name')]
            response, usage = gateway.call_ai(
                feature=_feature_for(agent),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                model_class=model_class_hint,
                image_data=image_data,
                image_mimetype=image_mimetype,
                tools=tool_codes if tool_codes else None,
            )
            usage = dict(usage or {})
            usage.setdefault('request_id', request_id)
            usage.setdefault('routed_via', 'gateway')
            return response, usage, 'gateway'
        except Exception as e:
            _logger.warning('Gateway call failed (%s) — trying direct provider', e)

    # ── Path 2: direct provider via ab_ai_base ────────────────
    Provider = env.get('ai.provider.service')
    if Provider is not None:
        try:
            response, usage = Provider.sudo().call(
                user_prompt,
                config=None,            # auto-pick active config
                system_prompt=system_prompt,
                image_data=image_data,
                image_mimetype=image_mimetype,
                model_override=None,    # no central routing without the gateway
            )
            usage = dict(usage or {})
            usage.setdefault('request_id', request_id)
            usage['routed_via'] = 'direct'
            return response, usage, 'direct'
        except Exception as e:
            _logger.warning('Direct provider call failed (%s) — simulating', e)

    # ── Path 3: simulation ─────────────────────────────────────
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

    Probes whether the gateway is *really* installed by checking for
    its own tables. On tenants and dev workspaces where saas-ai is
    on the addons_path but ab_ai_gateway isn't installed, the model
    classes load but tables are absent — calling the gateway endpoint
    in that case pollutes the log with "relation does not exist" lines
    AND wastes 1-3 s per request before the runtime falls back to the
    direct provider path. Probe result is cached on the registry per
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
    """True iff the gateway's own tables / columns exist on this DB.

    Cheap one-shot SQL — runs once per process. Tenants where
    ab_ai_gateway isn't installed get False and the runtime skips
    the broken endpoint entirely."""
    try:
        env.cr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_name = 'ai_tenant_budget'
        """)
        if env.cr.fetchone() is None:
            return False
        env.cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'ai_prompt_template'
               AND column_name = 'model_class'
        """)
        return env.cr.fetchone() is not None
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
