/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Real <table> for tabular AI output — top products, top cashiers,
 *  partner ledger row sets. Rows are arrays of cell strings; renderer
 *  is read-only by design (the plan rules out editable AI output). */
export class DataTable extends Component {
    static template = "ab_ai_ui.DataTable";
    static props = {
        title: { type: String, optional: true },
        headers: { type: Array, optional: true },
        rows: { type: Array, optional: true },
    };
    static defaultProps = { headers: [], rows: [] };
}
