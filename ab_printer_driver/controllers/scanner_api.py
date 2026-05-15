# -*- coding: utf-8 -*-
"""HTTP JSON API for the OWL printer-scanner app.

Endpoints:
  POST /ab_printer/scan/run     → sweep a /24 + N ports, return hits
  POST /ab_printer/scan/probe   → single-IP verification
  POST /ab_printer/scan/test    → send a test slip
  POST /ab_printer/scan/add     → register selected hits as drivers
"""
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo import http
from odoo.http import request

from ..lib import scan, tcp, verify, escpos as escpos_lib

_logger = logging.getLogger(__name__)


def _resolve_ports(port_mode):
    if port_mode == 'raw':
        return [9100]
    if port_mode == 'all':
        return scan.SCAN_PORTS
    return [9100, 631, 515]


def _friendly_name(bucket, ip):
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


class PrinterScannerController(http.Controller):

    @http.route('/ab_printer/scan/run', type='json', auth='user', methods=['POST'])
    def scan_run(self, **kw):
        """Run a synchronous /24 sweep. Bounded ~5-7 s."""
        subnet = (kw.get('subnet') or '').strip().rstrip('.')
        if not subnet:
            return {'success': False, 'error': 'subnet required'}
        # Accept full IP / CIDR / trailing 0 in the subnet field.
        forced_host = None
        import re as _re
        m = _re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})$', subnet)
        if m:
            subnet = m.group(1)
            forced_host = int(m.group(2))
        else:
            subnet = _re.sub(r'/\d+$', '', subnet)
            subnet = _re.sub(r'\.0$', '', subnet).rstrip('.')
        ports = _resolve_ports(kw.get('port_mode') or 'common')
        start_ip = max(1, int(kw.get('range_start') or 1))
        end_ip = min(254, int(kw.get('range_end') or 254))
        if forced_host is not None:
            start_ip = end_ip = max(1, min(254, forced_host))
        timeout_s = max(0.05, (int(kw.get('timeout_ms') or 250)) / 1000.0)
        do_banner = bool(kw.get('do_banner_grab', True))
        do_rdns = bool(kw.get('do_reverse_dns', True))
        do_verify = bool(kw.get('do_verify', True))

        targets = [(f'{subnet}.{i}', p)
                   for i in range(start_ip, end_ip + 1) for p in ports]
        scan_start = time.time()

        def _probe(t):
            ip, port = t
            ok, ms = tcp.probe(ip, port, timeout_s)
            return (ip, port, ms) if ok else None

        hits = {}
        with ThreadPoolExecutor(max_workers=40) as pool:
            for fut in as_completed({pool.submit(_probe, t): t for t in targets}):
                hit = fut.result()
                if not hit:
                    continue
                ip, port, ms = hit
                b = hits.setdefault(ip, {'ports': [], 'elapsed_ms': ms})
                b['ports'].append(port)
                b['elapsed_ms'] = min(b['elapsed_ms'], ms)

        if do_banner or do_rdns or do_verify:
            def _enrich(item):
                ip, b = item
                if do_banner:
                    for p in b['ports']:
                        banner = scan.banner_grab(ip, p, timeout_s * 2)
                        if banner:
                            v = scan.vendor_from_banner(banner)
                            if v:
                                b['vendor'] = v
                                b['banner'] = banner[:120]
                                break
                if do_rdns:
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
                if do_verify and 9100 in b['ports']:
                    vr = verify.verify_printer(ip, 9100, timeout_s=timeout_s * 4)
                    b['verified'] = vr['verified']
                else:
                    b['verified'] = False
                return ip, b
            with ThreadPoolExecutor(max_workers=12) as pool:
                hits = dict(pool.map(_enrich, hits.items()))

        results = []
        for ip in sorted(hits, key=lambda s: int(s.split('.')[-1])):
            b = hits[ip]
            sorted_ports = sorted(b['ports'])
            primary = sorted_ports[0]
            label, mode = scan.PORT_META.get(primary, ('Unknown', 'network'))
            ms = round(b['elapsed_ms'], 1)
            results.append({
                'ip': ip, 'port': primary, 'port_label': label,
                'open_ports': sorted_ports, 'mode_hint': mode,
                'vendor': b.get('vendor', ''), 'mac': b.get('mac', ''),
                'hostname': b.get('hostname', ''), 'banner': b.get('banner', ''),
                'verified': bool(b.get('verified')),
                'response_ms': ms,
                'speed': 'fast' if ms < 50 else 'ok' if ms < 200 else 'slow',
                'name': _friendly_name(b, ip),
            })

        return {
            'success': True, 'subnet': subnet, 'ports': ports,
            'scanned_count': len(targets), 'found_count': len(results),
            'duration_s': round(time.time() - scan_start, 2),
            'results': results,
        }

    @http.route('/ab_printer/scan/probe', type='json', auth='user', methods=['POST'])
    def scan_probe(self, ip=None, port=9100, **kw):
        if not ip:
            return {'success': False, 'error': 'ip required'}
        result = verify.verify_printer(ip, int(port), timeout_s=1.5)
        if not result['reachable']:
            return {'success': True, 'reachable': False,
                    'response_ms': result['response_ms'],
                    'error': result.get('error')}
        banner = scan.banner_grab(ip, int(port), 1.0)
        vendor = scan.vendor_from_banner(banner)
        mac, mac_vendor = scan.vendor_from_ip_arp(ip)
        return {
            'success': True, 'reachable': True,
            'verified': result['verified'],
            'response_ms': result['response_ms'],
            'vendor': vendor or mac_vendor or '',
            'banner': banner[:120] if banner else '',
            'mac': mac,
        }

    @http.route('/ab_printer/scan/test', type='json', auth='user', methods=['POST'])
    def scan_test(self, ip=None, port=9100, **kw):
        if not ip:
            return {'success': False, 'error': 'ip required'}
        payload = escpos_lib.build_test_slip(printer_name=f'{ip}:{port}')
        ok, err, duration = tcp.send_to_printer(ip, int(port), payload, timeout=5)
        return {'success': ok, 'error': err or '', 'duration': duration}

    @http.route('/ab_printer/scan/add', type='json', auth='user', methods=['POST'])
    def scan_add(self, printers=None, **kw):
        if not printers:
            return {'success': False, 'error': 'no printers selected'}
        ids = []
        Driver = request.env['ab.printer.config'].sudo()
        for p in printers:
            ip = p.get('ip')
            if not ip:
                continue
            rec = Driver.create({
                'name': p.get('name') or f'Printer @ {ip}',
                'printer_mode': p.get('mode_hint') or 'network',
                'printer_use': p.get('printer_use') or 'receipt',
                'printer_ip': ip,
                'printer_port': int(p.get('port') or 9100),
                'vendor': p.get('vendor', ''),
                'mac': p.get('mac', ''),
                'verified': bool(p.get('verified')),
                'state': 'connected' if p.get('verified') else 'disconnected',
            })
            ids.append(rec.id)
        return {'success': True, 'printer_ids': ids, 'count': len(ids)}
