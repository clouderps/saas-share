# -*- coding: utf-8 -*-
"""ESC/POS command builders.

Reference: Epson TM-T88V command spec. The same commands work on every
mainstream ESC/POS-compatible thermal printer we've shipped to (Star,
Bixolon, Xprinter, Citizen, …).

For raster image printing see lib/image.py — this module is text +
control commands only.
"""
ESC = b'\x1b'
GS = b'\x1d'

INIT     = ESC + b'@'
ALIGN_L  = ESC + b'a\x00'
ALIGN_C  = ESC + b'a\x01'
ALIGN_R  = ESC + b'a\x02'
BOLD_ON  = ESC + b'E\x01'
BOLD_OFF = ESC + b'E\x00'
DWIDTH   = GS + b'!\x10'
DHEIGHT  = GS + b'!\x01'
DBOTH    = GS + b'!\x11'
NORMAL   = GS + b'!\x00'
FEED1    = b'\n'
FEED3    = ESC + b'd\x03'
CUT_FULL = GS + b'V\x00'
CUT_PART = GS + b'V\x01'
DRAWER_PULSE = ESC + b'p\x00\x19\xfa'      # pin 2, 25/250 ms
STATUS_QUERY = b'\x10\x04\x01'              # DLE EOT 1 — printer status


def enc(s, encoding='cp864'):
    """Encode text. cp864 is Arabic-capable + safe for Latin. Falls
    back to UTF-8 if cp864 isn't available in the runtime."""
    if not s:
        return b''
    try:
        return str(s).encode(encoding, 'replace')
    except LookupError:
        return str(s).encode('utf-8', 'replace')


def line(left, right=None, width=42):
    """Build a single ESC/POS text line. If `right` is given, pads
    the gap between left+right to `width` columns."""
    left = str(left or '')
    if right is None:
        return enc(left) + FEED1
    right = str(right)
    pad = max(1, width - len(left) - len(right))
    return enc(left + (' ' * pad) + right) + FEED1


def divider(char='-', width=42):
    return enc(char * width) + FEED1


def build_test_slip(printer_name='', extra=''):
    """Build the standard 'Ghaima POS' test slip we send from the
    scanner / config-form Test buttons."""
    import time as _t
    return (
        INIT
        + ALIGN_C + DBOTH + enc('Ghaima POS') + FEED1 + NORMAL
        + ALIGN_L
        + (enc('Printer: ' + (printer_name or '—')) + FEED1)
        + (enc(_t.strftime('%Y-%m-%d %H:%M:%S')) + FEED1)
        + (enc(extra) + FEED1 if extra else b'')
        + FEED3 + CUT_FULL
    )


def build_order_summary(payload):
    """Build a kitchen-ticket ESC/POS payload from a JSON-ish dict.
    See controllers/print_dispatch.py for the payload shape."""
    out = [INIT, ALIGN_C, DBOTH, enc(payload.get('store_name', 'Kitchen Ticket')),
           FEED1, NORMAL]
    if payload.get('table'):
        out.append(BOLD_ON + enc(f"Table {payload['table']}") + FEED1 + BOLD_OFF)
    out.append(ALIGN_L)
    out.append(divider())
    out.append(line(payload.get('order_ref', ''),
                    payload.get('printed_at', '')))
    if payload.get('served_by'):
        out.append(line('Cashier:', payload['served_by']))
    out.append(divider())
    for ln in payload.get('lines') or []:
        qty = ln.get('qty') or 1
        name = ln.get('name') or 'Item'
        out.append(BOLD_ON + enc(f'{qty}x  {name}') + FEED1 + BOLD_OFF)
        for tag in (ln.get('modifiers') or []):
            out.append(enc(f'   + {tag}') + FEED1)
        if ln.get('note'):
            out.append(enc(f'   * {ln["note"]}') + FEED1)
    if payload.get('note'):
        out.append(divider())
        out.append(enc('NOTE: ' + payload['note']) + FEED1)
    out.append(divider())
    out.append(FEED3 + CUT_FULL)
    return b''.join(out)
