# -*- coding: utf-8 -*-
"""Per-user MCP tool catalogue."""
from odoo.addons.ab_ai_agent.services import tool_dispatcher

# Screen-only tools: they drive the in-app web client and mean nothing to
# an external client. Excluded whatever their mcp_enabled flag says.
SCREEN_ONLY = frozenset({'navigate', 'screen_button', 'update_preference', 'update_settings'})


def is_screen_only(tool):
    return (tool.code in SCREEN_ONLY or tool.code.startswith('open_')
            or tool.category == 'navigation')


# Write tools known to be confirm-first (they return a proposal and only
# change data after the user's click in Ghaima). Any other write tool would
# execute straight away, so MCP never offers it.
CONFIRM_FIRST_EXTRA = frozenset({'record_action'})


# Read tools whose rows are people's names (customers, debtors, cashiers).
# Regex masking cannot catch names, so over MCP they need the plan's PII
# right (model.allow_pii); the in-app assistant is unaffected.
NAME_PII_TOOLS = frozenset({'top_customers', 'top_overdue_partners', 'top_cashiers'})


def is_confirm_first(tool):
    return (tool.code in tool_dispatcher.ACTION_TOOLS
            or tool.code in tool_dispatcher.PROPOSAL_TOOLS
            or tool.code in CONFIRM_FIRST_EXTRA
            or bool(tool.preset_json and tool.preset_op in ('create', 'update')))


def is_mcp_safe(tool, policy=None):
    """False for tools that could change data without a confirmation:
    server actions run directly, memory tools write directly, and any
    write tool that is not a known confirm-first tool."""
    if tool.dispatch_kind == 'server_action' or tool.category == 'memory':
        return False
    if tool.code in NAME_PII_TOOLS and policy is not None and not policy.allow_pii:
        return False
    if tool.is_write_action:
        if policy is not None and not policy.allow_write_actions:
            return False
        return is_confirm_first(tool)
    return True


def _has_callable(tool):
    return bool(tool.preset_json or tool_dispatcher.get(tool.code))


def mcp_policy(env, token):
    Policy = env['ai.feature.policy']
    return tool_dispatcher.ToolPolicy(
        allow_write_actions=bool(Policy.get('mcp.write_tools') and token.allow_write),
        allow_pii=bool(Policy.get('model.allow_pii')),
        name='mcp')


def tools_for(env, token, policy):
    """``ai.agent.tool`` records ``env.user`` may see over MCP via ``token``."""
    Tool = env['ai.agent.tool']
    # sudo: the catalogue read is not the gate; _offered_to() below checks
    # groups / plan / write permission for env.user.
    tools = Tool.sudo().search([('mcp_enabled', '=', True), ('active', '=', True)]).with_env(env)
    tools = tools.filtered(lambda t: not is_screen_only(t) and _has_callable(t)
                           and is_mcp_safe(t, policy))
    tools = tools._offered_to(env.user, policy)
    if token.preset == 'readonly':
        tools = tools.filtered(lambda t: not t._is_mutating())
    elif token.preset == 'custom':
        allowed = set(token.sudo().tool_ids.ids)
        tools = tools.filtered(lambda t: t.id in allowed)
    return tools
