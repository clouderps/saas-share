# ePOS-Print smoke tests

End-to-end smoke for the `mode=epos` path in `ab_printer_driver` and
`ab_pos_printer_manager`. Useful after any change to the dispatch
controllers, the OWL ePOS client, or the printer-form Test button.

## What's tested

| Boundary | Test covers |
|---|---|
| `ab.printer.config.action_test_connection` (mode=epos) | returns the `ab_printer.test_epos` client action with `config` + `escpos_b64` + `driver_id` params |
| Server-rendered ESC/POS bytes for the test slip | are valid (decode + parse on the mock printer) |
| Browser SOAP envelope construction | matches what the OWL client builds — `<command>HEX</command>` body, correct devid in the query string |
| `driver.print_image(...)` (POS receipt path, image kind) | returns `browser_dispatch:True` + `mode:'epos'` + `epos_config:{...}` |
| Mock printer round-trip | receives the print, returns `<response success="true"/>` |

## What's NOT tested (yet)

The OWL ePOS client itself (`epos_printer.js`) — retry/backoff, PNA
preflight diagnostics, the cert-trust hint, the AbortController
timeout. These fire only in a real browser. A Playwright/Cypress
test against a containerised Chrome would close that gap.

## Usage

From the central management host (where `bk.server._execute_command`
works against the tenant container's docker host):

```sh
# copy the smoke dir to the host that has docker access to the tenant
scp -r tools/smoke/ root@apps-host:/tmp/

# on apps host:
cd /tmp/smoke && bash run_epos_smoke.sh <container> <database>
```

For fayia:

```sh
bash run_epos_smoke.sh fayia_7m2mg92 fayia_74756778
```

The script:
1. `docker cp`s the mock printer + smoke into the container's `/tmp/ab_printer_smoke/`
2. Starts the mock on `127.0.0.1:18043` in the container
3. Pipes `epos_smoke.py` to `odoo-bin shell --no-http -d <database>`
4. Prints the smoke output and the mock printer's request log
5. Stops the mock

Expected last line on success: `=== smoke OK ===`.

## Layout assumptions (edit if your container differs)

| Path | Default in this script |
|---|---|
| Python interpreter | `/venv3.12/bin/python3.12` |
| `odoo-bin`         | `/opt/ghaima/odoo_source_code/odoo/odoo-bin` |
| Odoo conf          | `/opt/ghaima/odoo.conf` |
| Mock-printer port  | `18043` (HTTP, no TLS) |

The mock printer always binds `127.0.0.1` so it's reachable only from
inside the container — never exposed to the docker network.

## Why a mock printer instead of a real one

The smoke runs against any tenant in CI / dev. Real Epson hardware is
only at the customer site, far from us, behind NAT. The mock speaks
the same SOAP / `<command>HEX</command>` protocol the OWL client uses
and returns the same `<response success="..." code="..." status="..."/>`
shape, so the contracts are exercised identically.
