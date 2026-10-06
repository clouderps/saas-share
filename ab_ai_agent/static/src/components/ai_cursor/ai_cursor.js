/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** The ghost pointer painted while aiNavigator glides to a target. */
export class AiCursor extends Component {
    static template = "ab_ai_agent.AiCursor";
    static props = {};

    setup() {
        this.nav = useState(useService("aiNavigator").state);
    }

    get style() {
        return `transform: translate3d(${Math.round(this.nav.x)}px, ${Math.round(this.nav.y)}px, 0);`;
    }
}

registry.category("main_components").add("AiCursor", { Component: AiCursor });
