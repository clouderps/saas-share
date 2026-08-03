# -*- coding: utf-8 -*-
"""``ai.command.mixin`` — how a business model becomes AI-creatable.

A domain model inherits this and declares which of its fields the
assistant may fill and what those fields are called in a user's own
words. Everything else — parsing, resolution, permission checks,
preview, confirmation — is handled by the core.

Why a mixin rather than a central registry: a command must not exist
when its module does not. Declaring ``/create quote`` inside a bridge
that ``auto_install``s with ``sale`` means the command appears exactly
when Sales is installed and disappears when it is not, with no
conditional code anywhere. Same shape as ``ab.branch.mixin``.

Minimal bridge::

    class SaleOrder(models.Model):
        _name = 'sale.order'
        _inherit = ['sale.order', 'ai.command.mixin']

        @api.model
        def _ai_command_spec(self):
            return {
                'partner_id': {'aliases': ['partner', 'customer', 'عميل'],
                               'resolver': 'partner', 'required': True},
                'validity_date': {'aliases': ['date', 'تاريخ'],
                                  'resolver': 'date'},
                'order_line': {'aliases': ['items', 'products', 'أصناف'],
                               'resolver': 'product_lines'},
            }
"""
from __future__ import annotations

import logging

from odoo import _, api, models

from ..services import resolvers

_logger = logging.getLogger(__name__)


class AICommandMixin(models.AbstractModel):
    _name = 'ai.command.mixin'
    _description = 'AI Command Target'

    # ── Declaration ────────────────────────────────────────────

    @api.model
    def _ai_command_spec(self):
        """``{field: {aliases: [...], resolver: str, required: bool}}``.

        Resolvers: ``partner`` | ``date`` | ``product_lines`` | ``text``
        | ``number``. Anything else falls back to ``text``.
        """
        return {}

    @api.model
    def _ai_command_alias_map(self):
        """Normalised alias → canonical field. The field's own name and
        its translated label are always accepted, so a bridge only has
        to list the *extra* words people use."""
        from ..services.parser import normalise_key
        out = {}
        fields_meta = self.fields_get()
        for field, spec in self._ai_command_spec().items():
            names = list(spec.get('aliases') or [])
            names.append(field)
            label = (fields_meta.get(field) or {}).get('string')
            if label:
                names.append(label)
            for alias in names:
                out.setdefault(normalise_key(alias), field)
        return out

    @api.model
    def _ai_command_defaults(self):
        """Extra create() values every command of this model needs."""
        return {}

    # ── Resolution ─────────────────────────────────────────────

    @api.model
    def _ai_command_resolve(self, pairs):
        """Resolve raw strings to real values.

        Returns ``(values, questions)``. ``questions`` is what the user
        still has to answer — a missing required field, an ambiguous
        partner, a product that matched nothing. A non-empty
        ``questions`` means nothing is created.
        """
        spec = self._ai_command_spec()
        values, questions = {}, []

        for field, raw in (pairs or {}).items():
            rule = spec.get(field)
            if not rule:
                continue
            kind = rule.get('resolver', 'text')

            if kind == 'partner':
                res = resolvers.resolve_partner(
                    self.env, raw, customer=rule.get('customer'))
                if res['confidence'] in ('exact', 'likely'):
                    values[field] = res['value']
                else:
                    questions.append({
                        'field': field, 'kind': 'partner', 'query': raw,
                        'message': res['note'] or _('Which partner?'),
                        'options': res['alternatives'],
                    })

            elif kind == 'date':
                res = resolvers.resolve_date(self.env, raw)
                if res['value']:
                    values[field] = res['value']
                    if res['note']:
                        questions.append({
                            'field': field, 'kind': 'confirm',
                            'query': raw, 'message': res['note'], 'options': [],
                        })
                else:
                    questions.append({
                        'field': field, 'kind': 'date', 'query': raw,
                        'message': res['note'], 'options': [],
                    })

            elif kind == 'product_lines':
                lines, problems = resolvers.resolve_product_lines(self.env, raw)
                if lines:
                    values[field] = lines
                for problem in problems:
                    questions.append({
                        'field': field, 'kind': 'product',
                        'query': problem['query'],
                        'message': problem['result']['note'],
                        'options': problem['result']['alternatives'],
                    })

            elif kind == 'number':
                try:
                    values[field] = float(str(raw).replace(',', '.'))
                except (TypeError, ValueError):
                    questions.append({
                        'field': field, 'kind': 'number', 'query': raw,
                        'message': _('"%s" is not a number.') % raw,
                        'options': [],
                    })
            else:
                values[field] = raw

        for field, rule in spec.items():
            if rule.get('required') and field not in values:
                if not any(q['field'] == field for q in questions):
                    questions.append({
                        'field': field, 'kind': 'missing', 'query': '',
                        'message': _('%s is required.')
                                   % (rule.get('label') or field),
                        'options': [],
                    })
        return values, questions

    # ── Creation ───────────────────────────────────────────────

    @api.model
    def _ai_command_line_field(self):
        """One2many holding the document lines, when there is one."""
        for field, rule in self._ai_command_spec().items():
            if rule.get('resolver') == 'product_lines':
                return field
        return None

    @api.model
    def _ai_command_line_vals(self, line):
        """One resolved line → create() vals for the o2m."""
        return {'product_id': line['product_id'], 'product_uom_qty': line['qty']}

    @api.model
    def _ai_command_create(self, values):
        """Create the draft.

        Runs as the requesting user on purpose: create rights, record
        rules and multi-company all apply exactly as they would if the
        user had clicked New. If they cannot create it by hand, the
        assistant cannot create it for them.
        """
        line_field = self._ai_command_line_field()
        vals = {k: v for k, v in values.items() if k != line_field}
        vals.update(self._ai_command_defaults())
        if line_field and values.get(line_field):
            vals[line_field] = [
                (0, 0, self._ai_command_line_vals(line))
                for line in values[line_field]
            ]
        return self.create(vals)

    # ── Preview ────────────────────────────────────────────────

    @api.model
    def _ai_command_preview_fields(self):
        """Header fields to show in the confirmation card, in order."""
        return [f for f, r in self._ai_command_spec().items()
                if r.get('resolver') != 'product_lines']

    def _ai_command_preview(self):
        """Render the created draft for confirmation.

        Deliberately reads back off the *record*, not the input: the user
        confirms the partner that was actually matched and the total that
        was actually computed, not the text they typed.
        """
        self.ensure_one()
        meta = self.fields_get()
        rows = []
        for field in self._ai_command_preview_fields():
            if field not in self._fields:
                continue
            value = self[field]
            if hasattr(value, 'display_name'):
                shown = value.display_name if value else ''
            elif hasattr(value, 'strftime'):
                shown = value.strftime('%d %B %Y')   # long form on purpose
            else:
                shown = value
            if shown in (False, None, ''):
                continue
            rows.append([(meta.get(field) or {}).get('string') or field,
                         str(shown)])

        lines = []
        line_field = self._ai_command_line_field()
        if line_field and line_field in self._fields:
            for line in self[line_field]:
                qty = getattr(line, 'product_uom_qty', None)
                if qty is None:
                    qty = getattr(line, 'product_qty', 1)
                lines.append([
                    line.product_id.display_name if line.product_id else '',
                    str(qty),
                    str(getattr(line, 'price_subtotal', '') or ''),
                ])

        return {
            'model': self._name,
            'id': self.id,
            'name': self.display_name,
            'header': rows,
            'lines': lines,
            'total': getattr(self, 'amount_total', None),
            'currency': (self.currency_id.name
                         if 'currency_id' in self._fields and self.currency_id
                         else ''),
        }
