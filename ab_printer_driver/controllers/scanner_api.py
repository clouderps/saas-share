# -*- coding: utf-8 -*-
"""HTTP JSON API for the OWL printer-scanner app.

Endpoints:
  POST /ab_printer/scan/run     → sweep a /24 + N ports, return hits
  POST /ab_printer/scan/probe   → single-IP verification
  POST /ab_printer/scan/test    → send a test slip
  POST /ab_printer/scan/add     → register selected hits as drivers
"""
import json
import logging
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from odoo import http, fields
from odoo.http import request

from ..lib import scan, tcp, verify, escpos as escpos_lib

_logger = logging.getLogger(__name__)

# RFC1918 ranges — used to decide when an agent is required.
_RFC1918_RE = re.compile(
    r'^(?:10\.\d{1,3}\.\d{1,3}'                         # 10.0.0.0/8
    r'|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}'              # 172.16.0.0/12
    r'|192\.168\.\d{1,3})$'                             # 192.168.0.0/16
)

# Polling cadence for the agent-mediated scan path.
SCAN_AGENT_TIMEOUT_S = 20
SCAN_POLL_TICK_S = 0.4


def _resolve_ports(port_mode):
    if port_mode == 'raw':
        return [9100]
    if port_mode == 'all':
        return scan.SCAN_PORTS
    return [9100, 631, 515]


def _is_private_subnet(subnet):
    """True when the /24 prefix is in an RFC1918 range."""
    return bool(_RFC1918_RE.match(subnet or ''))


def _scan_via_agent(agent, params):
    """Enqueue a scan request, wait for the agent's reply, return its JSON."""
    ScanReq = request.env['ab.printer.scan.request'].sudo()
    sr = ScanReq.create({
        'agent_id': agent.id,
        'params_json': json.dumps(params),
    })
    request.env.cr.commit()  # let the agent see this row immediately
    deadline = time.time() + SCAN_AGENT_TIMEOUT_S
    last_state = 'pending'
    while time.time() < deadline:
        request.env.cr.commit()  # see writes from the agent's /report
        sr.invalidate_recordset(['state', 'result_json', 'error'])
        last_state = sr.state
        if last_state == 'done':
            try:
                return json.loads(sr.result_json or '{}')
            except Exception:
                return {'success': False,
                        'error': 'agent returned non-JSON result'}
        if last_state in ('failed', 'expired'):
            return {'success': False,
                    'error': sr.error or 'agent reported failure'}
        time.sleep(SCAN_POLL_TICK_S)
    # Timed out — let the GC cron clean up.
    return {'success': False,
            'error': f'Agent "{agent.name}" did not respond within '
                     f'{SCAN_AGENT_TIMEOUT_S}s. Is it running?',
            'agent_timeout': True}


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
        """Run a synchronous /24 sweep.

        Routing (in priority order):
          1. kw['via_agent_id'] explicit → forward to that agent
          2. kw['via'] == 'agent' and an online agent matching the subnet
             exists → forward
          3. RFC1918 subnet + any online agent → forward to the best match
             (same /24 wins over any-other-online)
          4. Otherwise → direct sweep from this Odoo process

        The agent path enqueues an ab.printer.scan.request row, polls
        until the agent reports back, and returns the agent's result
        verbatim. Direct path is unchanged (works on-prem).

        For the direct path on an RFC1918 subnet when no agent is
        registered: returns a friendly error pointing the operator to
        the agent installer instead of silently returning 0 hits.
        """
        subnet = (kw.get('subnet') or '').strip().rstrip('.')
        if not subnet:
            return {'success': False, 'error': 'subnet required'}
        # Accept full IP / CIDR / trailing 0 in the subnet field.
        forced_host = None
        m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})$', subnet)
        if m:
            subnet = m.group(1)
            forced_host = int(m.group(2))
        else:
            subnet = re.sub(r'/\d+$', '', subnet)
            subnet = re.sub(r'\.0$', '', subnet).rstrip('.')
        ports = _resolve_ports(kw.get('port_mode') or 'common')
        start_ip = max(1, int(kw.get('range_start') or 1))
        end_ip = min(254, int(kw.get('range_end') or 254))
        if forced_host is not None:
            start_ip = end_ip = max(1, min(254, forced_host))
        timeout_s = max(0.05, (int(kw.get('timeout_ms') or 250)) / 1000.0)
        do_banner = bool(kw.get('do_banner_grab', True))
        do_rdns = bool(kw.get('do_reverse_dns', True))
        do_verify = bool(kw.get('do_verify', True))

        # ── Agent routing ─────────────────────────────────────────
        Agent = request.env['ab.printer.agent'].sudo()
        via_agent_id = kw.get('via_agent_id')
        agent = (Agent.browse(int(via_agent_id))
                 if via_agent_id else Agent.browse())
        if not agent and kw.get('via') == 'agent':
            agent = Agent._online_default_for_subnet(subnet)
        if not agent and _is_private_subnet(subnet) and kw.get('via') != 'direct':
            agent = Agent._online_default_for_subnet(subnet)

        if agent and agent.online:
            return _scan_via_agent(agent, {
                'subnet': subnet, 'ports': ports,
                'range_start': start_ip, 'range_end': end_ip,
                'timeout_s': timeout_s,
                'do_banner_grab': do_banner,
                'do_reverse_dns': do_rdns,
                'do_verify': do_verify,
            })
        if agent and not agent.online:
            return {
                'success': False,
                'error': f'Agent "{agent.name}" is offline. '
                         'Start the bridge agent on the LAN PC, '
                         'then retry the scan.',
                'agent_offline': True, 'agent_id': agent.id,
            }
        if _is_private_subnet(subnet) and not Agent.search_count([]):
            return {
                'success': False, 'needs_agent': True,
                'subnet': subnet,
                'error': (
                    f'{subnet}.0/24 is a private LAN range. This Ghaima server '
                    'cannot reach it directly. Register a Printer Bridge '
                    'Agent (Printers → Agents → New) and install it on a '
                    'PC inside that network. Once the agent is online, '
                    'rerun the scan.'
                ),
            }

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
                # ePOS-Print probe — if the printer's web server answers
                # on 443 / 8043, the browser can drive it directly. Save
                # the port we got a hit on so the caller can pre-fill
                # epos_port on the registered row.
                b['epos_https_port'] = 0
                for ep in (443, 8043):
                    ok, _ms = tcp.probe(ip, ep, timeout_s * 1.5)
                    if ok:
                        b['epos_https_port'] = ep
                        break
                if not b['epos_https_port']:
                    # Last-chance HTTP variant on common alt ports.
                    for ep in (80, 8008):
                        if ep in b['ports']:
                            b['epos_http_port'] = ep
                            break
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
            label, _legacy_mode = scan.PORT_META.get(primary, ('Unknown', 'network'))
            ms = round(b['elapsed_ms'], 1)
            # Mode recommendation: prefer ePOS when the printer's web
            # server is up on 443 / 8043 — browser can drive it directly.
            # Fall back to 'network' (server-side TCP) only if no HTTPS
            # endpoint is reachable.
            if b.get('epos_https_port'):
                mode_hint = 'epos'
            else:
                mode_hint = 'network'
            results.append({
                'ip': ip, 'port': primary, 'port_label': label,
                'open_ports': sorted_ports,
                'mode_hint': mode_hint,
                'epos_port': b.get('epos_https_port') or 0,
                'epos_use_https': bool(b.get('epos_https_port')),
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

    @http.route('/ab_printer/scan/agents', type='json',
                auth='user', methods=['POST'])
    def scan_agents(self, **_kw):
        """List bridge agents available on this DB — for the scan picker."""
        Agent = request.env['ab.printer.agent'].sudo()
        rows = []
        for a in Agent.search([], order='sequence, id'):
            rows.append({
                'id': a.id, 'name': a.name,
                'online': bool(a.online),
                'agent_subnet': a.agent_subnet or '',
                'agent_local_ip': a.agent_local_ip or '',
                'last_seen': a.last_seen and a.last_seen.isoformat() or '',
                'version': a.version or '',
                'location_hint': a.location_hint or '',
            })
        return {'success': True, 'agents': rows, 'count': len(rows)}

    @http.route('/ab_printer/scan/registered', type='json',
                auth='user', methods=['POST'])
    def scan_registered(self, **kw):
        """Return currently-registered ab.printer.config rows so the
        scanner UI can show 'what's already connected' on first open —
        operators no longer have to re-scan to see what's there."""
        Driver = request.env['ab.printer.config'].sudo()
        rows = []
        for d in Driver.search([], order='sequence, id'):
            rows.append({
                'id': d.id, 'name': d.name,
                'ip': d.printer_ip or '', 'port': d.printer_port or 9100,
                'vendor': d.vendor or '', 'mac': d.mac or '',
                'state': d.state, 'verified': bool(d.verified),
                'use': d.printer_use or '',
                'last_seen': d.last_seen and d.last_seen.isoformat() or '',
            })
        return {'success': True, 'registered': rows, 'count': len(rows)}

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
            mode = p.get('mode_hint') or 'epos'
            vals = {
                'name': p.get('name') or f'Printer @ {ip}',
                'printer_mode': mode,
                'printer_use': p.get('printer_use') or 'receipt',
                'printer_ip': ip,
                'printer_port': int(p.get('port') or 9100),
                'vendor': p.get('vendor', ''),
                'mac': p.get('mac', ''),
                'verified': bool(p.get('verified')),
                'state': 'connected' if p.get('verified') else 'disconnected',
            }
            if mode == 'epos':
                vals['epos_use_https'] = bool(p.get('epos_use_https', True))
                vals['epos_port'] = int(p.get('epos_port') or 0)
            rec = Driver.create(vals)
            ids.append(rec.id)
        return {'success': True, 'printer_ids': ids, 'count': len(ids)}
