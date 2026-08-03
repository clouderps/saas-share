# -*- coding: utf-8 -*-
"""``ai.agent.command`` — the registry behind ``/create quote``.

One record per command. Bridges seed them from their own data files, so
a command exists exactly when its module does.

Two rules are enforced here rather than left to callers:

* **Permission.** ``available_for`` checks the command's own groups AND
  create access on the target model. A command the user could not
  perform by hand never appears in the palette and cannot be run.
* **Draft only.** ``run`` creates and returns a preview. It never
  posts, confirms or validates. Those are separate, already-gated
  actions (``record_action``), and keeping them separate is what makes
  a wrong extraction recoverable.
"""
from __future__ import annotations

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services import parser

_logger = logging.getLogger(__name__)


class AIAgentCommand(models.Model):
    _name = 'ai.agent.command'
    _description = 'AI Command'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True, index=True,
        help='Stable identifier, e.g. create_quote.')
    verb = fields.Char(
        required=True, index=True,
        help='What the user types after the slash, e.g. "create quote". '
             'Matched longest-first, so a more specific verb always wins '
             'over a shorter one that prefixes it.')
    target_model = fields.Char(
        required=True,
        help='Model to create. Must inherit ai.command.mixin.')
    description = fields.Text(
        help='Shown in the palette under the verb.')
    example = fields.Char(
        help='One realistic example, shown as placeholder text.')
    icon = fields.Char(default='fa-plus-circle')
    context = fields.Char(
        string='Target context',
        help="Python dict merged into the target model's context, e.g. "
             "{'ai_command_move_type': 'out_invoice'}. Lets two commands "
             "share one model without the model guessing which one ran — "
             "an invoice command must never produce a vendor bill because "
             "a field was mis-extracted.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, index=True)
    group_ids = fields.Many2many(
        'res.groups', 'ai_agent_command_group_rel', 'command_id', 'group_id',
        string='Restricted to',
        help='Empty = anyone who can create the target model. The model '
             'ACL is always checked on top of this.')

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(code)', 'Command code must be unique.'),
        ('verb_uniq', 'UNIQUE(verb)', 'Two commands cannot share a verb.'),
    ]

    @api.constrains('target_model')
    def _check_target_model(self):
        for command in self:
            model = self.env.get(command.target_model)
            if model is None:
                raise ValidationError(
                    _('Model "%s" is not installed.') % command.target_model)
            if not hasattr(model, '_ai_command_spec'):
                raise ValidationError(
                    _('Model "%s" must inherit ai.command.mixin to be '
                      'used as a command target.') % command.target_model)

    # ── Availability ───────────────────────────────────────────

    def available_for(self, user):
        """True when this user may actually run the command.

        The command records themselves are configuration, so they are
        read under sudo — a portal user asking what they can do must get
        "nothing", not an AccessError on the registry. The real gate is
        the target model's create ACL, checked as that user, which is
        what stops a command becoming a way around create rights.
        """
        self.ensure_one()
        command = self.sudo()
        if not command.active:
            return False
        if command.group_ids and not (command.group_ids & user.groups_id):
            return False
        model = self.env.get(command.target_model)
        if model is None:
            return False
        try:
            return model.with_user(user).has_access('create')
        except Exception:
            return False

    @api.model
    def palette_for_user(self, user=None):
        """Commands to offer in the ``/`` menu, this user's set only."""
        user = user or self.env.user
        out = []
        for command in self.sudo().search([]):
            if not command.available_for(user):
                continue
            out.append({
                'code': command.code,
                'verb': command.verb,
                'name': command.name,
                'description': command.description or '',
                'example': command.example or '',
                'icon': command.icon or 'fa-plus-circle',
            })
        return out

    def _command_context(self):
        """Extra context for the target model. Never trusted from a
        request — it comes from the command record, which only an
        administrator can edit."""
        raw = (self.sudo().context or '').strip()
        if not raw:
            return {}
        try:
            from odoo.tools.safe_eval import safe_eval
            value = safe_eval(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            _logger.warning('command %s has an unreadable context: %r',
                            self.sudo().code, raw)
            return {}

    # ── Execution ──────────────────────────────────────────────

    @api.model
    def parse_text(self, text):
        """Match text against the registry. Returns the parse plus the
        matched command record (or None)."""
        commands = self.sudo().search([])
        verbs = {c.verb: c for c in commands}
        result = parser.parse(text, list(verbs), {})
        command = verbs.get(result['verb']) if result['verb'] else None
        if command:
            # Re-sweep with the target model's own aliases now that we
            # know which model we are filling.
            model = self.env.get(command.target_model)
            if model is not None:
                model = model.with_context(**command._command_context())
            alias_map = model._ai_command_alias_map() if model is not None else {}
            _verb, rest = parser.match_verb(text, list(verbs))
            pairs, leftover = parser.sweep_pairs(rest, alias_map)
            result['pairs'], result['leftover'] = pairs, leftover
        return result, command

    def run(self, pairs, dry_run=False, create_missing=None):
        """Resolve and create a draft. Returns a result dict.

        ``status``:
          ``needs_input`` — questions to answer; nothing was created
          ``created``     — draft exists, preview attached
          ``blocked``     — not permitted
          ``error``       — resolution or create failed
        """
        self.ensure_one()
        if not self.available_for(self.env.user):
            return {'status': 'blocked',
                    'message': _('You do not have permission to run "%s".')
                               % self.sudo().name}

        model = self.env.get(self.sudo().target_model)
        if model is None:
            return {'status': 'error',
                    'message': _('Model "%s" is not installed.')
                               % self.sudo().target_model}
        model = model.with_context(**self._command_context())

        values, questions = model._ai_command_resolve(
            pairs or {}, create_missing=create_missing)
        blocking = [q for q in questions if q['kind'] != 'confirm']
        if blocking:
            return {
                'status': 'needs_input', 'command': self.sudo().code,
                'questions': questions, 'resolved': list(values),
                # Fields the user could unblock by agreeing to create the
                # record. Echoed so the caller knows exactly what to pass
                # back in create_missing.
                'creatable': [q['field'] for q in questions
                              if q.get('can_create')],
            }

        if dry_run:
            return {'status': 'dry_run', 'command': self.sudo().code,
                    'values': {k: str(v) for k, v in values.items()},
                    'questions': questions}

        try:
            record = model._ai_command_create(values)
        except (AccessError, UserError) as e:
            # These carry a message written for a user — pass it through.
            return {'status': 'blocked', 'message': str(e)}
        except Exception:
            _logger.exception('command %s failed to create %s',
                              self.sudo().code, self.sudo().target_model)
            return {'status': 'error',
                    'message': _('Could not create the %s. The error has '
                                 'been logged.') % self.sudo().name}

        return {
            'status': 'created',
            'command': self.sudo().code,
            'model': self.sudo().target_model,
            'id': record.id,
            'preview': record._ai_command_preview(),
            # Surviving 'confirm' questions are soft — a date read
            # day-first that could also be month-first. The draft exists;
            # the user is told what we assumed.
            'questions': [q for q in questions if q['kind'] == 'confirm'],
        }
