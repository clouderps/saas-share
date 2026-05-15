"""ePOS-Print end-to-end smoke.

Run inside any tenant container via `odoo-bin shell --no-http`:

    docker exec <container> /venv/bin/python3 /opt/.../odoo-bin shell \\
        -c /opt/.../odoo.conf -d <database> --no-http < epos_smoke.py

Prereq: mock_epos_server.py is running on 127.0.0.1:18043 inside the
same container (start with run_epos_smoke.sh, or in another shell).

Exercises every boundary of the ePOS path that is testable without a
real browser:

  1. Create an ab.printer.config row with mode='epos' pointed at the
     mock printer (127.0.0.1:18043, HTTP).
  2. action_test_connection — verify it returns the
     `ab_printer.test_epos` client action with the expected params
     (config / escpos_b64 / driver_id).
  3. Simulate the browser leg: build the SOAP envelope from the
     base64 ESC/POS payload, POST it to the printer URL, confirm
     `<response success="true"/>`.
  4. driver.print_image(...) — confirm the POS receipt path returns
     {browser_dispatch:True, mode:'epos', epos_config:{...}}.
  5. Clean up the driver row.

Cannot test the OWL retry/backoff, PNA preflight diagnostics or self-
signed cert acceptance — those fire only inside a real browser. The
contracts at every boundary are still verified here.
"""
import base64
import binascii

import requests

print('=== ePOS smoke ===')

Driver = env['ab.printer.config'].sudo()
existing = Driver.search([('name', '=', 'SMOKE - ePOS Mock')])
if existing:
    existing.unlink()
drv = Driver.create({
    'name': 'SMOKE - ePOS Mock',
    'printer_mode': 'epos',
    'printer_use': 'receipt',
    'printer_ip': '127.0.0.1',
    'epos_port': 18043,
    'epos_use_https': False,
    'epos_dev_id': 'local_printer',
    'paper_width_mm': '80',
})
env.cr.commit()
print(f'driver: id={drv.id}  mode={drv.printer_mode}  '
      f'ip={drv.printer_ip}:{drv.epos_port}  https={drv.epos_use_https}')

# Step 2 — backend "Test Print" returns the OWL client action.
action = drv.action_test_connection()
assert action.get('tag') == 'ab_printer.test_epos', \
    f'expected ab_printer.test_epos client action, got {action}'
params = action.get('params') or {}
assert {'config', 'driver_id', 'escpos_b64'} <= set(params), \
    f'missing required params: {sorted(params)}'
cfg = params['config']
escpos_b64 = params['escpos_b64']
print('action tag:', action['tag'])
print('action params keys:', sorted(params))
print('dispatch URL ->',
      ('https' if cfg['use_https'] else 'http') +
      f"://{cfg['ip']}:{cfg['port']}/cgi-bin/epos/service.cgi?devid={cfg['dev_id']}")

# Step 3 — simulate the browser POST.
raw = base64.b64decode(escpos_b64)
hex_bytes = binascii.hexlify(raw).decode('ascii').upper()
soap = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
    '<s:Body>'
    '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'
    f'<command>{hex_bytes}</command>'
    '</epos-print></s:Body></s:Envelope>'
)
url = ('https' if cfg['use_https'] else 'http') + \
      f"://{cfg['ip']}:{cfg['port']}/cgi-bin/epos/service.cgi" \
      f"?devid={cfg['dev_id']}&timeout=10000"
r = requests.post(url, data=soap,
                  headers={'Content-Type': 'text/xml'},
                  timeout=5)
print('POST -> HTTP', r.status_code)
print('  body:', r.text)
assert r.status_code == 200 and 'success="true"' in r.text, \
    f'mock printer rejected the print: {r.text}'

# Step 4 — POS dispatch path (image kind) returns the browser_dispatch dict.
from PIL import Image
from io import BytesIO
img = Image.new('RGB', (80, 40), (255, 255, 255))
buf = BytesIO()
img.save(buf, format='PNG')

res = drv.print_image(buf.getvalue(), source='smoke')
print()
print('--- POS dispatch path ---')
print('print_image keys:', sorted(res))
assert res.get('browser_dispatch') is True
assert res.get('mode') == 'epos'
assert (res.get('epos_config') or {}).get('ip') == '127.0.0.1'
print('  browser_dispatch:', res['browser_dispatch'])
print('  mode:', res['mode'])
print('  epos_config.ip:', res['epos_config']['ip'])

# Cleanup
drv.unlink()
env.cr.commit()
print()
print('=== smoke OK ===')
