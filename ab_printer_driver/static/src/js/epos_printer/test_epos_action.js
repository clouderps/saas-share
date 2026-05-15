/** @odoo-module **/
/**
 * Client action `ab_printer.test_epos`.
 *
 * Server returns this action when the operator clicks "Test Print" on a
 * printer record with printer_mode='epos'. The action runs entirely in
 * the browser — it dispatches the ESC/POS test slip directly to the
 * printer's ePOS endpoint over the operator's LAN, then renders a
 * native Odoo notification with the outcome.
 *
 * Why a client action and not a notification on the server side? The
 * cloud Odoo cannot reach a private RFC1918 printer. Only code running
 * in the operator's browser is on the right network.
 */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { eposPrintEscposB64, eposHealthCheck } from "./epos_printer";

async function testEposAction({ env, action }) {
    const params = action.params || {};
    const cfg = params.config || {};
    const escposB64 = params.escpos_b64;
    const notification = env.services.notification;

    if (!cfg.ip) {
        notification.add(_t("Set the Printer IP first."), { type: "warning" });
        return { type: "ir.actions.act_window_close" };
    }

    // Health probe first — gives the operator a clean error if the
    // printer is unreachable, rather than letting the real print fail
    // with the same message.
    notification.add(_t("Probing %s…", cfg.ip), { type: "info" });
    const probe = await eposHealthCheck(cfg);
    if (!probe.success) {
        notification.add(
            probe.error || _t("Printer unreachable"),
            { type: "danger", sticky: true, title: _t("ePOS probe failed") },
        );
        return { type: "ir.actions.act_window_close" };
    }

    const res = await eposPrintEscposB64(cfg, escposB64);
    if (res.success) {
        notification.add(
            _t(
                "Test slip sent to %s (attempts: %s).",
                params.driver_name || cfg.name || cfg.ip,
                res.attempts || 1,
            ),
            { type: "success" },
        );
    } else {
        notification.add(res.error || _t("Print failed"), {
            type: "danger",
            sticky: true,
            title: _t("ePOS test failed"),
        });
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("ab_printer.test_epos", testEposAction);
