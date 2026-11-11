/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/** User-facing error card for AI responses.
 *  Raw codes (PROVIDER_ERROR, quota_exceeded, ...) are never shown as the
 *  message: they map to plain text plus a next step, and the code is kept
 *  only as a small reference for support. */
const CODE_RE = /^[A-Za-z_]+$/;

export class ErrorEnvelope extends Component {
    static template = "ab_ai_ui.ErrorEnvelope";
    static props = {
        message: { type: String, optional: true },
        status: { type: String, optional: true },
    };

    get code() {
        const msg = (this.props.message || "").trim();
        if (CODE_RE.test(msg)) {
            return msg.toLowerCase();
        }
        return (this.props.status || "error").toLowerCase();
    }

    get copy() {
        const map = {
            provider_error: {
                title: _t("The assistant can't answer right now"),
                body: _t("The AI service didn't respond, so no answer was created. Nothing in your data was changed."),
                hint: _t("Try again in a few minutes. If it keeps happening, contact your administrator."),
            },
            quota_exceeded: {
                title: _t("AI usage limit reached"),
                body: _t("Your plan's AI usage for this period has been used up."),
                hint: _t("Ask your administrator to upgrade the plan, or try again next period."),
            },
            rate_limited: {
                title: _t("Too many requests"),
                body: _t("The assistant received too many requests in a short time."),
                hint: _t("Wait a moment, then try again."),
            },
            auth_error: {
                title: _t("The assistant isn't set up correctly"),
                body: _t("The connection to the AI service isn't configured."),
                hint: _t("Contact your administrator."),
            },
        };
        const generic = {
            title: _t("Something went wrong"),
            body: _t("The assistant couldn't finish this request."),
            hint: _t("Try again. If it keeps happening, contact your administrator."),
        };
        const known = map[this.code];
        if (known) {
            return known;
        }
        // A real sentence from the server (already user-facing) wins over
        // the generic body; a bare code never does.
        const msg = (this.props.message || "").trim();
        return msg && !CODE_RE.test(msg) ? { ...generic, body: msg } : generic;
    }

    get reference() {
        return this.code === "error" ? "" : this.code.toUpperCase();
    }
}
