# -*- coding: utf-8 -*-
"""Turn on provider prompt caching where nobody chose otherwise.

The runtime already composes a stable system-prompt prefix with a cache
break marker, but ab_ai_base only sends it as a cacheable block when
``ab_ai_base.provider_cache_enabled`` is truthy — and it defaulted off,
so every hop paid full price for the same prefix (98% prompt tokens,
0% cache). Only an UNSET parameter is touched; an explicit 'False'
set by an operator is respected.
"""
import logging

_logger = logging.getLogger(__name__)

PARAM = 'ab_ai_base.provider_cache_enabled'


def migrate(cr, version):
    cr.execute("SELECT 1 FROM ir_config_parameter WHERE key = %s", (PARAM,))
    if cr.fetchone():
        return
    cr.execute(
        "INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date) "
        "VALUES (%s, 'True', 1, now() at time zone 'UTC', 1, now() at time zone 'UTC')",
        (PARAM,))
    _logger.info('ab_ai_agent: enabled %s (was unset)', PARAM)
