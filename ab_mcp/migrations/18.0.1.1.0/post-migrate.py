# -*- coding: utf-8 -*-
"""token / config_snippet became non-stored on mcp.connect.wizard: Odoo keeps
the old columns, which may still hold plaintext tokens from earlier dialogs.
Drop them (transient table; nothing else reads them)."""


def migrate(cr, version):
    cr.execute("ALTER TABLE mcp_connect_wizard DROP COLUMN IF EXISTS token, "
               "DROP COLUMN IF EXISTS config_snippet")
