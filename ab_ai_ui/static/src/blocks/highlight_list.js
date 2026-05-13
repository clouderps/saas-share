/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Coloured bulleted list for wins / risks / suggestions. Tone-driven
 *  border colour comes from the SCSS modifiers. */
export class HighlightList extends Component {
    static template = "ab_ai_ui.HighlightList";
    static props = {
        title: { type: String, optional: true },
        tone: { type: String, optional: true },
        items: { type: Array, optional: true },
    };
    static defaultProps = { tone: "", items: [] };
}
