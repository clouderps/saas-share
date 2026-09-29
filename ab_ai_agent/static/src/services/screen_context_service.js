/** @odoo-module **/
/**
 * aiScreenContext — what the user is looking at, for Ghaima AI.
 *
 * Event-driven, never scans the DOM, never RPCs. The main view's
 * SearchModel and view Model register themselves here (patches below)
 * when they are NOT inside a dialog; `snapshot()` reads them only when a
 * question is actually sent. The server re-validates every field of the
 * descriptor as the user (ai.screen.context.normalize), so nothing here
 * is a security boundary — it is only a cheap, accurate pointer.
 *
 * `bus` emits "change" once per meaningful change (action / view /
 * record / filters / group-by), used by the proactive insight. Filter
 * edits coalesce in a microtask — no timers.
 */

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { EventBus, toRaw } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { WithSearch } from "@web/search/with_search/with_search";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { FormController } from "@web/views/form/form_controller";
import { onWillUnmount } from "@odoo/owl";

const MAX_IDS = 50;

// Live registrations — plain module state, replaced as views mount.
const live = { searchModel: null, view: null };

function isMainView(env) {
    return !env.inDialog && !!env.config;
}

/** Called from a component's setup(): cleared again on unmount. */
function register(slot, value) {
    live[slot] = value;
    onWillUnmount(() => {
        if (live[slot] === value) {
            live[slot] = null;
        }
    });
}

patch(WithSearch.prototype, {
    setup() {
        super.setup(...arguments);
        if (isMainView(this.env)) {
            register("searchModel", this.searchModel);
            this.searchModel.addEventListener("update", () => notify());
        }
    },
});

for (const [Controller, kind] of [
    [ListController, "list"],
    [KanbanController, "kanban"],
    [FormController, "form"],
]) {
    patch(Controller.prototype, {
        setup() {
            super.setup(...arguments);
            if (isMainView(this.env)) {
                register("view", { kind, controller: this });
            }
        },
    });
}

let bus = null;
let pending = false;
let lastSignature = "";
let actionService = null;

function notify() {
    if (!bus || pending) {
        return;
    }
    pending = true;
    queueMicrotask(() => {
        pending = false;
        const sig = signature();
        if (sig !== lastSignature) {
            lastSignature = sig;
            bus.trigger("change", { signature: sig });
        }
    });
}

function currentAction() {
    const ctrl = actionService?.currentController;
    return ctrl ? toRaw(ctrl.action) : null;
}

function signature() {
    const a = currentAction();
    const sm = live.searchModel;
    const v = live.view;
    let resId = "";
    try {
        resId = v?.kind === "form" ? v.controller.model.root.resId || "" : "";
    } catch {
        resId = "";
    }
    let domain = "";
    try {
        domain = sm ? JSON.stringify(sm.domain) + JSON.stringify(sm.groupBy) : "";
    } catch {
        domain = "";
    }
    return [a?.id || a?.tag || "", actionService?.currentController?.view?.type || "", resId, domain].join("|");
}

function headerButtons(controller) {
    const root = controller.model?.root;
    const xmlDoc = controller.archInfo?.xmlDoc || controller.props?.archInfo?.xmlDoc;
    if (!root || !xmlDoc) {
        return [];
    }
    const out = [];
    for (const btn of xmlDoc.querySelectorAll("header button")) {
        const invisible = btn.getAttribute("invisible");
        try {
            if (invisible && evaluateBooleanExpr(invisible, root.evalContextWithVirtualIds)) {
                continue;
            }
        } catch {
            continue;   // cannot tell → do not claim it is there
        }
        const string = btn.getAttribute("string") || btn.textContent.trim();
        if (string) {
            out.push({ name: btn.getAttribute("name") || "", string, type: btn.getAttribute("type") || "" });
        }
    }
    return out.slice(0, 15);
}

/** The descriptor sent with a question. Never throws. */
function snapshot() {
    const out = {};
    try {
        const ctrl = actionService?.currentController;
        const action = currentAction();
        if (action) {
            out.action = { id: typeof action.id === "number" ? action.id : null, type: action.type, tag: action.tag || "" };
            if (action.res_model) {
                out.model = action.res_model;
            }
        }
        out.view_type = ctrl?.view?.type || "";
        const sm = live.searchModel;
        if (sm && (!out.model || sm.resModel === out.model)) {
            out.model = sm.resModel;
            out.domain = sm.domain;
            out.group_by = sm.groupBy;
            out.facets = sm.facets.map((f) =>
                (f.title ? `${f.title}: ` : "") + (f.values || []).join(` ${f.separator || "/"} `)
            );
        }
        const v = live.view;
        const root = v?.controller?.model?.root;
        if (root && (!out.model || root.resModel === out.model)) {
            out.model = root.resModel;
            if (v.kind === "form") {
                out.res_id = root.resId || null;
                out.buttons = headerButtons(v.controller);
            } else if (Array.isArray(root.records)) {
                // Loaded rows only (no fetch); grouped views have groups.
                out.visible_ids = root.records.slice(0, MAX_IDS).map((r) => r.resId).filter(Boolean);
                out.selected_ids = root.records.filter((r) => r.selected).slice(0, MAX_IDS).map((r) => r.resId);
            }
        }
    } catch {
        // A context we cannot read is simply smaller, never an error.
    }
    return out;
}

// One insight request per screen, shared by every consumer (the button's
// tip and the panel's screen card): same signature → same promise. A new
// screen aborts the previous request.
let insightCache = { sig: null, promise: null, req: null };

function insight() {
    const sig = signature();
    if (insightCache.sig === sig && insightCache.promise) {
        return insightCache.promise;
    }
    insightCache.req?.abort?.();
    const snap = snapshot();
    if (!snap.model) {
        insightCache = { sig, promise: Promise.resolve(null), req: null };
        return insightCache.promise;
    }
    const req = rpc("/ai_agent/screen/insight", { screen: snap }, { silent: true });
    const promise = req.then((res) => res || null).catch(() => null);
    insightCache = { sig, promise, req };
    return promise;
}

export const aiScreenContextService = {
    dependencies: ["action"],
    start(env, { action }) {
        actionService = action;
        bus = new EventBus();
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => notify());
        return {
            bus,
            snapshot,
            insight,
            signature: () => signature(),
        };
    },
};

registry.category("services").add("aiScreenContext", aiScreenContextService);
