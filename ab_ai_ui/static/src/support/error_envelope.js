/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Consistent error surface for AI responses. Maps low-level error codes
 *  to friendly hints — e.g. quota_exceeded explains the next step, not
 *  just the raw status string. */
export class ErrorEnvelope extends Component {
    static template = "ab_ai_ui.ErrorEnvelope";
    static props = {
        message: { type: String, optional: true },
        status: { type: String, optional: true },
    };

    get hint() {
        const map = {
            quota_exceeded: "This entity has hit its token quota. Top up the plan or wait for the next period.",
            rate_limited: "Too many requests per minute. Retry in a moment.",
            auth_error: "AI gateway token is missing or invalid. Check the X-Entity-Token configuration.",
            error: "The provider returned an error. The audit log on ai.usage.log has the details.",
        };
        return map[this.props.status] || "See the AI usage log for the full traceback.";
    }
}
