/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/** Phase F — collapsible audit of tools the model invoked. Each row
 *  shows tool name, success/fail, duration; clicking the row expands
 *  the JSON arguments + result so ops can inspect provenance. */
export class ToolTrace extends Component {
    static template = "ab_ai_ui.ToolTrace";
    static props = {
        calls: { type: Array, optional: true },
    };
    static defaultProps = { calls: [] };

    setup() {
        this.state = useState({ open: false, expanded: {} });
    }

    onToggle() {
        this.state.open = !this.state.open;
    }

    onRowToggle(idx) {
        this.state.expanded[idx] = !this.state.expanded[idx];
    }

    formatJson(value) {
        if (!value) {
            return "—";
        }
        if (typeof value === "string") {
            try {
                return JSON.stringify(JSON.parse(value), null, 2);
            } catch (e) {
                return value;
            }
        }
        return JSON.stringify(value, null, 2);
    }

    formatDuration(d) {
        if (typeof d !== "number") {
            return "—";
        }
        if (d < 0.001) {
            return "< 1 ms";
        }
        if (d < 1) {
            return Math.round(d * 1000) + " ms";
        }
        return d.toFixed(2) + " s";
    }
}
