/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * <AiAgentRunTrace/>
 *
 * Collapsible audit panel. Shows the tool-call timeline for one run:
 * which tools fired, in which order, with their durations and error
 * states. Closed by default — only the curious dig in.
 *
 * Renders inside the assistant bubble when toolCalls is non-empty.
 */
export class AiAgentRunTrace extends Component {
    static template = "ab_ai_agent.AiAgentRunTrace";
    static props = {
        toolCalls: { type: Array, optional: true },
        provenance: { type: Object, optional: true },
    };
    static defaultProps = { toolCalls: [] };

    callClass(c) {
        return c.ok ? "is-ok" : "is-error";
    }

    fmtDuration(ms) {
        if (!ms) return "—";
        if (ms < 1000) return `${ms} ms`;
        return `${(ms / 1000).toFixed(2)} s`;
    }
}
