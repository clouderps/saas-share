# -*- coding: utf-8 -*-
"""Encrypt any provider API keys that predate encryption-at-rest.

Before 18.0.1.3.0 the OpenAI / Gemini / Claude keys were stored as
plaintext in their own columns. This post-migration reads any plaintext
still present, Fernet-encrypts it into the matching *_encrypted column,
then blanks the plaintext column so nothing sensitive is left at rest.

Idempotent: once a row's plaintext is blanked, re-running is a no-op.
"""

import logging

from odoo import SUPERUSER_ID, api
from odoo.addons.ab_ai_base.lib import fernet as fernet_lib

_logger = logging.getLogger(__name__)

# (plaintext column, encrypted column)
KEY_COLUMNS = [
    ('openai_api_key', 'openai_api_key_encrypted'),
    ('gemini_api_key', 'gemini_api_key_encrypted'),
    ('claude_api_key', 'claude_api_key_encrypted'),
]


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    plain_cols = ', '.join(p for p, _enc in KEY_COLUMNS)
    # Column names are hardcoded constants above — no injection surface.
    cr.execute(f"SELECT id, {plain_cols} FROM ai_provider_config")
    rows = cr.fetchall()

    migrated = 0
    for row in rows:
        rec_id = row[0]
        updates = {}
        for idx, (plain_col, enc_col) in enumerate(KEY_COLUMNS, start=1):
            plaintext = row[idx]
            if plaintext:
                updates[enc_col] = fernet_lib.encrypt(env, plaintext)
                updates[plain_col] = ''
        if not updates:
            continue
        set_clause = ', '.join(f"{col} = %s" for col in updates)
        cr.execute(
            f"UPDATE ai_provider_config SET {set_clause} WHERE id = %s",
            list(updates.values()) + [rec_id],
        )
        migrated += 1

    if migrated:
        _logger.info(
            'ab_ai_base: encrypted plaintext provider API keys for '
            '%s config row(s)', migrated,
        )
