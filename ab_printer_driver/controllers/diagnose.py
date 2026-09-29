# -*- coding: utf-8 -*-
"""Print Diagnostics — answers the operator's question
"why didn't this print just now?" by walking the chain step by step.

The same chain a real print goes through:
  1. ab.printer.config row exists ?
  2. printer_ip set ?
  3. TCP probe succeeds ?
  4. ESC/POS DLE EOT 1 status reply ?
  5. Per-(ip,port) mutex acquired ?
  6. Test slip bytes built ?
  7. Bytes actually transmitted (test print) ?

Each step is reported with an explicit OK/WARN/FAIL label + the real
error string. The frontend renders them as a vertical traffic-light
list so the operator sees in 5 seconds where to look.
"""
import logging
import time

from odoo import http
from odoo.http import request

from ..lib import tcp, verify, escpos as escpos_lib

_logger = logging.getLogger(__name__)


def _step(name, status, detail='', duration_ms=None):
    """Status: 'ok' / 'warn' / 'fail' / 'skip'."""
    return {'name': name, 'status': status, 'detail': detail,
            'duration_ms': duration_ms or 0}


class PrintDiagnosticsController(http.Controller):

    @http.route('/ab_printer/snapshot', type='json', auth='user', methods=['POST'])
    def snapshot(self, **kw):
        """One-shot status for the Live Monitor.

        Reads from registries instead of hitting the network, so it
        comes back in < 50 ms even with 30 printers — the OWL component
        polls this every 5 s for the dashboard refresh.
        """
        env = request.env
        Driver = env['ab.printer.config'].sudo()
        Job = env['ab.printer.job'].sudo()
        Log = env['ab.printer.log'].sudo()
        labels = env['ab.printer.config']._ui_labels()

        printers = []
        for d in Driver.search([], order='sequence, id'):
            queued = Job.search_count([
                ('printer_config_id', '=', d.id),
                ('state', 'in', ('queued', 'retrying')),
            ])
            failed_24h = Job.search_count([
                ('printer_config_id', '=', d.id),
                ('state', '=', 'failed'),
                ('create_date', '>=',
                 _hours_ago_dt(24)),
            ])
            last_log = Log.search([
                ('printer_config_id', '=', d.id),
            ], order='create_date desc', limit=1)
            printers.append({
                'id': d.id,
                'name': d.name,
                'ip': d.printer_ip or '',
                'port': d.printer_port or 9100,
                'use': d.printer_use or '',
                'use_label': labels['use'].get(d.printer_use, ''),
                'vendor': d.vendor or '',
                'state': d.state or 'disconnected',
                'state_label': labels['state'].get(d.state or 'disconnected', ''),
                'verified': bool(d.verified),
                'last_seen': d.last_seen and d.last_seen.isoformat() or '',
                'queued': queued,
                'failed_24h': failed_24h,
                'last_status': last_log.job_status if last_log else '',
                'last_error': (last_log.error_message or '') if last_log else '',
                'last_at': (last_log.create_date.isoformat()
                            if last_log and last_log.create_date else ''),
            })

        recent_jobs = []
        for j in Job.search([], order='create_date desc', limit=20):
            recent_jobs.append({
                'id': j.id, 'name': j.name,
                'printer': j.printer_config_id.name,
                'kind': j.payload_kind,
                'kind_label': labels['job_kind'].get(j.payload_kind, j.payload_kind),
                'source': j.source or '',
                'source_label': labels['source'].get(j.source, j.source or ''),
                'state': j.state,
                'state_label': labels['job_state'].get(j.state, j.state),
                'attempts': j.attempts,
                'duration_ms': j.duration_ms,
                'error': j.last_error or '',
                'at': j.create_date and j.create_date.isoformat() or '',
            })

        recent_logs = []
        for lg in Log.search([], order='create_date desc', limit=30):
            recent_logs.append({
                'id': lg.id,
                'printer': lg.printer_config_id.name or '—',
                'source': lg.source or '',
                'source_label': labels['source'].get(lg.source, lg.source or ''),
                'status': lg.job_status,
                'status_label': labels['log_status'].get(lg.job_status, lg.job_status),
                'duration': lg.duration,
                'error': lg.error_message or '',
                'at': lg.create_date and lg.create_date.isoformat() or '',
            })

        return {
            'success': True,
            'printers': printers,
            'recent_jobs': recent_jobs,
            'recent_logs': recent_logs,
        }

    @http.route('/ab_printer/diagnose', type='json', auth='user', methods=['POST'])
    def diagnose(self, driver_id=None, send_test=True, **kw):
        """Walk the print chain for one printer and report what broke."""
        _ = request.env._  # step names/details are shown in the monitor UI
        if not driver_id:
            return {'success': False, 'error': _('driver_id required')}
        env = request.env
        d = env['ab.printer.config'].sudo().browse(int(driver_id))

        steps = []

        # 1. Driver exists
        if not d.exists():
            steps.append(_step(_('Driver record exists'), 'fail',
                               _('No ab.printer.config row with id %s', driver_id)))
            return {'success': False, 'steps': steps}
        steps.append(_step(_('Driver record exists'), 'ok',
                           f'{d.name} (id={d.id})'))

        # 2. IP configured
        if not d.printer_ip:
            steps.append(_step(_('Printer IP configured'), 'fail',
                               _('The printer IP is empty — set it on the driver form')))
            return {'success': False, 'steps': steps}
        steps.append(_step(_('Printer IP configured'), 'ok',
                           f'{d.printer_ip}:{d.printer_port or 9100}'))

        if d.printer_mode != 'network':
            steps.append(_step(_('Printer mode is network'), 'warn',
                               _('mode=%s — only "network" mode is dispatched '
                                 'through this stack', d.printer_mode)))
            return {'success': False, 'steps': steps}
        steps.append(_step(_('Printer mode is network'), 'ok'))

        # 3. TCP probe
        t0 = time.time()
        ok, ms = tcp.probe(d.printer_ip, int(d.printer_port or 9100), 1.5)
        steps.append(_step(_('TCP probe (port reachable)'),
                           'ok' if ok else 'fail',
                           _('%s ms', f'{ms:.1f}') if ok else
                           _('Connection refused / timeout — check the IP, the port, '
                             'and that the printer is powered on and on the same LAN'),
                           int(ms)))
        if not ok:
            return {'success': False, 'steps': steps}

        # 4. ESC/POS verify
        vr = verify.verify_printer(d.printer_ip, int(d.printer_port or 9100),
                                   timeout_s=1.5)
        if vr['verified']:
            steps.append(_step(_('ESC/POS status response'), 'ok',
                               _('status byte %s — real ESC/POS device',
                                 f'0x{vr["status_byte"]:02x}'), int(vr['response_ms'])))
        elif vr['reachable']:
            steps.append(_step(_('ESC/POS status response'), 'warn',
                               _('TCP open but no DLE EOT 1 reply — many '
                                 'compatible printers ignore the query and '
                                 'still print fine. Proceed to test print.'),
                               int(vr['response_ms'])))
        else:
            steps.append(_step(_('ESC/POS status response'), 'fail',
                               vr.get('error') or _('unreachable')))
            return {'success': False, 'steps': steps}

        # 5. Mutex
        lock = tcp.lock_for(d.printer_ip, int(d.printer_port or 9100))
        held = not lock.acquire(timeout=0.1)
        if held:
            steps.append(_step(_('Per-IP mutex available'), 'warn',
                               _('Lock currently held — another job is mid-send. '
                                 'This is expected if a print is in flight.')))
        else:
            lock.release()
            steps.append(_step(_('Per-IP mutex available'), 'ok',
                               _('free — no concurrent send')))

        # 6 + 7. Test slip (optional — skip when send_test=False so the
        # operator can diagnose without making the printer fire).
        if not send_test:
            steps.append(_step(_('Test print'), 'skip',
                               _('Skipped (send_test=false)')))
            return {'success': True, 'steps': steps}

        payload = escpos_lib.build_test_slip(
            printer_name=d.name,
            extra='Print Diagnostics',
        )
        steps.append(_step(_('Test slip bytes built'), 'ok',
                           _('%s bytes', len(payload))))

        res = d.print_bytes(payload, source='diagnose')
        steps.append(_step(_('Bytes transmitted'),
                           'ok' if res['success'] else 'fail',
                           _('sent in %s ms', int((res.get("duration") or 0) * 1000))
                           if res['success']
                           else _('send failed — %s', res.get("error")),
                           int((res.get('duration') or 0) * 1000)))
        return {'success': bool(res['success']), 'steps': steps}


def _hours_ago_dt(hours):
    from datetime import datetime, timedelta
    return datetime.utcnow() - timedelta(hours=hours)
