/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Safe text rendering with paragraph + line-break only — no markdown,
 *  no embedded HTML. Per SAAS_AI_UI_PLAN.md Part 9: "No client-side
 *  markdown. The model returns clean blocks; chatbot only needs
 *  <AiText/>". Streaming consumers pass ``streaming=true`` so the
 *  blinking cursor renders at the end. */
export class AiText extends Component {
    static template = "ab_ai_ui.AiText";
    static props = {
        text: { type: String, optional: true },
        streaming: { type: Boolean, optional: true },
    };
    static defaultProps = { text: "", streaming: false };

    get paragraphs() {
        // Split on double newline → paragraphs. Single newline → <br>.
        const t = (this.props.text || "").replace(/\r\n/g, "\n");
        return t.split(/\n\n+/).map((p) => p.split("\n"));
    }
}
