/** @odoo-module **/

import { Component, useRef, useState } from "@odoo/owl";

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
        // Track which chip the user clicked so we can paint it as
        // "picked" while the chat re-runs in the background. Reset
        // when SuggestionChips is unmounted (new message renders).
        this.state = useState({ pickedIndex: -1 });
    }

    isPicked(index) {
        return this.state.pickedIndex === index;
    }

    onPick(item, index) {
        if (this.state.pickedIndex >= 0) return;  // double-click guard
        this.state.pickedIndex = index;
        const root = this.rootRef.el;
        if (root) {
            // ``action`` carries a structured payload for write-action
            // confirmation chips (e.g. {type:'confirm_tool', tool, key}).
            // Host (chatbot widget) detects it and dispatches to the
            // dedicated confirm endpoint instead of the LLM path.
            root.dispatchEvent(new CustomEvent("ai-chip-pick", {
                detail: {
                    prompt: item.prompt,
                    label: item.label,
                    action: item.action || null,
                },
                bubbles: true,
                composed: true,
            }));
        }
    }
}
