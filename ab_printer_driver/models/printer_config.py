from odoo import api, fields, models

from ..lib import tcp, image, escpos, verify


class PrinterConfig(models.Model):
    """Driver registry: every physical printer the SaaS knows about.

    Domain-agnostic. Consumer modules (POS, accounting, …) layer
    references on top via _inherit + their own pos_config_id /
    invoice_use / picking_use fields.
    """
    _name = 'ab.printer.config'
    _description = 'Printer Driver Configuration'
    _order = 'sequence, name'

    name = fields.Char(string='Printer Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    category_id = fields.Many2one(
        'ab.printer.category', string='Category',
    )
    printer_mode = fields.Selection(
        [
            ('epos', 'ePOS-Print (Browser ↔ Printer, recommended)'),
            ('network', 'Network (TCP — server prints, on-prem only)'),
            ('agent', 'Bridge Agent (LAN proxy for cloud Odoo)'),
            ('iot', 'IoT Box'),
            ('usb', 'USB / WebUSB'),
            ('bluetooth', 'Bluetooth'),
            ('auto', 'Auto Detect'),
        ],
        string='Printer Mode',
        default='epos',
        required=True,
        help=(
            "ePOS-Print: the browser POSTs the print job directly to the "
            "printer's own HTTPS server. Works for any Epson/Star/Bixolon "
            "receipt printer with ePOS-Print enabled. No agent or LAN "
            "reachability needed from the cloud server.\n"
            "Network: classic raw ESC/POS over TCP 9100 from the Odoo "
            "process. Only works when Odoo is on the same LAN as the "
            "printer (on-prem deploys).\n"
            "Bridge Agent: a small daemon on a LAN PC executes the print "
            "on behalf of the cloud server."
        ),
    )

    # ── ePOS-Print fields (used when printer_mode='epos') ─────────
    epos_dev_id = fields.Char(
        string='ePOS Device ID', default='local_printer',
        help="The 'devid' query parameter sent to the printer's ePOS "
             "service. 99% of installs use 'local_printer'. Change "
             "only if the printer's web admin assigns a custom id.",
    )
    epos_use_https = fields.Boolean(
        string='ePOS over HTTPS', default=True,
        help="Highly recommended. Required when the Odoo page itself is "
             "HTTPS (mixed-content blocks HTTPS→HTTP). The browser will "
             "prompt to trust the printer's self-signed certificate on "
             "first use — accept it once per browser profile.",
    )
    epos_port = fields.Integer(
        string='ePOS Port', default=0,
        help="0 (default) = auto: 443 for HTTPS, 80 for HTTP. Some "
             "Epson firmwares use 8043 / 8008 instead — set explicitly "
             "if your printer's web admin shows a non-default port.",
    )
    printer_use = fields.Selection(
        [
            ('receipt', 'Receipt Printer'),
            ('kitchen', 'Kitchen / Order Printer'),
            ('document', 'Document Printer (A4)'),
            ('label', 'Label Printer'),
            ('both', 'Receipt & Kitchen'),
        ],
        string='Printer Use',
        default='receipt',
    )
    printer_ip = fields.Char(string='Printer IP')
    printer_port = fields.Integer(string='Printer Port', default=9100)
    paper_width_mm = fields.Selection(
        [('58', '58 mm'), ('80', '80 mm'), ('a4', 'A4')],
        string='Paper Width', default='80',
    )
    usb_vendor_id = fields.Char(string='USB Vendor ID')
    usb_product_id = fields.Char(string='USB Product ID')
    bluetooth_device_name = fields.Char(string='Bluetooth Device Name')
    enable_fallback = fields.Boolean(string='Enable Fallback', default=True)
    retry_count = fields.Integer(string='Retry Count', default=3)
    timeout = fields.Integer(string='Timeout (ms)', default=5000)
    state = fields.Selection(
        [
            ('connected', 'Connected'),
            ('disconnected', 'Disconnected'),
            ('printing', 'Printing'),
            ('error', 'Error'),
        ],
        string='Status', default='disconnected', readonly=True,
    )
    last_seen = fields.Datetime(string='Last Verified', readonly=True)
    verified = fields.Boolean(
        string='ESC/POS Verified', readonly=True,
        help='True when the printer answered our DLE EOT 1 status query — '
             'distinguishes a real ESC/POS device from a generic TCP port.',
    )
    vendor = fields.Char(string='Vendor', help='Detected by banner / MAC OUI.')
    mac = fields.Char(string='MAC Address')

    # ── Bridge agent (optional) ───────────────────────────────────
    agent_id = fields.Many2one(
        'ab.printer.agent', string='Via Agent', ondelete='set null',
        help="Set this when the printer is on a LAN unreachable from the "
             "Odoo server (typical for SaaS deployments). The bridge agent "
             "running inside the LAN will pick up jobs and execute them locally. "
             "Leave empty for on-prem deploys where Odoo can talk to the "
             "printer directly.",
    )
    agent_online = fields.Boolean(
        string='Agent Online', related='agent_id.online', readonly=True,
    )

    # ── Driver API ────────────────────────────────────────────────
    # env['ab.printer.config'].get_default(use='receipt').print_bytes(escpos)
    # env['ab.printer.config'].get_default(use='kitchen').print_report(...)

    @api.model
    def get_default(self, use='receipt', pos_config=None, partner=None):
        """Resolve the default printer for a given use.

        Resolution order:
          1. Consumer-supplied hint (pos_config / partner) — extended
             by consumer modules via _inherit + super()
          2. ab.printer.config with printer_use == use and state in
             (connected, printing), lowest sequence wins
          3. any connected printer (for emergency fallback)
        """
        rec = self.search([
            ('printer_use', 'in', (use, 'both')),
            ('state', 'in', ('connected', 'printing')),
        ], limit=1, order='sequence, id')
        if rec:
            return rec
        return self.search([('state', 'in', ('connected', 'printing'))],
                           limit=1, order='sequence, id')

    def print_bytes(self, data, *, source='backend', record_ref=None, timeout=None):
        """Send raw ESC/POS bytes — directly, via agent, or via browser.

        Routing:
          * mode='epos' (browser-side path) → the cloud server cannot
            speak to the printer (it's behind NAT and the server has no
            route). Return success=False with browser_dispatch=True so
            the caller can re-emit the job to the operator's browser.
            Only the OWL/POS frontend can drive ePOS over TLS to a
            private LAN IP.
          * mode in (network, agent) + agent_id set + agent online →
            enqueue an ab.printer.job marked for that agent, return
            {'success': True, 'queued': True, 'job_id': N} immediately.
            Agent's /poll picks it up, executes the TCP send on its
            LAN, reports back via /report. Final state via bus channel
            'ab_printer_job_<id>'.
          * mode='network' + no agent → direct TCP send (on-prem path,
            unchanged behaviour).

        Logs an ab.printer.log row on every direct attempt. Returns:
          {'success': bool, 'error': str, 'duration': float, ...}
        Never raises — callers inspect the dict.
        """
        self.ensure_one()
        if self.printer_mode == 'epos':
            return {
                'success': False, 'browser_dispatch': True,
                'mode': 'epos',
                'epos_config': self._get_browser_dispatch_config(),
                'error': (
                    "ePOS prints must be dispatched from the operator's "
                    "browser. The cloud Odoo cannot reach printers on "
                    "private LANs directly. Use the POS receipt button, "
                    "or 'Test ePOS' on the printer form."
                ),
            }
        if self.printer_mode not in ('network', 'agent'):
            return {'success': False,
                    'error': f'print_bytes does not support {self.printer_mode}; '
                             f'use epos/network/agent or the POS frontend'}
        if not self.printer_ip:
            return {'success': False, 'error': f'No printer_ip on {self.name}'}

        if isinstance(data, list):
            data = bytes(data)
        elif isinstance(data, str):
            data = data.encode('utf-8')

        # Agent path — enqueue and return; agent will execute on its LAN.
        if self.agent_id:
            import base64 as _b64
            if not self.agent_id.online:
                return {'success': False,
                        'error': f'Agent "{self.agent_id.name}" is offline. '
                                 'The print job will run when it reconnects.',
                        'agent_offline': True, 'queued': True,
                        'job_id': self.env['ab.printer.job'].sudo().create({
                            'printer_config_id': self.id,
                            'agent_id': self.agent_id.id,
                            'op_type': 'print',
                            'payload_kind': 'escpos',
                            'payload_b64': _b64.b64encode(data).decode('ascii'),
                            'source': source,
                            'state': 'queued',
                        }).id}
            job = self.env['ab.printer.job'].sudo().create({
                'printer_config_id': self.id,
                'agent_id': self.agent_id.id,
                'op_type': 'print',
                'payload_kind': 'escpos',
                'payload_b64': _b64.b64encode(data).decode('ascii'),
                'source': source,
                'state': 'queued',
            })
            return {'success': True, 'queued': True, 'job_id': job.id,
                    'error': '', 'duration': 0,
                    'agent_id': self.agent_id.id,
                    'agent_name': self.agent_id.name}

        # Direct path — server has reach to the printer.
        self.sudo().state = 'printing'
        ok, err, duration = tcp.send_to_printer(
            self.printer_ip, int(self.printer_port or 9100),
            data, timeout=(timeout or (self.timeout or 5000) / 1000.0),
        )
        self.sudo().state = 'connected' if ok else 'error'

        try:
            self.env['ab.printer.log'].sudo().create({
                'printer_config_id': self.id,
                'printer_type': self.printer_mode,
                'job_status': 'done' if ok else 'failed',
                'error_message': err or '',
                'duration': duration,
                'source': source,
            })
        except Exception:
            pass
        return {'success': ok, 'error': err or '', 'duration': duration}

    def print_image(self, image_bytes, *, source='backend'):
        """JPEG/PNG bytes → ESC/POS raster → dispatch."""
        self.ensure_one()
        max_w = image.THERMAL_58MM_MAX_WIDTH if self.paper_width_mm == '58' \
            else image.THERMAL_80MM_MAX_WIDTH
        try:
            escpos_bytes = image.image_to_escpos_raster(image_bytes, max_width=max_w)
        except Exception as e:
            return {'success': False, 'error': f'rasterise failed: {e}'}
        return self.print_bytes(escpos_bytes, source=source)

    def print_report(self, report_ref, records, *, render_kind='raster'):
        """Render an ir.actions.report (qweb-pdf) and dispatch to the
        printer. render_kind='raster' goes thermal; 'pdf' spools."""
        self.ensure_one()
        Report = self.env['ir.actions.report']
        if isinstance(report_ref, str):
            report = self.env.ref(report_ref, raise_if_not_found=False)
            if not report:
                return {'success': False, 'error': f'Report {report_ref} not found'}
        else:
            report = report_ref

        try:
            pdf_bytes, _ct = Report._render_qweb_pdf(report.report_name, records.ids)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        if render_kind == 'pdf':
            import os, tempfile, time as _t
            spool = '/var/spool/ghaima-printers'
            try:
                os.makedirs(spool, exist_ok=True)
                path = os.path.join(spool, f'{int(_t.time()*1000)}-{self.id}.pdf')
                with open(path, 'wb') as fh:
                    fh.write(pdf_bytes)
                return {'success': True, 'spool_path': path}
            except (PermissionError, OSError) as e:
                return {'success': False, 'error': f'Cannot write spool: {e}'}

        # Raster: render page 1 to PNG, rasterise, send.
        try:
            from pdf2image import convert_from_bytes
            from io import BytesIO
            images = convert_from_bytes(pdf_bytes, dpi=203, first_page=1, last_page=1)
            if not images:
                return {'success': False, 'error': 'PDF rendering produced no page'}
            buf = BytesIO()
            images[0].save(buf, format='PNG')
            return self.print_image(buf.getvalue(), source='report')
        except ImportError:
            return {'success': False,
                    'error': 'pdf2image / poppler not available — install for raster reports'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── Health / verification ─────────────────────────────────────

    def action_verify_connection(self):
        """Form button: probe + ESC @ + DLE EOT 1 status read. Updates
        state, verified, last_seen fields."""
        self.ensure_one()
        result = verify.verify_printer(self.printer_ip,
                                       int(self.printer_port or 9100))
        self.sudo().write({
            'state': 'connected' if result['reachable'] else 'disconnected',
            'verified': result['verified'],
            'last_seen': fields.Datetime.now() if result['reachable'] else self.last_seen,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if result['verified']
                       else 'warning' if result['reachable']
                       else 'danger',
                'title': ('Verified ESC/POS' if result['verified']
                          else 'Port open (no ESC/POS response)' if result['reachable']
                          else 'Unreachable'),
                'message': (result.get('error') or
                            f"Response: {result['response_ms']} ms"),
                'sticky': False,
            },
        }

    def action_test_connection(self):
        """Form button: send the canonical 'Ghaima POS' test slip."""
        self.ensure_one()
        # ePOS mode: hand the test slip off to the browser. The
        # 'ab_printer.test_epos' OWL service picks up the action and
        # POSTs to the printer directly from the operator's browser
        # (only place that can — the cloud has no route to the LAN).
        if self.printer_mode == 'epos':
            import base64
            payload = escpos.build_test_slip(printer_name=self.name)
            return {
                'type': 'ir.actions.client',
                'tag': 'ab_printer.test_epos',
                'params': {
                    'driver_id': self.id,
                    'driver_name': self.name,
                    'config': self._get_browser_dispatch_config(),
                    'escpos_b64': base64.b64encode(payload).decode('ascii'),
                },
            }
        payload = escpos.build_test_slip(printer_name=self.name)
        res = self.print_bytes(payload, source='test')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if res['success'] else 'danger',
                'title': 'Test print sent' if res['success'] else 'Test failed',
                'message': res.get('error') or f'Sent to {self.printer_ip}.',
                'sticky': False,
            },
        }

    def _get_browser_dispatch_config(self):
        """Bundle every field the OWL ePOS client needs for one print.

        Returned dict is JSON-safe and posted to the OWL frontend as
        part of the test action's params, or written into the POS pre-
        load so the cashier UI can dispatch without a round-trip back
        to the server.
        """
        self.ensure_one()
        port = self.epos_port or (443 if self.epos_use_https else 80)
        return {
            'id': self.id,
            'name': self.name,
            'mode': self.printer_mode,
            'ip': self.printer_ip or '',
            'port': port,
            'use_https': bool(self.epos_use_https),
            'dev_id': self.epos_dev_id or 'local_printer',
            'paper_width_mm': self.paper_width_mm,
            'timeout_ms': self.timeout or 5000,
            'retry_count': self.retry_count or 3,
        }

    @api.model
    def _cron_health_check(self):
        """Cron: every 5 min, re-verify every connected printer.
        Updates state + last_seen + fans out bus.bus 'printer_state_change'.

        Skips printers bound to a bridge agent — the server has no route
        to those LAN IPs, and the agent's own /poll heartbeat is the
        authoritative liveness signal for them.
        """
        for rec in self.search([('printer_mode', '=', 'network'),
                                ('printer_ip', '!=', False),
                                ('agent_id', '=', False)]):
            before = (rec.state, rec.verified)
            result = verify.verify_printer(
                rec.printer_ip, int(rec.printer_port or 9100), timeout_s=1.0,
            )
            after_state = 'connected' if result['reachable'] else 'disconnected'
            rec.sudo().write({
                'state': after_state,
                'verified': result['verified'],
                'last_seen': fields.Datetime.now() if result['reachable']
                             else rec.last_seen,
            })
            if (after_state, result['verified']) != before:
                try:
                    self.env['bus.bus']._sendone(
                        'printer_health',
                        'state_change',
                        {'printer_id': rec.id, 'state': after_state,
                         'verified': result['verified']},
                    )
                except Exception:
                    pass
