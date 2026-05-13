/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { AiResponse } from "@ab_ai_ui/ai_response/ai_response";

/** Form-view field widget that reads a Text field holding a JSON
 *  envelope (see ai.report.ai_render_envelope) and renders it with the
 *  shared <AiResponse/> component. Phase C of SAAS_AI_UI_PLAN.md.
 *
 *  Usage:
 *      <field name="ai_render_envelope" widget="ai_response_envelope"
 *             nolabel="1" readonly="1"/>
 *
 *  Falls back to a small placeholder when the field is empty so the
 *  draft / collecting / analyzing states don't render a broken card.
 */
export class AiResponseEnvelopeField extends Component {
    static template = "ab_ai_ui.AiResponseEnvelopeField";
    static components = { AiResponse };
    static props = { ...standardFieldProps };

    get envelope() {
        const raw = this.props.record.data[this.props.name];
        if (!raw) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (e) {
            // Treat malformed JSON as plain text so the renderer still
            // surfaces something instead of throwing in the form.
            return { response: String(raw) };
        }
    }

    get layout() {
        return this.envelope?.render?.layout || "report";
    }
}

export const aiResponseEnvelopeField = {
    component: AiResponseEnvelopeField,
    supportedTypes: ["text"],
    displayName: "AI Response Envelope",
};

registry.category("fields").add("ai_response_envelope", aiResponseEnvelopeField);
