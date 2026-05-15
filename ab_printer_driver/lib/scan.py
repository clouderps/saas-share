# -*- coding: utf-8 -*-
"""Network scan helpers — port probe, banner grab, MAC OUI vendor lookup."""
import socket

SCAN_PORTS = [9100, 631, 515, 80]

PORT_META = {
    9100: ('RAW / ESC-POS', 'network'),
    631:  ('IPP',           'network'),
    515:  ('LPD',           'network'),
    80:   ('Web UI',        'network'),
}

# Truncated MAC-OUI registry covering ~90% of receipt-printer SKUs.
OUI_VENDORS = {
    '00:00:48': 'Epson', '00:26:AB': 'Epson', '64:EB:8C': 'Epson', 'AC:64:62': 'Epson',
    '00:11:62': 'Star Micronics', '00:01:90': 'Star Micronics',
    '00:0E:CF': 'Bixolon', '00:15:94': 'Bixolon', '00:1B:78': 'Bixolon',
    '00:80:92': 'Brother', '00:21:5C': 'Brother', '40:B8:9A': 'Brother',
    '00:1B:A9': 'Zebra', '00:07:4D': 'Zebra',
    '00:1F:62': 'TSC', '00:80:77': 'Citizen',
    '00:11:5B': 'OKI', '00:11:88': 'OKI',
    '00:09:6B': 'IBM',
}


def vendor_from_mac(mac):
    if not mac or len(mac) < 8:
        return ''
    return OUI_VENDORS.get(mac.upper().replace('-', ':')[:8], '')


def vendor_from_ip_arp(ip):
    """Read /proc/net/arp on Linux → (mac, vendor) for `ip`."""
    try:
        with open('/proc/net/arp', 'r') as f:
            next(f)
            for line in f:
                cols = line.split()
                if (len(cols) >= 4 and cols[0] == ip
                        and cols[3] != '00:00:00:00:00:00'):
                    return cols[3], vendor_from_mac(cols[3])
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return '', ''


def banner_grab(ip, port, timeout=0.5):
    """Return up to 200 bytes from a TCP port, decoded leniently."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        if port == 80:
            sock.sendall(b'GET / HTTP/1.0\r\nHost: %s\r\n\r\n' % ip.encode())
        elif port == 9100:
            sock.sendall(b'\x10\x04\x01')      # ESC/POS DLE EOT 1
        try:
            data = sock.recv(200)
        except socket.timeout:
            data = b''
        sock.close()
        return (data or b'').decode('utf-8', errors='replace')
    except Exception:
        return ''


def vendor_from_banner(banner):
    if not banner:
        return ''
    b = banner.lower()
    for vendor, keys in (
        ('Epson',          ['epson', 'tm-', 'tm-t', 'tm-m']),
        ('Star Micronics', ['star ', 'tsp', 'sp7', 'mc-']),
        ('Bixolon',        ['bixolon', 'srp-']),
        ('Brother',        ['brother', 'ql-', 'qc-']),
        ('HP',             ['hp ', 'hewlett', 'laserjet', 'officejet']),
        ('Zebra',          ['zebra', 'zpl', 'gx420', 'gk420']),
        ('Citizen',        ['citizen']),
    ):
        for k in keys:
            if k in b:
                return vendor
    return ''
