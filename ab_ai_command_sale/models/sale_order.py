# -*- coding: utf-8 -*-
"""Make sale.order creatable by command.

The whole bridge is the spec below — parsing, resolution, permissions,
preview and confirmation all live in ai.command.mixin.
"""
from odoo import api, models


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'ai.command.mixin']

    @api.model
    def _ai_command_spec(self):
        return {
            'partner_id': {
                # customer=True so "abdalmola" resolves against customers
                # and a vendor-only contact reports "not a customer"
                # rather than silently not matching.
                'aliases': ['partner', 'partner name', 'customer', 'client',
                            'عميل', 'اسم العميل', 'زبون'],
                'resolver': 'partner', 'customer': True, 'allow_create': True,
                'required': True, 'label': 'Customer',
            },
            'validity_date': {
                'aliases': ['date', 'valid until', 'expiry', 'تاريخ',
                            'صالح حتى'],
                'resolver': 'date',
            },
            'client_order_ref': {
                'aliases': ['reference', 'ref', 'po', 'customer ref', 'مرجع'],
                'resolver': 'text',
            },
            'order_line': {
                'aliases': ['items', 'item', 'products', 'lines', 'أصناف',
                            'المنتجات', 'بنود'],
                'resolver': 'product_lines', 'allow_create': True,
            },
        }

    @api.model
    def _ai_command_line_vals(self, line):
        vals = {'product_id': line['product_id'],
                'product_uom_qty': line['qty']}
        # An inline "@ 14" wins over the pricelist. It is the only price
        # a just-created product has, and when the product already
        # existed the user typing a price means they meant that price.
        if line.get('price_unit') is not None:
            vals['price_unit'] = line['price_unit']
        return vals
