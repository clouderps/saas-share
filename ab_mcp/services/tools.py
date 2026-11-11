# -*- coding: utf-8 -*-
"""Read tools shipped by ab_mcp."""
from odoo.addons.ab_ai_agent.services import tool_dispatcher


def get_proposal_status(env, agent=None, key=None, **_kw):
    # Own-rows record rule limits the lookup to the caller's proposals.
    row = env['ai.agent.pending.action'].search(
        [('key', '=', key or ''), ('user_id', '=', env.uid)], limit=1)
    if not row:
        return {'key': key, 'state': 'unknown',
                'message': 'No proposal with this key for you.'}
    return row._mcp_status()


tool_dispatcher.register('get_proposal_status', get_proposal_status)
