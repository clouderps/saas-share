/** @odoo-module **/

import { registry } from "@web/core/registry";

/** Helper service that calls /api/v1/ai/analyze and normalises the
 *  response shape for <AiResponse/>. Consumers can stay one-liner:
 *
 *      const env = await this.aiResponse.analyze({
 *          feature: "daily_report",
 *          user_prompt: "..."
 *      });
 *      // env is the envelope; pass it straight to <AiResponse envelope=...>
 *
 *  Token resolution is left to the consumer because token storage
 *  varies (sys param, env var, prompted). The service accepts a token
 *  via ``opts.token`` or reads ir.config_parameter ``ab_ai_ui.token``
 *  from the active env as a default. */
const aiResponseService = {
    dependencies: ["rpc"],
    start(env, { rpc }) {
        async function _resolveToken(opts) {
            if (opts && opts.token) {
                return opts.token;
            }
            // Fall back to ir.config_parameter — read once and cache.
            if (_cache.token !== undefined) {
                return _cache.token;
            }
            try {
                const v = await rpc("/web/dataset/call_kw", {
                    model: "ir.config_parameter",
                    method: "get_param",
                    args: ["ab_ai_ui.token", false],
                    kwargs: {},
                });
                _cache.token = v;
                return v;
            } catch (e) {
                _cache.token = false;
                return false;
            }
        }
        const _cache = {};

        async function analyze(payload, opts) {
            const token = await _resolveToken(opts);
            const res = await fetch("/api/v1/ai/analyze", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { "X-Entity-Token": token } : {}),
                },
                body: JSON.stringify({ params: payload || {} }),
            });
            const data = await res.json();
            return data.result || data;
        }

        function streamEndpoint() {
            return "/api/v1/ai/stream";
        }

        async function streamHeaders(opts) {
            const token = await _resolveToken(opts);
            return {
                "Content-Type": "application/json",
                ...(token ? { "X-Entity-Token": token } : {}),
            };
        }

        async function fetchPromptTemplate(feature, locale, opts) {
            const token = await _resolveToken(opts);
            const res = await fetch("/api/v1/ai/prompts/" + encodeURIComponent(feature), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { "X-Entity-Token": token } : {}),
                },
                body: JSON.stringify({ params: { locale: locale || "both" } }),
            });
            const data = await res.json();
            return (data.result || data).template || null;
        }

        return { analyze, streamEndpoint, streamHeaders, fetchPromptTemplate };
    },
};

registry.category("services").add("aiResponse", aiResponseService);
