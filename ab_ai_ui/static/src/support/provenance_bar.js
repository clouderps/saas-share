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
        // Phase G.4 — cost-side chips. Cache hits get a green badge
        // so ops can tell why the call was free; tight budget shows
        // a yellow chip below 20% remaining.
        if (p.cache_hit) {
            chips.push({ kind: "good", icon: "fa-bolt", text: "cached" });
        }
        if (typeof p.budget_remaining_pct === "number"
                && p.budget_remaining_pct >= 0
                && p.budget_remaining_pct < 0.2) {
            const pct = Math.round(p.budget_remaining_pct * 100);
            chips.push({ kind: "warn", icon: "fa-tachometer", text: pct + "% budget left" });
        }
        // Stage 4 verdict chip — green / yellow / grey based on the
        // validator's verified / partial / unverified label. Hidden
        // when the envelope doesn't carry a verdict (legacy responses).
        if (p.verdict) {
            const map = {
                verified:           { kind: "good", icon: "fa-check-circle",  text: "verified" },
                partial:            { kind: "warn", icon: "fa-adjust",        text: "partial"  },
                unverified:         { kind: "muted", icon: "fa-question-circle", text: "unverified" },
                policy_violation:   { kind: "bad",  icon: "fa-shield",        text: "rule fix" },
            };
            const v = map[p.verdict];
            if (v) chips.push(v);
        }
        return chips;
    }

    get provenanceJson() {
        return JSON.stringify(this.props.provenance, null, 2);
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
