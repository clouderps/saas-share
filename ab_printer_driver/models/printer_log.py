from odoo import fields, models


class PrinterLog(models.Model):
    _name = 'ab.printer.log'
    _description = 'Printer Log'
    _order = 'create_date desc'

    printer_config_id = fields.Many2one('ab.printer.config', string='Printer',
                                        ondelete='set null')
    printer_type = fields.Char(string='Printer Type')
    job_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('printing', 'Printing'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        string='Job Status', default='pending',
    )
    error_message = fields.Text(string='Error Message')
    duration = fields.Float(string='Duration (s)')
    # Source = 'pos_frontend' | 'pos_kitchen' | 'backend' | 'invoice' |
    #          'report' | 'test' | 'queue_retry'
    source = fields.Char(string='Source')
