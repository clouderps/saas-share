from odoo import fields, models


class PrinterCategory(models.Model):
    _name = 'ab.printer.category'
    _description = 'Printer Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color')
    printer_ids = fields.One2many(
        'ab.printer.config', 'category_id', string='Printers',
    )
    printer_count = fields.Integer(
        string='Printer Count', compute='_compute_printer_count',
    )

    def _compute_printer_count(self):
        for cat in self:
            cat.printer_count = len(cat.printer_ids)
