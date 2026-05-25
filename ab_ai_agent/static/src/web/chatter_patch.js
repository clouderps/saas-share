/** @odoo-module **/

import { Component } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { Dialog } from "@web/core/dialog/dialog";
import { AiAgentChat } from "../components/ai_agent_chat/ai_agent_chat";

/**
 * Chatter "Ask AI" button.
 *
 * Two surfaces are wired up from the same topbar button:
 *
 *   • Inline panel — clicking "Ask AI" toggles state.composerType
 *     between 'ai' and false, slotting <AiAgentChat/> into the chatter
 *     composer area (alongside Send Message / Log Note). This is the
 *     default — fastest path, no dialog round-trip.
 *
 *   • Full dialog — the "Expand" button inside the inline panel opens
 *     <AiAgentChatDialog/> for users who want more room (long context,
 *     reviewing block-kit tables, side-by-side with the record).
 *
 * The state lives on the existing chatter `state.composerType` so the
 * AI panel is exclusive with the message / note composer — only one
 * composer panel at a time, matching native Odoo mental model.
 */

// Register AiAgentChat as a Chatter component so the inherited
// template can mount it without each user re-importing.
Object.assign(Chatter.components, { AiAgentChat });

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.aiDialog = useService("dialog");
    },

    /**
     * Open the AI in a full-screen Dialog. Triggered from the
     * "Expand" affordance inside the inline panel.
     */
    onClickAskAIPopOut() {
        const thread = this.state.thread;
        if (!thread || !thread.model || !thread.id) {
            return;
        }
        // Close the inline panel as we hand off to the dialog so the
        // user doesn't end up with two concurrent AI surfaces.
        if (this.state.composerType === "ai") {
            this.state.composerType = false;
        }
        this.aiDialog.add(
            AiAgentChatDialog,
            {
                recordModel: thread.model,
                recordId: thread.id,
                recordName: thread.name || thread.display_name || "",
                title: `Ask AI · ${thread.name || thread.model}`,
            },
            { size: "lg" },
        );
    },
});

/**
 * Tiny wrapper so we can mount <AiAgentChat/> inside the standard Odoo
 * Dialog frame for the pop-out path.
 */
class AiAgentChatDialog extends Component {
    static template = "ab_ai_agent.AiAgentChatDialog";
    static components = { Dialog, AiAgentChat };
    static props = {
        recordModel: String,
        recordId: { type: [Number, Boolean] },
        recordName: { type: String, optional: true },
        title: { type: String, optional: true },
        close: Function,
    };

    get dialogTitle() {
        return this.props.title || "Ask AI";
    }
}
