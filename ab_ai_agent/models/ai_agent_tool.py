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

    name = fields.Char(required=True, index=True, translate=True)
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

    # Console builder: a no-code tool is a preset over one of the generic
    # data tools (search / count / read / open / create / update).
    is_custom = fields.Boolean(
        default=False, readonly=True, copy=False,
        help='Created from the Agent Console builder. Module-shipped tools '
             'are protected.')
    preset_json = fields.Text(
        help='Builder preset: {"model", "op", "domain", "fields", "limit"}. '
             'When set, the dispatcher runs the matching generic data tool '
             'with this preset; the model cannot widen the fixed filter.')
    preset_model = fields.Char(readonly=True, index=True)
    preset_op = fields.Char(readonly=True)

    # External exposure (MCP). Off by default: a tool reaches an external
    # client only when an operator opts it in.
    mcp_enabled = fields.Boolean(
        string='Expose over MCP', default=False, index=True,
        help='Offer this tool to external MCP clients. The same gates apply '
             'as in the in-app assistant (groups, record rules, plan).')
    output_schema = fields.Text(
        help='Optional JSON Schema of the result, advertised to MCP clients '
             'as outputSchema.')

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

    @api.constrains('output_schema')
    def _check_output_schema(self):
        for tool in self.filtered('output_schema'):
            try:
                data = json.loads(tool.output_schema)
            except (ValueError, TypeError):
                data = None
            if not isinstance(data, dict):
                raise ValidationError(_(
                    "Tool '%(name)s' output schema must be a JSON object.",
                    name=tool.name))

    # ── Offering / external spec ───────────────────────────────

    def _is_mutating(self):
        """True for tools that change data, directly or once confirmed."""
        self.ensure_one()
        from ..services import tool_dispatcher
        return bool(self.is_write_action
                    or self.code in tool_dispatcher.ACTION_TOOLS
                    or self.code in tool_dispatcher.PROPOSAL_TOOLS
                    or (self.preset_json and self.preset_op in ('create', 'update')))

    def _offered_to(self, user, policy):
        """Subset of ``self`` that may be offered to ``user`` under ``policy``
        (an ``ai.agent`` record or a ``tool_dispatcher.ToolPolicy``).

        Write tools the policy may not run are not offered at all: listing a
        tool the dispatcher will refuse only teaches the model to call it
        again and again. The actions kill switch and the plan ceiling
        (central) hide every confirm-first tool; a tenant setting cannot
        re-enable what the subscription does not include.
        """
        from ..services import tool_dispatcher
        from ..services.llm_adapter import gateway_policy
        icp = self.env['ir.config_parameter'].sudo()

        def flag(key, default='True'):
            return str(icp.get_param(key, default)).lower() in ('1', 'true', 'yes')
        can_write = bool(policy) and bool(policy.allow_write_actions)
        actions_on = self.env['ai.feature.policy'].get('assistant.actions') and can_write
        if actions_on and gateway_policy(self.env).get('actions') is False:
            actions_on = False
        memory_on = flag('ab_ai_agent.user_memory')

        def allowed(t):
            if not t.is_invocable_by(user):
                return False
            if (t.code in tool_dispatcher.ACTION_TOOLS
                    or t.code in tool_dispatcher.PROPOSAL_TOOLS) and not actions_on:
                return False
            if t.preset_json and t.preset_op in ('create', 'update') and not actions_on:
                # Console-made write presets only propose, but they are still
                # writes: kill switch, plan and write permission all apply.
                return False
            if t.is_write_action:
                # A user's own memory is theirs to write; everything else
                # needs write permission (confirm-first action tools are not
                # write actions at dispatch — they only propose).
                return (t.category == 'memory' and memory_on) or can_write
            return True
        return self.filtered(allowed)

    def tool_spec(self):
        """Transport-neutral description of the tool (MCP and others)."""
        self.ensure_one()
        schema = json.loads(self.schema or '{}') or {}
        schema.setdefault('type', 'object')
        schema.setdefault('properties', {})
        # __end_message is an in-app LLM helper, never an external argument.
        schema['properties'].pop('__end_message', None)
        if '__end_message' in (schema.get('required') or []):
            schema['required'] = [r for r in schema['required'] if r != '__end_message']
        mutating = self._is_mutating()
        spec = {
            'name': self.code,
            'title': self.name or self.code,
            'description': self.description or '',
            'inputSchema': schema,
            'annotations': {
                'title': self.name or self.code,
                'readOnlyHint': not mutating,
                'destructiveHint': mutating,
            },
            # sudo: group xmlids are metadata; reading them must not need
            # Administration rights.
            'groups': [x for x in self.group_ids.sudo().get_external_id().values() if x],
        }
        if self.output_schema:
            spec['outputSchema'] = json.loads(self.output_schema)
        return spec

    def as_mcp_schema(self):
        """The tool as an MCP ``tools/list`` entry."""
        spec = self.tool_spec()
        spec.pop('groups', None)
        return spec

    @api.constrains('preset_json')
    def _check_preset(self):
        from ..services import generic_data
        for tool in self.filtered('preset_json'):
            try:
                preset = json.loads(tool.preset_json)
            except (ValueError, TypeError):
                raise ValidationError(_("Tool '%(name)s' has a malformed preset.", name=tool.name))
            if not isinstance(preset, dict) or preset.get('op') not in generic_data.PRESET_OPS:
                raise ValidationError(_("Tool '%(name)s' has an unknown operation.", name=tool.name))
            if not preset.get('model') or generic_data.model_blocked(self.env, preset['model']):
                raise ValidationError(_(
                    "Tool '%(name)s': the assistant cannot use this model.", name=tool.name))

    def is_invocable_by(self, user):
        """Per-tool ACL check used by the runtime BEFORE dispatching."""
        self.ensure_one()
        if not self.active:
            return False
        if self.group_ids and not (self.group_ids & user.groups_id):
            return False
        return True

    def _builder_edit_payload(self):
        """What the console's edit dialog needs to show a builder tool as
        saved (fixed filter, fields, Arabic description), so saving an edit
        never silently drops them."""
        self.ensure_one()
        import json
        try:
            preset = json.loads(self.preset_json or '{}')
        except ValueError:
            preset = {}
        lang_ar = 'ar_001' if self.env['res.lang']._lang_get('ar_001') else None
        return {
            'preset_domain': preset.get('domain') or [],
            'preset_fields': preset.get('fields') or [],
            'description_ar': (self.with_context(lang=lang_ar).description or '') if lang_ar else '',
        }
