/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";

import { SkeletonShimmer } from "../support/skeleton_shimmer";
import { ErrorEnvelope } from "../support/error_envelope";
import { ProvenanceBar } from "../support/provenance_bar";
import { AiText } from "../blocks/ai_text";
import { AiMarkdown } from "../blocks/ai_markdown";
import { SuggestionChips } from "../blocks/suggestion_chips";
import { KpiGrid } from "../blocks/kpi_grid";
import { HighlightList } from "../blocks/highlight_list";
import { DataTable } from "../blocks/data_table";
import { CalloutCard } from "../blocks/callout_card";
import { AiActionButton } from "../blocks/action_button";
import { ToolTrace } from "../blocks/tool_trace";

/** <AiResponse/> — the single OWL component every AI surface should use.
 *
 *  Three usage shapes:
 *
 *  1. ``envelope``: fully-loaded response from /api/v1/ai/analyze. Renders
 *     immediately, no skeleton. Picks layout from envelope.render.layout
 *     (chat | report | summary | extract | error).
 *
 *  2. ``streamUrl`` + ``streamBody``: connect to /api/v1/ai/stream over
 *     EventSource and paint deltas as they arrive. Shows skeleton until
 *     the first chunk lands, then a blinking cursor while streaming.
 *
 *  3. ``loading`` (flag): show skeleton until the parent passes
 *     ``envelope`` or ``error`` props.
 *
 *  ``layout`` prop overrides envelope.render.layout when the caller wants
 *  to force a presentation (e.g. dashboards always use "summary"). */
export class AiResponse extends Component {
    static template = "ab_ai_ui.AiResponse";
    static components = {
        SkeletonShimmer, ErrorEnvelope, ProvenanceBar,
        AiText, AiMarkdown, SuggestionChips, KpiGrid, HighlightList, DataTable,
        CalloutCard, AiActionButton, ToolTrace,
    };
    static props = {
        envelope: { type: Object, optional: true },
        layout: { type: String, optional: true },
        loading: { type: Boolean, optional: true },
        error: { type: [String, Boolean], optional: true },
        streamUrl: { type: String, optional: true },
        streamBody: { type: Object, optional: true },
        streamHeaders: { type: Object, optional: true },
        compact: { type: Boolean, optional: true },
    };
    static defaultProps = {
        loading: false, error: false, compact: false,
    };

    setup() {
        this.state = useState({
            streaming: false,
            streamedText: "",
            streamError: null,
            streamProvenance: null,
            streamDone: false,
        });

        if (this.props.streamUrl) {
            onMounted(() => this._openStream());
            onWillUnmount(() => this._closeStream());
        }
    }

    // ─── Layout resolution ────────────────────────────────────────

    get layout() {
        if (this.props.layout) {
            return this.props.layout;
        }
        const render = this.props.envelope?.render;
        if (render?.layout) {
            return render.layout;
        }
        if (this.props.error || this.props.envelope?.error) {
            return "error";
        }
        return "chat";
    }

    get classes() {
        return [
            "ai-response",
            "ai-response--" + this.layout,
            this.props.compact ? "ai-response--compact" : "",
        ].filter(Boolean).join(" ");
    }

    get isLoading() {
        if (this.props.loading) {
            return true;
        }
        if (this.props.streamUrl && !this.state.streamDone && !this.state.streamedText) {
            return true;
        }
        return false;
    }

    get errorMessage() {
        if (this.state.streamError) {
            return this.state.streamError;
        }
        if (typeof this.props.error === "string") {
            return this.props.error;
        }
        if (this.props.envelope?.error) {
            return this.props.envelope.error;
        }
        return "";
    }

    get errorStatus() {
        return this.props.envelope?.status || "error";
    }

    // ─── Envelope helpers ─────────────────────────────────────────

    get render() {
        return this.props.envelope?.render || null;
    }

    get title() {
        return this.render?.title || "";
    }

    get subtitle() {
        return this.render?.subtitle || "";
    }

    get blocks() {
        if (this.render?.blocks?.length) {
            return this.render.blocks;
        }
        // Fallback: synthesise a single AiText block from envelope.response
        const text = this.props.envelope?.response;
        if (text) {
            return [{ type: "text", text }];
        }
        return [];
    }

    get provenance() {
        if (this.state.streamProvenance) {
            return this.state.streamProvenance;
        }
        if (!this.props.envelope) {
            return null;
        }
        const p = this.props.envelope;
        return {
            provider: p.provider_used,
            model: p.usage?.model || p.provenance?.model,
            simulated: p.simulated,
            fallback_engaged: p.fallback_engaged,
            redaction_count: p.provenance?.redaction_count,
            prompt_injection_flagged: p.provenance?.prompt_injection_flagged,
            tool_calls_count: p.tool_calls_count,
            duration_s: p.usage?.duration,
            cost_usd: p.usage?.cost_usd,
            // Stage 4 validator verdict — surfaces verified / partial /
            // unverified / policy_violation on the ProvenanceBar.
            verdict: p.provenance?.verdict,
            apology_emitted: p.provenance?.apology_emitted,
            citations_checked: p.provenance?.citations_checked,
            citations_failed: p.provenance?.citations_failed,
            tokens: p.usage ? {
                prompt: p.usage.prompt_tokens,
                completion: p.usage.completion_tokens,
                total: p.usage.total_tokens,
            } : null,
        };
    }

    get toolCalls() {
        // Tool trace can come either as a block (from render.blocks) or
        // attached separately on the envelope.
        if (this.props.envelope?.tool_log_ids?.length) {
            return this.props.envelope.tool_log_ids;
        }
        const tc = this.blocks.find((b) => b.type === "tool_trace");
        return tc ? tc.calls : [];
    }

    isBlock(block, type) {
        return block && block.type === type;
    }

    // ─── Streaming ────────────────────────────────────────────────

    async _openStream() {
        this.state.streaming = true;
        const body = JSON.stringify(this.props.streamBody || {});
        const headers = Object.assign(
            { "Content-Type": "application/json" },
            this.props.streamHeaders || {}
        );

        // EventSource doesn't support custom POST bodies, so use fetch
        // with a ReadableStream reader and parse SSE manually.
        try {
            const res = await fetch(this.props.streamUrl, {
                method: "POST", headers, body,
            });
            if (!res.ok || !res.body) {
                throw new Error("HTTP " + res.status);
            }
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                buf += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buf.indexOf("\n\n")) >= 0) {
                    const frame = buf.slice(0, idx);
                    buf = buf.slice(idx + 2);
                    if (frame.startsWith("data:")) {
                        const payload = frame.slice(5).trim();
                        if (payload) {
                            this._handleStreamFrame(payload);
                        }
                    }
                }
            }
        } catch (e) {
            this.state.streamError = e.message || String(e);
            this.state.streamDone = true;
            this.state.streaming = false;
        }
    }

    _handleStreamFrame(payload) {
        let event;
        try {
            event = JSON.parse(payload);
        } catch (e) {
            return;
        }
        if (event.event === "delta" && event.data?.delta) {
            this.state.streamedText += event.data.delta;
        } else if (event.event === "done") {
            this.state.streaming = false;
            this.state.streamDone = true;
            const u = event.data?.usage || {};
            this.state.streamProvenance = {
                provider: u.provider,
                model: u.model,
                simulated: u.provider === "simulation",
                redaction_count: event.data?.redaction_count,
                prompt_injection_flagged: event.data?.prompt_injection_flagged,
                tokens: {
                    prompt: u.prompt_tokens,
                    completion: u.completion_tokens,
                    total: u.total_tokens,
                },
            };
        } else if (event.event === "error") {
            this.state.streamError = event.data?.message || "stream error";
            this.state.streaming = false;
            this.state.streamDone = true;
        }
    }

    _closeStream() {
        // The fetch reader is GC'd when the component unmounts.
        this.state.streaming = false;
    }
}
