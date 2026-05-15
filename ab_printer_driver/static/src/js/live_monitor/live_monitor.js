/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

/**
 * Print Diagnostics — answers "why didn't this print just now?"
 *
 * Three zones:
 *   • Printer grid: every ab.printer.config with state badge, last
 *     activity, queue depth. Click → Diagnose action runs the chain
 *     step-by-step on the server and renders the trace inline.
 *   • Recent jobs: last 20 ab.printer.job rows, auto-refreshed.
 *   • Recent log: last 30 ab.printer.log rows.
 *
 * Refresh: 5-second poll. Cheap (single /ab_printer/snapshot call,
 * 30-printer fleet returns in < 50 ms).
 */
export class PrintLiveMonitor extends Component {
    static template = "ab_printer_driver.PrintLiveMonitor";
    static props = ["*"];

    setup() {
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            printers: [],
            jobs: [],
            logs: [],
            loading: true,
            error: "",
            traces: {},          // {driver_id: {steps, running, ok}}
            lastRefresh: null,
            autoRefresh: true,
        });

        onWillStart(() => this.refresh());
        onMounted(() => this._startPoll());
        onWillUnmount(() => this._stopPoll());
    }

    _startPoll() {
        this._pollHandle = setInterval(() => {
            if (this.state.autoRefresh) this.refresh();
        }, 5000);
    }

    _stopPoll() {
        if (this._pollHandle) clearInterval(this._pollHandle);
    }

    async refresh() {
        try {
            const res = await rpc("/ab_printer/snapshot", {});
            if (res.success) {
                this.state.printers = res.printers;
                this.state.jobs = res.recent_jobs;
                this.state.logs = res.recent_logs;
                this.state.lastRefresh = new Date();
                this.state.error = "";
            } else {
                this.state.error = res.error || "snapshot failed";
            }
        } catch (e) {
            this.state.error = e?.message || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    async diagnose(driver, sendTest = true) {
        this.state.traces[driver.id] = { running: true, steps: [], ok: false };
        try {
            const res = await rpc("/ab_printer/diagnose", {
                driver_id: driver.id,
                send_test: sendTest,
            });
            this.state.traces[driver.id] = {
                running: false,
                steps: res.steps || [],
                ok: res.success === true,
            };
        } catch (e) {
            this.state.traces[driver.id] = {
                running: false,
                ok: false,
                steps: [{ name: "rpc", status: "fail",
                          detail: e?.message || String(e), duration_ms: 0 }],
            };
        }
    }

    openDriver(driver) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "ab.printer.config",
            res_id: driver.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openQueue() {
        this.action.doAction("ab_printer_driver.action_printer_job");
    }

    stateBadgeClass(p) {
        if (p.state === "connected" && p.verified) return "o_pm_badge--ok";
        if (p.state === "connected")               return "o_pm_badge--warn";
        if (p.state === "printing")                return "o_pm_badge--info";
        return "o_pm_badge--fail";
    }

    stepIcon(s) {
        if (s.status === "ok")   return "fa-check-circle text-success";
        if (s.status === "warn") return "fa-exclamation-circle text-warning";
        if (s.status === "fail") return "fa-times-circle text-danger";
        return "fa-circle text-muted";
    }

    relTime(iso) {
        if (!iso) return "—";
        const d = new Date(iso.replace(" ", "T") + "Z");
        const s = (Date.now() - d.getTime()) / 1000;
        if (s < 60)    return `${Math.round(s)}s ago`;
        if (s < 3600)  return `${Math.round(s / 60)}m ago`;
        if (s < 86400) return `${Math.round(s / 3600)}h ago`;
        return `${Math.round(s / 86400)}d ago`;
    }
}

registry.category("actions").add("ab_printer_driver.live_monitor", PrintLiveMonitor);
