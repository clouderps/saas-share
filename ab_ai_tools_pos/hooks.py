# -*- coding: utf-8 -*-
"""Adopt tool rows created before this pack existed, and offer the pack's
tools to the Ghaima Assistant. Shared logic: ab_ai_agent.services.tool_packs."""
from odoo.addons.ab_ai_agent.services.tool_packs import adopt_tool_rows, attach_to_assistant

from .services.pos_tools import TOOL_XMLIDS

MODULE = 'ab_ai_tools_pos'
XMLIDS = dict(TOOL_XMLIDS)


def pre_init_hook(env):
    adopt_tool_rows(env, MODULE, XMLIDS)


def post_init_hook(env):
    attach_to_assistant(env, MODULE, XMLIDS.values())
