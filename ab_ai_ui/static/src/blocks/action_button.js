/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/** Single suggested action the operator can run. Calls
 *  ``env[model].method(**kwargs)`` via the orm service. Disabled +
 *  spinning while in flight; toast on success/failure. Per the plan
 *  this is read-only-by-default — the operator chooses, the AI
 *  cannot auto-execute. */
export class AiActionButton extends Component {
    static template = "ab_ai_ui.AiActionButton";
    static props = {
        label: { type: String },
        method: { type: String },
        kwargs: { type: Object, optional: true },
        danger: { type: Boolean, optional: true },
        secondary: { type: Boolean, optional: true },
        icon: { type: String, optional: true },
    };
    static defaultProps = { kwargs: {}, danger: false, secondary: false, icon: "" };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ running: false });
    }

    get classes() {
        let cls = "ai-action";
        if (this.props.danger) {
            cls += " ai-action--danger";
        } else if (this.props.secondary) {
            cls += " ai-action--secondary";
        }
        return cls;
    }

    async onRun() {
        if (this.state.running) {
            return;
        }
        // method is "model.method" — split at first dot.
        const dot = this.props.method.indexOf(".");
        if (dot < 0) {
            this.notification.add("Invalid action target: " + this.props.method, { type: "danger" });
            return;
        }
        // Take the WHOLE prefix as model, last segment as method, so
        // "pos.config.action_open_ui" → model=pos.config method=action_open_ui.
        const lastDot = this.props.method.lastIndexOf(".");
        const model = this.props.method.slice(0, lastDot);
        const method = this.props.method.slice(lastDot + 1);
        this.state.running = true;
        try {
            await this.orm.call(model, method, [], this.props.kwargs);
            this.notification.add(this.props.label + " — done", { type: "success" });
        } catch (e) {
            this.notification.add(
                this.props.label + " failed: " + (e.data?.message || e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.running = false;
        }
    }
}
