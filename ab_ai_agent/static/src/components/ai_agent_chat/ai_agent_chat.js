/** @odoo-module **/

import { Component, useState, useRef, onMounted, onPatched, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { AiAgentChip } from "../ai_agent_chip/ai_agent_chip";
import { AiAgentSkillCard } from "../ai_agent_skill_card/ai_agent_skill_card";
import { AiAgentTokenMeter } from "../ai_agent_token_meter/ai_agent_token_meter";
import { AiAgentRunTrace } from "../ai_agent_run_trace/ai_agent_run_trace";

/**
 * <AiAgentChat/> — the universal chat surface.
 *
 * One OWL component drives the Discuss chatbot, the chatter "Ask AI"
 * button modal, the mail composer wizard, and the public website
 * widget. Surface-specific behaviour is selected by the `surface`
 * prop (chat | chatter | composer | website).
 *
 * Visual layout — 3 zones:
 *
 *  ┌─────────────────────────────────────────────────────────────┐
 *  │ AGENT CHIP        Title — Subtitle               TokenMeter │  header
 *  ├──────────────────────────────────────────────┬──────────────┤
 *  │                                              │              │
 *  │  ▌ Hi! What can I help with?                 │   Skills     │
 *  │                                              │   • Card 1   │
 *  │  user: how many sales today?             ▌   │   • Card 2   │
 *  │                                              │   • Card 3   │
 *  │  ▌ You sold 142 today (▲ 12 vs yesterday).  │              │
 *  │      └ tool trace (collapsed)                │              │
 *  │                                              │              │
 *  ├──────────────────────────────────────────────┴──────────────┤
 *  │ [ Ask me anything                                 ] [Send]  │  footer
 *  └─────────────────────────────────────────────────────────────┘
 *
 * Reuses ab_ai_ui block renderer for assistant content (via
 * dynamic-import; ab_ai_agent does NOT hard-depend on ab_ai_ui at
 * the model layer, only at the asset bundle level).
 */
export class AiAgentChat extends Component {
    static template = "ab_ai_agent.AiAgentChat";
    static components = {
        AiAgentChip,
        AiAgentSkillCard,
        AiAgentTokenMeter,
        AiAgentRunTrace,
    };
    static props = {
        // Hard-pin an agent (chatter button passes one). Optional;
        // omitted means the chip picker controls who answers.
        agentCode: { type: String, optional: true },
        // Where we are: chat | chatter | composer | website
        surface: { type: String, optional: true },
        // Optional record context for chatter / composer surfaces
        recordModel: { type: String, optional: true },
        recordId: { type: Number, optional: true },
        recordName: { type: String, optional: true },
        // Optional initial message (deep-link / shared prompts)
        initialMessage: { type: String, optional: true },
        // Loose conversation pointer for cache/history grouping
        conversationId: { type: String, optional: true },
        // Mute the sidebar — used in narrow surfaces
        hideSidebar: { type: Boolean, optional: true },
        // Locale override (default = user.lang)
        locale: { type: String, optional: true },
        onClose: { type: Function, optional: true },
        title: { type: String, optional: true },
    };
    static defaultProps = {
        surface: "chat",
        hideSidebar: false,
    };

    setup() {
        this.aiAgent = useService("aiAgentService");
        this.notification = useService("notification");
        try {
            this.actionService = useService("action");
        } catch (e) {
            this.actionService = null;
        }

        // Read sound preference from localStorage so it survives reloads.
        const muted = (() => {
            try { return localStorage.getItem("ai_agent_chat_muted") === "1"; }
            catch (e) { return false; }
        })();

        this.state = useState({
            input: this.props.initialMessage || "",
            messages: [],
            isThinking: false,
            muted,
        });

        this.streamRef = useRef("stream");
        this.textareaRef = useRef("textarea");
        this._audioCtx = null;

        // Auto-scroll on new messages.
        useEffect(
            () => {
                if (this.streamRef.el) {
                    this.streamRef.el.scrollTop = this.streamRef.el.scrollHeight;
                }
            },
            () => [this.state.messages.length, this.state.isThinking],
        );

        // Auto-pick the prop-specified agent on mount.
        onMounted(async () => {
            if (this.props.agentCode) {
                const found = this.aiAgent.state.agents.find((a) => a.code === this.props.agentCode);
                if (found) {
                    this.aiAgent.setActiveAgent(found);
                }
            }
            // Chatter / record-anchored surface: load any prior
            // conversation history before painting the welcome.
            if (this.props.recordModel && this.props.recordId) {
                const loaded = await this._loadRecordHistory();
                if (!loaded) {
                    this._addAssistantWelcome();
                }
            } else {
                this._addAssistantWelcome();
            }
            // Auto-send the initial prompt if the parent passed one.
            if (this.props.initialMessage) {
                await this._send(this.props.initialMessage);
            }
        });
    }

    async _loadRecordHistory() {
        try {
            const res = await this.aiAgent.lookupRecordConversation({
                recordModel: this.props.recordModel,
                recordId: this.props.recordId,
                agentCode: this.props.agentCode,
            });
            if (res?.success && res.messages?.length) {
                const agent = this.activeAgent;
                this._loadedConversationId = res.conversation_id;
                for (const m of res.messages) {
                    this.state.messages.push({
                        role: m.role || "assistant",
                        id: `h-${m.id}`,
                        text: m.text,
                        agentName: agent?.name || "Ghaima Assistant",
                        agentAccent: agent?.accent || "blue",
                        isHistorical: true,
                    });
                }
                return true;
            }
        } catch (e) {
            // Best-effort — fall back to welcome on any error.
        }
        return false;
    }

    // ── Derived state ─────────────────────────────────────────

    get activeAgent() {
        return this.aiAgent.state.activeAgent;
    }

    get visibleAgents() {
        return this.aiAgent.state.agents;
    }

    get skills() {
        const agent = this.activeAgent;
        if (!agent || !agent.skill_count) return [];
        return agent.skills || [];          // populated by /ai_agent/list later
    }

    get headerTitle() {
        return this.props.title || (this.activeAgent?.name ?? "Ghaima Assistant");
    }

    get headerSubtitle() {
        if (this.props.recordModel && this.props.recordName) {
            return `${this.props.recordName} · ${this.props.recordModel}`;
        }
        return this.activeAgent?.description || "Ask anything about your business";
    }

    get placeholderText() {
        if ((this.props.locale || "").startsWith("ar")) {
            return "اسأل عن أي شيء…";
        }
        return "Ask me anything…";
    }

    // ── Event handlers ────────────────────────────────────────

    onAgentPick(agent) {
        this.aiAgent.setActiveAgent(agent);
        // Reset to welcome on persona switch — keep history isolation per agent.
        this.state.messages = [];
        this._addAssistantWelcome();
    }

    onSkillPick(skill) {
        // Skills with required record context need a record present.
        if (skill.requires_record_context && !this.props.recordModel) {
            this.notification.add(
                "This skill needs a record. Open it from a form chatter.",
                { type: "warning" },
            );
            return;
        }
        this._send(this.state.input.trim() || skill.name, { skill });
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    send() {
        const msg = (this.state.input || "").trim();
        if (!msg) return;
        this._send(msg);
    }

    async rate(message, feedback) {
        message.feedback = feedback;
        if (message.runId) {
            this.aiAgent.rateRun(message.runId, feedback);
        }
    }

    close() {
        this.props.onClose?.();
    }

    toggleMute() {
        this.state.muted = !this.state.muted;
        try { localStorage.setItem("ai_agent_chat_muted", this.state.muted ? "1" : "0"); }
        catch (e) {}
    }

    /**
     * 6 example prompts shown on the empty state. Click → auto-send.
     * Localised; chatter surface gets record-aware variants.
     */
    get examplePrompts() {
        const isArabic = (this.props.locale || "").startsWith("ar");
        if (this.props.recordModel) {
            return isArabic ? [
                { icon: "fa-compress", text: "لخّص هذا السجل" },
                { icon: "fa-list", text: "ما الإجراءات المعلقة؟" },
                { icon: "fa-history", text: "اعرض آخر التعديلات" },
                { icon: "fa-lightbulb-o", text: "ما الذي يجب أن أفعله الآن؟" },
            ] : [
                { icon: "fa-compress", text: "Summarise this record" },
                { icon: "fa-list", text: "What activities are pending?" },
                { icon: "fa-history", text: "Show me recent changes" },
                { icon: "fa-lightbulb-o", text: "What should I do next?" },
            ];
        }
        return isArabic ? [
            { icon: "fa-bar-chart", text: "ما إجمالي مبيعات اليوم؟" },
            { icon: "fa-users", text: "أفضل 5 عملاء هذا الشهر" },
            { icon: "fa-money", text: "وضع النقدية الحالي" },
            { icon: "fa-exclamation-triangle", text: "اعرض الفواتير المتأخرة" },
            { icon: "fa-line-chart", text: "تقرير الربح والخسارة لهذا الشهر" },
            { icon: "fa-shopping-cart", text: "حالة نقاط البيع الآن" },
        ] : [
            { icon: "fa-bar-chart", text: "What are total sales today?" },
            { icon: "fa-users", text: "Top 5 customers this month" },
            { icon: "fa-money", text: "What's my cash position?" },
            { icon: "fa-exclamation-triangle", text: "Show overdue invoices" },
            { icon: "fa-line-chart", text: "P&L report for this month" },
            { icon: "fa-shopping-cart", text: "Status of POS sessions now" },
        ];
    }

    onExamplePick(prompt) {
        this._send(prompt.text);
    }

    /** Quick navigation actions emitted by the runtime via env action. */
    async runEnvelopeAction(action) {
        if (!action || !this.actionService) return;
        try {
            await this.actionService.doAction(action);
        } catch (e) {
            this.notification.add(e.message || "Action failed", { type: "warning" });
        }
    }

    // ── Internals ─────────────────────────────────────────────

    _addAssistantWelcome() {
        const agent = this.activeAgent;
        const greeting = (this.props.locale || "").startsWith("ar")
            ? "أهلاً! بماذا أساعدك اليوم؟"
            : `Hi! How can I help you today?`;
        this.state.messages.push({
            role: "assistant",
            id: `welcome-${Date.now()}`,
            text: greeting,
            agentName: agent?.name || "Ghaima Assistant",
            agentAccent: agent?.accent || "blue",
            isWelcome: true,
        });
    }

    _playDoneSound() {
        if (this.state.muted) return;
        try {
            const ctx = this._audioCtx
                || (this._audioCtx = new (window.AudioContext || window.webkitAudioContext)());
            const now = ctx.currentTime;
            // Two-tone soft "ding" — A5 then E6, very short, low volume.
            const tones = [{ f: 880, t: 0 }, { f: 1318.5, t: 0.08 }];
            for (const tone of tones) {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.value = tone.f;
                gain.gain.setValueAtTime(0.0001, now + tone.t);
                gain.gain.exponentialRampToValueAtTime(0.07, now + tone.t + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, now + tone.t + 0.22);
                osc.connect(gain).connect(ctx.destination);
                osc.start(now + tone.t);
                osc.stop(now + tone.t + 0.24);
            }
        } catch (e) {
            // AudioContext can fail before any user gesture — silent skip.
        }
    }

    async _send(text, { skill } = {}) {
        const userMsg = {
            role: "user",
            id: `u-${Date.now()}`,
            text,
        };
        this.state.messages.push(userMsg);
        this.state.input = "";
        this.state.isThinking = true;

        try {
            const envelope = await this.aiAgent.runAgent({
                message: text,
                skill,
                surface: this.props.surface,
                record: this.props.recordModel ? {
                    model: this.props.recordModel, id: this.props.recordId,
                } : null,
                locale: this.props.locale,
                conversationId: this.props.conversationId,
            });
            const agent = this.activeAgent;
            this.state.messages.push({
                role: "assistant",
                id: `a-${envelope.run_id || Date.now()}`,
                text: envelope.response || "",
                runId: envelope.run_id,
                agentName: agent?.name || "Ghaima Assistant",
                agentAccent: agent?.accent || "blue",
                toolCalls: envelope.tool_calls || [],
                provenance: envelope.provenance || {},
                // Lifted render block — when the LLM emitted a data_table
                // / kpi_grid / callout report, paint it via <AiResponse/>.
                render: envelope.render || null,
                envelope,
                feedback: null,
            });
            this._playDoneSound();
            // If the envelope carries a navigation action (open_menu,
            // doAction descriptor), surface it as a chip on the bubble.
            if (envelope.action) {
                // stored on the message for click-through; rendered as
                // an action button by the template
                this.state.messages[this.state.messages.length - 1].pendingAction = envelope.action;
            }
        } catch (e) {
            this.state.messages.push({
                role: "assistant",
                id: `err-${Date.now()}`,
                text: `Something went wrong: ${e.message || e}`,
                agentName: this.activeAgent?.name || "Ghaima Assistant",
                agentAccent: "rose",
                isError: true,
            });
        } finally {
            this.state.isThinking = false;
            // Refocus the input for the next turn.
            setTimeout(() => this.textareaRef.el?.focus(), 50);
        }
    }
}

// Client-action shim — agents.list "Open Chat" button + /odoo/action
// links use the agent_chat client action. Wraps the component so a
// standalone full-page surface works without a parent.
class AiAgentChatClientAction extends Component {
    static template = "ab_ai_agent.AiAgentChatPage";
    static components = { AiAgentChat };
    setup() {
        this.params = this.props.action?.params || {};
    }
}
registry.category("actions").add("ab_ai_agent.open_chat", AiAgentChatClientAction);
