/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * <AiAgentChip/>
 *
 * Persona picker. Click → dropdown of every visible agent. Selection
 * fires onPick(agent) — parent updates its activeAgent.
 *
 * Visual: pill-shaped chip with a 22px coloured avatar circle, the
 * agent name, and a caret. Active agent gets a 12% blue tint. Accent
 * colour follows the persona (assistant=blue, analyst=navy, …).
 */
export class AiAgentChip extends Component {
    static template = "ab_ai_agent.AiAgentChip";
    static props = {
        agent:    { type: Object, optional: true },
        agents:   { type: Array, optional: true },
        onPick:   { type: Function, optional: true },
        compact:  { type: Boolean, optional: true },
    };
    static defaultProps = { compact: false };

    setup() {
        this.state = useState({ open: false });
        this.rootRef = useRef("root");
        this._handleDocumentClick = this._handleDocumentClick.bind(this);

        onMounted(() => document.addEventListener("mousedown", this._handleDocumentClick));
        onWillUnmount(() => document.removeEventListener("mousedown", this._handleDocumentClick));
    }

    _handleDocumentClick(ev) {
        if (this.state.open && this.rootRef.el && !this.rootRef.el.contains(ev.target)) {
            this.state.open = false;
        }
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    pick(agent) {
        this.state.open = false;
        if (this.props.onPick) {
            this.props.onPick(agent);
        }
    }

    get initials() {
        const name = this.props.agent?.name || "AI";
        return name
            .split(/\s+/)
            .slice(0, 2)
            .map((w) => w[0]?.toUpperCase())
            .join("");
    }

    accentClass(agent) {
        return `o_accent-${agent?.accent || "blue"}`;
    }
}
