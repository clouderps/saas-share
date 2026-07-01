# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init(env):
    """Seed the ab.api.endpoint list from this server's live API surface."""
    try:
        env['ab.api.endpoint'].action_refresh()
    except Exception:  # noqa: BLE001 — routing map not ready is non-fatal
        pass
