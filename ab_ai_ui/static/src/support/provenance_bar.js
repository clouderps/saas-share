/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/** One-line footer that surfaces the audit data the gateway already
 *  collects: model, cost, tokens, redaction count, fallback flag,
 *  tool-call count. Collapsible so ops can read it without cluttering
 *  the response body. */
export class ProvenanceBar extends Component {
    static template = "ab_ai_ui.ProvenanceBar";
    static props = {
        provenance: { type: Object, optional: true },
        streaming: { type: Boolean, optional: true },
    };
    static defaultProps = { streaming: false };

    setup() {
        this.state = useState({ expanded: false });
    }

    get chips() {
        const p = this.props.provenance || {};
        const chips = [];

        if (this.props.streaming) {
            chips.push({ kind: "brand", icon: "fa-bolt", text: "streaming…" });
            return chips;
        }
        if (p.simulated) {
            chips.push({ kind: "warn", icon: "fa-flask", text: "simulated" });
        }
        if (p.fallback_engaged) {
            chips.push({ kind: "warn", icon: "fa-recycle", text: "fallback" });
        }
        if (p.prompt_injection_flagged) {
            chips.push({ kind: "bad", icon: "fa-shield", text: "injection flagged" });
        }
        if (p.redaction_count > 0) {
            chips.push({ kind: "good", icon: "fa-user-secret", text: p.redaction_count + " PII redacted" });
        }
        if (p.tool_calls_count > 0) {
            chips.push({ kind: "brand", icon: "fa-wrench", text: p.tool_calls_count + " tool" + (p.tool_calls_count === 1 ? "" : "s") });
        }
        return chips;
    }

    get summary() {
        const p = this.props.provenance || {};
        const bits = [];
        if (p.provider || p.model) {
            bits.push((p.provider ? p.provider + "/" : "") + (p.model || "—"));
        }
        if (p.tokens && p.tokens.total) {
            bits.push(p.tokens.total + " tok");
        }
        if (p.cost_usd > 0) {
            bits.push("$" + p.cost_usd.toFixed(4));
        }
        if (typeof p.duration_s === "number") {
            bits.push(p.duration_s.toFixed(2) + "s");
        }
        return bits.join(" · ");
    }

    onToggle() {
        this.state.expanded = !this.state.expanded;
    }

    async onCopy(text) {
        try {
            await navigator.clipboard.writeText(text || "");
        } catch (e) {
            // Ignore — clipboard might be disabled.
        }
    }
}
