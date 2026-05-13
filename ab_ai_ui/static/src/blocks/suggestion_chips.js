/** @odoo-module **/

import { Component, useRef } from "@odoo/owl";

/** <SuggestionChips/> — clarification UX.
 *
 *  Surfaces 2-4 pre-resolved interpretations of an ambiguous user
 *  prompt. Clicking a chip dispatches a CustomEvent("ai-chip-pick", …)
 *  the host (chatbot, dashboard, scan-docs) listens for and re-runs.
 *
 *  Server-side contract: returned envelope carries
 *    render.layout = "clarify"
 *    blocks[].type = "suggestion_chips"
 *    blocks[].items = [{ label, prompt, icon? }]
 *
 *  We deliberately do NOT call orm.call() from here — the chip just
 *  emits the chosen prompt back up to the conversation widget, which
 *  owns the send pipeline. */
export class SuggestionChips extends Component {
    static template = "ab_ai_ui.SuggestionChips";
    static props = {
        items: { type: Array, optional: true },
        title: { type: String, optional: true },
    };
    static defaultProps = { items: [], title: "" };

    setup() {
        this.rootRef = useRef("root");
    }

    onPick(item) {
        // Bubble through DOM so any ancestor (chat panel, scan widget,
        // dashboard) can listen without owning a Bus instance.
        const root = this.rootRef.el;
        if (root) {
            root.dispatchEvent(new CustomEvent("ai-chip-pick", {
                detail: { prompt: item.prompt, label: item.label },
                bubbles: true,
                composed: true,
            }));
        }
    }
}
