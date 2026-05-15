import base64
import logging

from odoo import api, fields, models

from ..lib import escpos as escpos_lib, image as image_lib

_logger = logging.getLogger(__name__)


class PrinterJob(models.Model):
    """Queue of pending print jobs with retry + bus.bus notifications.

    Submitters (POS frontend, account.move, sale.order, stock.picking)
    enqueue a job here and get a job_id back; cron drains the queue
    with backoff retry. Status is fanned out on bus channel
    'ab_printer_job_<id>' so the submitter's UI can render progress
    in real time.

    Why a queue instead of straight TCP send?
      - Network blips don't lose prints.
      - Retry / backoff is centralised, not duplicated in every caller.
      - Auditable in the backend.
      - Lets us shed load: if the printer is offline, queued jobs
        wait without burning HTTP threads.
    """
    _name = 'ab.printer.job'
    _description = 'Printer Job'
    _order = 'priority desc, create_date'

    name = fields.Char(string='Reference', default='New', readonly=True)
    printer_config_id = fields.Many2one(
        'ab.printer.config', string='Printer', required=True, ondelete='cascade',
    )
    agent_id = fields.Many2one(
        'ab.printer.agent', string='Via Agent', ondelete='set null',
        help='When set, this job is dispatched by the named LAN bridge '
             'agent, not the Odoo server.',
    )
    op_type = fields.Selection(
        [('print', 'Print'), ('test', 'Test Slip'), ('verify', 'Verify')],
        string='Operation', default='print', required=True,
        help='What the worker should do with this job.',
    )
    payload_kind = fields.Selection(
        [
            ('escpos', 'Raw ESC/POS bytes'),
            ('image',  'JPEG/PNG image'),
            ('summary', 'Structured order summary'),
        ],
        string='Payload Kind', required=True, default='escpos',
    )
    payload_b64 = fields.Text(string='Payload (base64)')
    state = fields.Selection(
        [
            ('queued',    'Queued'),
            ('claimed',   'Claimed by Agent'),
            ('sending',   'Sending'),
            ('retrying',  'Retrying'),
            ('done',      'Done'),
            ('failed',    'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='queued', tracking=True, index=True,
    )
    claimed_at = fields.Datetime(string='Claimed At', readonly=True)
    priority = fields.Integer(string='Priority', default=10,
                              help='Higher prints first.')
    attempts = fields.Integer(string='Attempts', default=0, readonly=True)
    max_attempts = fields.Integer(string='Max Attempts', default=3)
    last_error = fields.Text(string='Last Error', readonly=True)
    last_attempt_at = fields.Datetime(string='Last Attempt', readonly=True)
    duration_ms = fields.Integer(string='Last Duration (ms)', readonly=True)
    source = fields.Char(string='Source', help='Submitting subsystem.')

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get('name') or v['name'] == 'New':
                v['name'] = self.env['ir.sequence'].next_by_code(
                    'ab.printer.job') or 'JOB-NEW'
        return super().create(vals_list)

    # ── Dispatch one job ──────────────────────────────────────────

    def _decode_payload(self):
        self.ensure_one()
        raw = base64.b64decode(self.payload_b64 or '')
        if self.payload_kind == 'escpos':
            return raw
        if self.payload_kind == 'image':
            max_w = (image_lib.THERMAL_58MM_MAX_WIDTH
                     if self.printer_config_id.paper_width_mm == '58'
                     else image_lib.THERMAL_80MM_MAX_WIDTH)
            return image_lib.image_to_escpos_raster(raw, max_width=max_w)
        if self.payload_kind == 'summary':
            import json
            return escpos_lib.build_order_summary(json.loads(raw.decode('utf-8')))
        return raw

    def _dispatch_one(self):
        self.ensure_one()
        self.write({'state': 'sending',
                    'last_attempt_at': fields.Datetime.now(),
                    'attempts': self.attempts + 1})
        try:
            data = self._decode_payload()
        except Exception as e:
            self.write({'state': 'failed', 'last_error': f'decode: {e}'})
            self._notify()
            return False

        res = self.printer_config_id.print_bytes(
            data, source=self.source or 'queue', record_ref=self,
        )
        self.duration_ms = int((res.get('duration') or 0) * 1000)

        if res.get('success'):
            self.state = 'done'
            self.last_error = ''
            self._notify()
            return True

        # Retry?
        if self.attempts < self.max_attempts:
            self.state = 'retrying'
            self.last_error = res.get('error') or ''
        else:
            self.state = 'failed'
            self.last_error = res.get('error') or 'Exceeded max attempts'
        self._notify()
        return False

    def _notify(self):
        """Fan out the current state on bus channel 'ab_printer_job_<id>'."""
        try:
            self.env['bus.bus']._sendone(
                f'ab_printer_job_{self.id}', 'state',
                {
                    'job_id': self.id, 'state': self.state,
                    'attempts': self.attempts, 'error': self.last_error or '',
                    'duration_ms': self.duration_ms,
                },
            )
        except Exception:
            _logger.debug('bus notify failed for printer job %s', self.id)

    # ── Cron drain ────────────────────────────────────────────────

    @api.model
    def _cron_drain_queue(self, limit=50):
        """Process queued + retrying jobs in priority order.

        Skips agent-owned jobs — those are pulled by the agent's /poll
        endpoint and executed inside the customer's LAN.
        """
        jobs = self.search(
            [('state', 'in', ('queued', 'retrying')),
             ('agent_id', '=', False)],
            order='priority desc, create_date', limit=limit,
        )
        for j in jobs:
            j._dispatch_one()

    @api.model
    def _cron_reap_stale_claims(self):
        """Recover jobs claimed by an agent that never reported back.

        After 90 seconds in 'claimed' with no /report, mark them
        retrying so another agent /poll can pick them up.
        """
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(seconds=90)
        stale = self.search([('state', '=', 'claimed'),
                             ('claimed_at', '<', cutoff)])
        for j in stale:
            if j.attempts >= j.max_attempts:
                j.write({'state': 'failed',
                         'last_error': 'Agent claimed but never reported'})
            else:
                j.write({'state': 'retrying',
                         'last_error': 'Agent timeout — re-queued'})
            j._notify()

    # ── Actions ───────────────────────────────────────────────────

    def action_retry(self):
        for j in self:
            j.write({'state': 'queued', 'attempts': 0, 'last_error': ''})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_dispatch_now(self):
        """Bypass the cron — useful when an operator wants to force a
        retry from the UI without waiting up to 60s."""
        for j in self:
            if j.state in ('queued', 'retrying'):
                j._dispatch_one()
