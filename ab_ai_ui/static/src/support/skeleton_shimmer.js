/** @odoo-module **/

import { Component } from "@odoo/owl";

/** Animated placeholder shown while the first stream chunk hasn't arrived
 *  yet. ``lines`` lets the caller match the eventual content shape. */
export class SkeletonShimmer extends Component {
    static template = "ab_ai_ui.SkeletonShimmer";
    static props = {
        lines: { type: Number, optional: true },
    };
    static defaultProps = { lines: 3 };

    get lineWidths() {
        // Cycle through long/mid/short so the placeholder doesn't look
        // like a perfect block of rectangles.
        const widths = ["long", "mid", "short", "mid"];
        return Array.from({ length: this.props.lines }, (_, i) => widths[i % widths.length]);
    }
}
