/** @odoo-module **/

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

/**
 * aiAgentService — frontend orchestrator for the Phase H agent runtime.
 *
 * Wraps the three JSON endpoints (/ai_agent/list, /ai_agent/run,
 * /ai_agent/rate) and broadcasts state through a reactive store so
 * every component (chat, chip, skill card, token meter) reads the
 * same data and updates in lockstep.
 *
 * In Odoo 18, `rpc` and `user` are module imports rather than
 * registered services — only bus + notification go through useService.
 *
 * Lives in saas-share so it's available wherever ab_ai_agent is
 * installed (central + tenants). Components are surface-agnostic —
 * the chat shell, chatter button, composer wizard, and website
 * widget all consume this same service.
 */
export const aiAgentService = {
    dependencies: ["bus_service", "notification"],

    start(env, { bus_service, notification }) {
        const state = reactive({
            agents: [],
            activeAgent: null,
            isLoadingAgents: false,
            meter: {
                today: { tokens: 0, cost_sar: 0, calls: 0, cache_hits: 0 },
                period: "today",
                state: "ok",          // 'ok' | 'warn' | 'blocked'
                remaining_sar: -1,
            },
        });

        // ── Agent list ─────────────────────────────────────────
        async function refreshAgents() {
            state.isLoadingAgents = true;
            try {
                const res = await rpc("/ai_agent/list", {});
                if (res?.success) {
                    state.agents = res.agents || [];
                    if (!state.activeAgent && state.agents.length) {
                        state.activeAgent =
                            state.agents.find((a) => a.is_default) ||
                            state.agents[0];
                    }
                }
            } catch (e) {
                notification.add(e.message || "AI agent list failed", { type: "danger" });
            } finally {
                state.isLoadingAgents = false;
            }
        }

        function setActiveAgent(agent) {
            state.activeAgent = agent;
        }

        // ── Run ─────────────────────────────────────────────────
        async function runAgent({ message, agent, skill, surface, record, locale, conversationId } = {}) {
            agent = agent || state.activeAgent;
            const payload = {
                message: message || "",
                agent_id: agent?.id,
                agent_code: agent?.code,
                skill_code: skill?.code,
                surface: surface || "chat",
                record_model: record?.model,
                record_id: record?.id,
                conversation_id: conversationId || "",
                locale: locale || (user.lang || "en").slice(0, 2),
            };
            const res = await rpc("/ai_agent/run", payload);
            if (!res?.success) {
                throw new Error(res?.error || "agent_run_failed");
            }
            // Refresh meter after each run for the live chip.
            refreshMeter();
            return res;
        }

        async function rateRun(runId, feedback, note) {
            try {
                await rpc("/ai_agent/rate", { run_id: runId, feedback, note });
                return true;
            } catch (e) {
                return false;
            }
        }

        async function lookupRecordConversation({ recordModel, recordId, agentCode } = {}) {
            if (!recordModel || !recordId) return { success: false };
            try {
                return await rpc("/ai_agent/conversation/lookup", {
                    record_model: recordModel,
                    record_id: recordId,
                    agent_code: agentCode,
                });
            } catch (e) {
                return { success: false, error: e.message };
            }
        }

        // ── Live meter ──────────────────────────────────────────
        async function refreshMeter(period = "today") {
            try {
                const res = await rpc("/ai_agent/usage/live", { period });
                if (res?.success) {
                    state.meter.today = {
                        tokens:    res.summary.tokens || 0,
                        cost_sar:  res.summary.cost_sar || 0,
                        cost_usd:  res.summary.cost_usd || 0,
                        calls:     res.summary.calls || 0,
                        cache_hits: res.summary.cache_hits || 0,
                        cache_hit_rate: res.summary.cache_hit_rate || 0,
                    };
                    state.meter.period = period;
                }
            } catch (e) {
                // Silent — meter is best-effort.
            }
        }

        // Subscribe to live-meter bus pushes (per-company channel —
        // chip stays current even when a cron the user didn't trigger
        // bills the company).
        try {
            const channel = `ai.usage.live.${env.services?.company?.currentCompany?.id || ""}`;
            bus_service.subscribe(channel, (payload) => {
                if (!payload) return;
                state.meter.today = {
                    ...state.meter.today,
                    tokens: payload.tokens || state.meter.today.tokens,
                    cost_sar: payload.cost_sar || state.meter.today.cost_sar,
                    cost_usd: payload.cost_usd || state.meter.today.cost_usd,
                    calls: payload.calls || state.meter.today.calls,
                    cache_hits: payload.cache_hits || state.meter.today.cache_hits,
                };
            });
        } catch (e) {
            // bus_service might not be ready in all surfaces — non-fatal.
        }

        // Initial bootstrap.
        refreshAgents();
        refreshMeter();

        return {
            state,
            refreshAgents,
            setActiveAgent,
            runAgent,
            rateRun,
            refreshMeter,
            lookupRecordConversation,
        };
    },
};

registry.category("services").add("aiAgentService", aiAgentService);
