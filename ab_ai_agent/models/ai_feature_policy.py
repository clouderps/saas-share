# -*- coding: utf-8 -*-
"""ai.feature.policy — one place that answers "may this instance use X?".

Effective value = local setting combined with an optional ceiling:

* ``bool``  — local AND ceiling (``kill`` is the exception: local OR ceiling)
* ``limit`` — the smaller of the two; 0 means unlimited
* ``list``  — intersection; ``None`` means unrestricted
* ``enum``  — the more restrictive choice (lowest rank in its ordering)

Standalone, :meth:`_ceiling` returns ``None`` (no ceiling) and the local
settings decide. A SaaS bridge (tenant ceiling pushed from the plan)
overrides ``_ceiling`` only — never ``get``.

Keys mirror the plan's ``features.ai.*``. The assistant keys are owned
here and have real settings; the ``mcp.*``, ``branding.*`` and ``model.*``
keys are placeholders read from ``ab_ai_agent.feature.<key>`` until the
feature modules that own them (MCP server, branding, model catalogue)
ship their own settings.
"""
from __future__ import annotations

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

TRUE = ('1', 'true', 'yes')

# key: (kind, icp param, local default, enum ordering)
FEATURES = {
    'assistant.enabled':    ('bool', 'ab_ai_agent.assistant_enabled', True, None),
    'assistant.max_users':  ('limit', 'ab_ai_agent.assistant_max_users', 0, None),
    'assistant.activation': ('enum', 'ab_ai_agent.assistant_activation', 'self', ('admin', 'self')),
    'assistant.actions':    ('bool', 'ab_ai_agent.actions_enabled', True, None),
    'assistant.voice':      ('bool', 'ab_ai_agent.voice_enabled', True, None),
    # Pushed by the platform before this policy existed; kept as the local default.
    'agents.max':           ('limit', 'ab_ai_agent.max_agents', 0, None),
    'kill':                 ('kill', 'ab_ai_agent.kill_switch', False, None),
    # ── Placeholders — owned by later feature modules ───────────
    'mcp.enabled':          ('bool', 'ab_ai_agent.feature.mcp.enabled', False, None),
    'mcp.max_users':        ('limit', 'ab_ai_agent.feature.mcp.max_users', 0, None),
    'mcp.write_tools':      ('bool', 'ab_ai_agent.feature.mcp.write_tools', False, None),
    'mcp.max_calls_day':    ('limit', 'ab_ai_agent.feature.mcp.max_calls_day', 0, None),
    'mcp.clients':          ('list', 'ab_ai_agent.feature.mcp.clients', None, None),
    'branding.name':        ('bool', 'ab_ai_agent.feature.branding.name', True, None),
    'branding.persona':     ('bool', 'ab_ai_agent.feature.branding.persona', True, None),
    'model.choice':         ('enum', 'ab_ai_agent.feature.model.choice', 'none',
                             ('none', 'catalog', 'catalog_byok')),
    'model.tiers':          ('list', 'ab_ai_agent.feature.model.tiers', None, None),
    'model.regions':        ('list', 'ab_ai_agent.feature.model.regions', None, None),
    'model.allow_pii':      ('bool', 'ab_ai_agent.feature.model.allow_pii', False, None),
}


def _parse(kind, raw, default, order):
    if raw is None or (isinstance(raw, str) and raw.strip() == ''):
        return default
    if kind in ('bool', 'kill'):
        return raw if isinstance(raw, bool) else str(raw).strip().lower() in TRUE
    if kind == 'limit':
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return default
    if kind == 'list':
        if isinstance(raw, (list, tuple, set, frozenset)):
            items = raw
        else:
            items = str(raw).replace('\n', ',').split(',')
        return frozenset(str(i).strip() for i in items if str(i).strip())
    if kind == 'enum':
        raw = str(raw).strip()
        return raw if raw in order else default
    return raw


def combine(kind, local, ceiling, order=None):
    """Combine a local value with a ceiling value (``None`` = no ceiling)."""
    if ceiling is None:
        return local
    if kind == 'bool':
        return bool(local) and bool(ceiling)
    if kind == 'kill':
        return bool(local) or bool(ceiling)
    if kind == 'limit':
        vals = [v for v in (local, ceiling) if v]
        return min(vals) if vals else 0
    if kind == 'list':
        if local is None:
            return ceiling
        return frozenset(local) & frozenset(ceiling)
    if kind == 'enum':
        ranks = {v: i for i, v in enumerate(order)}
        return min((local, ceiling), key=lambda v: ranks.get(v, -1))
    return local


class AIFeaturePolicy(models.AbstractModel):
    _name = 'ai.feature.policy'
    _description = 'Ghaima AI — Feature policy (local setting AND ceiling)'

    @api.model
    def _ceiling(self):
        """``{key: value}`` the subscription allows, or None for no ceiling.

        The ONLY hook a SaaS bridge overrides. Missing keys = not capped.
        """
        return None

    @api.model
    def _local(self, key):
        kind, param, default, order = FEATURES[key]
        # sudo: ir.config_parameter is admin-only; these are instance-wide
        # feature flags every user's request has to evaluate.
        raw = self.env['ir.config_parameter'].sudo().get_param(param) or None  # unset → default
        return _parse(kind, raw, default, order)

    @api.model
    def _parse_cap(self, key, kind, raw, order):
        """Parse a ceiling value. A cap that is present but unreadable
        fails closed — it must never read as "no ceiling"."""
        if kind == 'list':
            # '' and [] both mean "nothing allowed" (None = not capped).
            if isinstance(raw, str) and not raw.strip():
                return frozenset()
            return _parse(kind, raw, frozenset(), order)
        cap = _parse(kind, raw, None, order)
        if cap is not None:
            return cap
        _logger.warning('ai.feature.policy: unreadable ceiling for %s: %r', key, raw)
        if kind == 'bool':
            return False
        if kind == 'kill':
            return True
        if kind == 'enum':
            return order[0]
        return None  # limit: keep the local value

    @api.model
    def get(self, key):
        if key not in FEATURES:
            raise KeyError(key)
        kind, _param, default, order = FEATURES[key]
        local = self._local(key)
        ceiling = self._ceiling() or {}
        cap = ceiling.get(key)
        if cap is not None:
            cap = self._parse_cap(key, kind, cap, order)
        return combine(kind, local, cap, order)

    @api.model
    def get_all(self):
        out = {}
        for key in FEATURES:
            value = self.get(key)
            out[key] = sorted(value) if isinstance(value, frozenset) else value
        return out
