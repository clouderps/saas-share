# -*- coding: utf-8 -*-
"""Existing proposals predate MCP: they all came from the in-app assistant."""


def migrate(cr, version):
    if not version:
        return
    cr.execute("UPDATE ai_agent_pending_action SET origin = 'assistant' WHERE origin IS NULL")
