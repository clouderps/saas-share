# -*- coding: utf-8 -*-
"""Phase H — ai.agent.topic.

A topic is a reusable capability bundle: instructions + a set of
tools. Agents reference topics rather than restating the same tool
list, so "Information Retrieval", "Navigation", "Write Actions" can
be shared across multiple personas.
"""
from __future__ import annotations

from odoo import fields, models, _


class AIAgentTopic(models.Model):
    _name = 'ai.agent.topic'
    _description = 'Ghaima AI — Agent capability bundle'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True, index=True)
    code = fields.Char(required=True, index=True, copy=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)

    auto_attach = fields.Boolean(
        string='Attach to the default assistant',
        default=False,
        help='When set, _heal_core_topics links this topic to the default '
             'assistant on every upgrade. Lets a module ship a capability '
             'that reaches existing tenants — the assistant record is '
             'noupdate=True in deployed databases, so a topic added to its '
             'seed data alone would never arrive.')

    # Instructions injected into the agent's system prompt right after
    # the persona block. Topic instructions tell the LLM how + when
    # to use the topic's tools; the agent's own prompt sets the tone.
    instructions = fields.Text(
        translate=True,
        help='Free-form guidance the LLM receives when this topic is '
             'active. Reference tools by their JSON name.')

    tool_ids = fields.Many2many(
        'ai.agent.tool', 'ai_agent_topic_tool_rel', 'topic_id', 'tool_id',
        string='Tools')

    agent_ids = fields.Many2many(
        'ai.agent', 'ai_agent_topic_rel', 'topic_id', 'agent_id',
        string='Used by Agents', readonly=True)
    agent_count = fields.Integer(
        compute='_compute_agent_count', store=False)

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)',
         'Topic code must be unique across the database.'),
    ]

    def _compute_agent_count(self):
        for topic in self:
            topic.agent_count = len(topic.agent_ids)
