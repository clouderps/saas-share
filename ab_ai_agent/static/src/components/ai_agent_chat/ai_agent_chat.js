/** @odoo-module **/

import { Component, useState, useRef, onMounted, onPatched, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
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
            // Voice (manager-only, gated by props.enableVoice)
            recording: false,
            speechAvailable: typeof window !== "undefined"
                && (window.SpeechRecognition || window.webkitSpeechRecognition),
        });

        this.streamRef = useRef("stream");
        this.textareaRef = useRef("textarea");
        this._audioCtx = null;
        this._recognition = null;       // SpeechRecognition instance, lazy
        this._lastSpoken = null;        // throttle re-speak of same text

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
            this._loadStarters();       // fire-and-forget; never blocks paint
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
        if (!this.state.conversationId) {
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
            try { window.speechSynthesis?.cancel(); } catch (e) {}
        }
    }

    // ── Voice in (SpeechRecognition) ──────────────────────────

    get speechLang() {
        return (this.props.locale || "en").startsWith("ar") ? "ar-SA" : "en-US";
    }

    toggleRecording() {
        if (!this.props.enableVoice) return;
        if (this.state.recording) {
            this._stopRecording();
        } else {
            this._startRecording();
        }
    }

    _startRecording() {
        const Recog = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Recog) {
            this.notification.add("Voice input not supported in this browser.",
                                  { type: "warning" });
            return;
        }
        try {
            const r = new Recog();
            r.lang = this.speechLang;
            r.continuous = false;
            r.interimResults = true;
            r.onresult = (ev) => {
                let transcript = "";
                for (let i = 0; i < ev.results.length; i++) {
                    transcript += ev.results[i][0].transcript;
                }
                this.state.input = transcript;
            };
            r.onend = () => {
                this.state.recording = false;
                this._recognition = null;
                // Auto-send when the user paused (non-empty result).
                const text = (this.state.input || "").trim();
                if (text) this._send(text);
            };
            r.onerror = (ev) => {
                this.state.recording = false;
                this._recognition = null;
                if (ev.error !== "no-speech" && ev.error !== "aborted") {
                    this.notification.add(`Voice error: ${ev.error}`,
                                          { type: "warning" });
                }
            };
            r.start();
            this._recognition = r;
            this.state.recording = true;
            this.state.input = "";
        } catch (e) {
            this.notification.add(e.message || "Voice start failed",
                                  { type: "warning" });
        }
    }

    _stopRecording() {
        try { this._recognition?.stop(); }
        catch (e) {}
    }

    // ── Voice out (SpeechSynthesis) ───────────────────────────

    _speakResponse(text) {
        if (!this.props.enableVoice || this.state.muted || !text) return;
        if (!window.speechSynthesis) return;
        // Throttle re-speak of identical text (welcomes, errors).
        if (text === this._lastSpoken) return;
        this._lastSpoken = text;
        // Cap length so we don't bombard the user with a 5-minute readout.
        const safe = text.slice(0, 600);
        try {
            const utter = new SpeechSynthesisUtterance(safe);
            utter.lang = this.speechLang;
            utter.rate = 1.05;
            utter.pitch = 1.0;
            utter.volume = 0.95;
            window.speechSynthesis.cancel();    // stop any prior utterance
            window.speechSynthesis.speak(utter);
        } catch (e) {
            // Voice synth can fail mid-load; silent.
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
        const loc = this.props.locale || document.documentElement.lang || "";
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
            stopRecording: _t("Stop recording"),
            answer: _t("Answer"),
            welcome: _t("Start here"),
            history: _t("Past chats"),
            newChat: _t("New chat"),
            noHistory: _t("No earlier chats yet"),
            confirmed: _t("Confirmed"),
            applying: _t("Applying…"),
            done: _t("Done."),
            confirmFailed: _t("That action could not be completed."),
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

        try {
            const envelope = await this.aiAgent.runAgent({
                message: text,
                skill,
                surface: this.props.surface,
                record: this.props.recordModel ? {
                    model: this.props.recordModel, id: this.props.recordId,
                } : null,
                locale: this.props.locale,
                // The live conversation wins over the prop: the prop is
                // only the id we were opened with, and the user may have
                // switched chats since.
                conversationId: this.state.conversationId
                    || this.props.conversationId,
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
            this._speakResponse(envelope.response || "");
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
