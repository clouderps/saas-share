/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * <AiAgentTokenMeter/>
 *
 * Always-visible chip showing today's tokens + SAR cost + remaining
 * budget. Reads reactive state from aiAgentService — every component
 * sees the same numbers.
 *
 * Visual states:
 *   ok       → grey-on-white pill
 *   warn     → gold border + tint at ≥ 80% budget
 *   blocked  → rose border + tint at 100% budget
 *
 * Format: "Today · 14,800 tokens · ر.س 3.45 · 86% budget left"
 * Truncates gracefully on narrow surfaces (chatter popover).
 */
export class AiAgentTokenMeter extends Component {
    static template = "ab_ai_agent.AiAgentTokenMeter";
    static props = {
        compact: { type: Boolean, optional: true },
    };
    static defaultProps = { compact: false };

    setup() {
        this.aiAgent = useService("aiAgentService");
    }

    get meter() {
        return this.aiAgent.state.meter;
    }

    get tokensFmt() {
        const n = this.meter.today.tokens || 0;
        if (n < 1000) return String(n);
        if (n < 1_000_000) return (n / 1000).toFixed(n < 10_000 ? 1 : 0) + "K";
        return (n / 1_000_000).toFixed(1) + "M";
    }

    get costFmt() {
        const sar = this.meter.today.cost_sar || 0;
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        }).format(sar);
    }

    get stateClass() {
        return `o_state-${this.meter.state || "ok"}`;
    }
}
