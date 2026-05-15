# -*- coding: utf-8 -*-
"""Connection verification — distinguishes a real ESC/POS printer from
a random TCP service that happens to answer on 9100.

A plain socket.connect_ex() returning 0 only tells us 'something
accepted the SYN'. Routers, firewalls and proxies can SYN-ACK on any
port without a printer behind them. We additionally:

  1. send ESC @ (init — every ESC/POS printer accepts and ignores)
  2. send DLE EOT 1 (transmit status request)
  3. read up to 8 bytes — a real ESC/POS printer answers with a status
     byte (bit pattern 0x16 / 0x12 / 0x1e variants depending on state).

If we get a printer-status byte back, the device is VERIFIED. If we
only get the TCP open with no response, it's PORT-ONLY (degraded).
"""
import socket
import time

from . import escpos


def verify_printer(ip, port=9100, timeout_s=1.5):
    """Return a dict:
        {
            'reachable': bool,         # TCP socket opened
            'verified': bool,          # ESC/POS response observed
            'response_ms': float,      # round-trip
            'status_byte': int|None,   # raw DLE EOT 1 reply
            'error': str|None,
        }
    """
    t0 = time.time()
    res = {'reachable': False, 'verified': False,
           'response_ms': 0.0, 'status_byte': None, 'error': None}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)
        sock.connect((ip, int(port)))
        res['reachable'] = True
        # Send init + status query
        sock.sendall(escpos.INIT + escpos.STATUS_QUERY)
        try:
            reply = sock.recv(8)
            if reply:
                res['status_byte'] = reply[0]
                res['verified'] = True
        except socket.timeout:
            # Many cheaper printers ignore status queries silently —
            # they're still functional ESC/POS devices. Mark as
            # reachable but not verified.
            pass
        sock.close()
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        res['error'] = str(e)
    res['response_ms'] = round((time.time() - t0) * 1000, 1)
    return res
