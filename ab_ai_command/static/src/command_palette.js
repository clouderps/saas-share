/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { AiAgentChat } from "@ab_ai_agent/components/ai_agent_chat/ai_agent_chat";

/**
 * Slash commands in the Ask AI composer.
 *
 * Two behaviours, both additive — with this module absent the composer
 * is exactly what it was:
 *
 *  1. Typing "/" at the start opens a palette of the commands THIS user
 *     may run. The list comes from the server, so it can never offer a
 *     door that is locked.
 *
 *  2. Submitting a recognised command runs it directly instead of
 *     asking the model. The user named the command and the fields, so
 *     there is nothing to infer — a round trip would only add latency,
 *     cost, and a chance to mis-read what was typed literally. Anything
 *     the parser cannot fill still goes to the agent.
 */
patch(AiAgentChat.prototype, {
    setup() {
        super.setup();
        this.state.commands = [];        // palette contents, loaded once
        // Dismissal, not visibility. Visibility is derived from the
        // input, because t-model updates state AFTER keydown fires —
        // setting a flag there always read the previous keystroke and
        // the palette never opened on the first "/".
        this.state.paletteDismissed = false;
        this.state.paletteIndex = 0;
        this._loadCommands();
    },

    async _loadCommands() {
        try {
            const res = await rpc("/ai_agent/commands", {});
            this.state.commands = (res && res.commands) || [];
        } catch (e) {
            this.state.commands = [];    // no palette is fine; typing still works
        }
    },

    /** Commands matching what has been typed after the slash. */
    get filteredCommands() {
        const raw = (this.state.input || "").trim();
        if (!raw.startsWith("/")) {
            return [];
        }
        const needle = raw.slice(1).toLowerCase();
        return this.state.commands.filter(
            (c) => !needle || c.verb.toLowerCase().startsWith(needle)
                || c.name.toLowerCase().includes(needle)
        );
    },

    get paletteVisible() {
        return !this.state.paletteDismissed
            && (this.state.input || "").trim().startsWith("/")
            && this.filteredCommands.length > 0;
    },

    onInputKeydown(ev) {
        const open = this.paletteVisible;
        if (open && ["ArrowDown", "ArrowUp", "Tab"].includes(ev.key)) {
            ev.preventDefault();
            const n = this.filteredCommands.length;
            const step = ev.key === "ArrowUp" ? -1 : 1;
            this.state.paletteIndex = (this.state.paletteIndex + step + n) % n;
            return;
        }
        if (open && ev.key === "Enter" && !ev.shiftKey) {
            // Enter picks the highlighted command rather than sending a
            // half-typed verb to the model.
            ev.preventDefault();
            this.pickCommand(this.filteredCommands[this.state.paletteIndex]);
            return;
        }
        if (ev.key === "Escape" && open) {
            ev.preventDefault();
            this.state.paletteDismissed = true;
            return;
        }
        // Any other key re-opens: dismissing is for the current attempt,
        // not for the session.
        this.state.paletteDismissed = false;
        this.state.paletteIndex = 0;
        return super.onInputKeydown(ev);
    },

    pickCommand(command) {
        if (!command) {
            return;
        }
        // Trailing space so the user types straight into the arguments.
        this.state.input = `/${command.verb} `;
        this.state.paletteDismissed = true;
        if (this.textareaRef.el) {
            this.textareaRef.el.focus();
        }
    },

    /** Placeholder text of the command being typed, as a hint. */
    get commandHint() {
        const raw = (this.state.input || "").trim();
        if (!raw.startsWith("/")) {
            return "";
        }
        const match = this.state.commands.find(
            (c) => raw.slice(1).toLowerCase().startsWith(c.verb.toLowerCase()));
        return match ? match.example || "" : "";
    },

    async send(ev) {
        if (ev && ev.preventDefault) {
            ev.preventDefault();
        }
        const text = (this.state.input || "").trim();
        this.state.paletteDismissed = true;

        // Only intercept when the text actually names a command this
        // user has. Anything else — including a slash the palette does
        // not recognise — falls through to the agent, which can explain
        // what went wrong far better than a parse error.
        const known = text.startsWith("/") && this.state.commands.some(
            (c) => text.slice(1).toLowerCase().startsWith(c.verb.toLowerCase()));
        if (!known) {
            return super.send(ev);
        }

        this.state.input = "";
        this.state.messages.push({
            role: "user",
            id: `u-${Date.now()}`,
            text,
            at: new Date().toLocaleTimeString(this.isRtl ? "ar-SA" : undefined,
                                              { hour: "2-digit", minute: "2-digit" }),
        });
        this.state.isThinking = true;
        this.state.thinkingLabel = _t("Preparing the draft…");
        try {
            const res = await rpc("/ai_agent/command/run", { text });
            this._paintCommandResult(res);
        } catch (e) {
            this._paintCommandError(e);
        } finally {
            this.state.isThinking = false;
        }
    },

    /** Re-run after the user agreed to create the missing records. */
    async confirmCreateMissing(msg) {
        const echo = msg.commandEcho;
        if (!echo) {
            return;
        }
        this.state.isThinking = true;
        this.state.thinkingLabel = _t("Creating…");
        try {
            const res = await rpc("/ai_agent/command/run", {
                command: echo.command,
                fields: echo.fields,
                create_missing: msg.creatable || [],
            });
            this._paintCommandResult(res);
        } catch (e) {
            this._paintCommandError(e);
        } finally {
            this.state.isThinking = false;
        }
    },

    _paintCommandError(e) {
        this.state.messages.push({
            role: "assistant",
            id: `cerr-${Date.now()}`,
            text: (e && e.message && e.message.data && e.message.data.message)
                || _t("The command could not be run."),
            collapsed: false,
            showTrace: false,
        });
    },

    _paintCommandResult(res) {
        const result = (res && res.result) || {};
        const msg = {
            role: "assistant",
            id: `cmd-${Date.now()}`,
            text: "",
            collapsed: false,
            showTrace: false,
            commandResult: result,
            commandEcho: result._echo,
            creatable: result.creatable || [],
        };

        if (!res || res.success === false) {
            msg.text = _t("That is not a command you can run.");
        } else if (result.status === "blocked" || result.status === "error") {
            msg.text = result.message || _t("The command could not be run.");
        } else if (result.status === "needs_input") {
            msg.text = _t("I need one more thing before I can draft this.");
        } else if (result.status === "created") {
            msg.text = _t("Draft created — nothing is confirmed yet.");
        }
        this.state.messages.push(msg);
    },

    /** The user picked one of the options we offered. */
    async answerCommandQuestion(msg, question, option) {
        const echo = msg.commandEcho;
        if (!echo) {
            return;
        }
        // Re-submit with the chosen record's id in place of the text
        // that was ambiguous. Everything else is echoed back verbatim so
        // the user never retypes what they already said.
        const fields = Object.assign({}, echo.fields);
        fields[question.field] = String(option.id);
        this.state.isThinking = true;
        this.state.thinkingLabel = _t("Preparing the draft…");
        try {
            const res = await rpc("/ai_agent/command/run", {
                command: echo.command, fields,
            });
            this._paintCommandResult(res);
        } catch (e) {
            this._paintCommandError(e);
        } finally {
            this.state.isThinking = false;
        }
    },

    cancelCommand(msg) {
        msg.commandResult = { status: "cancelled" };
        msg.creatable = [];
        msg.text = _t("Cancelled. Nothing was created.");
    },

    get labels() {
        return Object.assign(super.labels, {
            commands: _t("Commands"),
            draftOnly: _t("Draft — nothing is confirmed"),
            item: _t("Item"),
            qty: _t("Qty"),
            subtotal: _t("Subtotal"),
            total: _t("Total"),
            createAndContinue: _t("Create and continue"),
            cancel: _t("Cancel"),
        });
    },

    /** Card title for a command result. */
    answerTitle(msg) {
        if (msg.commandResult) {
            const status = msg.commandResult.status;
            if (status === "created") {
                return msg.commandResult.preview?.name || _t("Draft");
            }
            if (status === "needs_input") {
                return _t("Almost there");
            }
            return _t("Command");
        }
        return super.answerTitle(msg);
    },
});
