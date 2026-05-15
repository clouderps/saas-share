#!/usr/bin/env python3
"""Ghaima Printer Bridge Agent.

Runs **inside** the customer's LAN. Maintains an outbound HTTP long-poll
loop to the configured Odoo server, pulls scan + print jobs, executes
them against the local printers, reports results back.

No inbound port required. No public IP for the LAN. Auth is a per-agent
UUID hex token configured at install time.

Configuration:
    ENV var          default       purpose
    AGENT_NAME       hostname()    operator-visible label
    AGENT_URL        (required)    e.g. https://fayia.ghaima.sa
    AGENT_TOKEN      (required)    UUID hex assigned by the Odoo backend
    AGENT_SUBNET     auto          /24 prefix, e.g. 192.168.8 — used for scans

Single-file deliberately — easy to scp + systemctl-enable on a Pi or
office mini-PC. Only external dep is ``requests``; ESC/POS + scan
helpers come from the parent ab_printer_driver package on the operator
side, but the agent re-implements the minimal subset it needs so it
can ship as a single .py.

Usage (dev / debug):
    AGENT_URL=https://fayia.ghaima.sa \\
    AGENT_TOKEN=<copy-from-Odoo-agent-form> \\
    AGENT_NAME="Main Branch" \\
    python3 ab_printer_agent.py

Or via systemd: see ab_printer_agent.service in this directory.
"""
import base64
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("requests is required: pip install requests", file=sys.stderr)
    sys.exit(2)

AGENT_VERSION = '1.0.0'

logging.basicConfig(
    level=os.environ.get('AGENT_LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('ab_printer_agent')

# Per-(ip, port) lock — keeps two concurrent jobs from racing the same
# thermal printer (single-TCP-client hardware limit).
_LOCKS_GUARD = threading.Lock()
_LOCKS = {}


def lock_for(ip, port):
    key = (str(ip), int(port))
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


# ── Local network helpers ────────────────────────────────────────────

def detect_local_ip():
    """Resolve the LAN IP this host uses to reach the Internet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('1.1.1.1', 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ''


def subnet_of(ip):
    if not ip or ip.count('.') != 3:
        return ''
    return '.'.join(ip.split('.')[:3])


def tcp_probe(ip, port, timeout_s=0.5):
    """Pure TCP reachability probe."""
    t0 = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)
        rc = sock.connect_ex((ip, int(port)))
        sock.close()
        return rc == 0, (time.time() - t0) * 1000.0
    except Exception:
        return False, (time.time() - t0) * 1000.0


def banner_grab(ip, port, timeout=0.5):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        if port == 80:
            s.sendall(b'GET / HTTP/1.0\r\nHost: %s\r\n\r\n' % ip.encode())
        elif port == 9100:
            s.sendall(b'\x10\x04\x01')  # ESC/POS DLE EOT 1
        try:
            data = s.recv(200)
        except socket.timeout:
            data = b''
        s.close()
        return (data or b'').decode('utf-8', errors='replace')
    except Exception:
        return ''


_VENDOR_KEYS = (
    ('Epson',          ['epson', 'tm-', 'tm-t', 'tm-m']),
    ('Star Micronics', ['star ', 'tsp', 'sp7', 'mc-']),
    ('Bixolon',        ['bixolon', 'srp-']),
    ('Brother',        ['brother', 'ql-', 'qc-']),
    ('HP',             ['hp ', 'hewlett', 'laserjet', 'officejet']),
    ('Zebra',          ['zebra', 'zpl', 'gx420', 'gk420']),
    ('Citizen',        ['citizen']),
)


def vendor_from_banner(banner):
    if not banner:
        return ''
    b = banner.lower()
    for v, keys in _VENDOR_KEYS:
        for k in keys:
            if k in b:
                return v
    return ''


_PORT_LABELS = {
    9100: 'RAW / ESC-POS', 631: 'IPP', 515: 'LPD', 80: 'Web UI',
}


def run_scan(params):
    """Execute a scan locally using the same logic as scanner_api.scan_run."""
    subnet = params.get('subnet') or ''
    ports = params.get('ports') or [9100]
    rs = max(1, int(params.get('range_start') or 1))
    re_ = min(254, int(params.get('range_end') or 254))
    timeout_s = max(0.05, float(params.get('timeout_s') or 0.25))
    do_banner = bool(params.get('do_banner_grab', True))
    do_rdns = bool(params.get('do_reverse_dns', True))

    targets = [(f'{subnet}.{i}', p) for i in range(rs, re_ + 1) for p in ports]
    t0 = time.time()
    hits = {}

    def _probe(t):
        ip, port = t
        ok, ms = tcp_probe(ip, port, timeout_s)
        return (ip, port, ms) if ok else None

    with ThreadPoolExecutor(max_workers=40) as pool:
        for fut in as_completed({pool.submit(_probe, t): t for t in targets}):
            hit = fut.result()
            if not hit:
                continue
            ip, port, ms = hit
            b = hits.setdefault(ip, {'ports': [], 'elapsed_ms': ms})
            b['ports'].append(port)
            b['elapsed_ms'] = min(b['elapsed_ms'], ms)

    if do_banner or do_rdns:
        def _enrich(item):
            ip, b = item
            if do_banner:
                for p in b['ports']:
                    banner = banner_grab(ip, p, timeout_s * 2)
                    if banner:
                        v = vendor_from_banner(banner)
                        if v:
                            b['vendor'] = v
                            b['banner'] = banner[:120]
                            break
            if do_rdns:
                try:
                    b['hostname'] = socket.gethostbyaddr(ip)[0]
                except Exception:
                    b['hostname'] = ''
            return ip, b
        with ThreadPoolExecutor(max_workers=12) as pool:
            hits = dict(pool.map(_enrich, hits.items()))

    results = []
    for ip in sorted(hits, key=lambda s: int(s.split('.')[-1])):
        b = hits[ip]
        sp = sorted(b['ports'])
        primary = sp[0]
        ms = round(b['elapsed_ms'], 1)
        results.append({
            'ip': ip, 'port': primary,
            'port_label': _PORT_LABELS.get(primary, 'Unknown'),
            'open_ports': sp, 'mode_hint': 'network',
            'vendor': b.get('vendor', ''),
            'hostname': b.get('hostname', ''),
            'banner': b.get('banner', ''),
            'verified': bool(b.get('verified')),
            'response_ms': ms,
            'speed': 'fast' if ms < 50 else 'ok' if ms < 200 else 'slow',
            'name': ((b.get('vendor') or 'Printer') + f' @ {ip}'),
        })

    return {
        'success': True, 'subnet': subnet, 'ports': ports,
        'scanned_count': len(targets), 'found_count': len(results),
        'duration_s': round(time.time() - t0, 2),
        'results': results,
    }


def run_print(job):
    """Send the job payload to the printer over TCP, serialised per (ip,port)."""
    printer = job.get('printer') or {}
    ip = printer.get('ip')
    port = int(printer.get('port') or 9100)
    timeout = (int(printer.get('timeout_ms') or 5000)) / 1000.0
    payload = base64.b64decode(job.get('payload_b64') or '')
    t0 = time.time()

    lock = lock_for(ip, port)
    if not lock.acquire(timeout=8.0):
        return False, f'printer busy >8s ({ip}:{port})', int((time.time() - t0) * 1000)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.sendall(payload)
        try:
            s.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        s.close()
        return True, '', int((time.time() - t0) * 1000)
    except socket.timeout:
        return False, 'connection timeout', int((time.time() - t0) * 1000)
    except ConnectionRefusedError:
        return False, 'connection refused', int((time.time() - t0) * 1000)
    except OSError as e:
        return False, str(e), int((time.time() - t0) * 1000)
    finally:
        lock.release()


# ── HTTP client to the Odoo server ──────────────────────────────────

class AgentClient:
    def __init__(self, base_url, token, agent_name, subnet, local_ip):
        self.base = base_url.rstrip('/')
        self.token = token
        self.agent_name = agent_name
        self.subnet = subnet
        self.local_ip = local_ip
        self.session = requests.Session()
        self.session.headers.update({
            'X-Agent-Token': token,
            'User-Agent': f'GhaimaPrinterAgent/{AGENT_VERSION}',
            'Content-Type': 'application/json',
        })

    def _post(self, path, body=None, timeout=30):
        url = f'{self.base}{path}'
        return self.session.post(url, data=json.dumps(body or {}), timeout=timeout)

    def register(self):
        r = self._post('/ab_printer/agent/register', {
            'agent_name': self.agent_name, 'version': AGENT_VERSION,
            'agent_local_ip': self.local_ip, 'agent_subnet': self.subnet,
        }, timeout=15)
        r.raise_for_status()
        data = r.json()
        log.info("registered: id=%s name=%s server_time=%s",
                 data.get('agent_id'), data.get('agent_name'),
                 data.get('server_time'))
        return data

    def poll(self):
        r = self._post('/ab_printer/agent/poll', {}, timeout=40)
        r.raise_for_status()
        return r.json()

    def report_job(self, job_id, ok, error='', duration_ms=0):
        return self._post('/ab_printer/agent/report', {
            'job_id': job_id, 'ok': ok,
            'error': error, 'duration_ms': duration_ms,
        }, timeout=15)

    def report_scan(self, scan_request_id, ok, result=None, error=''):
        return self._post('/ab_printer/agent/report', {
            'scan_request_id': scan_request_id, 'ok': ok,
            'result': result or {}, 'error': error,
        }, timeout=20)


def main():
    base = os.environ.get('AGENT_URL')
    token = os.environ.get('AGENT_TOKEN')
    if not base or not token:
        print("AGENT_URL and AGENT_TOKEN required (see install instructions).",
              file=sys.stderr)
        sys.exit(2)
    name = os.environ.get('AGENT_NAME') or socket.gethostname() or 'agent'
    local_ip = detect_local_ip()
    subnet = os.environ.get('AGENT_SUBNET') or subnet_of(local_ip)

    log.info("starting Ghaima Printer Agent v%s  host=%s name=%s",
             AGENT_VERSION, platform.node(), name)
    log.info("server=%s  local_ip=%s  subnet=%s", base, local_ip, subnet)

    client = AgentClient(base, token, name, subnet, local_ip)
    # Register, with backoff.
    while True:
        try:
            client.register()
            break
        except requests.HTTPError as e:
            log.error("register HTTP %s: %s",
                      e.response.status_code,
                      e.response.text[:200] if e.response is not None else '')
            if e.response is not None and e.response.status_code == 401:
                log.error("token rejected — check AGENT_TOKEN. retry in 30s.")
            time.sleep(30)
        except requests.RequestException as e:
            log.warning("register failed: %s — retry in 5s", e)
            time.sleep(5)

    # Main loop.
    backoff = 1
    while True:
        try:
            msg = client.poll()
            backoff = 1
            kind = msg.get('kind')
            if not kind:
                continue  # idle tick — server timed out the long-poll
            if kind == 'print':
                jid = msg.get('job_id')
                log.info("print job %s → %s:%s", jid,
                         (msg.get('printer') or {}).get('ip'),
                         (msg.get('printer') or {}).get('port'))
                ok, err, dur = run_print(msg)
                try:
                    client.report_job(jid, ok, err, dur)
                except Exception as e:
                    log.error("report_job failed: %s", e)
                if ok:
                    log.info("print job %s OK in %d ms", jid, dur)
                else:
                    log.warning("print job %s failed: %s", jid, err)
            elif kind == 'scan':
                sid = msg.get('scan_request_id')
                log.info("scan request %s params=%s", sid, msg.get('params'))
                try:
                    result = run_scan(msg.get('params') or {})
                    client.report_scan(sid, True, result=result)
                    log.info("scan %s → %d hits in %.2fs",
                             sid, result.get('found_count'),
                             result.get('duration_s'))
                except Exception as e:
                    log.exception("scan crashed")
                    try:
                        client.report_scan(sid, False, error=str(e)[:512])
                    except Exception:
                        pass
            else:
                log.warning("unknown kind: %s", kind)
        except requests.HTTPError as e:
            sc = e.response.status_code if e.response is not None else '?'
            log.error("poll HTTP %s — sleep %ss", sc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except requests.RequestException as e:
            log.warning("poll connection issue: %s — sleep %ss", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except KeyboardInterrupt:
            log.info("shutdown requested")
            break
        except Exception:
            log.exception("loop crash — sleep 5s")
            time.sleep(5)


if __name__ == '__main__':
    main()
