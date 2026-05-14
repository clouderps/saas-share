# -*- coding: utf-8 -*-
"""Phase H Part 12 — meter writer.

Single function that writes ONE ai.usage.local.log row per LLM call,
in its own savepoint so the row survives downstream rollbacks. Called
exclusively by llm_adapter.call_llm() — never elsewhere.
"""
from __future__ import annotations

import logging

from odoo import fields

_logger = logging.getLogger(__name__)


def record(env, *, request_id, surface, feature, agent=None, agent_skill=None,
           agent_run=None, record_ref=None, provider, model_used, model_class,
           routed_via, cache_hit=False,
           prompt_tokens=0, completion_tokens=0, cached_tokens=0,
           web_grounding_calls=0, audio_seconds=0.0,
           duration_ms=0, status='ok', error_message='',
           prompt_excerpt=''):
    """Record one metering row. Returns the new id or 0 on failure.

    All errors are swallowed and logged — meter writes must never
    break the calling feature. Cost is computed via the local price
    book at call time so historical rows are stable when rates change.
    """
    try:
        with env.cr.savepoint():
            PriceBook = env['ai.usage.price.book'].sudo()
            usd, sar = PriceBook.estimate_cost(
                provider or '', model_used or '',
                prompt_tokens or 0, completion_tokens or 0, cached_tokens or 0,
            )
            billable = 0.0 if cache_hit or status == 'sim' else sar

            log = env['ai.usage.local.log'].sudo().create({
                'request_id': request_id,
                'surface': surface,
                'feature': feature or '',
                'agent_id': agent.id if agent else False,
                'agent_skill_id': agent_skill.id if agent_skill else False,
                'agent_run_id': agent_run.id if agent_run else False,
                'user_id': env.uid,
                'company_id': env.company.id,
                'record_ref': _stringify_ref(record_ref),
                'provider': provider or '',
                'model_used': model_used or '',
                'model_class': model_class or '',
                'routed_via': routed_via or '',
                'cache_hit': bool(cache_hit),
                'prompt_tokens': prompt_tokens or 0,
                'completion_tokens': completion_tokens or 0,
                'cached_tokens': cached_tokens or 0,
                'web_grounding_calls': web_grounding_calls or 0,
                'audio_seconds': audio_seconds or 0.0,
                'est_cost_usd': usd,
                'est_cost_sar': sar,
                'est_cost_billable': billable,
                'duration_ms': duration_ms or 0,
                'status': status,
                'error_message': (error_message or '')[:1000],
                'prompt_excerpt': (prompt_excerpt or '')[:200],
                'timestamp': fields.Datetime.now(),
            })
            return log.id
    except Exception:
        _logger.warning("ai.usage.local.log write failed", exc_info=True)
        return 0


def _stringify_ref(ref):
    """ai.usage.local.log.record_ref is a Reference field expecting
    'model,id' string format. Accept either a recordset or the string."""
    if not ref:
        return False
    if isinstance(ref, str):
        return ref
    try:
        return f'{ref._name},{ref.id}'
    except Exception:
        return False


def emit_live(env, summary):
    """Push the latest cost summary to the live meter chip on the UI.

    Per the §13.7.4 decision: broadcast on per-company channel so the
    chip updates even when the agent is fired by a cron the current
    user didn't trigger."""
    try:
        env['bus.bus']._sendone(
            f'ai.usage.live.{env.company.id}',
            'ai.usage.live',
            summary,
        )
    except Exception:
        # Bus is best-effort — meter row already persisted.
        pass
