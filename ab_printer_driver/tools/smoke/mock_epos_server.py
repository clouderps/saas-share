"""Minimal ePOS-Print server for end-to-end smoke testing.

Listens for SOAP envelopes POSTed to /cgi-bin/epos/service.cgi, extracts
the <command>HEX</command> payload, decodes the ESC/POS bytes, and
returns the standard Epson `<response success="true"/>` shape.

Captured prints are appended to /tmp/mock_epos.log:
    --- print #N (devid=...) ---
    <hex of escpos bytes>
    <ascii rendering of printable bytes>

Designed to be docker-cp'd into a tenant container and run on
127.0.0.1:18043 so the test can be driven via 'requests' from the same
container without any cross-network plumbing.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import binascii
import re
import sys
import time
import threading
import urllib.parse

LOG_PATH = '/tmp/mock_epos.log'
PORT = 18043
COUNTER = {'n': 0}


def log(msg):
    line = f'[{time.strftime("%H:%M:%S")}] {msg}\n'
    sys.stderr.write(line)
    sys.stderr.flush()
    with open(LOG_PATH, 'a') as fh:
        fh.write(line)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # quiet

    def do_GET(self):
        # Health probe-style.
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'mock epos OK\n')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        devid = (qs.get('devid') or ['?'])[0]
        length = int(self.headers.get('Content-Length') or '0')
        body = self.rfile.read(length) if length else b''
        body_text = body.decode('utf-8', errors='replace')

        m = re.search(r'<command>([0-9A-Fa-f]*)</command>', body_text)
        hex_payload = m.group(1) if m else ''
        try:
            raw = binascii.unhexlify(hex_payload) if hex_payload else b''
        except binascii.Error:
            raw = b''

        ascii_view = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw)

        COUNTER['n'] += 1
        with open(LOG_PATH, 'a') as fh:
            fh.write(
                f'\n--- print #{COUNTER["n"]} '
                f'(devid={devid}, body_len={len(body)}, '
                f'escpos_bytes={len(raw)}) ---\n'
                f'HEX:   {hex_payload[:200]}\n'
                f'ASCII: {ascii_view[:200]}\n'
            )
        log(f'print #{COUNTER["n"]} devid={devid} bytes={len(raw)}')

        resp = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<response success="true" code="" status="00000000"/>'
        )
        self.send_response(200)
        self.send_header('Content-Type', 'application/xml')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def main():
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    open(LOG_PATH, 'w').close()
    log(f'mock_epos listening on 127.0.0.1:{PORT}')
    server.serve_forever()


if __name__ == '__main__':
    main()
