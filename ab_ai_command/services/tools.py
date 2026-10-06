# -*- coding: utf-8 -*-
"""Expose commands to the agent runtime.

Registered as a write-action tool, so it inherits the machinery that is
already in place: ``allow_write_actions`` on the agent, the two-phase
confirmation chips, and the idempotency-protected action log. No new
write path and no second audit trail.

The tool is what makes the prose form work. ``/create quote partner: x``
is parsed without a model call; "make a quote for x" reaches the same
place because the model calls this tool with the fields it extracted.
"""
from __future__ import annotations

import logging

from odoo.addons.ab_ai_agent.services import tool_dispatcher

_logger = logging.getLogger(__name__)


def _builtin_list_commands(env, agent=None, **_kw):
    """Commands this user may run. Grounds the model so it cannot offer
    a command the user has no access to."""
    Command = env.get('ai.agent.command')
    if Command is None:
        return {'error': 'ai.agent.command not installed'}
    palette = Command.palette_for_user(env.user)
    return {
        'commands': palette,
        'count': len(palette),
        'note': ('Only what this user may run. Never offer a command that '
                 'is absent from this list.'),
    }


class _Rollback(Exception):
    pass


def _dry_run(env, record, pairs, create_missing):
    """Resolve without leaving anything behind: ``create_missing`` may
    create a partner/product during resolution, so the whole dry run sits
    in a savepoint that is always rolled back."""
    box = {}
    try:
        with env.cr.savepoint():
            box['result'] = record.run(pairs, dry_run=True, create_missing=create_missing)
            raise _Rollback()
    except _Rollback:
        pass
    env.invalidate_all()
    return box.get('result') or {'status': 'error'}


def _builtin_run_command(env, agent=None, command=None, fields=None,
                         text=None, create_missing=None, _ai_confirmed=False, **_kw):
    """Create a draft document from a command.

    Accepts either an explicit ``command`` code plus a ``fields`` dict
    (the model extracted them), or raw ``text`` to parse (the user typed
    the slash form). Always creates a DRAFT and returns a preview —
    never posts or confirms.
    """
    Command = env.get('ai.agent.command')
    if Command is None:
        return {'error': 'ai.agent.command not installed'}

    record = None
    pairs = dict(fields or {})

    if command:
        record = Command.search([('code', '=', command)], limit=1)
        if not record:
            record = Command.search([('verb', '=', command)], limit=1)

    if not record and text:
        parsed, record = Command.parse_text(text)
        if record:
            # Explicit fields win — the model has more context than the
            # sweep does about which value belongs to which field.
            merged = dict(parsed['pairs'])
            merged.update(pairs)
            pairs = merged

    if not record:
        palette = Command.palette_for_user(env.user)
        return {
            'error': 'no such command',
            'available': [c['verb'] for c in palette],
            'note': ('Tell the user which commands they can run, using the '
                     'list above. Do not invent one.'),
        }

    if isinstance(create_missing, list):
        create_missing = {f: True for f in create_missing}
    if not _ai_confirmed:
        # Confirm-first like every other agent write: resolve now (so
        # needs_input questions still come back immediately), create only
        # after the user presses Confirm on the proposal.
        preview = _dry_run(env, record, pairs, create_missing)
        if preview.get('status') != 'dry_run':
            if preview.get('status') == 'needs_input':
                preview['note'] = _NEEDS_INPUT_NOTE
            return preview
        from odoo.addons.ab_ai_agent.services.agent_actions import _propose
        details = [f'{k}: {v}' for k, v in (preview.get('values') or {}).items()]
        return _propose(env, 'run_command',
                        {'command': record.sudo().code, 'fields': pairs,
                         'create_missing': create_missing or None},
                        None, env._('Create a draft: %s', record.sudo().name), details)
    result = record.run(pairs, create_missing=create_missing)
    if result.get('status') == 'needs_input':
        result['note'] = _NEEDS_INPUT_NOTE
    elif result.get('status') == 'created':
        result['note'] = (
            'A DRAFT was created — nothing is confirmed or posted. Show '
            'the preview, state it is a draft, and tell them how to '
            'confirm it. If a question remains, it is an assumption we '
            'made (e.g. how a date was read) — surface it.')
    return result


_NEEDS_INPUT_NOTE = (
    'Nothing was created. Ask the user ONLY about the questions '
    'listed, in their own words, and offer the options verbatim '
    'when there are any. Never pick one for them. '
    'For a question of kind create_offer the record does not '
    'exist yet — ask whether to create it, and only if they say '
    'yes call this tool again with the same fields plus '
    'create_missing set to those field names. Never set '
    'create_missing without being asked: a typo would become a '
    'duplicate customer or a junk product.')


def register():
    # Proposal-only at dispatch: hidden by the actions kill switch / plan.
    tool_dispatcher.PROPOSAL_TOOLS.add('run_command')
    tool_dispatcher.register('list_commands', _builtin_list_commands)
    tool_dispatcher.register('run_command', _builtin_run_command)


register()
