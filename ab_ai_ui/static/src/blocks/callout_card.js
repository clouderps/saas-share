/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Single-line attention-grabber: "Saudi VAT return due in 3 days",
 *  "Stock low on 4 products". One per response by convention. */
export class CalloutCard extends Component {
    static template = "ab_ai_ui.CalloutCard";
    static props = {
        title: { type: String, optional: true },
        body: { type: String, optional: true },
        tone: { type: String, optional: true },
        icon: { type: String, optional: true },
    };
    static defaultProps = { tone: "", icon: "fa-info-circle" };
}
