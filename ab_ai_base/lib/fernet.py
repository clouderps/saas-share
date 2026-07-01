"""Fernet credential vault helper for ab_ai_base.

Provider API keys (OpenAI / Gemini / Claude) are stored encrypted at
rest and decrypted only at the point they are used to call the provider.

This is a self-contained copy of the ~30-line helper that
`payment-gateway/ab_saas_payment_middleware/lib/fernet.py` provides.
It is duplicated on purpose: ab_ai_base lives in the `saas-share` repo
and installs on both DBCLOUD and tenant containers, while the payment
middleware is a separate repo/module — importing across repos would add
a fragile cross-repo dependency. The pattern mirrors
`ab_aws_saas_dns/models/aws_config.py`.

Master key parameter: ``ab_ai_base.encryption_key``. If unset on first
call, a fresh Fernet key is generated and persisted so the module is
self-bootstrapping in dev/staging. In production, ops should pre-seed the
parameter from the same KMS-derived value used by the other vaults.
"""

import logging

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ENCRYPTION_KEY_PARAM = 'ab_ai_base.encryption_key'


def _import_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as e:
        raise UserError(_(
            'cryptography library is not installed. Run:\n'
            '    pip install cryptography'
        )) from e
    return Fernet, InvalidToken


def _get_or_create_master_key(env):
    """Return the Fernet master key as bytes, generating one on first use."""
    Fernet, _InvalidToken = _import_fernet()
    icp = env['ir.config_parameter'].sudo()
    key = icp.get_param(ENCRYPTION_KEY_PARAM)
    if not key:
        key = Fernet.generate_key().decode('utf-8')
        icp.set_param(ENCRYPTION_KEY_PARAM, key)
        _logger.warning(
            'Generated new ab_ai_base encryption key. In production, '
            'pre-seed %s from your KMS-derived value.',
            ENCRYPTION_KEY_PARAM,
        )
    return key.encode('utf-8')


def get_fernet(env):
    Fernet, _InvalidToken = _import_fernet()
    return Fernet(_get_or_create_master_key(env))


def encrypt(env, plaintext):
    """Encrypt a string. Empty input returns empty string so an unset
    credential can be stored cleanly without a token over empty bytes."""
    if not plaintext:
        return ''
    fernet = get_fernet(env)
    token = fernet.encrypt(plaintext.encode('utf-8'))
    return token.decode('utf-8')


def decrypt(env, ciphertext):
    """Decrypt a Fernet token previously created by encrypt(). Returns
    empty string on empty input. Raises UserError on a bad token —
    typically means the master key was rotated without re-encrypting."""
    if not ciphertext:
        return ''
    _Fernet, InvalidToken = _import_fernet()
    fernet = get_fernet(env)
    try:
        plain = fernet.decrypt(ciphertext.encode('utf-8'))
    except InvalidToken as e:
        _logger.error('Failed to decrypt an ab_ai_base provider key')
        raise UserError(_(
            'Failed to decrypt an AI provider API key. The encryption '
            'key may have been rotated without re-encrypting stored '
            'secrets. Re-enter the affected provider key.'
        )) from e
    return plain.decode('utf-8')
