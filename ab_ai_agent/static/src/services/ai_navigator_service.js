/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

/**
 * aiNavigator — executes the server's navigation directive behind the
 * in-app "AI cursor".
 *
 * Only three directive shapes are accepted (record / list / menu); the
 * action is ALWAYS built here, never taken from the envelope, so model
 * output can't smuggle a URL, a server action or a client action. A menu
 * must be in the user's own loaded menu tree (menu service), which only
 * holds menus they can see.
 */

const MODEL_RE = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;
const GLIDE_MS = 600;
const HOLD_MS = 250;

function isPrimitive(v) {
    return v === null || ["string", "number", "boolean"].includes(typeof v);
}

function cleanDomain(domain) {
    if (!Array.isArray(domain)) {
        return null;
    }
    for (const leaf of domain) {
        if (typeof leaf === "string") {
            if (!["&", "|", "!"].includes(leaf)) {
                return null;
            }
        } else if (!Array.isArray(leaf) || leaf.length !== 3 || typeof leaf[0] !== "string"
                   || typeof leaf[1] !== "string"
                   || !(isPrimitive(leaf[2]) || (Array.isArray(leaf[2]) && leaf[2].every(isPrimitive)))) {
            return null;
        }
    }
    return domain;
}

/** Validated copy of a directive, or null. Exported for tests. */
export function sanitizeDirective(d) {
    if (!d || typeof d !== "object") {
        return null;
    }
    const label = typeof d.label === "string" ? d.label.slice(0, 200) : "";
    if (d.type === "record") {
        const resId = Number(d.res_id);
        if (!MODEL_RE.test(d.model || "") || !Number.isInteger(resId) || resId <= 0) {
            return null;
        }
        return { type: "record", model: d.model, res_id: resId, label };
    }
    if (d.type === "list") {
        const domain = cleanDomain(d.domain || []);
        if (!MODEL_RE.test(d.model || "") || !domain) {
            return null;
        }
        return { type: "list", model: d.model, domain, label };
    }
    if (d.type === "menu") {
        const menuId = Number(d.menu_id);
        if (!Number.isInteger(menuId) || menuId <= 0) {
            return null;
        }
        return { type: "menu", menu_id: menuId, label };
    }
    return null;
}

/** Envelope actions (the "Open" chip): window and registered client actions only. */
export function isSafeEnvelopeAction(action) {
    if (!action || typeof action !== "object") {
        return false;
    }
    if (action.type === "ir.actions.act_window") {
        return MODEL_RE.test(action.res_model || "");
    }
    if (action.type === "ir.actions.client") {
        return registry.category("actions").contains(action.tag || "");
    }
    return false;
}

function prefersReducedMotion() {
    try {
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {
        return false;
    }
}

function visible(el) {
    if (!el) {
        return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
}

function centerOf(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const aiNavigatorService = {
    dependencies: ["action", "menu", "notification"],

    start(env, { action, menu, notification }) {
        const state = reactive({
            visible: false, x: 0, y: 0, gliding: false, ripple: false,
            label: "", announce: "",
        });
        let token = 0;
        let highlighted = null;

        function animationEnabled() {
            const info = session.ai_assistant || {};
            return info.cursor !== false && !prefersReducedMotion();
        }

        function navbarItem(xmlid) {
            if (!xmlid) {
                return null;
            }
            const el = document.querySelector(
                `.o_main_navbar [data-menu-xmlid="${CSS.escape(xmlid)}"]`);
            return visible(el) ? el : null;
        }

        /** The element the pointer should land on, or null (screen centre). */
        function findTarget(d) {
            if (d.type === "menu") {
                const m = menu.getMenu(d.menu_id);
                const app = m && m.appID ? menu.getMenu(m.appID) : null;
                return navbarItem(m && m.xmlid)
                    || navbarItem(app && app.xmlid)
                    || [...document.querySelectorAll(".o_navbar_apps_menu button, .o_navbar_apps_menu .dropdown-toggle")]
                        .find(visible) || null;
            }
            return null;
        }

        async function execute(d) {
            if (d.type === "menu") {
                const m = menu.getMenu(d.menu_id);
                if (!m || !m.actionID) {
                    throw new Error("menu not available");
                }
                return menu.selectMenu(m);
            }
            if (d.type === "record") {
                return action.doAction({
                    type: "ir.actions.act_window", name: d.label, res_model: d.model,
                    res_id: d.res_id, views: [[false, "form"]], target: "current",
                });
            }
            return action.doAction({
                type: "ir.actions.act_window", name: d.label, res_model: d.model,
                domain: d.domain, views: [[false, "list"], [false, "form"]], target: "current",
            });
        }

        function clearHighlight() {
            if (highlighted) {
                highlighted.classList.remove("o_ai_cursor_target");
                highlighted = null;
            }
        }

        /**
         * Glide the pointer from `originEl` to the target, then open it.
         * Returns true when navigation ran.
         */
        async function go(rawDirective, originEl = null) {
            const d = sanitizeDirective(rawDirective);
            if (!d) {
                return false;
            }
            const mine = ++token;
            clearHighlight();
            state.announce = d.label ? _t("Opening %s", d.label) : _t("Opening");
            if (animationEnabled()) {
                const start = visible(originEl) ? centerOf(originEl)
                    : { x: window.innerWidth / 2, y: window.innerHeight - 80 };
                const targetEl = findTarget(d);
                const area = document.querySelector(".o_action_manager");
                const end = targetEl ? centerOf(targetEl)
                    : visible(area) ? centerOf(area)
                    : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
                Object.assign(state, { visible: true, gliding: false, ripple: false,
                                       label: d.label, x: start.x, y: start.y });
                await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
                if (mine !== token) {
                    return false;
                }
                Object.assign(state, { gliding: true, x: end.x, y: end.y });
                await wait(GLIDE_MS);
                if (mine !== token) {
                    return false;
                }
                state.ripple = true;
                if (targetEl) {
                    highlighted = targetEl;
                    targetEl.classList.add("o_ai_cursor_target");
                }
                await wait(HOLD_MS);
                if (mine !== token) {
                    return false;
                }
            }
            try {
                await execute(d);
                return true;
            } catch {
                notification.add(_t("That screen could not be opened."), { type: "warning" });
                return false;
            } finally {
                if (mine === token) {
                    setTimeout(() => {
                        if (mine === token) {
                            Object.assign(state, { visible: false, gliding: false, ripple: false });
                            clearHighlight();
                        }
                    }, 350);
                }
            }
        }

        return { state, go, sanitizeDirective, isSafeEnvelopeAction };
    },
};

registry.category("services").add("aiNavigator", aiNavigatorService);
