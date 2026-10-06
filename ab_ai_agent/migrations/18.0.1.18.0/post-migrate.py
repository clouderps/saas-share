# -*- coding: utf-8 -*-
"""Default assistant gets every capability, once.

The deployed agent_ghaima_assistant row is noupdate, so the seed's new
use_all_capabilities / allow_write_actions values never reach existing
tenants. Set them here exactly once (a migration runs once per version),
so an operator who later switches them off in the console is respected.
Security is unchanged: tools run as the user and writes stay confirm-first.
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE ai_agent
           SET use_all_capabilities = TRUE,
               allow_write_actions = TRUE
         WHERE code = 'ghaima_assistant'
    """)
