# Ghaima Printer — Deployment Modes

Three independent paths reach a printer from `ab.printer.config`. Pick
one per printer based on **where the operator's browser is** relative
to **where the printer is**, and what hardware the customer owns.

| | ePOS (default) | WebUSB | Network (server TCP) | Bridge Agent |
|---|:-:|:-:|:-:|:-:|
| `printer_mode` value | `epos` | `usb` | `network` | `agent` |
| Cloud Odoo needs LAN reach | ❌ | ❌ | ✅ | ❌ |
| Customer installs anything | ❌ | ❌ | n/a | ✅ (1 PC per LAN) |
| Silent / unattended printing | ⚠ session-bound | ⚠ session-bound | ✅ | ✅ |
| iPad / iOS Safari support | ✅ | ❌ | n/a | ✅ |
| Firefox / Safari desktop | ✅ | ❌ | n/a | ✅ |
| Cron / scheduled reports | ❌ | ❌ | ✅ | ✅ |
| Setup friction | Trust cert × 1 | Allow USB × 1 | Configure server | Install agent |

## When to pick which

### Default — `epos` (browser ↔ printer)

Use when:
- The printer is a **modern Epson / Star / Bixolon / SNBC** thermal
  printer with ePOS-Print enabled (most retail thermal printers since
  2018).
- The cashier's device (tablet, laptop) is on the **same LAN** as the
  printer.

How it works:
1. Server renders ESC/POS bytes (so we don't ship dither code to every
   browser).
2. Browser POSTs the bytes as an ePOS-Print SOAP envelope to
   `https://<printer-ip>:443/cgi-bin/epos/service.cgi?devid=local_printer`.
3. Printer prints, returns `<response success="true"/>`, done.

Operator setup (one time per browser profile):
1. Open the printer's web admin URL in a tab (e.g.
   `https://192.168.1.50/`). Browser warns about the self-signed
   cert → click "Advanced" → "Proceed to site". This trusts the cert
   for that origin permanently.
2. In the printer's admin, confirm **ePOS-Print is enabled** and the
   **Device ID is `local_printer`**.
3. Done. Cashier never sees the cert warning again.

Browser support: **Chrome, Edge, Firefox, Safari, iPad Safari, Android
Chrome** — anything with `fetch()`.

Known gotchas this implementation handles:
- **Chrome ≥ 117 Private Network Access**: if the printer firmware
  doesn't return `Access-Control-Allow-Private-Network: true` on
  preflight, the fetch fails silently. Our client surfaces this with
  a clear hint (update firmware, or temporarily disable the chrome
  flag).
- **Mixed content**: HTTPS Odoo page cannot reach `http://` printer.
  We default to `epos_use_https=True`. If your printer can't do TLS,
  you must run Odoo on HTTP (not recommended).
- **Transient TCP blips**: 3 retries with exponential backoff (per
  print, not per asset bundle).

### `usb` (WebUSB)

Use when:
- Printer is **USB-connected** to the cashier's PC / tablet.
- Browser is **Chrome / Edge / Opera / Samsung Internet** (Chromium).
- OS is **Windows / macOS / Linux / Android**. **Not iOS, not Safari.**

Operator clicks "Allow this USB device" once per browser profile.

(Implementation pending — selection value reserved; routes through
`navigator.usb` like Odoo's IoT-less WebUSB pattern.)

### `network` (server TCP, on-prem)

Use when:
- Odoo runs **on the same LAN as the printer** (on-prem install,
  development box).
- You want one source of truth for prints (server logs every byte).

Cloud SaaS deploys: don't pick this — the server has no route to the
LAN and every print fails.

### `agent` (Bridge Agent)

Use when:
- Cloud Odoo + customer printer + the operator's browser is **not
  required to be on the same LAN** (e.g., head-office staff prints
  receipts on a branch printer).
- You need **scheduled / cron prints** (nightly Z-report).
- The printer doesn't have ePOS-Print firmware.
- You want **one server-side audit log** of every print across all
  branches.

Setup: see `install_agent.sh` in this directory. Operator runs one
shell command on any Linux PC inside the LAN; the agent connects
outbound to Odoo and pulls jobs.

## Decision flowchart

```
START
  │
  ├─ Is this a server-side print? (cron, scheduled report)
  │     YES → agent (or network for on-prem)
  │
  ├─ Is the printer thermal AND firmware supports ePOS-Print?
  │     YES → epos  ✅ (the default)
  │
  ├─ Is the printer USB-attached to the cashier's PC AND
  │   browser is Chromium AND OS is not iOS?
  │     YES → usb (WebUSB)
  │
  ├─ Is Odoo on the same LAN as the printer?
  │     YES → network
  │
  └─ Otherwise → agent
```

## Why ePOS is the default

The CloudERPs SaaS hosts every tenant in AWS. The cloud Odoo can't
reach a customer's `192.168.1.x` printer. ePOS puts the dispatch in
the cashier's browser, which is on the right network — so the most
common deployment (cloud Odoo + thermal printer + iPad-or-laptop
cashier) works without installing anything else.

The trade-off: ePOS prints only happen while a cashier session is
open. For unattended prints (nightly Z, batch invoices), pair an
agent alongside.

## Troubleshooting "every time disconnected"

If receipts print on the first attempt and then drop a session later:

1. Open browser DevTools → Network. Filter for the printer's IP.
2. Look at the failed request. Common patterns:

| What you see | Fix |
|---|---|
| `CORS error … private network` | Chrome PNA. Update printer firmware to one that responds to PNA preflight, OR add `chrome://flags/#block-insecure-private-network-requests=Disabled` |
| `net::ERR_CERT_AUTHORITY_INVALID` | Trust the cert: open `https://<printer-ip>/` in a tab, accept. |
| `Mixed content blocked` | `epos_use_https` must be True. If the printer can't do TLS, this path won't work. |
| `Failed to fetch` (no other info) | Cert was trusted in one session and revoked when browser restarted. Re-accept once. Or check ad-blockers / antivirus rewriting requests. |
| `printer rejected job (code DeviceNotFound)` | The printer's web admin assigns a different Device ID — set `epos_dev_id` to match (usually `local_printer`). |
| `EPTR_REC_EMPTY` | Out of paper. |

If the agent is the chosen mode instead:

| What you see | Fix |
|---|---|
| Agent shows offline within seconds of being online | systemd unit crashed; `journalctl -u ghaima-printer-agent -n 50` |
| Jobs queue but never claim | Token mismatch or wrong AGENT_URL. Hit `/ab_printer/agent/register` with curl + `X-Agent-Token` to verify. |
