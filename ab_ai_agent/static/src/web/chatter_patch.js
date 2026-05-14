/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Chatter } from "@mail/chatter/web/chatter";
import { AiAgentChat } from "../components/ai_agent_chat/ai_agent_chat";

/**
 * Chatter "Ask AI" button.
 *
 * Patches the native Chatter component to expose an "Ask AI" button in
 * the chatter top bar (next to Activity / Follow). Clicking opens
 * <AiAgentChat/> in a modal with the current record's context wired up
 * (surface=chatter, recordModel/Id/Name), so the agent can reason about
 * the form the user is currently looking at.
 *
 * No native Chatter behaviour is altered — pure additive setup.
 */
patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.aiDialog = useService("dialog");
    },

    onClickAskAI() {
        const thread = this.state.thread;
        if (!thread || !thread.model || !thread.id) {
            return;
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
 * Dialog without inlining a template here.
 */
import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

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
