# -*- coding: utf-8 -*-
"""Self-heal the system agent's topic wiring.

On long-lived tenants the seed `ai_agent_data.xml` `(6,0,[...])`
topic list on `agent_ghaima_assistant` has drifted (the live record
carries only general + date_math). A wholesale data re-seed would
clobber operator customisation, so instead we *append* the topics the
product guarantees — Navigation (open record/list/pivot/graph) and
Analytics (the deterministic `data_analysis` → chart tool).

Idempotent: `(4, id)` is a no-op when the link already exists. Safe to
re-run. Runs on upgrade to 18.0.1.8.1.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_TOPICS = ('ab_ai_agent.topic_navigation', 'ab_ai_agent.topic_analytics')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    agent = env.ref('ab_ai_agent.agent_ghaima_assistant',
                     raise_if_not_found=False)
    if not agent:
        _logger.info("agent_ghaima_assistant absent; nothing to heal")
        return
    have = set(agent.topic_ids.ids)
    add = []
    for xmlid in _TOPICS:
        topic = env.ref(xmlid, raise_if_not_found=False)
        if topic and topic.id not in have:
            add.append(topic.id)
    if add:
        agent.sudo().topic_ids = [(4, tid) for tid in add]
        _logger.info("Linked %d guaranteed topic(s) to Ghaima Assistant: %s",
                     len(add),
                     env['ai.agent.topic'].browse(add).mapped('code'))
    else:
        _logger.info("Ghaima Assistant topic wiring already complete")
