# -*- coding: utf-8 -*-
"""Make account.move creatable by command.

Highest-risk target so far, so two things are pinned here rather than
left to the generic path:

* the move type is forced per command (an invoice command must never
  produce a vendor bill because a field was mis-extracted), and
* only a DRAFT is created. Nothing in this file posts.
"""
from odoo import api, models


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'ai.command.mixin']

    @api.model
    def _ai_command_spec(self):
        # Which direction we are invoicing decides whether "abdalmola"
        # is looked up among customers or vendors.
        move_type = self.env.context.get('ai_command_move_type', 'out_invoice')
        is_customer = move_type in ('out_invoice', 'out_refund')
        return {
            'partner_id': {
                'aliases': (['partner', 'partner name', 'customer', 'client',
                             'عميل', 'اسم العميل', 'زبون']
                            if is_customer else
                            ['partner', 'partner name', 'vendor', 'supplier',
                             'مورد', 'اسم المورد']),
                'resolver': 'partner', 'customer': is_customer,
                'allow_create': True, 'required': True,
                'label': 'Customer' if is_customer else 'Vendor',
            },
            'invoice_date': {
                'aliases': ['date', 'invoice date', 'bill date', 'تاريخ',
                            'تاريخ الفاتورة'],
                'resolver': 'date',
            },
            'ref': {
                'aliases': ['reference', 'ref', 'مرجع'],
                'resolver': 'text',
            },
            'invoice_line_ids': {
                'aliases': ['items', 'item', 'products', 'lines', 'أصناف',
                            'المنتجات', 'بنود'],
                'resolver': 'product_lines', 'allow_create': True,
            },
        }

    @api.model
    def _ai_command_defaults(self):
        return {'move_type': self.env.context.get(
            'ai_command_move_type', 'out_invoice')}

    @api.model
    def _ai_command_line_vals(self, line):
        vals = {'product_id': line['product_id'], 'quantity': line['qty']}
        if line.get('price_unit') is not None:
            vals['price_unit'] = line['price_unit']
        return vals

    @api.model
    def _ai_command_preview_fields(self):
        return ['partner_id', 'invoice_date', 'ref']
