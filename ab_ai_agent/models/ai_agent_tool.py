# -*- coding: utf-8 -*-
"""Phase H — ai.agent.tool.

A tool is an operator-editable wrapper around either:
  * a Python callable registered in services/tool_dispatcher.py, or
  * an ir.actions.server record with use_in_ai=True (future).

Tools own the JSON schema, the description shown to the LLM, the
ACL group, and the cost/safety knobs (allow_end_message, write-action
flag). The runtime resolves an agent's tool list and hands schemas
to the LLM provider.
"""
from __future__ import annotations

import json
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


CATEGORY_SELECTION = [
    ('retrieval',   'Information Retrieval'),
    ('navigation',  'UI Navigation'),
    ('write',       'Write / Mutation'),
    ('memory',      'Memory'),
    ('analysis',    'Analysis / Compute'),
    ('integration', 'External Integration'),
]


class AIAgentTool(models.Model):
    _name = 'ai.agent.tool'
    _description = 'Ghaima AI — Agent tool'
    _order = 'category, sequence, name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(
        required=True, index=True, copy=False,
        help='Stable identifier exposed to the LLM as the tool name. '
             'Lowercase snake_case; matches the Python dispatcher key.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, index=True)
    category = fields.Selection(CATEGORY_SELECTION, default='retrieval', required=True)

    description = fields.Text(
        required=True, translate=True,
        help="What the tool does — the LLM reads this to decide whether "
             "to call it. Keep it concrete, ≤ 200 words.")

    schema = fields.Text(
        required=True, default='{"type": "object", "properties": {}, "required": []}',
        help='JSON Schema for the tool parameters. Validated on save.')

    # Behaviour
    allow_end_message = fields.Boolean(
        default=False,
        help='When True, the runtime appends a __end_message parameter '
             'to the schema. The LLM must populate it on the final tool '
             'call — that text becomes the user-visible response. '
             'Pattern from Odoo 19 native; eliminates "agent loops after '
             'it already has the answer".')
    is_write_action = fields.Boolean(
        default=False, index=True,
        help='Tool mutates data. Pairs with the chip-driven two-phase '
             'confirmation flow — first call returns "requires_confirmation", '
             'second call (idempotency_key + confirm=True) executes.')
    requires_pii = fields.Boolean(
        default=False,
        help='Tool legitimately reads PII (customer names, emails). '
             'Agent must have allow_pii=True to invoke it.')

    # Dispatch
    dispatch_kind = fields.Selection([
        ('python', 'Python callable (services.tool_dispatcher)'),
        ('server_action', 'ir.actions.server record'),
    ], default='python', required=True)
    server_action_id = fields.Many2one(
        'ir.actions.server', ondelete='set null',
        help='When dispatch_kind=server_action, this action runs with '
             'arguments injected as the env.context.')

    # ACL
    group_ids = fields.Many2many(
        'res.groups', 'ai_agent_tool_group_rel', 'tool_id', 'group_id',
        string='Restricted to Groups',
        help='Empty = every internal user can invoke. The runtime checks '
             'this BEFORE dispatching.')

    # Reverse links
    topic_ids = fields.Many2many(
        'ai.agent.topic', 'ai_agent_topic_tool_rel', 'tool_id', 'topic_id',
        string='Topics')
    agent_ids = fields.Many2many(
        'ai.agent', 'ai_agent_tool_rel', 'tool_id', 'agent_id',
        string='Directly attached to agents')

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)',
         'Tool code must be unique across the database.'),
    ]

    # ── Validation ─────────────────────────────────────────────

    @api.constrains('schema')
    def _check_schema(self):
        for tool in self:
            try:
                data = json.loads(tool.schema or '{}')
            except (ValueError, TypeError) as e:
                raise ValidationError(_(
                    "Tool '%(name)s' has malformed JSON schema: %(err)s",
                    name=tool.name, err=str(e),
                ))
            if not isinstance(data, dict):
                raise ValidationError(_(
                    "Tool '%(name)s' schema must be a JSON object.",
                    name=tool.name,
                ))
            if data.get('type') and data['type'] != 'object':
                raise ValidationError(_(
                    "Tool '%(name)s' schema root must be type=object.",
                    name=tool.name,
                ))

    # ── Runtime helpers ────────────────────────────────────────

    def as_llm_schema(self, agent=None):
        """Build the provider-facing tool schema. When the tool's
        allow_end_message is True (and either the agent demands it or
        it's flagged at the tool level), inject __end_message into the
        schema so the LLM provides its final answer there.

        Returns a dict shaped for the underlying LLM service to consume.
        """
        self.ensure_one()
        schema = json.loads(self.schema or '{"type": "object", "properties": {}, "required": []}')
        schema.setdefault('type', 'object')
        schema.setdefault('properties', {})
        schema.setdefault('required', [])

        if self.allow_end_message:
            schema['properties']['__end_message'] = {
                'type': 'string',
                'description': ('Final user-visible message. Required on '
                                'the terminating call; leave empty if you '
                                'will call another tool after this one.'),
            }
            if '__end_message' not in schema['required']:
                schema['required'].append('__end_message')

        return {
            'name': self.code,
            'description': self.description or '',
            'parameters': schema,
            'is_write_action': self.is_write_action,
            'allow_end_message': self.allow_end_message,
        }

    def is_invocable_by(self, user):
        """Per-tool ACL check used by the runtime BEFORE dispatching."""
        self.ensure_one()
        if not self.active:
            return False
        if self.group_ids and not (self.group_ids & user.groups_id):
            return False
        return True
