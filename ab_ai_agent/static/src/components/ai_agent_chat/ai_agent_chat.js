/** @odoo-module **/

import { Component, useState, useRef, onMounted, onPatched, onWillUnmount, onWillUpdateProps, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { pickStt, pickTts, speakableText, spokenDecision, voiceErrorMessage } from "../../voice/voice";
import { AiAgentChip } from "../ai_agent_chip/ai_agent_chip";
import { AiAgentSkillCard } from "../ai_agent_skill_card/ai_agent_skill_card";
import { AiAgentTokenMeter } from "../ai_agent_token_meter/ai_agent_token_meter";
import { AiAgentRunTrace } from "../ai_agent_run_trace/ai_agent_run_trace";
// The one block renderer every AI surface shares. This template used
// to re-implement data_table / kpi_grid / callout inline, so chart
// blocks rendered as nothing here while working everywhere else.
import { AiResponse } from "@ab_ai_ui/ai_response/ai_response";

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
        AiResponse,
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
        // Conversation to open with. A real ai.chat.conversation id once
        // the chatbot module is installed (the bubble's expand button
        // passes the chat it was showing); still accepts the old free
        // string used as a loose cache-grouping key.
        conversationId: { type: [String, Number], optional: true },
        // Mute the sidebar — used in narrow surfaces
        hideSidebar: { type: Boolean, optional: true },
        // Locale override (default = user.lang)
        locale: { type: String, optional: true },
        // Send what the user is looking at with every question. On for
        // the floating assistant; off for the full-page console, whose
        // "current screen" is the chat itself.
        screenAware: { type: Boolean, optional: true },
        // Floating panel: "open in the full console" button.
        onExpand: { type: Function, optional: true },
        // Floating panel: false while hidden, so the screen card is only
        // refreshed when someone can see it.
        visible: { type: Boolean, optional: true },
        onClose: { type: Function, optional: true },
        title: { type: String, optional: true },
        // Manager-only: enables Web Speech API mic input + voice
        // playback of assistant replies. Off by default — passed in
        // via the Manager Console client action params.
        enableVoice: { type: Boolean, optional: true },
    };
    static defaultProps = {
        surface: "chat",
        hideSidebar: false,
        enableVoice: false,
    };

    setup() {
        this.aiAgent = useService("aiAgentService");
        this.screenContext = this.props.screenAware ? useService("aiScreenContext") : null;
        this.radialRef = useRef("radial");
        this.headerRadialRef = useRef("headerRadial");
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
            thinkingLabel: "",
            muted,
            // Openers derived from this user's real menu access — see
            // _loadStarters. Empty until that resolves; the template
            // simply renders no chips in the meantime.
            starters: [],
            groups: [],
            // Shared history. The console used to forget everything the
            // moment it closed, while the bubble beside it remembered —
            // same user, same assistant, two different memories. These
            // stay empty (and the history button hidden) when the
            // chatbot module is not installed.
            conversationId: 0,
            conversations: [],
            showHistory: false,
            historyAvailable: false,
            shareUrl: "",
            // Live progress from the server while a run is in flight —
            // which step, which tool. A spinner that says nothing for
            // eight seconds reads as a hang.
            streamSteps: [],
            // Voice (manager-only, gated by props.enableVoice)
            recording: false,
            speechAvailable: false,          // set below from the adapters
            transcribing: false,             // server STT round-trip
            speakingId: null,                // message being read aloud
        });

        this.streamRef = useRef("stream");
        this.textareaRef = useRef("textarea");
        this._audioCtx = null;
        // Voice is an interface to this same chat: the adapters turn
        // speech into the text that _send() already handles, and an
        // answer's text into audio. Company setting + user preference
        // come from session_info (no RPC).
        this.voiceConfig = session.ai_assistant || {};
        this.voiceOn = !!(this.props.enableVoice || this.voiceConfig.voice);
        this.stt = this.voiceOn ? pickStt(this.voiceConfig.stt) : null;
        this.tts = this.voiceOn ? pickTts(this.voiceConfig.tts) : null;
        this.state.speechAvailable = !!this.stt;
        onWillUnmount(() => {
            this.stt?.cancel();
            this.tts?.stop();
        });

        // The screen card: what this page is, live numbers, and one-tap
        // questions — shown the moment the assistant opens, no question
        // needed. Same (cached) request as the button's tip.
        this.state.screenCard = null;
        this.state.screenCardDismissed = false;
        this.state.radialOpen = false;
        this.state.radialHover = "";
        this.state.headerRadialOpen = false;
        this.state.headerRadialHover = "";
        if (this.screenContext) {
            const refresh = () => this._refreshScreenCard();
            this.screenContext.bus.addEventListener("change", refresh);
            onWillUnmount(() => this.screenContext.bus.removeEventListener("change", refresh));
            onMounted(refresh);
            onWillUpdateProps((next) => {
                if (next.visible && !this.props.visible) {
                    this._refreshScreenCard(next);
                }
            });
        }
        const closeRadial = (ev) => {
            if (this.state.radialOpen && !this.radialRef.el?.contains(ev.target)) {
                this.state.radialOpen = false;
            }
            if (this.state.headerRadialOpen && !this.headerRadialRef.el?.contains(ev.target)) {
                this.state.headerRadialOpen = false;
            }
        };
        document.addEventListener("pointerdown", closeRadial, true);
        onWillUnmount(() => document.removeEventListener("pointerdown", closeRadial, true));
        this._lastSpoken = null;        // throttle re-speak of same text

        // What the assistant is doing, for the robot on the floating
        // button (eyes, mouth): listening / thinking / speaking / idle.
        useEffect(
            (recording, transcribing, thinking, speaking) => {
                const status = recording ? "listening"
                    : (transcribing || thinking) ? "thinking"
                    : speaking ? "speaking" : "idle";
                this.env.bus.trigger("GHAIMA_AI:STATUS", { status });
            },
            () => [this.state.recording, this.state.transcribing,
                   this.state.isThinking, this.state.speakingId],
        );

        // Auto-scroll on new messages. The element that scrolls is the
        // body around the stream (the stream itself never overflows, so
        // setting its scrollTop did nothing and new answers appeared below
        // the fold). A new answer is shown from its question down, so the
        // user reads it from the start rather than from its last line.
        useEffect(
            () => {
                const stream = this.streamRef.el;
                const box = stream?.closest(".o_ai_agent_chat__body") || stream;
                if (!box) {
                    return;
                }
                const last = this.state.messages[this.state.messages.length - 1];
                const questions = stream.querySelectorAll(".o_ai_answer_q");
                const q = questions[questions.length - 1];
                if (last?.role === "assistant" && !this.state.isThinking && q) {
                    box.scrollTop += q.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;
                } else {
                    box.scrollTop = box.scrollHeight;
                }
            },
            () => [this.state.messages.length, this.state.isThinking],
        );

        // Live progress while a run is in flight. Unsubscribed on
        // unmount so a closed chatter dialog stops repainting.
        this._stopStream = null;
        onWillUnmount(() => this._stopStream?.());

        // Auto-pick the prop-specified agent on mount.
        onMounted(async () => {
            if (this.aiAgent.onStream) {
                this._stopStream = this.aiAgent.onStream(
                    (p) => this._onStreamEvent(p));
            }
            this._loadStarters();       // fire-and-forget; never blocks paint
            // The agent list loads on first use, not at page boot.
            await this.aiAgent.ensureLoaded?.();
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
                // Standalone console: resume the user's last chat — the
                // same rows the bubble writes — so arriving by either
                // door lands in one continuous conversation.
                const resumed = await this._openConversation(
                    this.props.conversationId);
                if (!resumed) {
                    this._addAssistantWelcome();
                }
            }
            // Auto-send the initial prompt if the parent passed one.
            if (this.props.initialMessage) {
                await this._send(this.props.initialMessage);
            }
        });
    }

    /**
     * Opening suggestions, from the server, based on what this user can
     * actually open.
     *
     * This replaced a hardcoded list. The old chips offered every user
     * the same things — "P&L report for this month", "cash position" —
     * so a cashier was invited to open screens they have no access to
     * and every suggestion dead-ended. Failing quietly is correct here:
     * no chips is a smaller problem than wrong chips.
     */
    async _loadStarters() {
        try {
            const res = await this.aiAgent.fetchStarters({
                recordModel: this.props.recordModel,
            });
            if (res && res.starters) {
                this.state.starters = res.starters;
                this.state.groups = res.groups || [];
            }
        } catch (e) {
            this.state.starters = [];
            this.state.groups = [];
        }
    }

    /**
     * A chip inside an answer was clicked.
     *
     * <SuggestionChips/> bubbles `ai-chip-pick` and the host decides what
     * it means. Two shapes:
     *
     *   - `action` — a captured write the user is agreeing to. Replayed
     *     through the confirm endpoint, never back through the model:
     *     they approved a specific call, and re-asking could produce a
     *     different one.
     *   - `prompt` — a disambiguation ("did you mean last month?").
     *     Ordinary send.
     *
     * The console had no listener at all, so every clarification and
     * every confirmation chip was inert — the button moved and nothing
     * happened.
     */
    /**
     * Repaint the wait from what the server is actually doing.
     *
     * Events arrive only while a run is in flight. Anything that lands
     * when we are not thinking belongs to another tab on the same
     * session, so it is dropped rather than shown against nothing.
     */
    _onStreamEvent(payload) {
        if (!payload || !this.state.isThinking) {
            return;
        }
        const { kind, tool, hop } = payload;
        if (kind === "thinking") {
            this.state.thinkingLabel = hop > 1
                ? _t("Thinking… (step %s)", hop)
                : this.labels.working;
        } else if (kind === "tool_call" && tool) {
            this.state.thinkingLabel = _t("Looking up %s…", this.toolLabel(tool));
            // Keep the trail: which sources were consulted is the part
            // users ask about afterwards, and it is gone once the run
            // finishes unless it is recorded here.
            if (!this.state.streamSteps.includes(tool)) {
                this.state.streamSteps.push(tool);
            }
        } else if (kind === "done") {
            this.state.thinkingLabel = this.labels.working;
        }
    }

    /** Tool codes are snake_case internals; users read words. */
    toolLabel(code) {
        return String(code || "").replace(/_/g, " ");
    }

    async onChipPick(ev) {
        const detail = ev?.detail || {};
        if (detail.action?.type) {
            await this._confirmAction(detail.action, detail.label);
            return;
        }
        if (detail.prompt) {
            await this._send(detail.prompt);
        }
    }

    async _confirmAction(action, label) {
        if (this.state.isThinking) {
            return;
        }
        const native = ["confirm_pending", "cancel_pending"].includes(action?.type);
        if (!native && !this.state.conversationId) {
            // Nothing to replay against — the capture lives on the
            // conversation. Say so rather than failing silently.
            this._pushPlain(this.labels.confirmUnavailable);
            return;
        }
        // Echo the user's decision so the transcript reads as a dialogue.
        this.state.messages.push({
            role: "user",
            id: `c-${Date.now()}`,
            text: label || this.labels.confirmed,
        });
        this.state.isThinking = true;
        this.state.thinkingLabel = this.labels.applying;
        try {
            const res = await this.aiAgent.confirmAction({
                conversationId: this.state.conversationId,
                action,
            });
            this._pushPlain(res?.success
                ? (res.result?.content || this.labels.done)
                : (res?.error || this.labels.confirmFailed));
            if (res?.success && res.result?.action) {
                // Land on the record that just changed, as the Open chip would.
                this.state.messages[this.state.messages.length - 1].pendingAction = res.result.action;
            }
        } catch (e) {
            this._pushPlain(this.labels.confirmFailed);
        } finally {
            this.state.isThinking = false;
        }
    }

    _pushPlain(text) {
        const agent = this.activeAgent;
        this.state.messages.push({
            role: "assistant",
            id: `p-${Date.now()}`,
            text,
            agentName: agent?.name || "Ghaima Assistant",
            agentAccent: agent?.accent || "blue",
            collapsed: false,
            showTrace: false,
        });
    }

    /**
     * Resume the shared conversation. Returns true when prior turns
     * were painted, so the caller knows whether a welcome is still due.
     */
    async _openConversation(conversationId) {
        const res = await this.aiAgent.openConversation({
            conversationId,
            agentCode: this.props.agentCode,
        });
        if (!res?.available) {
            return false;               // no chatbot module — stay stateless
        }
        this.state.historyAvailable = true;
        this.state.conversationId = res.conversation_id || 0;
        this._refreshConversations();   // fire-and-forget; the list is not
                                        // needed to paint the transcript
        return this._paintMessages(res.messages);
    }

    /** Repaint the stream from stored turns. */
    _paintMessages(messages) {
        this.state.messages = [];
        if (!messages?.length) {
            return false;
        }
        const agent = this.activeAgent;
        for (const m of messages) {
            this.state.messages.push({
                role: m.role === "user" ? "user" : "assistant",
                id: `h-${m.id}`,
                text: m.text,
                // envelope_json is why reopening is worth doing: without
                // it a stored chart degrades to the sentence beside it.
                envelope: m.envelope || null,
                feedback: m.rating > 0 ? "up" : (m.rating < 0 ? "down" : null),
                agentName: agent?.name || "Ghaima Assistant",
                agentAccent: agent?.accent || "blue",
                isHistorical: true,
            });
        }
        return true;
    }

    async _refreshConversations() {
        const res = await this.aiAgent.listConversations();
        this.state.conversations = res?.conversations || [];
        this.state.historyAvailable = !!res?.available;
    }

    /**
     * Publish this chat to a link, and copy it.
     *
     * Copying is the whole point — a link the user then has to hunt for
     * and select by hand is barely a share. Clipboard access can be
     * refused (insecure origin, permission), so the URL is shown either
     * way rather than assuming the copy worked.
     */
    async shareConversation() {
        if (!this.state.conversationId) {
            return;
        }
        const res = await this.aiAgent.shareConversation({
            conversationId: this.state.conversationId,
        });
        if (!res?.success) {
            this.notification.add(res?.error || this.labels.shareFailed,
                                  { type: "danger" });
            return;
        }
        this.state.shareUrl = res.share_url || "";
        let copied = false;
        try {
            await navigator.clipboard.writeText(this.state.shareUrl);
            copied = true;
        } catch (e) {
            copied = false;
        }
        this.notification.add(
            copied ? this.labels.shareCopied : this.state.shareUrl,
            { type: "success", sticky: !copied });
    }

    async unshareConversation() {
        if (!this.state.conversationId) {
            return;
        }
        await this.aiAgent.shareConversation({
            conversationId: this.state.conversationId, revoke: true,
        });
        this.state.shareUrl = "";
        this.notification.add(this.labels.shareRevoked, { type: "info" });
    }

    toggleHistory() {
        this.state.showHistory = !this.state.showHistory;
        if (this.state.showHistory) {
            this._refreshConversations();
        }
    }

    async selectConversation(id) {
        if (!id || id === this.state.conversationId) {
            this.state.showHistory = false;
            return;
        }
        const res = await this.aiAgent.loadConversation(id);
        if (res?.success) {
            this.state.conversationId = id;
            if (!this._paintMessages(res.messages)) {
                this._addAssistantWelcome();
            }
        }
        this.state.showHistory = false;
    }

    async startNewConversation() {
        const res = await this.aiAgent.newConversation(this.props.agentCode);
        this.state.conversationId = res?.conversation_id || 0;
        this.state.messages = [];
        this.state.showHistory = false;
        this._addAssistantWelcome();
        this._refreshConversations();
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
        return this.activeAgent?.description || _t("Ask anything about your business");
    }

    get placeholderText() {
        return _t("Ask me anything\u2026");
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
        // If we just muted while a response is being read aloud, cut it.
        if (this.state.muted) {
            this.tts?.stop();
            this.state.speakingId = null;
        }
    }

    // ── Voice in (SpeechRecognition) ──────────────────────────

    /**
     * The conversation language. Falls back to the user's own language:
     * the console never passed a locale, so an Arabic user's mic
     * listened for English and their answers came back in English.
     */
    get locale() {
        return this.props.locale || user.lang || document.documentElement.lang || "en";
    }

    get speechLang() {
        return this.locale.startsWith("ar") ? "ar-SA" : "en-US";
    }

    // ── Screen card ──────────────────────────────────────────

    async _refreshScreenCard(props = this.props) {
        if (!this.screenContext || props.visible === false) {
            return;
        }
        const res = await this.screenContext.insight();
        this.state.screenCard = res && (res.title || (res.lines || []).length) ? res : null;
        this.state.screenCardDismissed = false;
    }

    askSuggestion(question) {
        this.state.radialOpen = false;
        this._send(question);
    }

    // ── One button, a circle of actions ──────────────────────
    //
    // Everything the composer can do besides typing sits behind one
    // button. Modules add items by patching composerActions (attach and
    // camera scan: ab_ai_chatbot; slash commands: ab_ai_command).

    get composerActions() {
        const items = [];
        if (this.state.speechAvailable) {
            items.push({
                id: "voice", icon: "fa-microphone", label: this.labels.startRecording,
                run: () => this.toggleRecording(),
            });
        }
        if (this.screenContext) {
            items.push({
                id: "explain", icon: "fa-lightbulb-o", label: this.labels.explainScreen,
                run: () => this._send(this.labels.explainScreen),
            });
        }
        return items;
    }

    /** Compact header: everything but the name and close sits behind
     *  one button — the same circle as the composer, opening downward. */
    get headerCompact() {
        return this.props.hideSidebar && this.props.surface !== "chatter";
    }

    get headerActions() {
        const items = [];
        if (this.state.historyAvailable) {
            items.push({ id: "history", icon: "fa-history", label: this.labels.history,
                         run: () => this.toggleHistory() });
            items.push({ id: "new", icon: "fa-plus", label: this.labels.newChat,
                         run: () => this.startNewConversation() });
            if (this.state.conversationId) {
                items.push(this.state.shareUrl
                    ? { id: "unshare", icon: "fa-chain-broken", label: this.labels.unshare,
                        run: () => this.unshareConversation() }
                    : { id: "share", icon: "fa-share-alt", label: this.labels.share,
                        run: () => this.shareConversation() });
            }
        }
        items.push({ id: "mute", icon: this.state.muted ? "fa-volume-off" : "fa-volume-up",
                     label: this.state.muted ? this.muteLabels.off : this.muteLabels.on,
                     run: () => this.toggleMute() });
        if (this.props.onExpand) {
            items.push({ id: "expand", icon: "fa-expand", label: this.labels.expand,
                         run: () => this.props.onExpand() });
        }
        return items;
    }

    toggleHeaderRadial() {
        this.state.headerRadialOpen = !this.state.headerRadialOpen;
        this.state.headerRadialHover = "";
    }

    pickHeaderAction(item) {
        this.state.headerRadialOpen = false;
        item.run();
    }

    onHeaderRadialKeydown(ev) {
        if (ev.key === "Escape" && this.state.headerRadialOpen) {
            ev.stopPropagation();
            this.state.headerRadialOpen = false;
        }
    }

    toggleRadial() {
        if (this.state.recording) {
            // While listening the button IS the stop button.
            this.toggleRecording();
            return;
        }
        this.state.radialOpen = !this.state.radialOpen;
        this.state.radialHover = "";
    }

    pickComposerAction(item) {
        this.state.radialOpen = false;
        item.run();
    }

    onRadialKeydown(ev) {
        if (ev.key === "Escape" && this.state.radialOpen) {
            ev.stopPropagation();
            this.state.radialOpen = false;
        }
    }

    /**
     * Items evenly spaced on a ring (first one at the top, clockwise).
     * Logical offsets (inset-inline-start), so RTL mirrors by itself.
     */
    radialStyle(index, count) {
        const radius = 66;
        const angle = (-90 + (360 / Math.max(count, 1)) * index) * (Math.PI / 180);
        const x = Math.round(Math.cos(angle) * radius);
        const y = Math.round(Math.sin(angle) * radius);
        return `inset-inline-start: calc(50% + ${x}px - 22px); top: calc(50% + ${y}px - 22px);`
            + ` transition-delay: ${index * 25}ms;`;
    }

    get radialCenterLabel() {
        return this.state.radialHover || this.labels.whatDoYouNeed;
    }

    /** Push-to-talk: first press starts, second press stops and sends. */
    async toggleRecording() {
        if (!this.stt || this.state.transcribing) {
            return;
        }
        if (this.state.recording) {
            await this._finishRecording();
            return;
        }
        this.tts?.stop();
        try {
            await this.stt.start({
                lang: this.speechLang,
                onPartial: (t) => (this.state.input = t),
            });
        } catch (e) {
            this._voiceError(e);
            return;
        }
        this.state.input = "";
        this.state.recording = true;
        // Browser recognition ends by itself when the user pauses; send
        // then, as a second press would.
        this.stt.ended?.().then(() => this.state.recording && this._finishRecording());
    }

    async _finishRecording() {
        this.state.recording = false;
        this.state.transcribing = true;
        try {
            const { text } = await this.stt.stop();
            this._voiceTurn = true;          // answer this one out loud
            // A spoken yes / no to the proposal on screen decides it —
            // same endpoint and rules as the button (own proposal, 15 min).
            const proposal = this.voiceConfig.voice_confirm && this._openProposal();
            const decision = proposal && spokenDecision(text);
            if (decision) {
                this.state.input = "";
                await this._confirmAction(proposal[decision].action, text);
                const last = this.state.messages[this.state.messages.length - 1];
                this._speakResponse(last?.text || "", last?.id);
                return;
            }
            this.state.input = text;
            await this._send(text);
        } catch (e) {
            this._voiceError(e);
        } finally {
            this.state.transcribing = false;
        }
    }

    /** Confirm / Cancel chips of the latest answer, if it is a proposal. */
    _openProposal() {
        const last = [...this.state.messages].reverse().find((m) => m.role === "assistant");
        const blocks = last?.render?.blocks || last?.envelope?.render?.blocks || [];
        const chips = blocks.find((b) => b.type === "suggestion_chips");
        const items = chips?.items || [];
        const confirm = items.find((i) => i.action?.type === "confirm_pending");
        const cancel = items.find((i) => i.action?.type === "cancel_pending");
        return confirm && cancel ? { confirm, cancel } : null;
    }

    _voiceError(e) {
        if (e?.code === "aborted") {
            return;
        }
        this.notification.add(voiceErrorMessage(e?.code), { type: "warning" });
    }

    // ── Voice out (SpeechSynthesis) ───────────────────────────

    /**
     * Speak the answer when the question was spoken (a voice turn is
     * answered by voice), or always when the user opted in to autoplay.
     */
    _speakResponse(text, msgId) {
        const voiceTurn = this._voiceTurn;
        this._voiceTurn = false;
        if (!this.tts || this.state.muted || !text) return;
        if (voiceTurn || this.voiceConfig.autoplay) {
            if (voiceTurn && this.voiceConfig.voice_confirm && this._openProposal()) {
                text = `${text}\n${this.labels.sayYesNo}`;
            }
            const spoken = this.listen({ id: msgId, text });
            // Hands-free: after answering a spoken question, listen again.
            // Ends by itself when the user says nothing (empty transcript)
            // or presses stop / mute.
            if (voiceTurn && this.voiceConfig.conversation) {
                spoken.then(() => {
                    if (!this.state.muted && !this.state.recording && !this.state.isThinking) {
                        this.toggleRecording();
                    }
                });
            }
        }
    }

    /** "Listen" on an answer: the text stays; audio is an extra. */
    async listen(msg) {
        if (!this.tts) return;
        if (this.state.speakingId === msg.id) {
            this.tts.stop();
            this.state.speakingId = null;
            return;
        }
        const text = speakableText(msg.text || msg.envelope?.response || "");
        if (!text) return;
        this.state.speakingId = msg.id;
        try {
            await this.tts.speak(text, this.speechLang);
        } catch (e) {
            this._voiceError(e);
        } finally {
            if (this.state.speakingId === msg.id) {
                this.state.speakingId = null;
            }
        }
    }

    /** True when this surface renders right-to-left.
     *
     * Checks the COMPUTED direction as well as the attributes: Odoo
     * puts dir on <html> for an RTL language, but a theme or an
     * embedding page can set it elsewhere, and the computed value is
     * the only signal that is always right.
     */
    get isRtl() {
        const loc = this.locale;
        if (loc.startsWith("ar")) {
            return true;
        }
        if (document.documentElement.dir === "rtl" || document.body.dir === "rtl") {
            return true;
        }
        try {
            return getComputedStyle(document.body).direction === "rtl";
        } catch (e) {
            return false;
        }
    }

    /** Narrow surfaces (chatter side panel) get the dense block layout. */
    get isCompact() {
        return this.props.surface === "chatter" || this.props.hideSidebar;
    }

    /**
     * UI strings.
     *
     * These go through _t so they land in the module's .po catalogue
     * and follow the user's language like every other string in Odoo.
     * They were briefly a locale ternary in this file, which meant the
     * Arabic UI still rendered English chrome around Arabic answers.
     */
    get labels() {
        return {
            close: _t("Close"),
            sources: _t("Sources used"),
            collapse: _t("Collapse answer"),
            open: _t("Open"),
            refine: _t("Refine"),
            helpful: _t("Helpful"),
            unhelpful: _t("Not helpful"),
            working: _t("Working\u2026"),
            skills: _t("Quick skills"),
            tryAsking: _t("Try asking"),
            ask: _t("Ask"),
            listening: _t("Listening\u2026"),
            startRecording: _t("Tap to speak"),
            stopRecording: _t("Stop and send"),
            listen: _t("Listen"),
            stopListening: _t("Stop reading"),
            transcribing: _t("Transcribing…"),
            answer: _t("Answer"),
            welcome: _t("Start here"),
            history: _t("Past chats"),
            newChat: _t("New chat"),
            noHistory: _t("No earlier chats yet"),
            share: _t("Share this chat"),
            shareCopied: _t("Link copied — anyone with it can read this chat."),
            shareRevoked: _t("Link revoked. The chat is private again."),
            shareFailed: _t("The link could not be created."),
            unshare: _t("Revoke the link"),
            confirmed: _t("Confirmed"),
            applying: _t("Applying…"),
            done: _t("Done."),
            confirmFailed: _t("That action could not be completed."),
            sendFailed: _t("The assistant could not answer right now. Please try again."),
            expand: _t("Open in full screen"),
            explainScreen: _t("Explain this screen"),
            moreActions: _t("Voice, files and more"),
            nowOn: _t("You are on"),
            whatDoYouNeed: _t("What do you need?"),
            chatOptions: _t("Chat options"),
            sayYesNo: _t("Say yes to confirm, or no to cancel."),
            confirmUnavailable: _t("This chat has no saved history, so there is nothing to confirm against. Ask again and confirm from the new answer."),
        };
    }

    get muteLabels() {
        return {
            on: _t("Mute response sound"),
            off: _t("Unmute response sound"),
        };
    }

    /**
     * Card title. The runtime already names structured reports via
     * render.title — use it, because it describes what the answer IS
     * ("Sales · today") rather than restating the question.
     */
    answerTitle(msg) {
        if (msg.isWelcome) {
            return this.labels.welcome;
        }
        return (msg.render && msg.render.title)
            || (msg.envelope && msg.envelope.render && msg.envelope.render.title)
            || this.labels.answer;
    }

    toggleCollapse(msg) {
        msg.collapsed = !msg.collapsed;
    }

    toggleTrace(msg) {
        msg.showTrace = !msg.showTrace;
    }

    /** Put the original question back in the box to reword and re-ask. */
    refine(msg) {
        const idx = this.state.messages.indexOf(msg);
        for (let i = idx - 1; i >= 0; i--) {
            if (this.state.messages[i].role === "user") {
                this.state.input = this.state.messages[i].text;
                break;
            }
        }
        if (this.textareaRef.el) {
            this.textareaRef.el.focus();
        }
    }

    onExamplePick(prompt) {
        const text = (prompt && prompt.text) || "";
        if (text.trim().startsWith("/")) {
            // A command opener is the START of a command — put it in the
            // box for the user to finish, rather than sending a verb
            // with no arguments.
            this.state.input = text;
            if (this.textareaRef.el) {
                this.textareaRef.el.focus();
            }
            return;
        }
        this._send(text);
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
        const greeting = _t("Hi! How can I help you today?");
        this.state.messages.push({
            role: "assistant",
            id: `welcome-${Date.now()}`,
            text: greeting,
            agentName: agent?.name || "Ghaima Assistant",
            agentAccent: agent?.accent || "blue",
            isWelcome: true,
            collapsed: false,
            showTrace: false,
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
            // Shown at the end of the question line. Locale-formatted so
            // Arabic users get Arabic-Indic digits when their locale
            // asks for them.
            at: new Date().toLocaleTimeString(this.isRtl ? "ar-SA" : undefined,
                                              { hour: "2-digit", minute: "2-digit" }),
        };
        this.state.messages.push(userMsg);
        this.state.input = "";
        this.state.isThinking = true;
        this.state.thinkingLabel = this.labels.working;
        this.state.streamSteps = [];        // trail belongs to this turn

        try {
            const envelope = await this.aiAgent.runAgent({
                message: text,
                skill,
                surface: this.props.surface,
                record: this.props.recordModel ? {
                    model: this.props.recordModel, id: this.props.recordId,
                } : null,
                locale: this.locale.slice(0, 2),
                screen: this.screenContext?.snapshot(),
                // The live conversation wins over the prop: the prop is
                // only the id we were opened with, and the user may have
                // switched chats since.
                conversationId: this.state.conversationId
                    || this.props.conversationId,
                stream: true,
            });
            // First turn of a brand-new chat mints the row server-side.
            if (envelope.conversation_id) {
                if (envelope.conversation_id !== this.state.conversationId) {
                    this.state.conversationId = envelope.conversation_id;
                }
                this._refreshConversations();
            }
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
                // Card UI state — declared up-front so OWL's reactivity
                // tracks them; adding keys later would not re-render.
                collapsed: false,
                showTrace: false,
            });
            this._playDoneSound();
            // Voice playback for the Manager Console — reads the
            // rendered text (or report summary) aloud through the
            // browser's SpeechSynthesis. No-op when enableVoice=false
            // or the user has muted.
            this._speakResponse(envelope.response || "",
                                this.state.messages[this.state.messages.length - 1].id);
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
                // Never paint a raw RPC error (it can carry server internals).
                text: this.labels.sendFailed,
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
