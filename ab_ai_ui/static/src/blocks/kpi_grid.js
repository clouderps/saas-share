/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Headline number grid for daily reports / dashboards. Each tile has
 *  optional delta_pct + tone (good/warn/bad) for an at-a-glance status. */
export class KpiGrid extends Component {
    static template = "ab_ai_ui.KpiGrid";
    static props = {
        items: { type: Array, optional: true },
    };
    static defaultProps = { items: [] };

    toneClass(tone) {
        if (!tone) {
            return "";
        }
        return "ai-kpi__delta--" + tone;
    }
}
