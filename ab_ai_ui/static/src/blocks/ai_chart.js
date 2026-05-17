/** @odoo-module **/
/* global Chart */

import { Component, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";

/** <AiChart/> — analytical chart block for the AI response renderer.
 *
 *  Renders a `chart` envelope block:
 *
 *    {
 *      "type": "chart",
 *      "chart": "line" | "bar" | "area" | "pie" | "donut",
 *      "title": "Sales — last 30 days",
 *      "x": ["2026-04-18", ...],
 *      "series": [
 *        { "name": "Net sales (SAR)", "data": [12450, ...] },
 *        { "name": "Orders", "data": [83, ...], "axis": "right" }
 *      ],
 *      "unit": "SAR",
 *      "insight": "Weekends drive ~38% of weekly revenue.",
 *      "tone": "good" | "warn" | "bad" | "info"
 *    }
 *
 *  The wire format is Chart.js-agnostic on purpose — neither the LLM nor
 *  the server tool ever sees a Chart.js config. We translate here.
 *
 *  Uses Odoo's own bundled Chart.js (`web.chartjs_lib`) loaded lazily,
 *  exactly like the native graph view (web/views/graph/graph_renderer).
 *  No vendored copy, no extra dependency — keeps ab_ai_ui (saas-share)
 *  free of any business-domain / dashboard dep. */
export class AiChart extends Component {
    static template = "ab_ai_ui.AiChart";
    static props = {
        chart: { type: String, optional: true },
        title: { type: String, optional: true },
        x: { type: Array, optional: true },
        series: { type: Array, optional: true },
        unit: { type: String, optional: true },
        insight: { type: String, optional: true },
        tone: { type: String, optional: true },
    };
    static defaultProps = { chart: "line", x: [], series: [], unit: "", insight: "" };

    setup() {
        this.canvasRef = useRef("canvas");
        this._chart = null;
        onWillStart(() => loadBundle("web.chartjs_lib"));
        onMounted(() => this._draw());
        onWillUnmount(() => this._chart && this._chart.destroy());
    }

    /** Resolve a Ghaima design token to a concrete colour (Chart.js
     *  paints on <canvas> and can't read CSS vars). Falls back to the
     *  same hex the SCSS uses when ab_ghaima_theme isn't installed. */
    _token(name, fallback) {
        const v = getComputedStyle(document.documentElement)
            .getPropertyValue(name).trim();
        return v || fallback;
    }

    get _palette() {
        return [
            this._token("--ghaima-blue", "#005FF6"),
            this._token("--ghaima-cyan", "#5DD8CA"),
            this._token("--ghaima-navy", "#0D00A2"),
            "#F6A609",
            "#E5484D",
        ];
    }

    get _isRTL() {
        return document.dir === "rtl"
            || document.documentElement.getAttribute("dir") === "rtl";
    }

    _draw() {
        if (typeof Chart === "undefined" || !this.canvasRef.el) {
            return;
        }
        const rtl = this._isRTL;
        const pal = this._palette;
        const kind = this.props.chart || "line";
        const type = { area: "line", donut: "doughnut" }[kind] || kind;
        const isPie = type === "pie" || type === "doughnut";
        const hasRightAxis = (this.props.series || []).some((s) => s.axis === "right");

        const datasets = (this.props.series || []).map((s, i) => {
            const color = pal[i % pal.length];
            if (isPie) {
                return { label: s.name, data: s.data, backgroundColor: pal };
            }
            return {
                label: s.name,
                data: s.data,
                borderColor: color,
                backgroundColor: kind === "area" ? color + "33" : color,
                fill: kind === "area",
                tension: 0.3,
                borderWidth: 2,
                pointRadius: (s.data || []).length > 40 ? 0 : 3,
                yAxisID: s.axis === "right" ? "y1" : "y",
            };
        });

        const scales = isPie ? {} : {
            x: { ticks: { maxRotation: 0, autoSkip: true }, grid: { display: false } },
            y: {
                position: rtl ? "right" : "left",
                beginAtZero: true,
                ticks: {
                    callback: (v) =>
                        this.props.unit ? `${v} ${this.props.unit}` : v,
                },
            },
            y1: {
                position: rtl ? "left" : "right",
                display: hasRightAxis,
                beginAtZero: true,
                grid: { drawOnChartArea: false },
            },
        };

        this._chart = new Chart(this.canvasRef.el, {
            type,
            data: { labels: this.props.x || [], datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        rtl,
                        position: "bottom",
                        labels: { boxWidth: 12, usePointStyle: true },
                        display: datasets.length > 1 || isPie,
                    },
                    tooltip: { rtl },
                },
                scales,
            },
        });
    }
}
