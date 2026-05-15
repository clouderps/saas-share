"""Bridge agent registry.

An ``ab.printer.agent`` row represents a small daemon installed on a PC
inside the customer's LAN. The daemon opens **outbound** HTTP long-poll
requests to this Odoo instance, picks up scan/print jobs queued
server-side, executes them locally (where it actually has L2 reach to
the printer), and reports the result back.

The cloud server cannot speak TCP to RFC-1918 IPs behind the customer's
NAT. The agent inverts the direction of every printer-bound network
operation so the SaaS works regardless of where Odoo is hosted.

Auth: every agent gets a UUID4 hex token at create time. The agent
sends it in the ``X-Agent-Token`` header on every request. Token never
leaves the agent's local config file.
"""
import uuid

from odoo import api, fields, models

AGENT_ONLINE_GRACE_S = 60  # last_seen within this window = online


class PrinterAgent(models.Model):
    _name = 'ab.printer.agent'
    _description = 'Printer Bridge Agent'
    _order = 'sequence, name'

    name = fields.Char(string='Agent Name', required=True,
                       help="Operator-visible label, e.g. 'Main Branch — Front Office PC'.")
    sequence = fields.Integer(default=10)
    token = fields.Char(
        string='Auth Token', readonly=True, copy=False, required=True,
        default=lambda self: uuid.uuid4().hex,
        help='UUID4 hex sent by the agent in the X-Agent-Token header.',
    )
    location_hint = fields.Char(
        string='Location / Branch',
        help='Operator-supplied free text — what office or branch this agent serves.',
    )
    version = fields.Char(string='Agent Version', readonly=True)
    agent_local_ip = fields.Char(string='Agent LAN IP', readonly=True)
    agent_subnet = fields.Char(
        string='LAN Subnet', readonly=True,
        help="Detected /24 the agent lives on, e.g. '192.168.8'. The scanner "
             "pre-fills this on subnet entry.",
    )
    last_seen = fields.Datetime(string='Last Seen', readonly=True)
    online = fields.Boolean(
        string='Online', compute='_compute_online', search='_search_online',
        help=f'True when the agent reported within the last {AGENT_ONLINE_GRACE_S}s.',
    )
    note = fields.Text(string='Notes')

    printer_count = fields.Integer(
        string='Printers', compute='_compute_printer_count',
    )

    _sql_constraints = [
        ('token_unique', 'unique(token)', 'Agent token must be unique.'),
    ]

    @api.depends('last_seen')
    def _compute_online(self):
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(seconds=AGENT_ONLINE_GRACE_S)
        for rec in self:
            rec.online = bool(rec.last_seen) and rec.last_seen >= cutoff

    def _search_online(self, op, val):
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(seconds=AGENT_ONLINE_GRACE_S)
        want_online = (op == '=' and val) or (op == '!=' and not val)
        return [('last_seen', '>=' if want_online else '<', cutoff)]

    def _compute_printer_count(self):
        Cfg = self.env['ab.printer.config']
        for rec in self:
            rec.printer_count = Cfg.search_count([('agent_id', '=', rec.id)])

    def action_view_printers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Printers — {self.name}',
            'res_model': 'ab.printer.config',
            'view_mode': 'list,form',
            'domain': [('agent_id', '=', self.id)],
            'context': {'default_agent_id': self.id},
        }

    def action_rotate_token(self):
        self.ensure_one()
        self.token = uuid.uuid4().hex
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'warning', 'sticky': True,
                'title': 'Token rotated',
                'message': 'The running agent on the LAN will lose its session and '
                           'must be reconfigured with the new token.',
            },
        }

    @api.model
    def _resolve_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([('token', '=', token)], limit=1)

    @api.model
    def _online_default_for_subnet(self, subnet):
        """Best agent for a given subnet: same /24 if available, else any online."""
        domain = [('online', '=', True)]
        if subnet:
            sub24 = '.'.join(subnet.split('.')[:3]).rstrip('.')
            same = self.sudo().search(
                domain + [('agent_subnet', '=', sub24)], limit=1,
            )
            if same:
                return same
        return self.sudo().search(domain, limit=1)


class PrinterScanRequest(models.Model):
    """One row per pending scan request awaiting an agent reply.

    The scanner controller creates a row in state=pending with the scan
    parameters, polls until state=done|failed, and returns the result.
    The agent's /poll endpoint hands these out alongside print jobs.
    """
    _name = 'ab.printer.scan.request'
    _description = 'Pending Printer Scan Request (agent-mediated)'
    _order = 'create_date desc'

    agent_id = fields.Many2one('ab.printer.agent', required=True, ondelete='cascade')
    params_json = fields.Text(string='Scan Params (JSON)', required=True)
    state = fields.Selection(
        [('pending', 'Pending'), ('claimed', 'Claimed by Agent'),
         ('done', 'Done'), ('failed', 'Failed'), ('expired', 'Expired')],
        default='pending', index=True,
    )
    result_json = fields.Text(string='Result (JSON)')
    error = fields.Char()
    claimed_at = fields.Datetime()
    done_at = fields.Datetime()

    @api.model
    def _cron_gc(self):
        """Expire requests older than 5 minutes still not done."""
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        stale = self.search([('state', 'in', ('pending', 'claimed')),
                             ('create_date', '<', cutoff)])
        stale.write({'state': 'expired'})
