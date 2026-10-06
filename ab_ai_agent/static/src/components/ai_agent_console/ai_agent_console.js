/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { AiAgentChat } from "../ai_agent_chat/ai_agent_chat";
import { AiAgentTokenMeter } from "../ai_agent_token_meter/ai_agent_token_meter";
import { AiAgentBuilderDialog } from "./ai_agent_builder_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const PANEL_KEY = "ab_ai_agent.console.panels";

function readPanels() {
    try {
        return JSON.parse(localStorage.getItem(PANEL_KEY) || "null");
    } catch {
        return null;
    }
}

function writePanels(value) {
    try {
        localStorage.setItem(PANEL_KEY, JSON.stringify(value));
    } catch {
        // Private window / blocked storage: panels just reset next visit.
    }
}

/**
 * <AiAgentConsole/> — full-page agent workspace.
 *
 *   header   agent picker · live status · panel toggles · new chat
 *   start    configuration panel (prompt / tools / skills / scope)
 *   center   the ONE chat engine (<AiAgentChat/>), unchanged
 *   end      identity, behaviour, permissions, 30-day KPIs
 *   footer   token / cost meter
 *
 * The console only wraps the chat; it never forks it. The floating
 * assistant and the chatter dialog keep using <AiAgentChat/> directly.
 * Config is read/written through /ai_agent/console/* which run as the
 * caller (no sudo) — designers edit, everyone else reads.
 */
export class AiAgentConsole extends Component {
    static template = "ab_ai_agent.AiAgentConsole";
    static components = { AiAgentChat, AiAgentTokenMeter };
    static props = ["*"];

    setup() {
        this.aiAgent = useService("aiAgentService");
        this.notification = useService("notification");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.params = this.props.action?.params || {};
        this.service = useState(this.aiAgent.state);

        const narrow = window.innerWidth < 992;
        const saved = readPanels() || {};
        this.state = useState({
            agent: null,          // console payload of the selected agent
            loading: true,
            error: "",
            saving: false,
            tab: "prompt",
            showConfig: narrow ? false : saved.config !== false,
            showAgent: narrow ? false : saved.agent !== false,
            draft: {},            // pending edits, keyed by field
            status: "idle",
            chatKey: 1,
            conversationId: this.params.conversation_id || undefined,
            agentCode: this.params.agent_code || undefined,
        });

        this._onStatus = (ev) => {
            this.state.status = ev.detail?.status || "idle";
        };
        this.env.bus.addEventListener("GHAIMA_AI:STATUS", this._onStatus);
        onWillUnmount(() => this.env.bus.removeEventListener("GHAIMA_AI:STATUS", this._onStatus));

        // The chat keeps its own agent chip; follow it so the panels
        // always describe the agent that is actually answering.
        useEffect(
            (activeId) => {
                const current = this.state.agent?.id;
                if (activeId && current && activeId !== current && !this.dirty) {
                    const a = this.agents.find((x) => x.id === activeId);
                    if (a) {
                        this.state.agentCode = a.code;
                        this.loadConfig(a.id);
                    }
                }
            },
            () => [this.service.activeAgent?.id],
        );

        onWillStart(async () => {
            await this.aiAgent.ensureLoaded?.();
            const agents = this.service.agents || [];
            const wanted = agents.find((a) => a.id === this.params.agent_id)
                || agents.find((a) => a.code === this.state.agentCode)
                || this.service.activeAgent
                || agents.find((a) => a.is_default)
                || agents[0];
            if (wanted) {
                this.state.agentCode = wanted.code;
                await this.loadConfig(wanted.id);
                // First visit of a non-designer: chat first, panels on demand.
                if (!readPanels() && !this.canEdit) {
                    this.state.showConfig = false;
                    this.state.showAgent = false;
                }
            } else {
                this.state.loading = false;
            }
        });
    }

    // ── Data ─────────────────────────────────────────────────

    get agents() {
        return this.service.agents || [];
    }

    get labels() {
        return {
            status: {
                idle: _t("Ready"),
                thinking: _t("Thinking…"),
                listening: _t("Listening…"),
                speaking: _t("Speaking…"),
            },
        };
    }

    get tabs() {
        return [
            { id: "prompt", label: _t("System prompt"), icon: "fa-file-text-o" },
            { id: "tools", label: _t("Tools"), icon: "fa-wrench" },
            { id: "skills", label: _t("Skills"), icon: "fa-magic" },
            { id: "scope", label: _t("Scope"), icon: "fa-crosshairs" },
        ];
    }

    get permissionRows() {
        return [
            { field: "use_all_capabilities", label: _t("All capabilities"),
              help: _t("Every tool, skill and topic, including ones added later. Still limited to each user's own access rights.") },
            { field: "allow_pii", label: _t("Personal data"),
              help: _t("Skip PII redaction for this agent.") },
            { field: "allow_write_actions", label: _t("Write actions"),
              help: _t("May propose changes; each one still needs confirmation.") },
            { field: "allow_web_grounding", label: _t("Web grounding"),
              help: _t("May search the web.") },
            { field: "is_public", label: _t("Public website"),
              help: _t("Exposed on the public website widget.") },
        ];
    }

    async loadConfig(agentId) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const res = await rpc("/ai_agent/console/config", { agent_id: agentId });
            if (res?.success) {
                this.state.agent = res.agent;
                this.state.draft = {};
            } else {
                this.state.agent = null;
                this.state.error = res?.error === "forbidden"
                    ? _t("This agent is not available to you.")
                    : _t("The agent could not be loaded.");
            }
        } catch {
            this.state.error = _t("The agent could not be loaded.");
        } finally {
            this.state.loading = false;
        }
    }

    value(field) {
        return field in this.state.draft ? this.state.draft[field] : this.state.agent?.[field];
    }

    get canEdit() {
        return !!this.state.agent?.can_edit;
    }

    get dirty() {
        return Object.keys(this.state.draft).length > 0;
    }

    setDraft(field, value) {
        if (!this.canEdit) {
            return;
        }
        if (value === this.state.agent[field]) {
            delete this.state.draft[field];
        } else {
            this.state.draft[field] = value;
        }
    }

    onInput(field, ev) {
        this.setDraft(field, ev.target.value);
    }

    onNumber(field, ev) {
        const n = parseFloat(ev.target.value);
        this.setDraft(field, Number.isFinite(n) ? n : 0);
    }

    onToggle(field) {
        this.setDraft(field, !this.value(field));
    }

    get fullAccess() {
        return !!this.value("use_all_capabilities");
    }

    toolEnabled(tool) {
        if (this.fullAccess) {
            return tool.active !== false;
        }
        const ids = this.state.draft.tool_ids;
        return ids ? tool.via_topic || ids.includes(tool.id) : tool.enabled;
    }

    onToolToggle(tool) {
        if (!this.canEdit || tool.via_topic || this.fullAccess) {
            return;
        }
        const current = this.state.draft.tool_ids
            || this.state.agent.tools.filter((t) => t.enabled && !t.via_topic).map((t) => t.id);
        const next = current.includes(tool.id)
            ? current.filter((id) => id !== tool.id)
            : [...current, tool.id];
        this.state.draft.tool_ids = next;
    }

    get enabledToolCount() {
        return (this.state.agent?.tools || []).filter((t) => this.toolEnabled(t)).length;
    }

    // ── Builder ──────────────────────────────────────────────

    openBuilder(kind, item = undefined) {
        if (!this.canEdit) {
            return;
        }
        if (this.dirty && !window.confirm(_t("Discard unsaved changes to this agent?"))) {
            return;
        }
        this.dialog.add(AiAgentBuilderDialog, {
            kind,
            item,
            agentId: this.state.agent.id,
            tools: (this.state.agent.tools || []).map((t) => ({ id: t.id, name: t.name, code: t.code })),
            onSaved: () => this.loadConfig(this.state.agent.id),
        });
    }

    removeItem(kind, item) {
        if (!this.canEdit || !item.is_custom) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove"),
            body: _t("Remove \"%s\"? The assistant will stop using it.", item.name),
            confirmLabel: _t("Remove"),
            confirm: async () => {
                const res = await rpc("/ai_agent/console/builder/delete", { kind, id: item.id });
                if (res?.success) {
                    this.notification.add(_t("Removed."), { type: "success" });
                    await this.loadConfig(this.state.agent.id);
                } else {
                    this.notification.add(res?.message || _t("Something went wrong. Try again."),
                        { type: "danger" });
                }
            },
            cancel: () => {},
        });
    }

    discard() {
        this.state.draft = {};
    }

    async save() {
        if (!this.dirty || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const res = await rpc("/ai_agent/console/save", {
                agent_id: this.state.agent.id,
                values: { ...this.state.draft },
            });
            if (res?.success) {
                this.state.agent = res.agent;
                this.state.draft = {};
                this.notification.add(_t("Agent saved."), { type: "success" });
                // Name / persona may have changed → refresh the picker.
                this.aiAgent.refreshAgents?.();
            } else {
                this.notification.add(res?.message || _t("The agent could not be saved."),
                    { type: "danger" });
            }
        } catch {
            this.notification.add(_t("The agent could not be saved."), { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    // ── Header actions ───────────────────────────────────────

    async onAgentChange(ev) {
        const id = parseInt(ev.target.value, 10);
        const agent = this.agents.find((a) => a.id === id);
        if (!agent) {
            return;
        }
        if (this.dirty && !window.confirm(_t("Discard unsaved changes to this agent?"))) {
            ev.target.value = String(this.state.agent?.id || "");
            return;
        }
        this.aiAgent.setActiveAgent(agent);
        this.state.agentCode = agent.code;
        this.state.conversationId = undefined;
        this.state.chatKey++;
        await this.loadConfig(agent.id);
    }

    async newChat() {
        const res = await this.aiAgent.newConversation(this.state.agentCode);
        this.state.conversationId = res?.conversation_id || undefined;
        this.state.chatKey++;
    }

    togglePanel(which) {
        const key = which === "config" ? "showConfig" : "showAgent";
        this.state[key] = !this.state[key];
        // On narrow screens the panels overlay the chat: one at a time.
        if (window.innerWidth < 992 && this.state[key]) {
            this.state[key === "showConfig" ? "showAgent" : "showConfig"] = false;
        }
        writePanels({ config: this.state.showConfig, agent: this.state.showAgent });
    }

    closePanels() {
        this.state.showConfig = false;
        this.state.showAgent = false;
    }

    openForm() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "ai.agent",
            res_id: this.state.agent.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ── Formatting ───────────────────────────────────────────

    fmtUsd(v, digits = 4) {
        return `$${(v || 0).toFixed(digits)}`;
    }

    fmtInt(v) {
        return (v || 0).toLocaleString(localization.code?.replace("_", "-") || undefined);
    }

    get lastRun() {
        const v = this.state.agent?.kpis?.last_run_at;
        return v ? formatDateTime(deserializeDateTime(v)) : _t("Never");
    }

    get showCost() {
        return !!this.state.agent?.show_cost;
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    get scopeCompanies() {
        return this.state.agent?.scope.companies.join(", ") || _t("All companies");
    }

    get scopeGroups() {
        return this.state.agent?.scope.groups.join(", ") || _t("All internal users");
    }

    get initials() {
        const name = this.state.agent?.name || "";
        return name.trim().slice(0, 1).toUpperCase() || "AI";
    }
}

registry.category("actions").add("ab_ai_agent.console", AiAgentConsole);
// Every door into the full-page chat (agent "Open Chat", the floating
// assistant's expand button, manager menus) now lands in the console.
// Same params contract, so callers need no change.
registry.category("actions").add("ab_ai_agent.open_chat", AiAgentConsole, { force: true });
