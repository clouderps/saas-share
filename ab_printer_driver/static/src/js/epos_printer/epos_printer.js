/** @odoo-module **/
/**
 * ePOS-Print browser client.
 *
 * Talks directly to the printer's on-board HTTPS server, from the
 * operator's browser, over the local network. No cloud round-trip and
 * no bridge agent — this is the path that makes a SaaS Odoo print
 * receipts on a LAN thermal printer with no extra install.
 *
 * Works with Epson TM-T20III / TM-T88VI / TM-m30 / TM-P80 and every
 * vendor that speaks Epson's ePOS-Print XML SOAP protocol (Star,
 * Bixolon, SNBC ship compatible firmware on modern models).
 *
 * Why a custom client and not pos_epson_printer's EpsonPrinter?
 *  1. Configurable port — the stock Odoo client hardcodes 80/443. Some
 *     firmwares use 8043 / 8008.
 *  2. Per-print retry with exponential backoff — pos_epson_printer
 *     clears the queue on any error. One TCP blip kills the print.
 *  3. Private Network Access diagnostics — we surface PNA + self-signed
 *     cert errors as actionable messages instead of "Failed to fetch".
 *  4. Health-check probe — the form can show live online/offline status
 *     without queuing a real print.
 */

import { _t } from "@web/core/l10n/translation";

const SOAP_TEMPLATE_PREFIX =
    '<?xml version="1.0" encoding="utf-8"?>' +
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">' +
    '<s:Body>' +
    '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">';
const SOAP_TEMPLATE_SUFFIX = '</epos-print></s:Body></s:Envelope>';

/**
 * Build the ePOS endpoint URL for a driver config.
 * @param {object} cfg — output of ab.printer.config._get_browser_dispatch_config
 */
export function eposUrl(cfg) {
    const proto = cfg.use_https ? "https" : "http";
    const port = cfg.port || (cfg.use_https ? 443 : 80);
    const devid = encodeURIComponent(cfg.dev_id || "local_printer");
    // Timeout is the printer's own timeout for the print job (not our
    // fetch timeout). 10s is the Epson default; we expose nothing in
    // the model — operator sets the per-fetch timeout via cfg.timeout_ms.
    return `${proto}://${cfg.ip}:${port}/cgi-bin/epos/service.cgi?devid=${devid}&timeout=10000`;
}

/**
 * Hex-encode binary bytes for the <command> element. Epson's ePOS XML
 * <command> accepts uppercase hex without separators (e.g. "1B40" for
 * ESC @ init).
 *
 * @param {Uint8Array|ArrayBuffer|number[]} bytes
 */
function bytesToHex(bytes) {
    const view =
        bytes instanceof Uint8Array
            ? bytes
            : bytes instanceof ArrayBuffer
            ? new Uint8Array(bytes)
            : new Uint8Array(bytes);
    let out = "";
    for (let i = 0; i < view.length; i++) {
        out += view[i].toString(16).padStart(2, "0").toUpperCase();
    }
    return out;
}

/**
 * Decode a base64 string to a Uint8Array. ESC/POS payloads from the
 * server arrive base64-encoded (transport-safe JSON).
 */
function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
        out[i] = bin.charCodeAt(i);
    }
    return out;
}

/**
 * Wrap raw ESC/POS bytes into a single ePOS SOAP envelope.
 */
export function buildEposSoapEscpos(bytes) {
    return (
        SOAP_TEMPLATE_PREFIX +
        `<command>${bytesToHex(bytes)}</command>` +
        SOAP_TEMPLATE_SUFFIX
    );
}

/**
 * Build a "test slip" SOAP — high-level XML so we don't depend on the
 * server having ESC/POS bytes pre-built.
 *
 * Used by the form's Test button; the cashier flow always sends the
 * server-rendered ESC/POS via buildEposSoapEscpos().
 */
export function buildEposSoapTestSlip({ name = "" }) {
    const safe = (name || "Test Print").replace(/[<>&"']/g, "");
    return (
        SOAP_TEMPLATE_PREFIX +
        `<text align="center" font="font_a" width="2" height="2">` +
        `Ghaima ePOS&#10;</text>` +
        `<text align="center">` +
        `${safe}&#10;${new Date().toLocaleString()}&#10;</text>` +
        `<feed line="2"/>` +
        `<cut type="feed"/>` +
        SOAP_TEMPLATE_SUFFIX
    );
}

/**
 * Inspect the ePOS XML response and return {success, code, status}.
 * The printer answers with:
 *   <response success="true|false" code="..." status="..." battery="..."/>
 */
function parseEposResponse(xmlText) {
    try {
        const dom = new DOMParser().parseFromString(xmlText, "application/xml");
        const r = dom.querySelector("response");
        if (!r) {
            return { success: false, code: "MALFORMED", status: "no <response>" };
        }
        return {
            success: r.getAttribute("success") === "true",
            code: r.getAttribute("code") || "",
            status: r.getAttribute("status") || "",
        };
    } catch (e) {
        return { success: false, code: "PARSE_ERROR", status: e.message };
    }
}

/**
 * Translate low-level fetch errors into actionable user messages.
 *
 * Browsers don't expose much detail on cross-origin / mixed-content /
 * PNA failures — the request just resolves with TypeError. We pattern
 * match the message to give the operator something useful.
 */
function diagnoseFetchError(err, cfg) {
    const msg = String(err && err.message ? err.message : err);
    const url = eposUrl(cfg);
    // Chrome / Firefox: failed CORS or PNA preflight → "Failed to fetch"
    if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        const hints = [];
        if (cfg.use_https && window.location.protocol === "https:") {
            hints.push(
                _t(
                    "1. Open %s in a new tab and accept the printer's self-signed certificate (one time per browser).",
                    url,
                ),
            );
        }
        if (cfg.use_https === false && window.location.protocol === "https:") {
            hints.push(
                _t(
                    "2. The Odoo page is HTTPS but the printer is HTTP. Mixed content is blocked — set 'ePOS over HTTPS' on the printer record.",
                ),
            );
        }
        hints.push(
            _t(
                "3. Chrome 117+ requires Private Network Access. The printer's firmware must respond to PNA preflight or the request fails silently. Update the printer firmware, or enable chrome://flags/#block-insecure-private-network-requests = Disabled.",
            ),
        );
        hints.push(
            _t(
                "4. Verify the printer is reachable: ping %s from the operator device.",
                cfg.ip,
            ),
        );
        return _t(
            "Could not reach the printer at %s. Likely causes:\n%s",
            url,
            hints.join("\n"),
        );
    }
    if (msg.includes("aborted")) {
        return _t("Print request timed out after %sms.", cfg.timeout_ms || 5000);
    }
    return _t("Print transport error: %s", msg);
}

/**
 * Do one fetch attempt with timeout. Returns {ok, parsed?, error?}.
 * Caller adds retry/backoff.
 */
async function eposFetchOnce(cfg, soapXml, timeoutMs) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        const params = {
            method: "POST",
            headers: {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": '""',
            },
            body: soapXml,
            signal: ctrl.signal,
            // Don't send credentials cross-origin — the printer has no
            // auth model and including cookies makes some PNA preflights
            // fail.
            credentials: "omit",
            mode: "cors",
        };
        const resp = await fetch(eposUrl(cfg), params);
        if (!resp.ok) {
            return {
                ok: false,
                error: _t("Printer responded HTTP %s", resp.status),
            };
        }
        const text = await resp.text();
        const parsed = parseEposResponse(text);
        return { ok: true, parsed, rawResponse: text };
    } catch (err) {
        return { ok: false, error: diagnoseFetchError(err, cfg) };
    } finally {
        clearTimeout(t);
    }
}

/**
 * High-level entry point. Sends a SOAP envelope to the printer with
 * retries, returns the operational result.
 *
 * @param {object} cfg — driver config from _get_browser_dispatch_config
 * @param {string} soapXml — full SOAP envelope (use buildEposSoap*)
 * @returns {{ success: bool, code?, status?, error? }}
 */
export async function eposDispatch(cfg, soapXml) {
    if (!cfg || !cfg.ip) {
        return { success: false, error: _t("Printer IP not set.") };
    }
    const maxAttempts = Math.max(1, cfg.retry_count || 3);
    const baseTimeout = cfg.timeout_ms || 5000;
    let lastError = "";
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        const res = await eposFetchOnce(cfg, soapXml, baseTimeout);
        if (res.ok && res.parsed && res.parsed.success) {
            return {
                success: true,
                code: res.parsed.code,
                status: res.parsed.status,
                attempts: attempt,
            };
        }
        // Printer reachable but returned success=false — no point retrying.
        if (res.ok && res.parsed && !res.parsed.success) {
            return {
                success: false,
                code: res.parsed.code,
                status: res.parsed.status,
                error: _t(
                    "Printer rejected the job (code %s, status %s).",
                    res.parsed.code || "?",
                    res.parsed.status || "?",
                ),
                attempts: attempt,
            };
        }
        // Transport failure → backoff and retry.
        lastError = res.error || _t("Unknown transport error");
        if (attempt < maxAttempts) {
            await new Promise((r) => setTimeout(r, 250 * attempt));
        }
    }
    return { success: false, error: lastError, attempts: maxAttempts };
}

/**
 * Print raw ESC/POS bytes via ePOS.
 */
export async function eposPrintEscposBytes(cfg, bytes) {
    return eposDispatch(cfg, buildEposSoapEscpos(bytes));
}

/**
 * Print ESC/POS bytes given as a base64 string (what the server's
 * dispatch endpoints return).
 */
export async function eposPrintEscposB64(cfg, b64) {
    return eposDispatch(cfg, buildEposSoapEscpos(b64ToBytes(b64)));
}

/**
 * Print the test slip (built client-side, no server round-trip).
 */
export async function eposPrintTestSlip(cfg) {
    return eposDispatch(cfg, buildEposSoapTestSlip({ name: cfg.name }));
}

/**
 * Quick reachability probe — sends an empty <epos-print/> envelope. The
 * printer answers `success="true"` if it can talk; faster than a real
 * print and used by the form's Live status indicator and the periodic
 * health poll.
 */
export async function eposHealthCheck(cfg) {
    return eposDispatch(cfg, SOAP_TEMPLATE_PREFIX + SOAP_TEMPLATE_SUFFIX);
}
