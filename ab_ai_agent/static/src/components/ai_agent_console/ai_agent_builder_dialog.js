/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const BUILDER = "/ai_agent/console/builder/";

async function call(method, params = {}) {
    const res = await rpc(BUILDER + method, params);
    if (!res?.success) {
        throw new Error(res?.message || _t("Something went wrong. Try again."));
    }
    return res.result;
}

/**
 * <AiAgentBuilderDialog/> — guided "add / edit" for a tool, skill or topic.
 *
 * Tool:  pick a model (only models the designer can read) → operation →
 *        optional fixed filter + fields → name/description, pre-filled in
 *        English and Arabic. Saved as a preset over the generic data tools.
 * Skill: name, icon, prompt template with {placeholders}, optional model.
 * Topic: name, instructions, tools to bundle.
 *
 * All writes go through /ai_agent/console/builder/* which run as the
 * caller and re-check the designer right; this dialog only shapes input.
 */
export class AiAgentBuilderDialog extends Component {
    static template = "ab_ai_agent.AiAgentBuilderDialog";
    static components = { Dialog, AutoComplete };
    static props = {
        kind: { type: String, validate: (k) => ["tool", "skill", "topic"].includes(k) },
        agentId: { type: Number, optional: true },
        item: { type: Object, optional: true },     // edit mode
        tools: { type: Array, optional: true },     // catalog for topics
        onSaved: { type: Function },
        close: { type: Function },
    };

    setup() {
        this.notification = useService("notification");
        const item = this.props.item || {};
        this.state = useState({
            saving: false,
            error: "",
            // tool
            model: item.preset_model || "",
            modelLabel: item.preset_model || "",
            op: item.preset_op || "search",
            fieldOptions: [],
            filterField: "",
            filterOp: "=",
            filterValue: "",
            domain: [...(item.preset_domain || [])],
            fields: [...(item.preset_fields || [])],
            presetDirty: false,
            // shared
            name: item.name || "",
            description: item.description || "",
            descriptionAr: item.description_ar || "",
            // skill
            icon: item.icon || "fa-magic",
            template: item.template || "",
            contextModel: item.context_model || "",
            needsRecord: !!item.requires_record_context,
            shared: item.id ? !!item.is_global : true,
            // topic
            instructions: item.instructions || "",
            toolIds: [...(item.tool_ids || [])],
            toolQuery: "",
        });
        onWillStart(async () => {
            if (this.props.kind === "tool" && this.state.model) {
                await this.loadFields();
            }
        });
    }

    get isEdit() {
        return !!this.props.item?.id;
    }

    get title() {
        const titles = {
            tool: this.isEdit ? _t("Edit tool") : _t("Add a tool"),
            skill: this.isEdit ? _t("Edit skill") : _t("Add a skill"),
            topic: this.isEdit ? _t("Edit topic") : _t("Add a topic"),
        };
        return titles[this.props.kind];
    }

    get ops() {
        return [
            { id: "search", label: _t("Find records"), help: _t("List matching records") },
            { id: "count", label: _t("Count records"), help: _t("How many match") },
            { id: "read", label: _t("Record details"), help: _t("All fields of one record") },
            { id: "open", label: _t("Open the list"), help: _t("Take the user to the screen") },
            { id: "create", label: _t("Create a record"), help: _t("Proposed, the user confirms") },
            { id: "update", label: _t("Update a record"), help: _t("Proposed, the user confirms") },
        ];
    }

    get filterOps() {
        return [
            ["=", _t("is")], ["!=", _t("is not")], ["ilike", _t("contains")],
            [">", _t("greater than")], ["<", _t("less than")],
        ];
    }

    get placeholders() {
        return ["{message}", "{model}", "{id}", "{record_name}"];
    }

    get iconChoices() {
        return ["fa-magic", "fa-search", "fa-bar-chart", "fa-file-text-o", "fa-envelope-o",
            "fa-calendar", "fa-users", "fa-shopping-cart", "fa-money", "fa-cubes",
            "fa-lightbulb-o", "fa-check-square-o"];
    }

    // ── Model picker ─────────────────────────────────────────

    get modelSources() {
        return [{
            placeholder: _t("Loading…"),
            options: async (query) => {
                try {
                    const write = ["create", "update"].includes(this.state.op);
                    const rows = await call("models", { query, write });
                    if (!rows.length) {
                        return [{ label: _t("No model you can use matches"), unselectable: true }];
                    }
                    return rows.map((r) => ({ label: `${r.name} (${r.model})`, model: r.model, name: r.name }));
                } catch (e) {
                    return [{ label: e.message, unselectable: true }];
                }
            },
        }];
    }

    async onModelSelect(option, target = "model") {
        if (!option?.model) {
            return;
        }
        if (target === "context") {
            this.state.contextModel = option.model;
            return;
        }
        this.state.model = option.model;
        this.state.modelLabel = option.label;
        this.state.fields = [];
        this.state.domain = [];
        await this.loadFields();
        await this.suggest(true);
    }

    async loadFields() {
        try {
            this.state.fieldOptions = await call("fields", { model: this.state.model });
        } catch (e) {
            this.state.fieldOptions = [];
            this.state.error = e.message;
        }
    }

    async suggest(force = false) {
        if (!this.state.model || this.isEdit) {
            return;
        }
        try {
            const s = await call("suggest", { model: this.state.model, op: this.state.op });
            const ar = document.documentElement.dir === "rtl";
            if (force || !this.state.name) {
                this.state.name = ar ? s.name_ar : s.name_en;
            }
            this.state.description = s.description_en;
            this.state.descriptionAr = s.description_ar;
        } catch {
            // Suggestion is a convenience; the user can type their own.
        }
    }

    async setOp(op) {
        this.state.op = op;
        await this.suggest(true);
    }

    toggleField(name) {
        const i = this.state.fields.indexOf(name);
        if (i >= 0) {
            this.state.fields.splice(i, 1);
        } else if (this.state.fields.length < 20) {
            this.state.fields.push(name);
        }
        this.state.presetDirty = true;
    }

    addFilter() {
        if (!this.state.filterField) {
            return;
        }
        const meta = this.state.fieldOptions.find((f) => f.name === this.state.filterField);
        let value = this.state.filterValue;
        if (meta && ["integer", "float", "monetary", "many2one"].includes(meta.type) && value !== ""
            && !Number.isNaN(Number(value))) {
            value = Number(value);
        } else if (meta?.type === "boolean") {
            value = ["1", "true", "yes", "نعم"].includes(String(value).toLowerCase());
        }
        this.state.domain.push([this.state.filterField, this.state.filterOp, value]);
        this.state.presetDirty = true;
        this.state.filterValue = "";
    }

    removeFilter(index) {
        this.state.domain.splice(index, 1);
        this.state.presetDirty = true;
    }

    fieldLabel(name) {
        return this.state.fieldOptions.find((f) => f.name === name)?.string || name;
    }

    // ── Topic tools ──────────────────────────────────────────

    get topicTools() {
        const q = this.state.toolQuery.trim().toLowerCase();
        return (this.props.tools || []).filter((t) => !q
            || t.name.toLowerCase().includes(q) || t.code.toLowerCase().includes(q));
    }

    toggleTool(id) {
        const i = this.state.toolIds.indexOf(id);
        if (i >= 0) {
            this.state.toolIds.splice(i, 1);
        } else {
            this.state.toolIds.push(id);
        }
    }

    insertPlaceholder(ph) {
        this.state.template = `${this.state.template}${this.state.template && !this.state.template.endsWith(" ") ? " " : ""}${ph}`;
    }

    // ── Save ─────────────────────────────────────────────────

    get canSave() {
        const s = this.state;
        if (s.saving) {
            return false;
        }
        if (this.props.kind === "tool") {
            return !!s.model && !!s.op;
        }
        if (this.props.kind === "skill") {
            return !!s.name.trim() && !!s.template.trim();
        }
        return !!s.name.trim();
    }

    payload() {
        const s = this.state;
        if (this.props.kind === "tool") {
            const v = {
                name: s.name, description: s.description, description_ar: s.descriptionAr,
                // which language the one Name box is in (server stores both)
                name_lang: document.documentElement.dir === "rtl" ? "ar" : "en",
            };
            if (!this.isEdit) {
                Object.assign(v, { model: s.model, op: s.op, domain: s.domain, fields: s.fields });
            } else if (s.presetDirty) {
                // Only a changed filter/field list is sent: an edit that
                // leaves them alone can never wipe the saved ones.
                Object.assign(v, { domain: s.domain, fields: s.fields });
            }
            return v;
        }
        if (this.props.kind === "skill") {
            const v = { name: s.name, description: s.description, icon: s.icon, template: s.template };
            if (!this.isEdit) {
                Object.assign(v, {
                    context_model: s.contextModel, requires_record_context: s.needsRecord, shared: s.shared,
                });
            }
            return v;
        }
        return { name: s.name, description: s.description, instructions: s.instructions, tool_ids: s.toolIds };
    }

    async save() {
        if (!this.canSave) {
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        const kind = this.props.kind;
        try {
            const params = { values: this.payload() };
            if (this.isEdit) {
                params.id = this.props.item.id;
                await call(`update_${kind}`, params);
            } else {
                params.agent_id = this.props.agentId;
                await call(`create_${kind}`, params);
            }
            this.notification.add(this.isEdit ? _t("Saved.") : _t("Added. The assistant can use it now."),
                { type: "success" });
            await this.props.onSaved();
            this.props.close();
        } catch (e) {
            this.state.error = e.message;
        } finally {
            this.state.saving = false;
        }
    }
}
