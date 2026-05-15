# -*- coding: utf-8 -*-
"""Legacy form-view wizard for printer detection. Kept for compatibility
with bookmarks / agents that expect a form-based flow. The primary
discovery UX is now the OWL <PrinterScannerApp/> client action — both
share the same lib helpers."""
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo import api, fields, models

from ..lib import scan, tcp, verify, escpos as escpos_lib

_logger = logging.getLogger(__name__)


class PrinterDetectWizard(models.TransientModel):
    _name = 'ab.printer.detect.wizard'
    _description = 'Printer Auto-Detection Wizard'

    subnet = fields.Char(
        string='Subnet',
        default=lambda self: self._default_subnet(),
        help='First three octets of the network to scan, e.g. 192.168.1',
    )
    port_mode = fields.Selection([
        ('common', 'Common (9100 + 631 + 515)'),
        ('all',    'Full sweep (incl. 80 web UI)'),
        ('raw',    'RAW / ESC-POS only (9100)'),
    ], default='common', required=True)
    scan_range_start = fields.Integer(string='Range Start', default=1)
    scan_range_end = fields.Integer(string='Range End', default=254)
    timeout_ms = fields.Integer(string='Timeout (ms)', default=250)
    do_banner_grab = fields.Boolean(string='Identify vendor', default=True)
    do_reverse_dns = fields.Boolean(string='Resolve hostnames', default=True)
    detected_printer_ids = fields.One2many(
        'ab.printer.detect.line', 'wizard_id', string='Detected Printers',
    )
    state = fields.Selection([
        ('draft', 'Ready'), ('scanning', 'Scanning…'), ('done', 'Scan Complete'),
    ], default='draft', readonly=True)
    scan_duration_s = fields.Float(readonly=True)
    scanned_count = fields.Integer(readonly=True)
    found_count = fields.Integer(readonly=True)

    @api.model
    def _default_subnet(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.split('.')
            if len(parts) == 4:
                return '.'.join(parts[:3])
        except Exception:
            pass
        return '192.168.1'

    def _ports_to_scan(self):
        if self.port_mode == 'raw':
            return [9100]
        if self.port_mode == 'all':
            return scan.SCAN_PORTS
        return [9100, 631, 515]

    def action_scan(self):
        self.ensure_one()
        self.state = 'scanning'
        self.detected_printer_ids.unlink()

        subnet = (self.subnet or '').strip().rstrip('.')
        if not subnet:
            self.state = 'draft'
            return False

        ports = self._ports_to_scan()
        timeout_sec = max(0.05, (self.timeout_ms or 250) / 1000.0)
        start_ip = max(1, self.scan_range_start)
        end_ip = min(254, self.scan_range_end)

        targets = [(f'{subnet}.{i}', p)
                   for i in range(start_ip, end_ip + 1) for p in ports]
        scan_started = time.time()

        def _probe(t):
            ip, port = t
            ok, ms = tcp.probe(ip, port, timeout_sec)
            return (ip, port, ms) if ok else None

        hits = {}
        with ThreadPoolExecutor(max_workers=40) as pool:
            for fut in as_completed({pool.submit(_probe, t): t for t in targets}):
                hit = fut.result()
                if not hit:
                    continue
                ip, port, elapsed = hit
                b = hits.setdefault(ip, {'ports': [], 'elapsed_ms': elapsed})
                b['ports'].append(port)
                b['elapsed_ms'] = min(b['elapsed_ms'], elapsed)

        if self.do_banner_grab or self.do_reverse_dns:
            def _enrich(item):
                ip, b = item
                if self.do_banner_grab:
                    for p in b['ports']:
                        banner = scan.banner_grab(ip, p, timeout_sec * 2)
                        if banner:
                            v = scan.vendor_from_banner(banner)
                            if v:
                                b['vendor'] = v
                                b['banner'] = banner[:120]
                                break
                if self.do_reverse_dns:
                    try:
                        b['hostname'] = socket.gethostbyaddr(ip)[0]
                    except Exception:
                        b['hostname'] = ''
                if not b.get('vendor'):
                    mac, v = scan.vendor_from_ip_arp(ip)
                    if mac:
                        b['mac'] = mac
                    if v:
                        b['vendor'] = v
                return ip, b
            with ThreadPoolExecutor(max_workers=12) as pool:
                hits = dict(pool.map(_enrich, hits.items()))

        for ip in sorted(hits, key=lambda s: int(s.split('.')[-1])):
            b = hits[ip]
            ports_list = sorted(b['ports'])
            primary_port = ports_list[0]
            label, mode_hint = scan.PORT_META.get(primary_port, ('Unknown', 'network'))
            self.env['ab.printer.detect.line'].create({
                'wizard_id': self.id,
                'ip_address': ip,
                'port': primary_port,
                'open_ports': ','.join(str(p) for p in ports_list),
                'port_label': label,
                'mode_hint': mode_hint,
                'vendor': b.get('vendor', ''),
                'mac': b.get('mac', ''),
                'hostname': b.get('hostname', ''),
                'name': self._friendly_name(b, ip),
                'banner_excerpt': b.get('banner', ''),
                'selected': True,
                'response_time_ms': round(b['elapsed_ms'], 1),
            })

        self.scan_duration_s = round(time.time() - scan_started, 2)
        self.scanned_count = len(targets)
        self.found_count = len(hits)
        self.state = 'done'

        _logger.info(
            'Printer scan: subnet=%s ports=%s scanned=%d found=%d duration=%.2fs',
            subnet, ports, len(targets), len(hits), self.scan_duration_s,
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ab.printer.detect.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _friendly_name(self, bucket, ip):
        vendor = bucket.get('vendor') or ''
        hostname = bucket.get('hostname') or ''
        banner = bucket.get('banner', '')
        model = ''
        for tok in banner.replace('\r', ' ').replace('\n', ' ').split():
            if any(tok.upper().startswith(p) for p in
                   ('TM-', 'TSP', 'SRP-', 'QL-', 'GX', 'GK')):
                model = tok.strip(',.;')
                break
        head = ' '.join(x for x in (vendor, model) if x).strip() or hostname or 'Printer'
        return f'{head} @ {ip}'

    def action_test_print_line(self, line_id):
        line = self.env['ab.printer.detect.line'].browse(int(line_id))
        if not line or not line.ip_address:
            return False
        payload = escpos_lib.build_test_slip(printer_name=line.name or line.ip_address)
        ok, err, duration = tcp.send_to_printer(
            line.ip_address, int(line.port or 9100), payload, timeout=5,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if ok else 'danger',
                'title': 'Test print sent' if ok else 'Test failed',
                'message': err or f'Printout sent to {line.ip_address}.',
                'sticky': False,
            },
        }

    def action_register_selected(self):
        """Promote the wizard's selected detect-lines to live drivers."""
        self.ensure_one()
        Driver = self.env['ab.printer.config'].sudo()
        created = 0
        for ln in self.detected_printer_ids.filtered('selected'):
            Driver.create({
                'name': ln.name or f'Printer @ {ln.ip_address}',
                'printer_mode': ln.mode_hint or 'network',
                'printer_use': 'receipt',
                'printer_ip': ln.ip_address,
                'printer_port': int(ln.port or 9100),
                'vendor': ln.vendor or '',
                'mac': ln.mac or '',
                'state': 'connected',
            })
            created += 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ab.printer.config',
            'view_mode': 'list,form',
            'name': f'{created} new printers',
        }


class PrinterDetectLine(models.TransientModel):
    _name = 'ab.printer.detect.line'
    _description = 'Detected Printer Line'

    wizard_id = fields.Many2one('ab.printer.detect.wizard', ondelete='cascade')
    selected = fields.Boolean(default=True)
    name = fields.Char(string='Name', required=True)
    ip_address = fields.Char(string='IP Address', required=True)
    port = fields.Integer(string='Port', default=9100)
    port_label = fields.Char(string='Port Label')
    open_ports = fields.Char(string='Open Ports')
    mode_hint = fields.Char(string='Mode')
    vendor = fields.Char(string='Vendor')
    mac = fields.Char(string='MAC')
    hostname = fields.Char(string='Hostname')
    banner_excerpt = fields.Char(string='Banner')
    response_time_ms = fields.Float(string='Response (ms)')
