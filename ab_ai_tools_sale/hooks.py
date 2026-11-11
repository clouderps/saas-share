# -*- coding: utf-8 -*-
"""Adopt tool rows created before this pack existed, and offer the pack's
tools to the Ghaima Assistant. Shared logic: ab_ai_agent.services.tool_packs."""
from odoo.addons.ab_ai_agent.services.tool_packs import adopt_tool_rows, attach_to_assistant

from .services.sale_tools import TOOL_CODES

MODULE = 'ab_ai_tools_sale'
XMLIDS = {c: f'tool_{c}' for c in TOOL_CODES}


def pre_init_hook(env):
    adopt_tool_rows(env, MODULE, XMLIDS)


def post_init_hook(env):
    attach_to_assistant(env, MODULE, XMLIDS.values())
