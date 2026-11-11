# -*- coding: utf-8 -*-
"""Per-user assistant activation: keep everyone who could use it working.

Before 18.0.1.20.0 every internal user had the assistant. Activation now
defaults to "self", so the non-breaking choice is to activate ALL active
internal users (not only those with a run in the last 90 days — an
occasional user would otherwise lose the button silently). No seat limit
is set by default, so this never trips the seat constraint.
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE res_users
           SET ai_assistant_active = TRUE,
               ai_assistant_activated_on = COALESCE(ai_assistant_activated_on, create_date, now() at time zone 'UTC')
         WHERE share IS NOT TRUE AND active
    """)
