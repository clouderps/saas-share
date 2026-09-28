/** @odoo-module **/
/**
 * Error help: "Why this happens" / "How to fix it" / "Open guide" in the
 * web client's error dialogs.
 *
 * The server sends the help as `error.data.context.error_help`
 * ({code, why, fix}; see ab_error_help/exceptions.py). Any error dialog that
 * receives it renders <ErrorHelpPanel/> under the message.
 *
 * The "Open guide" button comes from the `error_help_providers` registry.
 * This module registers none: without a provider (no Knowledge Base
 * installed) the dialog shows the texts only. A provider is
 *
 *     {
 *         // true when a guide exists for `code`; may be async
 *         hasGuide(env, code): boolean | Promise<boolean>,
 *         // open it; `close` closes the error dialog if the provider wants
 *         openGuide(env, code, { close }): void | Promise<void>,
 *     }
 *
 * The first provider (by registry sequence) whose hasGuide() is true wins.
 */
import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import {
    ErrorDialog,
    WarningDialog,
    odooExceptionTitleMap,
} from "@web/core/errors/error_dialogs";

export const errorHelpProviders = registry.category("error_help_providers");

const MODULE = "odoo.addons.ab_error_help.exceptions";

/** The help payload of an RPC error's `data`, or null. */
export function getErrorHelp(data) {
    const help = data && data.context && data.context.error_help;
    return help && help.code ? help : null;
}

export class ErrorHelpPanel extends Component {
    static template = "ab_error_help.ErrorHelpPanel";
    static props = {
        help: Object,
        close: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({ provider: null, opening: false });
        onWillStart(async () => {
            this.state.provider = await this.findProvider();
        });
    }

    get labels() {
        return {
            why: _t("Why this happens"),
            fix: _t("How to fix it"),
            open: _t("Open guide"),
            code: _t("Help code"),
        };
    }

    async findProvider() {
        for (const provider of errorHelpProviders.getAll()) {
            try {
                if (await provider.hasGuide(this.env, this.props.help.code)) {
                    return provider;
                }
            } catch {
                // A failing provider must never break the error dialog.
            }
        }
        return null;
    }

    async openGuide() {
        if (!this.state.provider || this.state.opening) {
            return;
        }
        this.state.opening = true;
        try {
            await this.state.provider.openGuide(this.env, this.props.help.code, {
                close: this.props.close,
            });
        } finally {
            this.state.opening = false;
        }
    }
}

// One sub-component for every error dialog. RPCErrorDialog and the other
// ErrorDialog subclasses read ErrorDialog.components through the class chain.
WarningDialog.components = { ...WarningDialog.components, ErrorHelpPanel };
ErrorDialog.components = { ...ErrorDialog.components, ErrorHelpPanel };

// One patch object per class: `super` inside an object literal is bound to
// that object's prototype, which patch() sets to the patched class -- sharing
// one object between two patches would make WarningDialog call
// ErrorDialog.setup().
const errorHelpPatch = () => ({
    setup() {
        super.setup(...arguments);
        this.errorHelp = getErrorHelp(this.props.data);
    },
});
patch(WarningDialog.prototype, errorHelpPatch());
patch(ErrorDialog.prototype, errorHelpPatch());

// The server-side class names map to the stock dialog and title. Without
// this the dialog would still be the warning dialog (the payload names the
// core class as `exception_class`), only with the generic title.
const dialogs = registry.category("error_dialogs");
const kinds = [
    ["HelpUserError", "odoo.exceptions.UserError"],
    ["HelpValidationError", "odoo.exceptions.ValidationError"],
    ["HelpAccessError", "odoo.exceptions.AccessError"],
];
for (const [name, core] of kinds) {
    dialogs.add(`${MODULE}.${name}`, WarningDialog, { force: true });
    if (odooExceptionTitleMap.has(core)) {
        odooExceptionTitleMap.set(`${MODULE}.${name}`, odooExceptionTitleMap.get(core));
    }
}
