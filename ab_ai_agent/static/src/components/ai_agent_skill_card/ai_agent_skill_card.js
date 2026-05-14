/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * <AiAgentSkillCard/>
 *
 * Clickable launcher card for a single agent.skill. Renders inside the
 * chat sidebar (default) or as a row in the chatter button popover.
 * Composition: 36px icon tile (accent-tinted) + name + optional hint.
 */
export class AiAgentSkillCard extends Component {
    static template = "ab_ai_agent.AiAgentSkillCard";
    static props = {
        skill: { type: Object },
        onPick: { type: Function, optional: true },
    };

    get accentClass() {
        return `o_accent-${this.props.skill.accent || "blue"}`;
    }

    get iconClass() {
        const icon = this.props.skill.icon || "fa-magic";
        return icon.startsWith("fa-") ? `fa ${icon}` : `fa fa-${icon}`;
    }

    pick() {
        this.props.onPick?.(this.props.skill);
    }
}
