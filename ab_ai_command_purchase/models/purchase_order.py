# -*- coding: utf-8 -*-
"""Make purchase.order creatable by command."""
from odoo import api, models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'ai.command.mixin']

    @api.model
    def _ai_command_spec(self):
        return {
            'partner_id': {
                'aliases': ['vendor', 'supplier', 'partner', 'partner name',
                            'مورد', 'اسم المورد'],
                # customer=False → resolve against suppliers, and say so
                # when the name exists but is not set up as one.
                'resolver': 'partner', 'customer': False,
                'required': True, 'label': 'Vendor',
            },
            'date_planned': {
                'aliases': ['date', 'expected', 'delivery date', 'تاريخ',
                            'تاريخ التسليم'],
                'resolver': 'date',
            },
            'partner_ref': {
                'aliases': ['reference', 'ref', 'vendor ref', 'مرجع'],
                'resolver': 'text',
            },
            'order_line': {
                'aliases': ['items', 'item', 'products', 'lines', 'أصناف',
                            'المنتجات', 'بنود'],
                'resolver': 'product_lines',
            },
        }

    @api.model
    def _ai_command_line_vals(self, line):
        # purchase.order.line uses product_qty, not product_uom_qty, and
        # needs a planned date on every line.
        vals = {'product_id': line['product_id'], 'product_qty': line['qty']}
        product = self.env['product.product'].browse(line['product_id'])
        vals['name'] = product.display_name
        vals['price_unit'] = product.standard_price
        return vals
