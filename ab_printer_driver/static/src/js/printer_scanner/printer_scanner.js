/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

/**
 * <PrinterScannerApp/>
 *
 * Full-page client action that owns the network printer discovery UX.
 * Talks to /ab_printer/scan/* JSON endpoints — no form view, no
 * transient wizard. Three-zone layout: scan controls top, live results
 * grid centre, action bar (test / add as driver) bottom.
 *
 * Designed to fit a 13" laptop without horizontal scroll: the results
 * grid uses CSS grid with tabular numerics so 10+ rows are readable
 * at a glance.
 */
export class PrinterScannerApp extends Component {
    static template = "ab_printer_driver.PrinterScannerApp";
    static props = ["*"];

    setup() {
        this.notification = useService("notification");
        this.action = useService("action");
        this.dialog = useService("dialog");

        this.state = useState({
            // Scan parameters (controls)
            subnet:        "",
            portMode:      "common",
            rangeStart:    1,
            rangeEnd:      254,
            timeoutMs:     250,
            doBannerGrab:  true,
            doReverseDns:  true,

            // Scan status
            phase: "ready",                // 'ready' | 'scanning' | 'done'
            scannedCount: 0,
            foundCount: 0,
            durationS: 0,
            error: "",

            // Results
            results: [],                  // { ip, port, vendor, ... selected: bool, busy: bool }
            selectedCount: 0,

            // Manual "Add IP" form
            manualOpen: false,
            manualIp: "",
            manualPort: 9100,
            manualBusy: false,
        });

        onMounted(async () => {
            // Auto-detect subnet on first open by probing the user's
            // session storage cache OR running a 1-IP scan to seed.
            const cached = sessionStorage.getItem("ab_printer_scanner_subnet");
            this.state.subnet = cached || await this._guessSubnet();
        });
    }

    async _guessSubnet() {
        // Best-effort guess from window.location.host if it resolves to
        // an RFC-1918 IP. Otherwise leave blank — the user fills in.
        try {
            const host = window.location.hostname;
            if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
                return host.split(".").slice(0, 3).join(".");
            }
        } catch (e) {}
        return "192.168.1";
    }

    // ── Actions ───────────────────────────────────────────────

    async scan() {
        if (!this.state.subnet) {
            this.notification.add("Subnet required", { type: "warning" });
            return;
        }
        // Forgive a full IPv4 entered in the Subnet field: split into
        // a /24 prefix + lock the range to that single host. People
        // type the printer's IP here all the time and it should "just work".
        const fullIp = this.state.subnet.match(/^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})$/);
        if (fullIp) {
            this.state.subnet = fullIp[1];
            const lastOctet = parseInt(fullIp[2], 10);
            this.state.rangeStart = lastOctet;
            this.state.rangeEnd = lastOctet;
            this.notification.add(
                `Treating ${fullIp[0]} as a single-host scan on ${fullIp[1]}.0/24.`,
                { type: "info" },
            );
        }
        // Trim CIDR mask if present (192.168.8.0/24 → 192.168.8).
        this.state.subnet = this.state.subnet
            .replace(/\/\d+$/, "")
            .replace(/\.0$/, "")
            .replace(/\.$/, "");
        this.state.phase = "scanning";
        this.state.error = "";
        this.state.results = [];
        this.state.selectedCount = 0;
        sessionStorage.setItem("ab_printer_scanner_subnet", this.state.subnet);
        try {
            const res = await rpc("/ab_printer/scan/run", {
                subnet: this.state.subnet,
                port_mode: this.state.portMode,
                range_start: this.state.rangeStart,
                range_end: this.state.rangeEnd,
                timeout_ms: this.state.timeoutMs,
                do_banner_grab: this.state.doBannerGrab,
                do_reverse_dns: this.state.doReverseDns,
            });
            if (!res.success) {
                this.state.error = res.error || "Scan failed";
                this.state.phase = "ready";
                return;
            }
            this.state.scannedCount = res.scanned_count;
            this.state.foundCount = res.found_count;
            this.state.durationS = res.duration_s;
            this.state.results = (res.results || []).map((r) => ({
                ...r,
                selected: true,
                busy: false,
                printer_use: "receipt",
                custom_name: r.name,
            }));
            this.state.selectedCount = this.state.results.length;
            this.state.phase = "done";
        } catch (e) {
            this.state.error = e?.message || String(e);
            this.state.phase = "ready";
        }
    }

    toggleAll() {
        const next = this.state.selectedCount !== this.state.results.length;
        this.state.results.forEach((r) => (r.selected = next));
        this.state.selectedCount = next ? this.state.results.length : 0;
    }

    toggleOne(row) {
        row.selected = !row.selected;
        this.state.selectedCount = this.state.results.filter((r) => r.selected).length;
    }

    async testPrint(row) {
        row.busy = true;
        try {
            const res = await rpc("/ab_printer/scan/test", {
                ip: row.ip,
                port: row.port,
            });
            this.notification.add(
                res.success
                    ? `Test slip sent to ${row.ip}.`
                    : `Test failed: ${res.error || "unknown error"}`,
                { type: res.success ? "success" : "danger" },
            );
        } finally {
            row.busy = false;
        }
    }

    async addDrivers() {
        const selected = this.state.results.filter((r) => r.selected);
        if (!selected.length) {
            this.notification.add("Select at least one printer.", { type: "warning" });
            return;
        }
        try {
            const res = await rpc("/ab_printer/scan/add", {
                printers: selected.map((r) => ({
                    ip: r.ip,
                    port: r.port,
                    mode_hint: r.mode_hint,
                    printer_use: r.printer_use,
                    name: r.custom_name || r.name,
                })),
            });
            if (res.success) {
                this.notification.add(
                    `${res.count} printer driver(s) registered. ` +
                        `The POS receipt flow + any module calling ` +
                        `env['ab.printer.config'].get_default() will use them.`,
                    { type: "success" },
                );
                // Land the user on the printer list to verify.
                this.action.doAction({
                    type: "ir.actions.act_window",
                    name: "Printers",
                    res_model: "ab.printer.config",
                    view_mode: "list,form",
                    views: [[false, "list"], [false, "form"]],
                    target: "current",
                });
            } else {
                this.notification.add(`Add failed: ${res.error || "unknown"}`,
                                      { type: "danger" });
            }
        } catch (e) {
            this.notification.add(e?.message || String(e), { type: "danger" });
        }
    }

    async addManualIp() {
        if (!this.state.manualIp) return;
        this.state.manualBusy = true;
        try {
            const probe = await rpc("/ab_printer/scan/probe", {
                ip: this.state.manualIp,
                port: this.state.manualPort,
            });
            if (!probe.success || !probe.reachable) {
                this.notification.add(
                    probe.error || `${this.state.manualIp}:${this.state.manualPort} unreachable.`,
                    { type: "warning" },
                );
                return;
            }
            // Push into results so the user can name / test / add.
            this.state.results.unshift({
                ip: this.state.manualIp,
                port: this.state.manualPort,
                port_label: this.state.manualPort === 9100 ? "RAW / ESC-POS" : "Unknown",
                open_ports: [this.state.manualPort],
                mode_hint: "network",
                vendor: probe.vendor || "",
                hostname: "",
                response_ms: probe.response_ms,
                speed: probe.response_ms < 50 ? "fast" : probe.response_ms < 200 ? "ok" : "slow",
                name: probe.vendor ? `${probe.vendor} @ ${this.state.manualIp}` : `Printer @ ${this.state.manualIp}`,
                selected: true,
                busy: false,
                printer_use: "receipt",
                custom_name: probe.vendor ? `${probe.vendor} @ ${this.state.manualIp}` : `Printer @ ${this.state.manualIp}`,
            });
            this.state.selectedCount += 1;
            this.state.foundCount = this.state.results.length;
            this.state.phase = "done";
            this.state.manualOpen = false;
            this.state.manualIp = "";
        } finally {
            this.state.manualBusy = false;
        }
    }

    // ── Derived ───────────────────────────────────────────────

    get scanLabel() {
        return this.state.phase === "scanning" ? "Scanning…" : "Scan network";
    }

    get summaryLine() {
        if (this.state.phase !== "done") return "";
        return `${this.state.foundCount} printer(s) found · scanned ${this.state.scannedCount} targets in ${this.state.durationS}s`;
    }

    speedClass(row) {
        return `o_ab_printer_speed--${row.speed || "ok"}`;
    }

    vendorChipClass(row) {
        const v = (row.vendor || "").toLowerCase().replace(/[^a-z]/g, "");
        return v ? `o_ab_printer_vendor--${v}` : "";
    }

    portsLabel(row) {
        if (!row.open_ports || row.open_ports.length === 1) return row.port_label || "";
        return `${row.open_ports.join(", ")}`;
    }
}

registry.category("actions").add("ab_printer_driver.scanner", PrinterScannerApp);
