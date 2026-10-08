# Ghaima AI agent vs Odoo AI — gap analysis and plan

_2026-10-08 · Interactive version (EN/AR): https://claude.ai/artifact/TtbrXyhKwxmyF1paHhLEuD_

> Odoo 19 Community has no AI agent; the reference is the Odoo 20.0 Enterprise `ai*` source (OEEL — behaviour studied only, no code copied). Our stack is Odoo 18.

Odoo 20 Enterprise (OEEL, studied for behaviour only) has one agent framework: server actions as tools, durable sessions, on-demand skills, per-agent knowledge with citations, and AI in the editor, composer, fields, server actions, automation and MCP, across ≈53 auto-install ai modules (ai_agentic is opt-in). Ghaima (Odoo 18) leads on multi-tenant metering, provider choice, prompt caching, block-kit analytics, Arabic, voice, document scanning, slash commands and confirm-first configuration.

Code review found P0 defects that come before new features:
- the default assistant can confirm its own chatbot write tools, including post_invoice (G45);
- Confirm skips the kill switch, plan and group checks, and chatbot confirm chips are not bound to their proposal (G02);
- data_analysis runs unscoped raw SQL (G01);
- every Claude model we offer is retired (G08);
- Odoo's native editor and composer AI send tenant text to Odoo (G24);
- gateway refusals fall back to tenant keys (G07, G44).

Plan: Phases 1–4, about 26–32 weeks with 2 developers: stabilise; agent-core parity; knowledge and surfaces; AI fields, server actions, scheduled agents and read-only MCP. Livechat, CRM/HR bridges and MCP OAuth stay in backlog.

## Scorecard (0–5)

| Area | Ghaima | Odoo | Comment |
|---|---|---|---|
| Agent model & configuration | 3.5 | 4.5 | Ours: ai.agent personas, topics/tools/skills, a no-code builder, use_all_capabilities, plan cap on agent count. Odoo adds skills loaded on demand, sub-agent delegation, a Self Update skill (limited to ai.* models) and ai.composer rules that map each UI surface to an agent. |
| LLM providers, gateway & cost control | 3 | 3 | Ours: provider choice, central gateway, plans, budgets, SAR price book, reconcile. Odoo: IAP only (Odoo picks the model, billed in credits), no per-user budgets. Ours is lowered from 3.5 because every Claude ID we offer is retired (the provider fails today), plus the cost bugs, the closed feature list and 'auto' mode falling back to tenant keys after a gateway refusal. |
| Tool calling & actions on records | 3.5 | 4.5 | Ours: generic CRUD and query_data, open_list/pivot/graph with domains, group-bys and measures, navigate, record_action, create_record with VAT handling, date_reference (on par with Odoo's compute_date). Odoo: any server action as a schema-validated tool, 24 built-in _ai_tool_* methods including bulk create/update and file reading (read_binary_content), and browser tools that adjust the open view in place. |
| Human-in-the-loop & security | 2.5 | 4 | Our design is stricter (no auto-approve, draft-only accounting), but today the assistant can confirm its own chatbot write tools including post_invoice (G45), Confirm skips gates and chatbot confirm chips are unbound (G02), data_analysis runs unscoped SQL (G01) and a guest can get a superuser-backed bot reply (G03). Stays at 2.5 until the Phase 1 wave-1a fixes ship. Odoo's own gap: _ai_tool_run runs server-action code via _run_action_code_multi, so the action's group_ids are not checked on that path. |
| RAG / knowledge & embeddings | 2.5 | 4.5 | Ours: knowledge digest, ai.chat.fact (pgvector and trigram), kb_search (plain word matching) over 10 curated EN/AR KB packs, the website excerpt; semantic_index exists but no model uses it; citations are a stub. Odoo: sources per agent (files, URLs, Knowledge, Documents), chunking, batch embedding, citations filtered by access. |
| Memory & sessions | 2.5 | 4 | Ours: sessions exist only through ab_ai_chatbot; history is the last 6 messages as plain text; no summarisation; no retention. Odoo: ai.session and ai.session.event store every step durably, with Discuss channels, auto-titled chats and autovacuum. |
| UI surfaces (chat, console, composer, prompt buttons) | 3.5 | 4.5 | Ours: console, chatter panel, floating button, AI cursor, plus surfaces Odoo lacks: a native mobile AI API (6 JWT endpoints used by the Flutter apps) and the scan-docs portal. Odoo: AI in the html editor, mail composer, file viewer, systray and Ctrl+K, with prompt buttons on records. Odoo 18 CE's own editor and composer AI exist on our tenants but route to Odoo's servers (G24). |
| Answer rendering & analytics | 4.5 | 3 | Our block kit (KPI grid, Chart.js charts, tables, callouts) plus query_data with comparison to the previous period. Odoo answers by opening pivot or graph views and links records in answers; our table rows are not yet clickable (G48). |
| Voice | 4 | 3.5 | Ours: hands-free mode, spoken confirm, Arabic TTS, metered. Odoo: speech-to-text in the composer, live dictation in the editor, and transcription of call recordings, which we lack. |
| Documents / OCR extraction | 4 | 3.5 | ab_scan_docs reads documents with AI vision into drafts of 7 types behind autopilot gates, with a full portal. Odoo sorts Documents folders, exposes bill creation as a tool and lets users chat about any file (read_binary_content, 'Summarize this file'), which we cannot do (G46). The gateway-path bug lowers our score. |
| AI fields | 0 | 4 | Not present in our stack. |
| AI in automation / server actions | 1 | 4.5 | Ours: fixed crons only (daily report, digest). Odoo: an 'AI' server action type, 'Update with AI' (evaluation_type 'ai_computed'), agents triggered by base.automation with schedules and a run inbox. |
| MCP / interop | 1.5 | 4 | Ours: REST plus OpenAPI through ab_api_base. Odoo: an MCP server with OAuth 2.1, dynamic client registration, an 'mcp' API-key scope and an initial-context tool. |
| AI-driven configuration | 3.5 | 1.5 | Ours: ab_ai_agent_config changes a whitelisted set of business settings (e.g. multi-currency) only after Confirm. Odoo's Self Update skill is scoped to ai.* models (_check_tool_scope) and its AI_MODELS_BLOCKLIST covers only a few models. |
| Per-app: accounting | 3 | 3.5 | Ours: draft invoice, bill and journal-entry commands, finance tools, report insights (broken through the gateway). The post_invoice chatbot tool breaks draft-only (G45), and the reports themselves are only partly audited. Odoo: tools that drive the accounting reports, plus audit agents. |
| Per-app: sales/CRM, purchase, inventory, POS | 3.5 | 2 | Ours: analytics tools, /create quote and /create rfq, stock tools, POS and kitchen tools (some broken by the closed feature list). Odoo: mostly prompt buttons, plus a tool that creates leads from livechat. |
| Per-app: HR, project, helpdesk, marketing, website | 1.5 | 3.5 | Ours: /create employee, ab_error_help (errors across apps, 478 for HR), HR tools that the PII gate makes dead. Odoo: AI-drafted recruitment refusal emails, a timesheet assistant, similar-ticket search, a campaign builder, social posts and a social-inbox agent, a website page generator. |
| Multi-language / Arabic | 4.5 | 3 | Arabic text normalisation in routing, the cache and menu search; Arabic brand scrub in gateway guardrails; Saudi business wording; Arabic TTS; ar.po files. Odoo only tells the model to answer in the user's language. |
| Observability, evals & tests | 3.5 | 3.5 | Ours: run audit with a grounding label, latency and feedback; about 453 Python tests (182 agent, 98 chatbot, 98 command, 32 scan, 18 client, 13 gateway, 12 other), but none for ab_ai_base, ab_ai_ui, central billing or any JS; the eval harness scores a retired runtime. Odoo: strong unit and OAuth tests and visible agent steps, but no run analytics. |
| Performance | 3 | 3.5 | Ours: answer cache, prompt caching, tool routing; but the run is synchronous, the transcript is one growing string, and the record context reads every field. Odoo: asynchronous loop, RAG fetched on the first round only, records truncated before they go to the model. |
| Multi-tenant SaaS concerns | 4 | 2 | Ours: tenant tokens, entity_ref protected against tampering, plan ceilings, provisioning push. Odoo is single-database with IAP. Ours is lowered by the tenant guard that blocks ab_ai_base (confirmed by code) and by O1 (no real-provider run through the gateway yet). |

## Concept mapping

| Odoo concept | Our equivalent | Note |
|---|---|---|
| **ai.agent (persona backed by a partner record)**<br>`ai/models/ai_agent.py (AIAgent, _get_instructions, _build_rag_context)` | **ai.agent persona (no partner record); the Discuss bot partner lives in ab_ai_chatbot**<br>`saas-share/ab_ai_agent/models/ai_agent.py; saas-client/ab_ai_chatbot/models/discuss_channel.py` | Ours adds plan caps, a cost cap per run and use_all_capabilities; Odoo adds allowed_agent_ids for delegation and per-agent sources. Paths: Odoo refs are relative to odoo-20.0/odoo/addons/, ours to clouderps-apps/ (odoo-18/ is our Odoo 18 core). |
| **ai.skill (description advertised; instructions and tools loaded on demand by load_skills)**<br>`ai/models/ai_skill.py; ai/models/ai_tool.py#_ai_tool_load_skills` | **ai.agent.topic (instructions + tool_ids, auto_attach), with keyword routing**<br>`saas-share/ab_ai_agent/models/ai_agent_topic.py; services/runtime.py#_route_tools` | Naming clash: our ai.agent.skill is a prompt template (context_model, surfaces, requires_record_context), closer to Odoo's ai.prompt.button. Our topics are always loaded, never on demand. |
| **ir.actions.server use_in_ai tools with ai_tool_schema**<br>`ai/models/ir_actions_server.py#_ai_tool_run,_check_ai_tool_schema; ai/utils/tools_schema/validators.py` | **ai.agent.tool + the module-level _REGISTRY; dispatch_kind python\|server_action**<br>`saas-share/ab_ai_agent/models/ai_agent_tool.py#is_invocable_by; services/tool_dispatcher.py#dispatch,_dispatch_server_action` | Group checks already exist on our side (Odoo 18 run() enforces groups_id; dispatch checks tool group_ids). Missing: argument validation at dispatch, confirm-first for writing states, active-record context, seeds and tests (G16). |
| **Built-in tools on ai.tool (search, read_group, get_fields, get_models, compute_date, get_menus, get_menu_details, open_menu_list/kanban/pivot/graph, run_view_action, compute_report_measures, read_binary_content, prepare_record_previews, update_records, create_records)**<br>`ai/models/ai_tool.py (24 _ai_tool_* methods, incl. _ai_tool_compute_date, _ai_tool_read_binary_content, _ai_tool_prepare_record_previews, _ai_tool_update_records); ai/data/ir_actions_server_data.xml` | **search/read_group/get_fields → find_records, count_records, read_record, query_data, explain_screen; compute_date → date_reference; get_menus/get_menu_details → find_menu, list_my_apps; run_view_action/open_menu_* → open_action, navigate, open_list/open_pivot/open_graph; compute_report_measures → closest is query_data; read_binary_content → none (G46); prepare_record_previews → none (G48); update_records/create_records → single-record update_record/act_on_record (G47)**<br>`saas-share/ab_ai_agent/services/generic_data.py; services/query_data.py; services/tool_dispatcher.py (date_reference, find_menu, list_my_apps, open_action, open_list/pivot/graph); services/agent_actions.py#update_record,act_on_record` | Same principle: tools run as the user and blocked models are refused. Ours returns render envelopes (charts, KPI tiles). |
| **ai.session + ai.session.event (durable state machine)**<br>`ai/models/ai_session.py (loop_state, _handle_tool_calls, _resume_pending_interaction)` | **ai.agent.run (audit row per run) + ai.chat.conversation/message (tenant module) + ai.agent.pending.action**<br>`saas-share/ab_ai_agent/models/ai_agent_run.py; saas-client/ab_ai_chatbot/models/ai_chat.py` | Our run ends when a write is proposed; Confirm executes outside the loop and the model does not see the result. ab_ai_chatbot also still carries a legacy runtime (G49). |
| **waiting_confirmation + resume_token / auto_confirm**<br>`ai/utils/ai_utils.py#make_confirmation_request_preview; ai/controllers/thread.py#resume_pending_interaction` | **ai.agent.pending.action (random key, 15-minute TTL, idempotent; tool_code and agent_run_id fields, agent_id missing)**<br>`saas-share/ab_ai_agent/models/ai_agent_pending_action.py#propose,resolve` | We deliberately have no 'Always approve'. But the legacy chatbot write tools bypass this model and hand their confirmation key to the LLM (G45), and resolve() skips the gates (G02). |
| **ask_user_question (choice question that pauses the run)**<br>`ai/models/ai_tool.py#_ai_tool_ask_user_question` | **need_info text from create_record; ambiguity questions in ab_ai_command; SuggestionChips**<br>`saas-share/ab_ai_agent/services/agent_actions.py#_required_missing; saas-share/ab_ai_command/services/resolvers.py` | We have no structured choice tool (G12). |
| **Client tools (do_action, show_view, adjust_view/adjust_search) + current view info**<br>`ai/models/ai_tool.py#_ai_tool_adjust_search; ai/static/src/core/web/search_model_patch.js; ai/static/src/core/web/with_search_patch.js` | **navigate + open_list/open_pivot/open_graph + aiNavigator.sanitizeDirective + AiCursor; ai.screen.context (sends domain, group-bys and facets, validated on the server)**<br>`saas-share/ab_ai_agent/services/navigate.py; services/tool_dispatcher.py#_builtin_open_list,_builtin_open_pivot,_builtin_open_graph; static/src/services/screen_context_service.js; models/ai_screen_context.py#_domain_ok` | We already open filtered, grouped and pivot views with chosen measures. Missing: in-place adjustment of the open view, and field validation of the model's domains in open_* (G17). |
| **ai.composer (UI surface key mapped to an agent) + ai.prompt.button**<br>`ai/models/ai_composer.py; ai/models/ai_prompt_button.py` | **ai.agent surface_ids + ai.agent.skill (context_model, surfaces) + starters built from the user's menus**<br>`saas-share/ab_ai_agent/models/ai_agent_skill.py; static/src/web/chatter_patch.js` | No per-model chips are shown yet (G23). Editor and composer surfaces exist natively in Odoo 18 CE but route to Odoo IAP (G24). |
| **ai.agent.source + ai.embedding + ai.embedding.mixin (pgvector 1536, HNSW)**<br>`ai/models/ai_agent_source.py; ai/models/ai_embedding.py; ai/orm/field_vector.py` | **ai.semantic.index (768-dim, HNSW or JSON fallback) + ai.chat.fact + ai.agent.knowledge.digest + kb_search over ab_knowledge_base_* packs**<br>`saas-share/ab_ai_base/models/semantic_index.py; saas-client/ab_ai_chatbot/models/chat_fact.py; saas-share/ab_ai_agent/models/ai_agent_knowledge_digest.py; saas-theme/ab_knowledge_base_ai/models/kb_tools.py` | No per-agent sources and no ingestion pipeline. Citations exist only as a stub (services/citation.py). |
| **IAP odoo_ai transport (call_odoo_ai) + usage tag**<br>`ai/utils/ai_utils.py#call_odoo_ai_transport` | **ab_ai_gateway (central) + ab_ai_client ai.client.config.call_ai + llm_adapter (gateway → direct → simulation)**<br>`saas-ai/ab_ai_gateway/models/ai_gateway_service.py; saas-client/ab_ai_client/models/ai_client_config.py; saas-share/ab_ai_agent/services/llm_adapter.py#call_llm` | Our feature names are a closed Selection, unlike Odoo's free usage string (G05). In the default 'auto' mode, a gateway refusal falls back to the tenant's own key (G07). |
| **IAP credits**<br>`ai/data/iap_service_data.xml` | **ai.plan / ai.plan.subscription / ai.tenant.budget / ai.usage.local.budget / ai.usage.price.book (+ central ai.token.pricing)**<br>`saas-ai/ab_ai_plan/models/ai_plan_subscription.py; saas-share/ab_ai_agent/models/ai_usage_local_budget.py; saas-share/ab_ai_agent/models/ai_usage_price_book.py` | Ours is richer (limits per company, user, agent and surface, SAR billing, overage) but has accuracy bugs and two price tables (G06, G08). |
| **Provider-neutral parts messages (TextPart, ToolCallPart, ToolResultPart)**<br>`ai/utils/types.py` | **A single growing string transcript, with provider-native tool schemas**<br>`saas-share/ab_ai_agent/services/runtime.py#run; saas-share/ab_ai_base/models/ai_service.py#_tools_for_openai,_tools_for_anthropic,_tools_for_gemini` | The main architectural difference in the agent loop (G10). |
| **Layered instructions + <odoo_current_context> appended to the user turn**<br>`ai/models/ai_agent.py#_get_instructions; ai/models/ai_session.py#_get_context_input` | **_compose_system_prompt: stable prefix, CACHE_BREAK, then the volatile part**<br>`saas-share/ab_ai_agent/services/runtime.py#_compose_system_prompt` | Same idea. Ours adds explicit provider caching, but it is off on fresh installs (G09). |
| **web_search tool + [WEB_SOURCE:uuid] citations**<br>`ai/models/ai_tool.py#_ai_tool_web_search; ai/utils/ai_citation.py` | **allow_web_grounding flag (stub)**<br>`saas-share/ab_ai_agent/models/ai_agent.py` | Missing (G18). |
| **ai_fields (field-level prompts, cron fill, on-demand button)**<br>`ai_fields/models/models.py#_fill_ai_field,get_ai_field_value; ai_fields/models/ir_model_fields.py#_cron_fill_ai_fields; ai_fields/data/ir_cron_data.xml` | **None**<br>`-` | Missing (G30). |
| **ir.actions.server state 'ai' + 'Update with AI' (evaluation_type 'ai_computed')**<br>`ai/models/ir_actions_server.py#_ai_action_run; ai_server_actions/models/ir_actions_server.py` | **None**<br>`-` | Missing (G31). |
| **base.automation.ai_agent_id + ai.automation.trigger schedules + run inbox**<br>`ai_agentic/models/base_automation.py; ai_agentic/models/ai_automation_trigger.py; ai_agentic/models/ir_actions_server.py#_ai_action_run_agent` | **Fixed crons: ai.report daily report, knowledge digest**<br>`saas-client/ab_ai_client/models/report_generator.py; saas-share/ab_ai_agent/data/ir_cron_data.xml` | We cannot run user-defined agents on triggers or schedules (G32). ai_agentic is opt-in, not auto-install. |
| **ai_agentic Self Update skill (agent edits its own ai.* configuration)**<br>`ai_agentic/data/ai_skill_data.xml; ai_agentic/models/ai_tool.py#_check_tool_scope; ai/utils/ai_utils.py#AI_MODELS_BLOCKLIST` | **ab_ai_agent_config: confirm-first changes to a whitelisted set of business settings**<br>`saas-share/ab_ai_agent_config/__manifest__.py` | Different scope: Odoo's agent configures itself; ours configures the company's ERP settings, only after Confirm. Never automation-safe. |
| **ai_mcp (/mcp server + OAuth 2.1 + 'mcp' API-key scope + initial-context tool)**<br>`ai_mcp/controllers/mcp_controller.py; ai_mcp/controllers/oauth_server_controller.py; ai_mcp/models/ai_mcp_request_dispatcher.py; ai_mcp/models/ai_tool.py#_ai_tool_mcp_retrieve_initial_context; ai_mcp/models/res_users_description.py` | **ab_api_base (JWT scopes, @api_route, OpenAPI/Swagger)**<br>`saas-share/ab_api_base/controllers/api.py#_auth_token,register_scope_validator` | ab_api_base is the right foundation. Odoo 18's auth='bearer' has no scope parameter (odoo-18/odoo/addons/base/models/ir_http.py:204). |
| **ai_livechat (agent as livechat operator, forward_operator) + ai_social (agent on social DMs with handoff and enable conditions) + preview cards**<br>`ai_livechat/models/im_livechat_channel_rule.py; ai_livechat/controllers/main.py#forward_operator; ai_social/models/ai_agent.py#_ai_tool_social_livechat_add_human; ai_social/models/im_livechat_channel.py; ai_website_livechat/models/ai_preview_card_mixin.py` | **ghaima.sa sales chatbot (central) + embed widget**<br>`saas-ai/ab_ghaima_website_chatbot/controllers/main.py; saas-ai/ab_ghaima_ai_embed/controllers/widget.py` | The website chatbot calls the provider directly (per-worker rate limits only); embed turns are logged and guardrailed via the gateway but have no budget. Neither has ERP data or human handoff. WhatsApp is outbound only (G26). |
| **html editor ChatGPTPlugin / mail_composer_chatgpt / /prompt blocks**<br>`ai/static/src/editor/plugins/chatgpt_plugin.js; ai/static/src/mail_composer_chatgpt.js; ai/models/mail_render_mixin.py` | **Odoo 18 CE's native ChatGPT, translate and alternatives dialogs and the mail_composer_chatgpt widget, plus the website configurator OLG call — all routed to Odoo's IAP OLG endpoint**<br>`odoo-18/addons/html_editor/controllers/main.py#generate_text; odoo-18/addons/mail/static/src/core/web/mail_composer_chatgpt.js; odoo-18/addons/website/models/website.py#_OLG_api_rpc` | Tenant text and database.uuid leave our platform unmetered, under Odoo branding. Contain via ICP on day one; one inherited generate_text then gives metered editor and composer AI (G24). |
| **ir.attachment._ai_read + read_binary_content + file-viewer prompts**<br>`ai/models/ir_attachment.py#_ai_read; ai/models/ai_tool.py#_ai_tool_read_binary_content; ai/data/ai_composer_data.xml` | **None: chat attach sends files only to the scan-docs extractor**<br>`saas-client/ab_ai_chatbot/static/src/js/ai_agent_chat_attach_patch.js; saas-share/ab_ai_agent/controllers/agent_chat.py` | Missing (G46). |
| **mail.call.artifact transcription / voip_ai summaries / realtime dictation**<br>`ai/models/mail_call_artifact.py; voip_ai/models/voip_call.py#_generate_call_summary; ai/static/src/core/realtime_client.js` | **Live voice: /ai_agent/voice/transcribe and /speak, hands-free mode, voice confirm**<br>`saas-share/ab_ai_agent/controllers/voice.py; static/src/voice/voice.js` | We are ahead on conversational voice; we have no transcription of recordings (G28). |
| **ai_documents auto-sort + ai_documents_account bill tools**<br>`ai_documents/models/documents_document.py#_ai_setup_sort_actions; ai_documents/models/ir_actions_server.py` | **ab_scan_docs AI-vision extraction + autopilot + portal**<br>`saas-client/ab_scan_docs/models/scanned_document.py#_run_autopilot; models/scan_ai_config.py#call_ai; controllers/portal_document.py` | We are ahead on extraction. Folder auto-sort does not apply (Community has no Documents app). |
| **ai_account_reports report tools + Auditor agents**<br>`ai_account_reports/models/ai_tool.py#_ai_tool_accounting_report_get_values; ai_account_reports/data/ai_audit_agents.xml` | **ab_account_reports_ai get_ai_insights (one-shot, on the legacy ab_ai_client)**<br>`saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py` | We need report tools the agent can call, limited to audited reports (G34). |
| **Model _explanation attribute / ir.actions explanation (descriptions written for the LLM)**<br>`ai/models/ai_tool.py#_ai_tool_get_models; ai/models/ai_agent.py#_get_available_menus` | **Knowledge digest + find_menu glossary (Arabic→English) + explain_screen**<br>`saas-share/ab_ai_agent/services/tool_dispatcher.py#_MENU_GLOSSARY,_builtin_explain_screen` | Odoo 20 core API; on Odoo 18 we rebuild this as data. |

## Gap matrix

| ID | Capability | Status | Priority | Impact | Effort |
|---|---|---|---|---|---|
| G01 | Data tools respect company, branch and access rules | partial | P0 | high | M |
| G02 | Confirm re-checks every gate; confirmations are bound to their proposal | partial | P0 | high | M |
| G03 | Correct identity on bot, public and shared surfaces | partial | P0 | high | M |
| G04 | Keep cost telemetry and secrets private | partial | P0 | high | S |
| G05 | Open feature names for usage attribution | partial | P0 | high | S |
| G06 | Accurate metering, cost caps and overage billing | partial | P0 | high | M |
| G07 | Every AI call metered and governed, including public surfaces | partial | P1 | high | M |
| G08 | Working provider IDs, resilience, one model catalogue, structured output | partial | P0 | high | M |
| G09 | Prompt caching enabled by default | ours_ahead | P0 | medium | S |
| G10 | Provider-neutral message transcript (messages[] with tool_call/tool_result parts) | partial | P1 | high | L |
| G11 | Durable runs that survive restarts and resume after pauses | partial | P2 | medium | L |
| G12 | Structured clarifying questions (choices, multi-select, free text) | partial | P1 | medium | S |
| G13 | Topics loaded on demand to keep the prompt and tool list small | partial | P2 | medium | M |
| G14 | Multi-agent delegation | missing | P3 | low | M |
| G15 | Agents that update their own configuration | partial | P3 | low | M |
| G16 | Server actions as tools, with arguments validated against their schema | partial | P1 | medium | M |
| G17 | Shape the user's current view (filters, group-bys, measures) | partial | P1 | medium | M |
| G18 | Web search grounding with citations | missing | P2 | medium | M |
| G19 | Image generation and editing | missing | P3 | low | M |
| G20 | Per-agent knowledge sources: ingestion, embeddings, retrieval, citations | partial | P1 | high | L |
| G21 | Sessions stored in the core, with structured history and summarisation | partial | P1 | high | M |
| G22 | Retention for runs and usage logs | missing | P0 | medium | S |
| G23 | Prompt chips per model and prompt packs per app | partial | P1 | medium | M |
| G24 | AI in the editor and mail composer (draft, rewrite, translate) through our gateway | partial | P0 | high | M |
| G25 | 'Ask AI' in the command palette and systray | partial | P2 | low | S |
| G26 | AI agent on livechat, website and social-inbox channels, with human handoff | partial | P2 | medium | L |
| G27 | AI website builder (page generation, brand kit, SEO, webforms) | missing | P3 | low | XL |
| G28 | Transcribing recordings and dictation (we are ahead on live voice) | ours_ahead | P3 | low | M |
| G29 | Document extraction on one shared policy path | ours_ahead | P0 | high | S |
| G30 | Fields filled by AI prompts | missing | P2 | medium | L |
| G31 | AI server action type and 'Update with AI' | missing | P2 | medium | M |
| G32 | Agents triggered by events or schedules, with a run inbox | missing | P2 | high | L |
| G33 | MCP server for external AI clients | missing | P2 | medium | L |
| G34 | Agent tools for accounting reports, and report insights that work | partial | P1 | high | M |
| G35 | Lead capture and summaries; sales email drafting | partial | P2 | medium | M |
| G36 | HR assistant tools and HR email drafting | partial | P2 | medium | M |
| G37 | Timesheet assistant and project prompts | partial | P3 | low | M |
| G38 | Similar tickets and reply drafts | missing | P3 | low | M |
| G39 | Campaign, mass-mailing and social content drafting | missing | P3 | low | L |
| G40 | Operational tools for purchase, stock and POS (we are ahead) | ours_ahead | P3 | medium | S |
| G41 | Arabic-first behaviour (we are ahead) | ours_ahead | P2 | medium | S |
| G42 | Test coverage and evals of the production runtime | partial | P1 | high | M |
| G43 | Lean context per hop | partial | P1 | medium | S |
| G44 | Tenant provisioning reliability for the AI stack | partial | P0 | high | S |
| G45 | Every write needs a human click (no model self-confirmation) | partial | P0 | high | S |
| G46 | Chat about files and record attachments | missing | P1 | high | M |
| G47 | Bulk create and update in one confirmation | partial | P2 | medium | M |
| G48 | Clickable records in answers | missing | P2 | medium | S |
| G49 | One runtime; no global state swapped per request | partial | P1 | medium | M |
| G50 | Per-app integrations in auto-install bridges | partial | P1 | medium | M |

## Gap details

### G01 — Data tools respect company, branch and access rules

`partial` · `P0` · Security

**Odoo:** All data tools run in a non-sudo env through the ORM (_ai_tool_search and _ai_tool_read_group use has_access plus record rules). ir.* models and AI_MODELS_BLOCKLIST are refused. Domains are parsed with literal_eval and capped at 5000 characters.

**Ghaima:** query_data runs as the user through Model._read_group, whose _search is overridden by ab.branch.mixin, so it is already branch-scoped (query_data.py:117; odoo-18/odoo/models.py:2006; ab_branch_base/models/branch_mixin.py:40-60). Defects: _builtin_data_analysis runs raw SQL on pos_order, sale_order and account_move with no company, branch, ACL or record-rule filter (tool_dispatcher.py:840-905); it also buckets days on UTC timestamps (wrong for Asia/Riyadh), sums amount_total across currencies under the company currency, and returns str(e) to the model. ab_ai_chatbot fact marts (fact_query) are materialized views that bypass record rules. query_data skips generic_data.model_blocked. semantic_search compiles extra_domain under sudo, but hits are re-filtered as the user (tool_dispatcher.py:1369), so the risk is an inference oracle, not leaked records. _record_context_block reads chatter via record.sudo().message_ids (runtime.py:1322).

**Recommendation:** Rebuild data_analysis on Model._read_group as the user, with the user's tz in context and totals grouped by currency (or converted to the company currency); return a generic error and log the exception; keep the deterministic envelope. Call model_blocked in query_data. Validate semantic_search extra_domain fields as the user. Read chatter as the user. No branch bridge for query_data. For fact_query only, add ab_ai_chatbot_branch (saas-branches, auto_install on ab_branch_base + ab_ai_chatbot), or rebuild the marts on _read_group and drop the bridge. Tests: query_data and data_analysis are branch-scoped for a branch-restricted user; a 23:30 Riyadh order lands on the correct day; two currencies show per-currency totals.

`ai/models/ai_tool.py#_ai_tool_read_group,_check_agent_model_access,_parse_domain` `ai/utils/ai_utils.py#AI_MODELS_BLOCKLIST` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_data_analysis,_DA_METRICS,_builtin_semantic_search` `saas-share/ab_ai_agent/services/query_data.py#query_data` `saas-share/ab_ai_agent/services/runtime.py#_record_context_block` `saas-client/ab_ai_chatbot/services/fact_query.py` `saas-branches/ab_branch_base/models/branch_mixin.py`

### G02 — Confirm re-checks every gate; confirmations are bound to their proposal

`partial` · `P0` · Human-in-the-loop

**Odoo:** Confirmation pauses the session's tool batch. Resuming validates the resume_token with compare_digest and continues the same tool call, with tools limited to the agent's skills, su=False and a savepoint. (Odoo's own gap: _ai_tool_run runs server-action code via _run_action_code_multi, so the action's group_ids are not checked on that path.)

**Ghaima:** ai.agent.pending.action.resolve() calls the tool function directly with agent=None, skipping actions_enabled, plan policy, tool group_ids and allow_write_actions. tool_code and agent_run_id already exist on the pending action (ai_agent_pending_action.py:40, :45), but agent_id does not, and no propose() caller passes agent_run (agent_actions.py:232; tool_dispatcher.py:1185, :1271). A second, unaudited confirm path: ab_ai_chatbot execute_action (ai_chat.py:596-660) re-invokes a tool with confirm=True using client-sent tool_name and args; _replay_or_execute checks only that the key is 'proposed' (sudo lookup on tool + key, chat_action_log.py:56-62), not the user, conversation, target or args, with no TTL, so a proposal for record A can execute on record B. screen_button and act_on_record can press account.move 'Post' for any invoicing user. HR roll-call tools (requires_pii=True) are offered to the default agent (allow_pii=False) and always refused. The model-driven self-confirm path is G45.

**Recommendation:** Add only agent_id and pass agent and agent_run from every propose() call site. Give dispatch() a keyword-only confirmed: bool, outside the arguments (dispatch strips _ai_* keys, tool_dispatcher.py:90), that forwards _ai_confirmed=True to the tool. resolve() looks up ai.agent.tool by tool_code, browses agent_id and calls dispatch(), so is_invocable_by, PII and write gates, actions_enabled and plan policy are re-checked at click time. Route chatbot confirm chips through /ai_agent/action/confirm and delete execute_action; until then bind the log row to create_uid == env.uid and the conversation, compare a hash of target and args, and expire it after 15 minutes. Add a protected-methods registry (account.move/account.payment action_post, hr.payslip done) that no agent path may call. Filter requires_pii tools in _resolve_tools when the agent disallows PII, and set the names-only HR roll-call tools to requires_pii=False (still HR-role gated). Tests for mismatched target, other user and expiry.

`ai/models/ai_session.py#_resume_pending_interaction,_handle_tool_calls` `ai/controllers/thread.py#resume_pending_interaction` `ai/models/ir_actions_server.py#_ai_tool_run` `saas-share/ab_ai_agent/models/ai_agent_pending_action.py#propose,resolve` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch,_builtin_screen_button,_builtin_record_action` `saas-share/ab_ai_agent/services/runtime.py#_resolve_tools` `saas-client/ab_ai_chatbot/models/ai_chat.py#execute_action` `saas-client/ab_ai_chatbot/models/chat_action_log.py` `saas-client/ab_ai_chatbot/services/tools/actions.py#_replay_or_execute`

### G03 — Correct identity on bot, public and shared surfaces

`partial` · `P0` · Security

**Odoo:** The webhook rebuilds the env as the original user with su=False and re-validates company access. Channel lookup is non-sudo; discuss.channel.ai_agent_id is groups=NO_ACCESS; guests get explicit guest context; previews are filtered by user_has_access.

**Ghaima:** The Discuss bot runs on a sudo conversation and, when the author has no res.users (a guest or external partner), on the SUPERUSER env, then posts str(e) into the channel (verified, discuss_channel.py ~L190-220). /ai_chat/shared/<token> links never expire. ghaima.sa chatbot.js renders model output with innerHTML. /entity/express/status/<id> does not check is_express, so any tenant's state can be looked up. conversation_lookup can show the display_name of a record the user cannot read.

**Recommendation:** Wave 1a: never run the bot without an internal asker (reply with a localized sign-in message), never on the SUPERUSER env; log exceptions and reply generically. Wave 1b: share_expires_at (default 7 days) and revoke links on delete; render chatbot replies with textContent plus safe markdown; check is_express and use a signed status token; call check_access('read') before find_or_create_for_record.

`ai/controllers/thread.py#completion_result_ready,_validate_session_request_company_access` `ai/models/ai_session.py#_get_request_context_snapshot` `ai/models/discuss_channel.py` `saas-client/ab_ai_chatbot/models/discuss_channel.py#_ai_bot_do_reply` `saas-client/ab_ai_chatbot/controllers/chat_controller.py` `saas-ai/ab_ghaima_website_chatbot/static/src/js/chatbot.js` `saas-ai/ab_ai_express_signup/controllers/express.py` `saas-share/ab_ai_agent/controllers/agent_chat.py#conversation_lookup`

### G04 — Keep cost telemetry and secrets private

`partial` · `P0` · Security

**Odoo:** Sessions, events and embeddings are readable by admins only. The webhook secret field is NO_ACCESS. Usage is metered on Odoo's server and never shown to users.

**Ghaima:** /ai_agent/usage/live returns the company's spend (read with sudo) to any internal user, and any logged-in user can join the plain string bus channel ai.usage.live.<company_id> for any company. Every envelope carries usage.cost_usd. Gemini vision (ai_service.py:1010) and embed (:1286) put ?key= in the URL; vision logs the exception and re-raises its text as a UserError (:1048-1050), so the key can reach the end user's screen, not only the logs. Text chat and speech already use the x-goog-api-key header (:739, :1176, :1238), and the gateway already scrubs secrets (_scrub_secrets, gateway_api.py:312, since 2026-06-22). ai.client.config.entity_token is readable over RPC by group_ai_report_user.

**Recommendation:** Restrict usage_live to AI Manager or system users; send the live meter on a res.company record channel checked against groups in a _build_bus_channel_list override; strip cost from envelopes for non-admins. Move both Gemini calls to the x-goog-api-key header; never put exception text into a UserError; move _scrub_secrets into ab_ai_base and add a log filter that redacts key=. Set groups='base.group_system' on entity_token. Acceptance: grep finds no '?key=' in ab_ai_base, and a forced HTTP error shows no key in the log or the UI.

`ai/security/ir.access.csv` `ai/models/ai_session.py (request_webhook_secret groups NO_ACCESS)` `saas-share/ab_ai_agent/controllers/agent_chat.py#usage_live` `saas-share/ab_ai_agent/services/meter.py#emit_live` `saas-share/ab_ai_base/models/ai_service.py#_call_gemini_vision,_call_gemini_embed` `saas-ai/ab_ai_gateway/controllers/gateway_api.py (_scrub_secrets)` `saas-client/ab_ai_client/models/ai_client_config.py (entity_token)`

### G05 — Open feature names for usage attribution

`partial` · `P0` · Gateway

**Odoo:** The client sends a free-form usage string ('agent:<xmlid>', 'ai_field', 'web_search', channel_name). Attribution and billing happen on the server, and no closed list is enforced on the client.

**Ghaima:** ai.usage.log.feature is a closed Selection, and the plan's allowed_features lists are closed too. Tenants send business_query, pos_suggestions, kitchen_prediction, kitchen_performance, anomaly_detection, dashboard_insights and accounting_report_insight. Writing the log then raises ValueError, after the provider has been billed when there is no plan. As a result mobile AI, dashboard insights and accounting-report insights never work through the gateway.

**Recommendation:** Change feature to Char and add a mapping model (feature → bucket: chat, analytics, documents, voice, compose, automation, mcp, custom). Plans gate on buckets; unknown names fall into 'custom'. Write the log row as 'pending' before the provider call and update it afterwards. Add a gateway test for every feature string the tenants send. Deploy central before tenants.

`ai/models/ai_agent.py#_get_usage_string` `ai/utils/types.py (CompletionOptions.usage)` `saas-ai/ab_ai_gateway/models/ai_usage_log.py` `saas-ai/ab_ai_plan/models/ai_plan.py#get_allowed_features_list` `ghaima-api/ab_mobile_ai_api/controllers/ai_query.py` `saas-dashboard/ab_dynamic_dashboard/models/dashboard_ai_bridge.py` `saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py`

### G06 — Accurate metering, cost caps and overage billing

`partial` · `P0` · Cost control

**Odoo:** IAP credits are counted per call on Odoo's server, so the client does no cost arithmetic.

**Ghaima:** Cached tokens are added to total_tokens again and charged twice in ai.usage.price.book.estimate_cost. The direct path never sets usage['cost_usd'], so ai.agent.max_cost_usd never fires and run.cost_usd stays 0. Models without a price row (gpt-3.5-turbo, gpt-4, claude-3-sonnet/haiku, gemini-flash-latest) cost $0, so budgets never fill. _cron_generate_overage_invoices has no ir.cron record. The credit bridge writes two rate_limited rows per blocked call and prints '$' for SAR.

**Recommendation:** Normalize usage once in ab_ai_base into (input_uncached, cached, output) and use one cost function for the gateway and the direct path. On the direct path, compute cost locally from the synced price book so the per-run cap works. When a budget is enforced and the model has no price row, block the call. Add the missing overage cron, remove the duplicate rate-limit log, use the plan currency symbol, and add tests in ab_ai_plan.

`ai/utils/ai_utils.py#call_odoo_ai (credits via iap)` `ai/data/iap_service_data.xml` `saas-share/ab_ai_agent/models/ai_usage_price_book.py#estimate_cost` `saas-share/ab_ai_agent/services/meter.py#record` `saas-share/ab_ai_agent/services/runtime.py (cum_cost)` `saas-ai/ab_ai_gateway/models/ai_token_pricing.py` `saas-ai/ab_ai_plan/models/ai_plan_subscription.py#_cron_generate_overage_invoices` `saas-ai/ab_ai_plan_credit_bridge/models/ai_gateway_service.py`

### G07 — Every AI call metered and governed, including public surfaces

`partial` · `P1` · Gateway

**Odoo:** There is one transport (IAP). The server chooses the model, the client sends only the usage tag and flags, and every call costs credits.

**Ghaima:** Embed widget turns go through ai.gateway.service.process_request (guardrails + ai.usage.log) as entity_ref 'embed:<id>' with feature 'website_chatbot' (widget.py:340-370), but no plan or budget exists for embed:*, and the rows are lumped with the website chatbot. The ghaima.sa chatbot calls ab_ai_base directly with no usage log, guardrails or budget; it has a per-IP rate limit (20/min) and message and size caps, held in memory per worker (main.py:36-85), and the client controls history. /api/v1/ai/embed has no quota, rate limit or log. Express signup uses a shared entity_ref with no metering. resolve_model_for accepts the tenant's model_override unconditionally. max_tokens and temperature are ignored (O2). In the default 'auto' llm_mode, llm_adapter falls back to the tenant's own provider key after a gateway refusal (quota, plan) whenever an active ai.provider.config exists (llm_adapter.py:203-215), so the F9 bypass is open in the agent too, not only in scan_docs. call_llm has no feature parameter; the feature comes from the agent's surface ('chat' without an agent).

**Recommendation:** First, the routing policy (ships with G44 in Phase 1): in llm_adapter a gateway refusal is final unless an explicit ICP opt-in exists, only transport errors fall back, and provisioning pushes llm_mode='gateway' to linked tenants; add a feature= keyword to call_llm. Then (Phase 2): platform budget rows with hard daily USD caps for embed:*, express_signup and website_chatbot, with a separate feature for embed; route the website chatbot through process_request with server-held history; meter /embed; gate model_override by the plan's allowed model classes; forward max_tokens and temperature.

`ai/utils/ai_utils.py#call_odoo_ai_transport` `ai/models/ai_session.py#_get_model_round_options` `saas-share/ab_ai_agent/services/llm_adapter.py#call_llm,_feature_for` `saas-ai/ab_ghaima_ai_embed/controllers/widget.py` `saas-ai/ab_ai_gateway/controllers/gateway_api.py (/embed)` `saas-ai/ab_ghaima_website_chatbot/controllers/main.py` `saas-ai/ab_ai_gateway/models/ai_prompt_template.py#resolve_model_for` `saas-client/ab_scan_docs/models/scan_ai_config.py#call_ai`

### G08 — Working provider IDs, resilience, one model catalogue, structured output

`partial` · `P0` · LLM providers

**Odoo:** Provider handling is centralised on Odoo's AI server. provider_data (e.g. thinking signatures) is passed through unchanged. A cron (_cron_update_deprecated_embedding_models) migrates deprecated models. CompletionOptions.schema provides JSON-schema output.

**Ghaima:** Every Claude model ab_ai_base offers, including the default claude-3-5-sonnet-20241022, is retired as of 2026-10-08 (ai_config.py:105-112; same IDs in ab_ai_gateway token_pricing_data.xml), so the Claude provider fails on every call today. _call_claude also always sends temperature, which current Claude models reject (any value on Opus 5.5; only the default on Sonnet and Haiku 5.5). No retry or backoff on 429/5xx. _call_gemini forces thinkingBudget=0 for every gemini-2.5* model, vision path included (ai_service.py:722, :1018); whether gemini-2.5-pro accepts this is unverified. fallback_provider_id is used only on central. No response-schema parameter. The direct path ignores the agent's temperature and model_class. Model prices live in two tables: ai.usage.price.book (tenant, synced nightly from central, already has model_class and effective_from/to) and ai.token.pricing (central).

**Recommendation:** Phase 1 hotfix: replace the Claude selection and price rows with current IDs (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5; confirm against Anthropic's docs at implementation), stop sending temperature to Claude, and migrate stored ai.provider.config.claude_model values. Phase 2: jittered retry (429/500/502/503/529, honour Retry-After, ≤2 retries); add deprecated_on and replacement_model to ai.usage.price.book and fold ai.token.pricing into it (or derive one from the other) so gateway and direct path read one table — no new catalogue model; a health-check and remap cron over price-book rows; per-model thinking config; response_schema per provider (OpenAI json_schema, Gemini responseSchema, Anthropic forced tool); pass temperature (where the model accepts it), max_tokens and model_class on the direct path.

`ai/utils/types.py (CompletionOptions.schema)` `ai/models/ai_embedding.py#_cron_update_deprecated_embedding_models` `ai/utils/ai_fields_tools.py#get_ai_value` `saas-share/ab_ai_base/models/ai_service.py#call,_call_openai,_call_gemini,_call_claude` `saas-share/ab_ai_base/models/ai_config.py (claude_model)` `saas-share/ab_ai_agent/models/ai_usage_price_book.py#_cron_sync_pricebook` `saas-ai/ab_ai_gateway/models/ai_token_pricing.py` `saas-ai/ab_ai_gateway/data/token_pricing_data.xml`

### G09 — Prompt caching enabled by default

`ours_ahead` · `P0` · Performance / cost

**Odoo:** No client-side caching was found. Instructions are stable and the volatile context is appended to the user turn, which suits caching.

**Ghaima:** The design caches better than Odoo's: stable prefix, CACHE_BREAK, Anthropic cache_control, implicit caching on OpenAI and Gemini. But ab_ai_base.provider_cache_enabled defaults to False and only the 18.0.1.15.0 migration sets it, so fresh installs fold the system prompt into the user message. The digest is filtered by user group before the break, so the cached prefix differs for each group combination.

**Recommendation:** Seed provider_cache_enabled=True through noupdate data and expose it in settings. Move the group-filtered digest sections after CACHE_BREAK, or cache one digest per group set. Add a fresh-install test that asserts the system role is used and cached_tokens > 0 on the second call.

`ai/models/ai_agent.py#_get_instructions` `ai/models/ai_session.py#_get_context_input` `saas-share/ab_ai_agent/services/runtime.py#_compose_system_prompt` `saas-share/ab_ai_base/models/ai_service.py#_provider_cache_enabled` `saas-share/ab_ai_agent/migrations/18.0.1.15.0/post-migrate.py`

### G10 — Provider-neutral message transcript (messages[] with tool_call/tool_result parts)

`partial` · `P1` · Agent loop

**Odoo:** TypedDict parts (TextPart, InlineDataPart, ToolCallPart, ToolResultPart) are stored as ai.session.event metadata, with provider_data passed through. RAG runs on the first round only. Tool results go through format_tool_result.

**Ghaima:** runtime.run builds one growing user-prompt string and appends 'Tool result for X: …' truncated to 4000 characters. Every hop resends the full system prompt plus that string. The provider-native tool_result blocks are not used (the code comment says so). The Gemini MALFORMED_FUNCTION_CALL retries work around this.

**Recommendation:** Add a message list (role + parts) to ab_ai_base with a serializer per provider: OpenAI tool role, Anthropic tool_use/tool_result blocks (cache breakpoint on the last tool result), Gemini functionCall/functionResponse. Central adds 'messages_v1' to GATEWAY_CAPABILITIES and accepts messages[] on /analyze and /stream; a tenant sends messages[] only when config.has_capability('messages_v1') and otherwise keeps the string transcript. Keep the string path behind an ICP flag as fallback. Land after the provider contract tests and G08.

`ai/utils/types.py` `ai/models/ai_session.py#AiSessionEvent,_submit_agent_request` `saas-share/ab_ai_agent/services/runtime.py#run,_parse_response` `saas-share/ab_ai_base/models/ai_service.py#_tools_for_openai,_tools_for_anthropic,_tools_for_gemini,_parse_anthropic_tool_uses` `saas-ai/ab_ai_gateway/models/ai_gateway_service.py#_clean_tool_schemas,GATEWAY_CAPABILITIES` `saas-client/ab_ai_client/models/ai_client_config.py#has_capability`

### G11 — Durable runs that survive restarts and resume after pauses

`partial` · `P2` · Agent loop

**Odoo:** ai.session.loop_state (waiting_model/confirmation/answer/client_result/external_result/child) is guarded by SQL CHECK constraints. Requests are submitted after commit and resumed by an HMAC-verified webhook, with max_successive_calls=30 and max_tool_calls_per_call=20. Odoo has no watchdog for a lost webhook.

**Ghaima:** A synchronous ReAct loop runs inside one HTTP worker (default 6 hops, up to 20), with progress sent on the bus. Proposing a write ends the run; after Confirm the model never sees the result and cannot continue a chain such as 'create then email'.

**Recommendation:** Do not adopt Odoo's webhook model, because we call providers ourselves. Persist the run state (G10 messages) on ai.agent.run. Run long or automation jobs in the background (ir.cron _trigger, or a worker thread with a fresh cursor as the stream emitter already does) and stream progress over the bus. After Confirm, append the tool_result and resume the same run. Add a watchdog cron that fails runs stuck longer than N minutes.

`ai/models/ai_session.py#_save_and_submit_request,_continue_agent_loop,_advance_tool_batch` `saas-share/ab_ai_agent/services/runtime.py#run` `saas-share/ab_ai_agent/controllers/agent_chat.py#_make_stream_emitter,action_confirm`

### G12 — Structured clarifying questions (choices, multi-select, free text)

`partial` · `P1` · Human-in-the-loop

**Odoo:** ai_tool_ask_user_question offers 2–4 choices with multi_select and allow_free_text, sets waiting_answer and returns 'USER ANSWER:' to the model. It is forced at the round limit.

**Ghaima:** create_record returns need_info as a text list of missing fields. ab_ai_command asks about ambiguity in text (MAX_ALTERNATIVES=5). SuggestionChips exist but are not tied to a pending question.

**Recommendation:** Add a core ask_user tool that returns a 'question' render block. Its chips post the answer with a question_id as the next turn. Use it for resolver ambiguity and for create_record's missing fields, and force it when max_hops is reached.

`ai/models/ai_tool.py#_ai_tool_ask_user_question` `ai/static/src/discuss/ai_user_input_request.js` `saas-share/ab_ai_agent/services/agent_actions.py#_required_missing,create_record` `saas-share/ab_ai_command/services/resolvers.py` `saas-share/ab_ai_ui/static/src/ai_response/ai_response.js`

### G13 — Topics loaded on demand to keep the prompt and tool list small

`partial` · `P2` · Agent model

**Odoo:** Skill names and descriptions are listed in available_skills. ai_tool_load_skills adds instructions and tools to the session state on demand. Skills are typed executable or guidance; native skills cannot be changed.

**Ghaima:** Topics are attached in full every run. _route_tools picks tool groups by Arabic and English keywords. Builder tools are pruned by keyword after 8.

**Recommendation:** List topic name and one-line description in the cached prefix. Add a load_topic tool that adds the topic's instructions and tools for the rest of the conversation, and keep keyword routing as a prefetch hint. Rename internally to avoid the clash with our ai.agent.skill (a prompt template).

`ai/models/ai_skill.py` `ai/models/ai_tool.py#_ai_tool_load_skills` `ai/utils/ai_utils.py#enable_skills` `saas-share/ab_ai_agent/services/runtime.py#_route_tools,_TOOL_GROUPS` `saas-share/ab_ai_agent/models/ai_agent_topic.py`

### G14 — Multi-agent delegation

`missing` · `P3` · Agent model

**Odoo:** An agent's allowed_agent_ids enables the start_session and continue_session tools. Child sessions run in parallel, nesting depth is below 4, and _merge_child_result merges answers and attachments.

**Ghaima:** Users pick a persona; there is no delegation.

**Recommendation:** Defer. If needed later, add an ask_agent tool that calls runtime.run with the target agent as the same user, with depth ≤2 and a cost budget shared with the parent.

`ai/models/ai_tool.py#_ai_tool_start_session,_ai_tool_continue_session` `ai/models/ai_session.py#_merge_child_result` `saas-share/ab_ai_agent/controllers/agent_chat.py#list_agents` `saas-ai/ab_manager_agents/data/manager_agent.xml`

### G15 — Agents that update their own configuration

`partial` · `P3` · Agent model

**Odoo:** The ai_agentic 'Self Update' skill makes confirmed writes to the agent's system_prompt and skill_ids, creates custom guidance skills, and can bind the agent as the default composer. _check_tool_scope limits these writes to ai.* models.

**Ghaima:** The console builder is driven by people (builder_suggest gives EN/AR suggestions). ab_ai_chatbot has remember_note and remember_fact for user memory. ab_ai_agent_config changes business settings (not agent setup) after Confirm.

**Recommendation:** Defer. Later, a remember_procedure tool restricted to admins could create an is_custom topic through a pending action.

`ai_agentic/data/ai_skill_data.xml (ai_skill_self_update)` `ai_agentic/models/ai_tool.py#_check_tool_scope` `saas-share/ab_ai_agent/models/ai_agent_builder.py` `saas-client/ab_ai_chatbot/services/tools/memory.py` `saas-share/ab_ai_agent_config`

### G16 — Server actions as tools, with arguments validated against their schema

`partial` · `P1` · Tools

**Odoo:** An ir.actions.server record becomes a tool with use_in_ai, a unique ai_tool_name and ai_tool_schema (checked by validate_schema). The LLM's arguments are validated against the schema before running, in a non-sudo env, and the code returns its result through ai['result'].

**Ghaima:** _dispatch_server_action exists and appears in the tool form, but nothing seeds or tests it, and it calls action.run() with only ai_tool_arguments in the context (no active record). Group checks already exist: Odoo 18's ir.actions.server.run() enforces groups_id (odoo-18/odoo/addons/base/models/ir_actions.py:964-966) and dispatch() checks tool group_ids through is_invocable_by (tool_dispatcher.py:68-70; ai_agent_tool.py:189-196). The schema is checked only when the tool is saved; dispatch() does not validate the model's arguments, although the module docstring says it does. jsonschema is not declared for the tenant image (absent from dockerfile/requirements-odoo.txt and requirements-extra.txt); it is in saas-venv only as a dependency of openapi-spec-validator.

**Recommendation:** Validate arguments in dispatch() and return {ok: False} errors the model can act on. Add jsonschema to dockerfile/requirements-extra.txt and ab_ai_agent external_dependencies, or ship a minimal validator for the JSON-Schema subset we use. Always confirm first for server-action states that write. Pass the active record (active_model/active_id) when the tool targets one. Add a 'Use in Ghaima AI' toggle with Arabic labels, and tests.

`ai/models/ir_actions_server.py#_ai_tool_run,_check_ai_tool_schema` `ai/utils/tools_schema/validators.py` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch,_dispatch_server_action` `saas-share/ab_ai_agent/models/ai_agent_tool.py#as_llm_schema,is_invocable_by` `dockerfile/requirements-extra.txt`

### G17 — Shape the user's current view (filters, group-bys, measures)

`partial` · `P1` · Tools

**Odoo:** Browser-side tools: do_action, show_view and adjust_view. ai_tool_adjust_search applies a domain, facets and groupby through SearchModel.applyAISearch, and patches set pivot and graph measures. WithSearch.getCurrentViewInfo sends the current domain and facets each turn.

**Ghaima:** The screen descriptor already sends the search domain, group-bys and facets, validated on the server (ai_screen_context.py:103-113, _domain_ok at :166; screen_context_service.js:156-157). open_list, open_pivot and open_graph already open filtered or grouped views with chosen measures (tool_dispatcher.py:236-330). Gaps: (1) the open_* tools only literal_eval the model's domain, with no field validation; (2) the agent cannot adjust the view already open, in place.

**Recommendation:** (1) Run open_* domains, group-bys and measures through ai.screen.context._domain_ok and fields_get as the user. (2) Add an optional in-place 'adjust' directive that the client applies to the current SearchModel (check the Odoo 18 SearchModel API first), sanitised like navigate.

`ai/models/ai_tool.py#_ai_tool_adjust_search,_ai_tool_open_menu_list` `ai/static/src/core/web/search_model_patch.js` `ai/static/src/core/web/with_search_patch.js` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_open_list,_builtin_open_pivot,_builtin_open_graph` `saas-share/ab_ai_agent/models/ai_screen_context.py#_domain_ok` `saas-share/ab_ai_agent/static/src/services/screen_context_service.js` `saas-share/ab_ai_agent/static/src/services/ai_navigator_service.js#sanitizeDirective`

### G18 — Web search grounding with citations

`missing` · `P2` · Tools / RAG

**Odoo:** _ai_tool_web_search makes a nested grounded call (modes fact, summary, deep). Sources are stored under uuids and rendered from [WEB_SOURCE:uuid] citations. It can be toggled per session and is off when answers are restricted to sources. It never visits URLs the user supplies.

**Ghaima:** Only a stub: the allow_web_grounding flag and the web_grounding_calls meter column.

**Recommendation:** Implement it on the central gateway as feature 'web_search', using the provider's grounding or search tool (check current API names), so keys stay central and use is plan-gated. Add a tenant web_search tool, a SourceList block in ab_ai_ui, and an Arabic answer policy. Never fetch URLs the user supplies.

`ai/models/ai_tool.py#_ai_tool_web_search` `ai/utils/ai_citation.py#apply_web_citations` `saas-share/ab_ai_agent/models/ai_agent.py (allow_web_grounding)` `saas-share/ab_ai_agent/models/ai_usage_local_log.py (web_grounding_calls)`

### G19 — Image generation and editing

`missing` · `P3` · Tools

**Odoo:** ai_tool_generate_image takes an aspect ratio and reference images and creates attachments tracked for cleanup. It is used in the media dialog, Knowledge covers, products and social posts.

**Ghaima:** None.

**Recommendation:** Defer. Later, add gateway feature 'image' and a media-dialog patch in ab_ai_composer, mainly for restaurant menu and product images.

`ai/models/ai_tool.py#_generate_image_attachments` `ai/models/ai_attachment_vacuum.py` `-`

### G20 — Per-agent knowledge sources: ingestion, embeddings, retrieval, citations

`partial` · `P1` · RAG / knowledge

**Odoo:** ai.agent.source covers files, URLs, Knowledge articles and Documents (tree, status, is_active). ai.embedding.mixin chunks with chunk_text (~2000 characters). A triggered cron batches embeddings (100 rows / ~10k tokens) and dedups by checksum. Vectors are pgvector(1536) with an HNSW index. The top 5 chunks are added on the first round. restrict_to_sources limits answers. [SOURCE:id] citations are filtered by user_has_access. Autovacuum and the deprecated-model cron maintain the index.

**Ghaima:** ab_ai_base semantic_index (provision, embed_records, search; HNSW or JSON fallback; Gemini 768 dimensions), but no model provisions it. ai.chat.fact does hybrid pgvector and trigram search. A nightly digest gives structure only. kb_search and kb_read do plain word matching (kb_tools.py:26, :42) over 10 curated ab_knowledge_base_* packs (~93 EN/AR records). Citations are a stub because source_lookup is never passed. The ghaima_base URL guard allows only ghaima.sa (ghaima_base.py:58) and resolves DNS separately from the later requests.get (:120-136), so it cannot serve customer URLs.

**Recommendation:** New module ab_ai_knowledge (saas-share) with ai.agent.source and ai.agent.chunk on semantic_index. Source types in order: KB articles first (embed the ab_knowledge_base_* packs through the hybrid index, with ab_knowledge_base_ai as the bridge), then attachments (index_content; PDF text via pdfminer.six), then URLs through a new parameterised guard in ab_ai_base: https only, port 443, no userinfo, globally routable IP, connect to the IP already resolved, no redirects, size and content-type caps; admin only. ghaima_base keeps its fixed allow-list for the locked website excerpt. Embed via the metered gateway /embed (G07). Retrieve as the user, filtered by access to each source. Add restrict_to_sources, a Knowledge tab and wire citation.apply_numeric_citations. Acceptance: Arabic recall@5 on a KB question set.

`ai/models/ai_agent_source.py` `ai/models/ai_embedding.py#_get_similar_chunks,_cron_generate_embedding` `ai/models/ai_embedding_mixin.py` `ai/models/ai_agent.py#_build_rag_context,_get_llm_response_with_sources` `ai_knowledge/models/ai_agent_source.py` `saas-share/ab_ai_base/models/semantic_index.py#provision,embed_records,search` `saas-share/ab_ai_base/services/embeddings.py` `saas-client/ab_ai_chatbot/models/chat_fact.py` `saas-share/ab_ai_agent/services/citation.py` `saas-share/ab_ai_agent/services/ghaima_base.py#_check_url,_fetch_text` `saas-theme/ab_knowledge_base_ai/models/kb_tools.py`

### G21 — Sessions stored in the core, with structured history and summarisation

`partial` · `P1` · Memory / sessions

**Odoo:** ai.session and ai.session.event store every round in parts format, tied to an ai_chat Discuss channel. Odoo suggests a previous chat for the same record and surface, auto-titles chats, has an AI tab in the messaging menu, and vacuums chats idle for 30 days.

**Ghaima:** Conversations exist only when saas-client/ab_ai_chatbot is installed (duck-typed); otherwise chat is stateless. History is the last 6 messages as plain text (≤3000 characters), never summarised on the agent path. User memory is opt-in (≤1500 characters).

**Recommendation:** Add ai.agent.session and ai.agent.session.message to ab_ai_agent, storing envelope_json plus a nullable parts JSON so this does not wait for G10. Migrate ai.chat.conversation in ab_ai_chatbot so it keeps the surfaces and delegates storage. Summarise history with a cheap model class once it passes the token budget. Anchor sessions to records.

`ai/models/ai_session.py` `ai/models/discuss_channel.py` `ai/controllers/messaging_menu.py` `saas-share/ab_ai_agent/controllers/agent_chat.py#conversation_*` `saas-client/ab_ai_chatbot/models/ai_chat.py#_send_via_agent_runtime,find_or_create_for_record` `saas-share/ab_ai_agent/services/runtime.py#_user_memory_block`

### G22 — Retention for runs and usage logs

`missing` · `P0` · Privacy / data

**Odoo:** Autovacuum deletes AI chats idle for 30 days or empty for 1 day; _gc_sources_targets and the attachment vacuum clean the rest. Session data is readable by admins only.

**Ghaima:** Rows in ai.agent.run (up to 60k characters of system prompt, 30k of context, 50k of tool JSON with customer data) and ai.usage.local.log are kept forever. Pending actions are garbage-collected after 90 days, which is good.

**Recommendation:** Add an @api.autovacuum that blanks system_prompt, retrieved_context and tool_calls_json after N days (ICP, default 30) and deletes runs after 180 days, keeping the stats aggregates. Purge usage logs older than M days once they are reconciled and aggregated. Record this as the PDPL retention position.

`ai/models/discuss_channel.py (autovacuum)` `ai/models/ai_agent_source.py#_gc_sources_targets` `saas-share/ab_ai_agent/models/ai_agent_run.py` `saas-share/ab_ai_agent/models/ai_usage_local_log.py` `saas-share/ab_ai_agent/models/ai_agent_pending_action.py#_gc_old_proposals`

### G23 — Prompt chips per model and prompt packs per app

`partial` · `P1` · UI surfaces

**Odoo:** ai.prompt.button holds a QWeb prompt rendered with the record and shows 3 at random, hiding chatter-only prompts on non-thread models. Data-only per-app packs: ai_sale, ai_sale_margin, ai_sale_stock, ai_purchase, ai_stock, ai_project, ai_calendar (meeting prep), ai_account ('Show me the current cash flow status'), plus global chatter prompts (ai_prompt_summarize_chatter, ai_prompt_write_followup_chatter/_composer).

**Ghaima:** ai.agent.skill already has context_model, surfaces (chatter included) and requires_record_context (ai_agent_skill.py:62-80), used by the builder, console and chat controller; templates use str.format_map placeholders. Console skill cards and starters come from the user's menus and commands. Missing: chips per model in the chatter panel, per-app packs, calendar, chatter-summary and follow-up prompts.

**Recommendation:** Filter chatter and floating-assistant chips on the existing context_model plus surfaces; if multi-model support is needed, migrate context_model to a Many2many in one step rather than adding a parallel field. Ship data-only auto-install packs with Arabic prompts: ab_ai_agent_sale, _purchase, _stock, _account, _pos, _project, _calendar (meetings, reservations, appointments) and _hr (saas-share). Add global 'Summarize this chatter' and 'Draft follow-up' skills.

`ai/models/ai_prompt_button.py#_render_prompt` `ai_sale/data/ai_prompt_button_data.xml` `ai_account/data/ai_prompt_button_data.xml` `ai_calendar/data/ai_prompt_button_data.xml` `ai/data/ai_composer_data.xml` `saas-share/ab_ai_agent/models/ai_agent_skill.py#render_prompt` `saas-share/ab_ai_agent/models/ai_agent_builder.py` `saas-share/ab_ai_agent/static/src/web/chatter_patch.js` `saas-share/ab_ai_agent/static/src/components/ai_agent_chat/ai_agent_chat.js`

### G24 — AI in the editor and mail composer (draft, rewrite, translate) through our gateway

`partial` · `P0` · UI surfaces

**Odoo:** ai.composer interface keys cover html_field_record, mail_composer, html_field_text_select and more. ChatGPTPlugin opens an AI chat on a field or selection, with 'Use this', 'Send as Message' and 'Log as Note'. The mail_composer_chatgpt widget is used in the invoice send wizard, recruitment refusals and sign. /prompt blocks in mail templates are evaluated when the mail is rendered.

**Ghaima:** Partial: the native UI exists but is routed to Odoo IAP. Odoo 18 CE's ChatGPT, translate and alternatives dialogs call one controller method serving /html_editor/generate_text and /web_editor/generate_text, which sends prompts and database.uuid to the ICP web_editor.olg_api_endpoint (html_editor/controllers/main.py:543-549). The mail_composer_chatgpt widget on mail.compose.message and mail.scheduled.message bodies opens the same dialog (mail_compose_message_views.xml:84; mail_scheduled_message_views.xml:37). Separately, the website configurator calls website._OLG_api_rpc('/api/olg/1/generate_placeholder') with database.uuid, industry and language (website.py:48, :480-482, :862). Nothing in saas-*/ghaima-api overrides either path, so the traffic is unmetered, Odoo-branded and leaves our platform. No record-aware drafting.

**Recommendation:** Phase 1 (hours): push web_editor.olg_api_endpoint and website.olg_api_endpoint to a disabled or central endpoint for every tenant through the cockpit, and set them at provisioning. Phase 3: ab_ai_composer (saas-share) inherits the generate_text method — one override covers both routes and the translate and alternatives dialogs — and routes it through llm_adapter with feature 'compose' in the user's locale; debrand the dialog labels. Then add record context to the native mail composer and a draft action in account.move.send.wizard (body widget=html_mail, account_move_send_wizard.xml:50); never auto-send. Acceptance mocks both iap_jsonrpc and website._OLG_api_rpc, or explicitly scopes the configurator out.

`ai/static/src/editor/plugins/chatgpt_plugin.js` `ai/static/src/mail_composer_chatgpt.js` `ai/models/mail_render_mixin.py#_render_template` `ai_account/wizard/account_move_send_wizard.xml` `hr_recruitment_ai/wizard/applicant_refuse_reason_views.xml` `odoo-18/addons/html_editor/controllers/main.py#generate_text` `odoo-18/addons/html_editor/static/src/main/chatgpt/` `odoo-18/addons/mail/static/src/core/web/mail_composer_chatgpt.js` `odoo-18/addons/website/models/website.py#_OLG_api_rpc` `odoo-18/addons/account/wizard/account_move_send_wizard.xml`

### G25 — 'Ask AI' in the command palette and systray

`partial` · `P2` · UI surfaces

**Odoo:** A systray AI button (opens the chatter composer in form view). Ctrl+K falls back to 'Ask AI' when nothing matches, and '@' searches agents.

**Ghaima:** Floating button (ab_ai_chatbot), console client action, chatter button. Nothing in the command palette.

**Recommendation:** Register a command_provider in ab_ai_agent that offers 'Ask Ghaima AI: <query>' as the fallback and lists slash commands from ab_ai_command, in Arabic and English.

`ai/static/src/core/web/command_palette.js` `ai/static/src/web/systray_action.js` `ai_agentic/static/src/command_palette.js` `odoo-18/addons/web/static/src/core/commands/default_providers.js (command_provider registry)` `saas-client/ab_ai_chatbot/static/src/assistant/assistant.js` `saas-share/ab_ai_command/static/src/command_palette.js`

### G26 — AI agent on livechat, website and social-inbox channels, with human handoff

`partial` · `P2` · UI surfaces

**Odoo:** ai_livechat sets an ai_agent_id on im_livechat channel rules, adds a livechat preprompt and a forward_operator route for human handoff. ai_crm_livechat adds a lead-creation tool. ai_website_livechat shows preview cards. ai_social runs an agent on social-media direct messages with a human-handoff tool and three enable conditions: always, only when no operator is available, only when an operator is available.

**Ghaima:** The central ghaima.sa sales chatbot calls the provider directly (no usage log, guardrails or budget), renders replies with innerHTML (G03) and lets the client control history; it has per-IP rate limits and message caps held per worker. Embed widget turns are logged and guardrailed through process_request but have no budget or plan (G07). Neither has ERP data or human handoff. Tenants have no livechat, website or social-inbox AI; WhatsApp is outbound only (saas-hr/ab_whatsapp_notify).

**Recommendation:** Backlog after Phase 4. New channel-agnostic module ab_ai_livechat in saas-share (installable on central and tenants): an agent per channel with enable conditions (always, no operator online, operator online), a public-safe tool set (published products and menu, hours, reservations), a human-handoff tool, transcripts and a budget. Bridges: ab_ai_livechat_crm (draft leads), ab_ai_livechat_website_sale (product cards), and later an inbound WhatsApp adapter, which matters most for restaurant inquiries and reservations. Rebuild the ghaima.sa chatbot on it.

`ai_livechat/models/im_livechat_channel_rule.py` `ai_livechat/controllers/main.py#forward_operator` `ai_crm/data/ir_actions_server_tools.xml` `ai_website_livechat/models/ai_preview_card_mixin.py` `ai_social/models/ai_agent.py#_ai_tool_social_livechat_add_human` `ai_social/models/im_livechat_channel.py` `saas-ai/ab_ghaima_website_chatbot/controllers/main.py` `saas-ai/ab_ghaima_ai_embed/controllers/widget.py` `saas-hr/ab_whatsapp_notify` `odoo-18/addons/im_livechat`

### G27 — AI website builder (page generation, brand kit, SEO, webforms)

`missing` · `P3` · Per-app: website

**Odoo:** ai_website ships Website Page Generator, Builder and Reviewer agents, a brand kit, an SEO helper composer, webform tools, snippets, image search and page scraping. ai_website_sale adds product content.

**Ghaima:** None for tenant websites.

**Recommendation:** Defer. Start with drafting SEO meta and product descriptions through ab_ai_composer.

`ai_website/models/ai_website_service_brand_kit.py` `ai_website/models/ai_tool_webform.py` `ai_website/data/website_ai_agent.xml` `saas-erp/ghaima/ab_ghaima_website_theme`

### G28 — Transcribing recordings and dictation (we are ahead on live voice)

`ours_ahead` · `P3` · Voice

**Odoo:** Composer voice-to-text (/ai/transcription). Live dictation in the editor through an OpenAI realtime ephemeral token. Call recording transcription (mail.call.artifact with a lease and compare-and-swap). voip_ai call summaries.

**Ghaima:** Browser or server STT and TTS, hands-free mode, spoken confirm and cancel, Arabic Gemini TTS, metered seconds, plan-gated. No dictation into fields and no transcription or summary of recordings.

**Recommendation:** Later, add a dictation button in ab_ai_composer that reuses ServerStt, and 'meeting note from audio' (upload, transcribe via the gateway, summarise, propose a chatter note).

`ai/controllers/ai.py#transcribe` `ai/models/mail_call_artifact.py#action_transcribe_gevent` `voip_ai/models/voip_call.py` `saas-share/ab_ai_agent/static/src/voice/voice.js` `saas-share/ab_ai_agent/controllers/voice.py`

### G29 — Document extraction on one shared policy path

`ours_ahead` · `P0` · Documents / OCR

**Odoo:** ai_documents sorts folders by prompt (move, tag and rename tools, PDF capped at 5 pages, cron batch for mail aliases). ai_documents_account turns vendor-bill creation into tools. ir.attachment._ai_read sends PDFs inline and resizes images to at most 1024 px.

**Ghaima:** ab_scan_docs uses AI vision to create invoices, bills, credit notes, SOs, POs, pickings and payments, with autopilot gates (confidence, totals, duplicate, type) and 32 tests; we are ahead here. Bugs: call_ai calls get_config() outside its try block, so tenants without an active gateway row (FAYIAPROD) never reach the direct fallback; after a quota refusal it falls back to the tenant's own key (llm_adapter does the same in 'auto' mode, G07); it ignores llm_mode and the breaker. Among AI modules it depends only on ab_ai_ui, not ab_ai_agent. autopilot_terminal='post' lets automation post bills, an admin opt-in that conflicts with the draft-only rule. correction_log is collected (scanned_document.py:438, written at ~:1434) but only displayed, never fed back.

**Recommendation:** Adopt the llm_adapter routing policy from G07 (refusal final, only outages fall back), then route scan_docs through call_llm(feature='scan_docs'), either by adding an ab_ai_agent dependency or by moving the resolution helper down into ab_ai_base or ab_ai_client. Allow autopilot 'post' only when set by an account manager, and log it. Feed correction_log back as per-vendor few-shot examples. Expose a scan_document agent tool that returns a pending action.

`ai_documents/models/ir_actions_server.py#_ai_action_run` `ai/models/ir_attachment.py#_ai_read` `saas-client/ab_scan_docs/models/scan_ai_config.py#call_ai,autopilot_terminal` `saas-client/ab_scan_docs/models/scanned_document.py#_run_autopilot,_autopilot_finalize,correction_log` `saas-client/ab_scan_docs/__manifest__.py`

### G30 — Fields filled by AI prompts

`missing` · `P2` · AI fields

**Odoo:** An ai= prompt can be set on a Python field, on ir.model.fields or on a property definition. A daily cron (ir.model.fields._cron_fill_ai_fields) fills empty char, text and HTML values; field creation backfills the last 50 records; failures are stored as empty. Every field type gets an on-demand button (get_ai_field_value) that returns structured output with enums for selection, m2o and m2m, with web search on. web_studio_ai_fields adds this to Studio.

**Ghaima:** None.

**Recommendation:** New module ab_ai_fields (saas-share): ai_prompt and ai_enabled on ir.model.fields, and an OWL 'Fill with AI' field widget that proposes a value the user accepts (written as the user). A batch cron fills empty values within ai.usage.local.budget and a per-run cap. Depends on structured output (G08). Arabic prompts.

`ai_fields/models/models.py#_fill_ai_field,get_ai_field_value` `ai_fields/models/ir_model_fields.py#_cron_fill_ai_fields` `ai/utils/ai_fields_tools.py#get_ai_value,parse_ai_response` `-`

### G31 — AI server action type and 'Update with AI'

`missing` · `P2` · Automation

**Odoo:** ir.actions.server state 'ai': an HTML prompt with /field tokens, ai_tool_ids on the same model, and AI_ACTIONS_PROMPT (non-conversational, ignore instructions found in documents). Tool calls are logged in the chatter (ai.ai_log_action) with the agent as tracking author. ai_server_actions adds evaluation_type 'ai_computed' ('Update with AI') to object_write.

**Ghaima:** None. Note for design: base.automation's scheduled cron has no user_id, so it runs as __system__ (base_automation_data.xml:4-6; ir_cron.py:358, :414), and uid SUPERUSER_ID implies su=True (odoo-18/odoo/api.py:572-573).

**Recommendation:** New module ab_ai_server_actions (saas-share; depends base_automation and ab_ai_agent): selection_add a state with an explicit owner user (res.users, never superuser). Run runtime.run headless with env(user=owner, su=False), and refuse to run when env.su or uid == SUPERUSER_ID. Use an explicit tool allow-list and only tools flagged automation_safe (never post or confirm accounting). Log each run to the chatter, linked to ai.agent.run. Add an 'ai_computed'-style evaluation on object_write using ab_ai_fields.

`ai/models/ir_actions_server.py#_ai_action_run,AI_ACTIONS_PROMPT` `ai_server_actions/models/ir_actions_server.py#_run_action_object_write` `odoo-18/addons/base_automation/data/base_automation_data.xml` `odoo-18/odoo/addons/base/models/ir_cron.py`

### G32 — Agents triggered by events or schedules, with a run inbox

`missing` · `P2` · Automation

**Odoo:** base.automation.ai_agent_id plus an HTML prompt creates a child AI action. ai.automation.trigger reuses the date trigger to run schedules, and the next date advances even when a run fails. Each run gets its own channel with auto_confirm and an admin 'Automation' inbox, plus 'Run now'. Agents can create their own automations through a confirmed tool. ai_agentic is opt-in.

**Ghaima:** Only fixed crons (ai.report daily report, digest). Manager Bot has no schedule. Scheduled callers send feature 'custom'.

**Recommendation:** New module ab_ai_agent_automation (saas-share). ai.agent.automation holds the agent, trigger (schedule, create, write, date), model, domain, prompt, owner user and delivery (chatter note, inbox, email). Runs as the owner with su=False, never superuser, under a per-rule budget, and advances the next run even on failure. Writes become pending actions for the owner; nothing is auto-approved. Add an Automations tab in the console with Run now.

`ai_agentic/models/base_automation.py#_is_schedule_automation,action_ai_run_now` `ai_agentic/models/ai_automation_trigger.py#_advance_next_trigger_date` `ai_agentic/models/ir_actions_server.py#_ai_action_run_agent` `saas-client/ab_ai_client/models/report_generator.py#cron_generate_reports` `saas-ai/ab_manager_agents/data/manager_skills.xml`

### G33 — MCP server for external AI clients

`missing` · `P2` · Interop

**Odoo:** ai_mcp: POST /mcp (auth='bearer', bearer_scope='mcp') handles initialize, ping, tools/list and tools/call. use_in_mcp on server actions; 5 read-only tools by default. An initial-context tool injects timezone, user and active company, because an MCP client has no web client. API keys gain an 'mcp' scope. A full OAuth 2.1 server: PKCE S256, dynamic client registration, client allow-list, consent screen, revocation.

**Ghaima:** ab_api_base has JWT access tokens, register_scope_validator, @api_route and OpenAPI/Swagger at /api/v1/docs. ab_mobile_ai_api has a rate limiter pattern. No MCP. Odoo 18's _auth_method_bearer has no scope argument (it always checks the 'rpc' global key).

**Recommendation:** New module ab_ai_mcp (saas-share; depends ab_ai_agent and ab_api_base): a JSON-RPC endpoint behind an 'mcp' scope validator that exposes ai.agent.tool records flagged mcp_enabled (read-only by default) through tool_dispatcher.dispatch as the token's user. Add an initial-context tool (tz, company, UTC note), a per-token rate limit on the rate_limiter pattern, and usage rows under bucket 'mcp' (tool calls hit the database even without an LLM call). Write tools return a pending-action link to confirm inside Ghaima. Opt-in per company with an audit log. OAuth 2.1 and dynamic client registration go to backlog.

`ai_mcp/controllers/mcp_controller.py#handle_mcp_request` `ai_mcp/models/ai_mcp_request_dispatcher.py#_mcp_tools_list,_mcp_tools_call` `ai_mcp/models/ai_tool.py#_ai_tool_mcp_retrieve_initial_context` `ai_mcp/models/res_users_description.py` `ai_mcp/controllers/oauth_server_controller.py` `saas-share/ab_api_base/controllers/api.py#_auth_token,register_scope_validator,api_route` `ghaima-api/ab_mobile_ai_api/controllers/rate_limiter.py` `odoo-18/odoo/addons/base/models/ir_http.py#_auth_method_bearer`

### G34 — Agent tools for accounting reports, and report insights that work

`partial` · `P1` · Per-app: accounting

**Odoo:** ai_account_reports tools: accounting_report_list, describe, select, get_values, expand_line and open, with paginated values and report configs kept in session state. 'Accounting Report Analysis' skill. Auditor and Audit Reviewer agents with audit working files and cycle checks. ai_account adds a cash-flow prompt and AI drafting in account.move.send.wizard.

**Ghaima:** ab_account_reports_ai.get_ai_insights is a one-shot over ≤40 lines, depends on the legacy ab_ai_client and fails through the gateway because of its feature name. The reports themselves are partly unreliable: the accounting-report audit found 22 fine, 19 wrong, 7 broken and 3 empty out of 51, and only its phase 1 fixes have shipped. Also: /create invoice, /create bill, create_journal_entry (draft), DRAFT_GUARD, finance tools in the chatbot (ar_aging, pl_trend, pl_summary, cash_position, tax_summary, cashflow_*), ZATCA and KSA context in the base instruction.

**Recommendation:** New auto-install bridge ab_ai_agent_account_reports (saas-accounting; ab_account_reports + ab_ai_agent): report_list, get_values, expand_line and open over ab.account.report as the user, allow-listed to audited reports only (P&L, Balance Sheet, Trial Balance, VAT) until the audit phases 2–4 land, keeping the is_year_end_closing exclusion; an 'explain my P&L / balance sheet / VAT' topic in Arabic. Rebase ab_account_reports_ai onto ab_ai_agent and merge it into the bridge. Acceptance: get_values equals the report UI for the same options on a FAYIAPROD copy. An audit-checklist agent comes later.

`ai_account_reports/models/ai_tool.py#_ai_tool_accounting_report_get_values,_ai_tool_accounting_report_expand_line` `ai_account_reports/data/ai_skill_data.xml` `ai_account_reports/data/ai_audit_agents.xml` `saas-accounting/ab_account_reports_ai/models/ab_account_report_ai.py#get_ai_insights` `saas-share/ab_ai_command_account_entry/services/journal_entry.py` `saas-client/ab_ai_chatbot/services/tools/finance.py`

### G35 — Lead capture and summaries; sales email drafting

`partial` · `P2` · Per-app: CRM / sales

**Odoo:** ai_crm: ai_tool_create_livechat_lead plus parameter discovery. ai_crm_livechat. Sales prompt packs (charts by country, rep, category). ai_product product descriptions and images.

**Ghaima:** /create quote command; sales analytics tools (sales_totals, top_products, top_customers, sales_by_branch, sales_trend_monthly); legacy confirm_sale_order and cancel_sale_order tools (unsafe, see G45). Manager Bot's 'Create a Quote' skill wrongly tells the model to call confirm_sale_order. No CRM integration. We are ahead on sales analytics.

**Recommendation:** Fix the Manager Bot skill to use run_command create_quote now (with G45). Backlog: ab_ai_command_crm (/create lead, a spec on crm.lead) and ab_ai_agent_crm (lead summary and next step; create a lead from chat or email as a pending action).

`ai_crm/models/crm_lead.py#_ai_create_lead,_ai_get_lead_create_available_params` `ai_sale/data/ai_prompt_button_data.xml` `saas-share/ab_ai_command_sale/models/sale_order.py` `saas-client/ab_ai_chatbot/services/tools/sales.py` `saas-ai/ab_manager_agents/data/manager_skills.xml`

### G36 — HR assistant tools and HR email drafting

`partial` · `P2` · Per-app: HR

**Odoo:** hr_recruitment_ai drafts refusal emails with AI (mail_composer_chatgpt on applicant.get.refuse.reason). sign_ai drafts sign-request messages. No other HR AI.

**Ghaima:** /create employee (identity fields only, no wage). HR roll-call tools that are dead on the default agent (PII gate, see G02). ab_error_help explains errors across apps (478 for HR) with KB links. HR mobile API. The Saudi HR suite in saas-hr.

**Recommendation:** Backlog. Either ab_ai_agent_hr in saas-share next to ab_ai_command_hr (auto_install on hr + ab_ai_agent), or ab_hr_ai inside saas-hr to follow its ab_hr_* naming rule; branch-free either way, with no dependency on the 18 legacy ab_hr_* duplicates. If placed in saas-hr, verify_no_conflict.py and verify_branch_free.py must pass. Scope: leave balance and attendance as the user, Saudi labor-law and policy answers grounded in G20 sources, draft-only payslip explanations. Recruitment refusal emails come through ab_ai_composer.

`hr_recruitment_ai/wizard/applicant_refuse_reason_views.xml` `sign_ai/static/src/sign_ai_button.js` `saas-share/ab_ai_command_hr/models/hr_employee.py` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_hr_*` `saas-share/ab_error_help/__manifest__.py`

### G37 — Timesheet assistant and project prompts

`partial` · `P3` · Per-app: project

**Odoo:** ai_project prompt buttons. ai_timesheet_grid: timesheet assistant (get_assistant_data, timesheets_assistant_model.js) on the Enterprise timesheet grid.

**Ghaima:** Only the chatbot's legacy create_task tool (see G45).

**Recommendation:** Defer. Later, add a /log time command (ab_ai_command mixin on account.analytic.line, drafts) and task summaries.

`ai_timesheet_grid/models/account_analytic_line.py#get_assistant_data` `ai_project/data/ai_prompt_button_data.xml` `saas-client/ab_ai_chatbot/services/tools/actions.py (create_task)`

### G38 — Similar tickets and reply drafts

`missing` · `P3` · Per-app: helpdesk

**Odoo:** ai_helpdesk: use_ai and an AI agent per team; ticket embeddings with a similarity threshold and time range; a reply composer seeded with the ticket history.

**Ghaima:** Central ab_ghaima_support (ticketing and SLA) has no AI. Tenants run Community and have no helpdesk.

**Recommendation:** Defer. Later, add ab_ghaima_support_ai (central): similar tickets via semantic_index, Arabic reply drafts and KB suggestions.

`ai_helpdesk/models/helpdesk_ticket.py#_get_similar_tickets,_get_embedding_content` `ai_helpdesk/models/ai_composer.py#_get_initial_context` `saas-erp/ghaima/ab_ghaima_support`

### G39 — Campaign, mass-mailing and social content drafting

`missing` · `P3` · Per-app: marketing

**Odoo:** ai_marketing_automation Campaign Builder agent and skills (sort, delete steps), ai_mass_mailing builder patch, ai_social posts and images, ai_esg emission-factor assignment. (The ai_social inbox agent is a channel pattern, covered in G26.)

**Ghaima:** None.

**Recommendation:** Defer. Later, add ab_ai_agent_mass_mailing: Arabic subject lines and copy via ab_ai_composer, and restaurant promotion ideas from POS data.

`ai_marketing_automation/data/ai_agent.xml` `ai_mass_mailing/static/src/builder/mass_mailing_builder_patch.js` `ai_social/data/ai_composer_data.xml` `odoo-18/addons/mass_mailing`

### G40 — Operational tools for purchase, stock and POS (we are ahead)

`ours_ahead` · `P3` · Per-app: purchase / inventory / POS

**Odoo:** Prompt buttons only (ai_purchase, ai_stock, ai_sale_stock). No POS AI.

**Ghaima:** /create rfq; stock tools (low_stock_products, out_of_stock_products, reorder_rules, inventory_summary, product_stock_status); POS tools (pos_session_status, top_cashiers); scanning of POs and pickings; mobile kitchen predictions and anomalies, currently broken by G05.

**Recommendation:** After G05, add restaurant topics (menu engineering, waste, peak hours) to the ab_ai_agent_pos and _stock prompt packs.

`ai_purchase/data/ai_prompt_button_data.xml` `ai_stock/data/ai_prompt_button_data.xml` `saas-share/ab_ai_command_purchase/models/purchase_order.py` `saas-client/ab_ai_chatbot/services/tools/inventory.py` `saas-client/ab_ai_chatbot/services/tools/pos.py` `ghaima-api/ab_mobile_ai_api/controllers/ai_kitchen.py`

### G41 — Arabic-first behaviour (we are ahead)

`ours_ahead` · `P2` · Multi-language / Arabic

**Odoo:** Tool and skill descriptions are translatable and the protocol says to reply in the user's language. No Arabic-specific normalisation was found.

**Ghaima:** ar.po across modules; Arabic folding in routing, the cache key and menu search; an Arabic→English menu glossary; Arabic brand scrub in the gateway guardrails (أودو, اوضو, اوديو, اودو → غيمة, ai_guardrails.py:104-108); Saudi wording; Arabic TTS. Remaining issues: hard-coded AR/EN ternaries in Python (starters, confirmations); PII masking is all-or-nothing per plan (allow_pii, ai_plan.py:53; the gateway skips redaction when set, ai_gateway_service.py:177-183), so with it off the VAT, CR and phone numbers the agent needs are stripped; the express-signup prompt says 'Odoo 18'.

**Recommendation:** Move the ternaries into _() with ar.po entries. Replace the all-or-nothing plan.allow_pii with selective masking: keep VAT, CR and phone numbers the business needs, still mask card, IBAN and national-ID numbers. Add a per-user setting for Arabic-Indic or Latin numerals. Fix the signup prompt.

`ai/utils/agent_instructions_prompts.py (GLOBAL_PROTOCOL_TEMPLATE)` `saas-share/ab_ai_agent/services/runtime.py#_fold,_confirmation_text` `saas-ai/ab_ai_gateway/models/ai_guardrails.py#_BRAND_REPLACEMENTS,apply_pre_call` `saas-ai/ab_ai_plan/models/ai_plan.py (allow_pii)` `saas-ai/ab_ai_gateway/models/ai_gateway_service.py` `saas-ai/ab_ai_express_signup/models/ai_onboarding_service.py`

### G42 — Test coverage and evals of the production runtime

`partial` · `P1` · Observability / tests

**Odoo:** ai/tests (test_ai_session, test_llm_tool_calling, test_ai_access, test_tool_update_records, test_tool_create_records), test_ai, test_ai_fields, ai_mcp OAuth edge-case tests, tours.

**Ghaima:** About 453 Python tests: ab_ai_agent 182, ab_ai_chatbot 98, ab_ai_command 98, ab_scan_docs 32, ab_ai_client 18, ab_ai_gateway 13, ab_ai_agent_cache 5, ab_ai_command_account_entry 4, ab_ai_agent_config 3. None for ab_ai_base, ab_ai_ui, ab_ai_plan, the credit bridge, ab_ai_entity, embed, the website chatbot, express signup or manager agents, and no JS tests in any AI module. ab_ai_chatbot tests/test_actions.py asserts that confirm=True executes, which is the behaviour behind G45. The golden-set eval scores the retired agent_loop and intent_router for non-assistant items. No CI exists and no real-provider run through the gateway yet (O1).

**Recommendation:** Provider payload contract tests with recorded fixtures in ab_ai_base; hoot tests for AiAgentChat and navigator sanitize; a regression test for every P0 defect (update test_actions.py with G45). Point the eval harness at runtime.run only, with a golden set of ≥150 items in English and Arabic, and gate releases on measurable thresholds (tool accuracy ≥90% EN and ≥85% AR, no regression against the previous build, p95 latency and cost per run reported). Run odoo-bin --test-tags plus the eval nightly from an ir.cron on staging, through the gateway with a real provider (closes O1), and store the results.

`ai/tests/test_llm_tool_calling.py` `ai/tests/test_ai_access.py` `ai_mcp/tests` `saas-share/ab_ai_agent/tests` `saas-client/ab_ai_chatbot/tests/test_actions.py` `saas-client/ab_ai_chatbot/services/eval_runner.py` `saas-client/ab_ai_chatbot/data/golden_set.json` `saas-ai/docs/AI_GATEWAY_TENANT_LINK_ANALYSIS.md`

### G43 — Lean context per hop

`partial` · `P1` · Performance

**Odoo:** RAG is fetched on the first round only and cached. Record serialization truncates names to 60 characters, skips x2many lists over 50 and drops fields the user cannot read. Search returns 50 records by default, at most 200.

**Ghaima:** _record_context_block reads every field, non-stored computed fields included. explain_screen runs search_count([]) on the whole model. Each hop resends the full prompt. Up to 6 provider calls run synchronously in one worker.

**Recommendation:** Limit record context to fields in the current form view that are stored or related, cap x2many lists at 20 and truncate long values. Have explain_screen use a bounded count. Per-hop savings come with G10.

`ai/models/models.py#_ai_serialize_fields_data,_ai_truncate` `ai/models/ai_session.py (rag_context state)` `saas-share/ab_ai_agent/services/runtime.py#_record_context_block` `saas-share/ab_ai_agent/services/tool_dispatcher.py#_builtin_explain_screen`

### G44 — Tenant provisioning reliability for the AI stack

`partial` · `P0` · Multi-tenant SaaS

**Odoo:** Single database. ai_auto_install installs ai only when pgvector is available. One IAP account per database.

**Ghaima:** Confirmed by code: ab_tenant_module_guard lists ab_ai_base in MAIN_SERVER_MODULES (ir_module_module.py:33-36), marks it uninstallable on update_list (:88-104) and refuses button_install (:111-119); ab_ai_agent and ab_dashboard_ai_insights both depend on ab_ai_base, so a fresh tenant cannot install the AI stack. Simply unblocking it would let tenant admins add their own provider keys and, in 'auto' mode, sidestep central quota refusals (G07). ab_manager_agents is a tenant module kept in the central repo and calls env._t, which is undefined in Odoo 18, so the login prompt never appears. Stale tenant rows pointing at the tenant itself remain (O10). No real-provider test through the gateway yet (O1). saas-ai/ab_ai_daily_report is a leftover tree of empty folders.

**Recommendation:** Remove ab_ai_base from MAIN_SERVER_MODULES only together with the routing policy pushed from central: when a tenant is gateway-linked, set llm_mode='gateway', make provider key fields read-only or hidden, and have llm_adapter refuse direct mode. Acceptance: a linked tenant cannot run a direct call or bypass a quota refusal even with a key entered, and a fresh tenant installs the AI stack with the guard active. Import _t in ab_manager_agents and move it to saas-client after checking its bind-mount. Check pgvector at provisioning and record availability. Delete the leftover folders. Run the O1 smoke test through the cockpit before switching any tenant to gateway mode.

`ai_auto_install/__manifest__.py` `ai/__init__.py#pgvector_is_available` `saas-client/ab_tenant_module_guard/models/ir_module_module.py#_tenant_guard_sweep,button_install` `saas-share/ab_ai_agent/__manifest__.py` `saas-dashboard/ab_dashboard_ai_insights/__manifest__.py` `saas-ai/ab_manager_agents/static/src/services/manager_open_on_login.js` `saas-ai/ab_ai_plan/models/odoo_entity.py#_push_ai_gateway_config` `saas-ai/ab_ai_daily_report`

### G45 — Every write needs a human click (no model self-confirmation)

`partial` · `P0` · Human-in-the-loop

**Odoo:** Write tools pause the session in waiting_confirmation; execution resumes only from the user's click, validated with a resume_token checked by compare_digest. Odoo also offers auto_confirm, which we deliberately do not.

**Ghaima:** The legacy chatbot write tools (confirm_sale_order, post_invoice, cancel_sale_order, create_task) are bridged into the agent and attached to Ghaima Assistant with is_write_action=True (agent_bridge.py:172-191); that agent has allow_write_actions=True and use_all_capabilities=True (ai_agent_data.xml:28-29). They return the legacy two-phase shape: _preview (actions.py:36-58) returns the idempotency_key plus a confirm_prompt telling the model to 'Call <tool> with confirm=true and idempotency_key=…'. The runtime treats a result as a proposal only when result['confirmation']['key'] is set (runtime.py:697-706), so no pending action or chip is created and the key goes back to the model. confirm and idempotency_key are ordinary arguments: _wrap drops only '_'-prefixed keys (agent_bridge.py:121) and dispatch strips only _ai_* (tool_dispatcher.py:83-90). actions_enabled and the plan's 'actions' limit gate only ACTION_TOOLS and PROPOSAL_TOOLS (runtime.py:1430-1453); tools outside _ALL_ROUTED are always offered (:1557); the acl_group check lives in call_tool, which _wrap never calls (tool_registry.py:127-130). post_invoice calls action_post (actions.py:160-190), breaking draft-only accounting. Found by reading the code; not reproduced live.

**Recommendation:** First item of Phase 1. Deactivate post_invoice in the agent catalogue (posting stays a human action). Rewrite confirm_sale_order, cancel_sale_order and create_task to propose through ai.agent.pending.action.propose (returning result.confirmation.key), or drop them in favour of screen_button. In dispatch(), strip confirm and idempotency_key from arguments the model sends. Add the rewritten tools to PROPOSAL_TOOLS and apply actions_enabled and the plan gate to every is_write_action tool. Map acl_group to ai.agent.tool.group_ids in sync_agent_tools. Update manager_agent.xml:66-67 and ai_agent_data.xml:87. Acceptance: a mocked model that calls post_invoice or confirm_sale_order with confirm=true and the returned key, in the same run or the next turn, executes nothing; with actions_enabled=False no write tool is offered.

`ai/models/ai_session.py#_resume_pending_interaction` `ai/controllers/thread.py#resume_pending_interaction` `ai/utils/ai_utils.py#make_confirmation_request_preview` `saas-client/ab_ai_chatbot/services/tools/actions.py#_preview,_replay_or_execute,post_invoice` `saas-client/ab_ai_chatbot/services/agent_bridge.py#_wrap,_is_write_action,sync_agent_tools` `saas-share/ab_ai_agent/services/runtime.py#_proposal_of,_resolve_tools` `saas-share/ab_ai_agent/services/tool_dispatcher.py#dispatch` `saas-share/ab_ai_agent/data/ai_agent_data.xml` `saas-ai/ab_manager_agents/data/manager_agent.xml`

### G46 — Chat about files and record attachments

`missing` · `P1` · Tools / Documents

**Odoo:** read_binary_content reads up to 5 records (MAX_BINARY_CONTENT_RECORDS_TO_READ=5). ir.attachment._ai_read sends PDFs inline, capped to the first and last N pages (ai_max_pdf_pages), and resizes images. The file viewer has 'Summarize this file' and 'Explain this file'. Chat attachments travel as inline-data parts.

**Ghaima:** Chat attach sends every file to /scan-docs/upload/submit for extraction into invoice-like fields (ai_agent_chat_attach_patch.js); /ai_agent/run takes no attachments (agent_chat.py:412). A contract, tender or policy PDF cannot be summarised or questioned, and the agent cannot read the current record's attachments.

**Recommendation:** Add a read_attachment tool to the ab_ai_agent core with no scanner dependency: check read access on res_model/res_id as the user, cap pages and size, and use the existing ab_ai_base vision path with gateway feature 'document_qa'. Accept uploads in /ai_agent/run and let the user choose 'ask about this file' or 'scan as a document'. Acceptance: 'summarise the attached contract' on a 40-page Arabic PDF answers from at most N pages; an attachment on an unreadable record is refused.

`ai/models/ai_tool.py#_ai_tool_read_binary_content` `ai/models/ir_attachment.py#_ai_read` `ai/data/ai_composer_data.xml (ai_file_viewer_helper, ai_prompt_summarize_file, ai_prompt_explain_file)` `saas-client/ab_ai_chatbot/static/src/js/ai_agent_chat_attach_patch.js` `saas-share/ab_ai_agent/controllers/agent_chat.py#run` `saas-share/ab_ai_base/models/ai_service.py (vision path)`

### G47 — Bulk create and update in one confirmation

`partial` · `P2` · Tools

**Odoo:** update_records takes a list of updates across records and models with an explanation and a preview; create_records takes a list of values.

**Ghaima:** One record per proposal (update_record, act_on_record). A request like 'assign these 12 leads to Ahmed' needs 12 confirmations or cannot be done.

**Recommendation:** Add a batch pending action that carries a diff data_table block. Cap it at 50 records, require one confirm, check write access per record, and use a savepoint per record with per-record results. Draft-only rules still apply.

`ai/models/ai_tool.py#_ai_tool_update_records,_ai_tool_create_records` `saas-share/ab_ai_agent/services/agent_actions.py#update_record,act_on_record`

### G48 — Clickable records in answers

`missing` · `P2` · Answer rendering

**Odoo:** Answers link to records (prepare_record_previews, _ai_get_preview_metadata); livechat shows preview cards.

**Ghaima:** data_table and highlight_list blocks show records the user cannot open (no click, href or res_id handling), which weakens the block kit for lists such as 'overdue invoices'.

**Recommendation:** Add row_ref {model, id} to data_table rows. Validate it on the server as the user (check_access) and open it through aiNavigator.

`ai/models/ai_tool.py#_ai_tool_prepare_record_previews` `ai_website_livechat/models/ai_preview_card_mixin.py` `saas-share/ab_ai_ui/static/src/blocks/data_table.js` `saas-share/ab_ai_ui/static/src/blocks/data_table.xml`

### G49 — One runtime; no global state swapped per request

`partial` · `P1` · Agent loop / reliability

**Odoo:** One agent loop (ai.session) serves every surface; we found no per-request patching of module globals.

**Ghaima:** ab_ai_chatbot still ships the pre-agent runtime: agent_loop.py (438 lines) and its own tool_dispatcher.py (168) are reachable only from evals and tests (eval_runner.py:24); chat_response_cache.py (437) is imported only by models/__init__.py; the legacy two-phase write tools remain (G45). _send_via_agent_runtime swaps the module-wide tool_registry.call_tool for each request and restores it in finally (ai_chat.py:563-590). In threaded or gevent mode, concurrent requests can send tool events to another user's bus channel, and the restore can clobber a concurrent swap.

**Recommendation:** After G45, delete the dead modules and the legacy write tools, pass on_event explicitly instead of swapping the global, and point eval_runner at runtime.run (G42). Acceptance: two concurrent users each receive only their own tool events.

`ai/models/ai_session.py` `saas-client/ab_ai_chatbot/services/agent_loop.py` `saas-client/ab_ai_chatbot/services/tool_dispatcher.py` `saas-client/ab_ai_chatbot/models/chat_response_cache.py` `saas-client/ab_ai_chatbot/models/ai_chat.py#_send_via_agent_runtime` `saas-client/ab_ai_chatbot/services/eval_runner.py`

### G50 — Per-app integrations in auto-install bridges

`partial` · `P1` · Module architecture

**Odoo:** Per-app AI features ship as ai_<app> bridge modules; 53 of the 56 ai-related modules are auto-install, so a database gets only the AI pieces for apps it has.

**Ghaima:** The bridge rule is broken today. ab_ai_chatbot hard-depends on ab_scan_docs (which pulls account, sale, purchase, stock and portal) and on ab_ai_client (sale, account). ab_manager_agents hard-depends on crm, hr, sale_management and account. ab_account_reports_ai depends on the legacy ab_ai_client instead of ab_ai_agent. HR-only or basic-plan tenants must install accounting, stock and sales to get the chatbot.

**Recommendation:** Move the attach and camera patch to ab_ai_chatbot_scan_docs (auto_install); move the finance and sales chatbot tools into per-app bridges; split the ab_manager_agents domain topics into bridges; rebase ab_account_reports_ai onto ab_ai_agent (merging into ab_ai_agent_account_reports). Acceptance: ab_ai_chatbot installs on a database with only hr.

`ai_sale/__manifest__.py` `ai_account/__manifest__.py` `saas-client/ab_ai_chatbot/__manifest__.py` `saas-client/ab_ai_client/__manifest__.py` `saas-client/ab_scan_docs/__manifest__.py` `saas-ai/ab_manager_agents/__manifest__.py` `saas-accounting/ab_account_reports_ai/__manifest__.py`

## Strengths

- Multi-tenant gateway (ab_ai_gateway + ab_ai_plan + ab_ai_entity): tenant tokens, entity_ref protected against tampering, plan ceilings, per-tenant USD budgets, rate limits, guardrails (including an Arabic brand scrub), a fallback provider, and a SAR price book reconciled against tenant usage. Odoo has only IAP credits for a single database.
- Choice of provider and on-prem option: OpenAI, Gemini, Claude (IDs need the G08 refresh) and Ollama, with Fernet-encrypted keys, a simulation mode and a circuit breaker (llm_adapter). Odoo is locked to its IAP endpoint.
- Prompt caching designed into the prompt layout (stable prefix + CACHE_BREAK + Anthropic cache_control), plus an answer cache that normalises Arabic and re-runs data plans as the user. Odoo has no client-side caching that we could find.
- Answers render as a block kit (KPI grid, Chart.js charts, tables, callouts, provenance) fed by query_data, which compares with the previous period under an 8-second statement timeout. Odoo opens views instead.
- Confirm-first for core action tools, with no 'Always approve': confirmations are idempotent and expire after 15 minutes, DRAFT_GUARD keeps accounting in draft, create_record rejects anything that does not stay a draft, and voice confirm uses the same path. Chatbot write tools are pending migration (G45).
- Confirm-first configuration agent (ab_ai_agent_config): changes a whitelisted set of business settings (e.g. multi-currency) only after Confirm. Odoo's Self Update skill is scoped to ai.* models and its blocklist covers only a few models.
- Deterministic slash commands (ab_ai_command, 98 tests): an Arabic-aware parser, resolvers that ask when a match is ambiguous, drafts only, no LLM round trip.
- Arabic first: text normalisation, an Arabic→English menu glossary, Saudi business wording, Gemini Arabic TTS, Saudi Arabic ar.po across the modules.
- Curated knowledge content: 10 ab_knowledge_base_* packs (about 93 EN/AR records with screenshots, hiding features that are not installed) feed kb_search, kb_read and explain_screen; ab_error_help explains errors across apps (478 for HR). This is the obvious first RAG corpus.
- Conversational voice (hands-free mode, spoken confirm and cancel, metered and plan-gated). Odoo has dictation and transcription only.
- AI-vision document scanning into 7 record types with confidence, total, duplicate and type gates (ab_scan_docs, 32 tests), plus a portal: batch upload, camera auto-capture, line re-matching, product-creation requests (ab.product.request) and a correction log (20 /scan-docs/* routes).
- Native mobile AI API used by the Flutter apps: 6 JWT endpoints (/api/v1/ai/query, /suggestions, /dashboard/summary, /dashboard/anomalies, /kitchen/predict, /kitchen/performance), a rate limiter and OpenAPI docs (ghaima-api/ab_mobile_ai_api).
- AI-assisted SaaS signup (ab_ai_express_signup).
- Run audit (ai.agent.run): tokens, latency, routed_via, a grounded/partial/ungrounded label and user feedback, plus usage logs per hop and an eval harness.
- Safe navigation: the server builds every navigation directive, the screen descriptor's domain is validated on the server, the client accepts only record, list or menu shapes, and the AI cursor shows where it is going.
- Zero-cost proactive tips and a daily briefing, and a nightly knowledge digest kept byte-stable so the cached prefix stays valid.
- POS and restaurant analytics (fact marts, cashier and session tools, kitchen endpoints), which Odoo's AI does not cover at all.
- Locked base instruction and a website knowledge excerpt that is HMAC-signed and fetched only from the allow-listed ghaima.sa hosts.

## Improvements

### One policy layer for every AI write

Writes reach records through six paths with different rules: the dispatcher, resolve() on Confirm, chatbot execute_action, screen_button, the legacy chatbot write tools (which the model can confirm itself) and scan_docs autopilot. Odoo gets consistency by running every tool inside the session's tool batch.

Make tool_dispatcher.dispatch the only way to execute a tool, including on Confirm (keyword-only confirmed flag). Move every write onto ai.agent.pending.action; remove post_invoice and execute_action. Add a protected-methods registry (posting, payslip done) that no agent path may call. Give each tool an automation_safe flag for headless runs, and link each pending action to its agent and run.

Covers: G45, G02, G29, G31, G32, G47

### Make the gateway the only metered way in

Public surfaces, embeddings, document scanning and Odoo's native editor and configurator OLG calls bypass metering; 'auto' mode lets tenant keys sidestep quota refusals; and the closed feature list breaks legitimate callers.

Make a gateway refusal final and push llm_mode='gateway' to linked tenants; make feature a Char mapped to buckets; give public surfaces platform budgets; meter /embed; gate model_override; contain then override the OLG endpoints; use one cost-normalisation function for every path.

Covers: G05, G06, G07, G24, G29, G44

### A parts-based transcript and structured output in ab_ai_base

The single growing string costs tokens on every hop, causes malformed tool calls and blocks multi-hop caching. AI fields and automations need JSON-schema outputs, and model IDs must stay current.

Provider contract tests first; then retry with backoff, response_schema support and deprecation fields on ai.usage.price.book (one price table); then a provider-neutral message list with a serializer per provider, offered by central as the 'messages_v1' capability and used by tenants only when advertised.

Covers: G08, G10, G43, G30, G42

### Sessions in the core, with retention

Memory and history depend on a tenant-side module, and audit rows store customer data forever.

Add ai.agent.session and ai.agent.session.message to ab_ai_agent (with a nullable parts JSON so it does not wait for G10), migrate ab_ai_chatbot onto them, add rolling summaries and autovacuum runs and logs.

Covers: G21, G22, G11

### Knowledge sources with citations

Answers about company policy, product manuals or Saudi regulation cannot be grounded today. The citation and semantic-index code and a curated KB corpus exist but are not wired together.

Build ab_ai_knowledge on ai.semantic.index with KB articles as the first source, then attachments and URLs through a new parameterised SSRF guard in ab_ai_base; embed through the metered gateway, filter retrieval by access and wire up [SOURCE:id] citations. Add web search through the gateway after that.

Covers: G20, G18, G38, G36

### Route the native editor and composer AI through our gateway

Odoo 18 CE already shows AI in every html field and the mail composer, but it sends tenant text and database.uuid to Odoo. One inherited controller method turns it into metered, Arabic-aware AI everywhere.

Contain both OLG endpoints by ICP on day one. Then ab_ai_composer inherits generate_text (both routes, translate and alternatives dialogs), adds record context to the native composer and a draft action in account.move.send.wizard, plus the Ctrl+K command provider.

Covers: G24, G25, G28

### Read files, act in bulk, link records

Users cannot ask about a contract or tender PDF, bulk requests need one confirmation per record, and records listed in answers cannot be opened.

A read_attachment tool on the vision path with access checks and page caps; a batch pending action with a diff table and per-record savepoints; row_ref on data_table rows validated as the user and opened through aiNavigator.

Covers: G46, G47, G48

### Per-app prompt packs as data-only bridges

Odoo's per-app value comes mostly from data-only prompt packs. We have stronger tools but fewer entry points to discover them.

Show chips filtered on the existing context_model and surfaces. Ship ab_ai_agent_sale, _purchase, _stock, _account, _pos, _project, _calendar and _hr as auto-install data modules with Arabic prompts, plus global chatter-summary and follow-up skills. Ship ab_ai_agent_account_reports over audited reports only.

Covers: G23, G34, G35, G40

### Headless agents that stay confirm-first and never run as superuser

Recurring SMB work (overdue chasing, a daily cash note, stock alerts) needs triggers and schedules. Odoo approves tool calls automatically during these runs, and base.automation's cron runs as the system user; we should do neither.

ab_ai_fields, then ab_ai_server_actions, then ab_ai_agent_automation. Every rule has an owner user; runs use env(user=owner, su=False) within a budget, writes become pending actions in the owner's inbox, and the next scheduled run advances even after a failure.

Covers: G30, G31, G32

### Read-only MCP on ab_api_base

Customers increasingly ask ChatGPT, Claude and similar clients about their ERP data. Odoo 18 bearer authentication has no scopes, but our JWT scope validators do.

ab_ai_mcp: tools/list and tools/call over ai.agent.tool records flagged for MCP, read-only by default, opt-in per company, with an initial-context tool, a per-token rate limit, usage rows under 'mcp' and an audit log. OAuth 2.1 goes to backlog.

Covers: G33

### Clean module boundaries

A legacy runtime still ships with a concurrency bug, and hard dependencies force accounting, stock and sales onto HR-only tenants, breaking the bridge rule.

Retire the legacy chatbot runtime and the global call_tool swap; split the chatbot's scan, finance and sales pieces and the Manager Bot topics into auto-install bridges; rebase ab_account_reports_ai onto ab_ai_agent.

Covers: G49, G50

### Release gate with tests and evals

Most P0 defects sit in modules with no tests, one existing test asserts the unsafe self-confirm behaviour, and the eval harness scores code that is no longer used.

Contract tests for providers, hoot tests for the chat UI, a regression test per fix, a ≥150-item EN/AR golden set against runtime.run with accuracy thresholds, and a nightly staging cron that runs tests and evals through the gateway with a real provider (O1).

Covers: G42, G44

## Implementation plan

### Phase 1 — 4 weeks (2 developers)

Stabilise: close the security, metering and provisioning defects without adding features. Wave 1a (week 1) is hotfixes; wave 1b (weeks 2–4) finishes the fixes. Assumes 2 developers. Definition of done for every item in every phase: Saudi Arabic ar.po verified to load in Odoo on a fresh database (not only polib); RTL checked; upgrade tested on a FAYIAPROD copy or demo tenant, never on production; central deployed before tenants for any gateway contract change; one commit per repo with a CHANGELOG entry; a regression test for every fix.

#### 1a: Stop the assistant confirming its own writes (G45)

Modules: `ab_ai_chatbot`, `ab_ai_agent`, `ab_manager_agents`

Steps:
1. Deactivate post_invoice in the agent catalogue (sync_agent_tools); posting stays a human action
2. Rewrite confirm_sale_order, cancel_sale_order and create_task to propose through ai.agent.pending.action.propose (returning result.confirmation.key), or drop them in favour of screen_button
3. In dispatch(), strip confirm and idempotency_key from model-supplied arguments; add the rewritten tools to PROPOSAL_TOOLS
4. Apply actions_enabled and the plan 'actions' limit to every is_write_action tool in _resolve_tools; map acl_group to ai.agent.tool.group_ids in sync_agent_tools
5. Update the instructions in ai_agent_data.xml:87 and manager_agent.xml:66-67; change ab_ai_chatbot tests/test_actions.py, which asserts that confirm=True executes

**Done when:** A scripted run in which the mocked model calls post_invoice or confirm_sale_order with confirm=true and the returned key, in the same run or the next turn, executes nothing and the invoice stays draft; with actions_enabled=False no write tool is offered; a grep test plus a dispatch test show no agent path reaches account.move.action_post.

#### 1a: Re-check every gate on Confirm (G02)

Modules: `ab_ai_agent`, `ab_ai_chatbot`

Steps:
1. Add agent_id to ai.agent.pending.action (tool_code and agent_run_id already exist); pass agent and agent_run from every propose() call site (agent_actions.py:232; tool_dispatcher.py:1185, :1271)
2. Give dispatch() a keyword-only confirmed: bool, outside the arguments, that forwards _ai_confirmed=True to the tool
3. resolve(): look up ai.agent.tool by tool_code, browse agent_id and call dispatch(..., confirmed=True)
4. Interim binding on ab_ai_chatbot execute_action: create_uid == env.uid, same conversation, hash of target and args, 15-minute TTL

**Done when:** Tests: turning actions_enabled off between propose and Confirm blocks execution; a user who lost the tool's group cannot confirm; a chatbot proposal for record A cannot execute on record B or for another user; an expired key is refused.

#### 1a: Rebuild data_analysis on the ORM (G01)

Modules: `ab_ai_agent`

Steps:
1. Rebuild _builtin_data_analysis on Model._read_group as the user (query_data presets), keeping the kpi_grid and chart envelope
2. Pass the user's tz in context for day buckets; group totals by currency or convert to the company currency
3. Return a generic error to the model and log the exception
4. Call generic_data.model_blocked in query_data

**Done when:** Tests: a company-B user gets only company-B totals; a user without POS or accounting read access gets ok=False; a branch-restricted user sees only their branch through query_data and data_analysis; a 23:30 Riyadh order lands on the correct day; a company with two currencies shows totals per currency.

#### 1a: Close the superuser bot path and the key and spend leaks (G03, G04)

Modules: `ab_ai_chatbot`, `ab_ai_agent`, `ab_ai_base`

Steps:
1. Discuss bot: with no internal asker, reply with a localized sign-in message; never use the SUPERUSER env; log exceptions and reply generically
2. usage_live: require AI Manager; move the live meter to a res.company record channel checked in _build_bus_channel_list; strip cost_usd from envelopes for non-admins
3. Gemini vision and embed: send the key in the x-goog-api-key header; never put exception text in a UserError; move _scrub_secrets into ab_ai_base and add a log filter that redacts key=

**Done when:** A guest @mention gets no data; a non-manager gets 403 from /ai_agent/usage/live and cannot subscribe to another company's channel; grep finds no '?key=' in ab_ai_base; a forced Gemini HTTP error shows no key in the log or the UI.

#### 1a: Contain Odoo OLG egress and restore the Claude provider (G24, G08)

Modules: `ab_ai_plan (tenant config push)`, `ab_ai_base`, `ab_ai_gateway`

Steps:
1. Push web_editor.olg_api_endpoint and website.olg_api_endpoint to a disabled (or central) endpoint for every tenant through the cockpit, and set them at provisioning
2. Replace the Claude selection and price rows with current IDs (claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5; confirm against Anthropic's docs at implementation)
3. Stop sending temperature in _call_claude; migrate stored ai.provider.config.claude_model values

**Done when:** With iap_jsonrpc and website._OLG_api_rpc mocked, no call reaches the OLG host from the editor, composer or configurator; a Claude call succeeds on each new ID in direct and gateway mode.

#### 1b: Open feature names and accurate metering (G05, G06)

Modules: `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_plan_credit_bridge`, `ab_ai_agent`, `ab_ai_base`

Steps:
1. Convert ai.usage.log.feature to Char with a migration; add an ai.feature.bucket mapping and gate plans on buckets ('custom' for unknown names)
2. Write the log row as 'pending' before the provider call and finalize it afterwards
3. Add usage normalization in ab_ai_base (input_uncached, cached, output) and use it in meter.record, estimate_cost and the gateway
4. Compute cost_usd locally on the direct path so max_cost_usd is enforced
5. Seed the missing rows in ai.usage.price.book; fail closed when a budget is enforced and the model has no price
6. Add the ir.cron for _cron_generate_overage_invoices; remove the duplicate rate-limit log; use the plan currency symbol

**Done when:** Gateway tests pass for every feature tenants send (business_query, pos_suggestions, kitchen_prediction, kitchen_performance, anomaly_detection, dashboard_insights, accounting_report_insight); a cached call reports total = prompt + completion; a direct-mode run stops at max_cost_usd; the overage cron exists and is tested.

#### 1b: One routing policy: gateway refusals are final (G07, G29, G44)

Modules: `ab_ai_agent`, `ab_ai_base`, `ab_ai_client`, `ab_scan_docs`, `ab_tenant_module_guard`, `ab_ai_plan`, `ab_manager_agents`

Steps:
1. llm_adapter: a gateway refusal (quota, plan) is final unless an explicit ICP opt-in exists; only transport errors fall back
2. Provisioning pushes llm_mode='gateway' to linked tenants; provider key fields become read-only or hidden there and llm_adapter refuses direct mode
3. Add a feature= keyword to call_llm; route scan_docs through it (add the ab_ai_agent dependency, or move the resolution helper into ab_ai_base or ab_ai_client); fix get_config() outside the try block
4. Remove ab_ai_base from MAIN_SERVER_MODULES together with the policy above
5. Allow autopilot_terminal='post' only when an account manager sets it, and log every automatic post
6. ab_manager_agents: import _t; move it to saas-client after checking the container bind-mount; delete the empty saas-ai/ab_ai_daily_report folders
7. Run the O1 real-provider smoke test through the cockpit before any tenant switches to gateway mode

**Done when:** On a FAYIAPROD copy (no gateway row) scans run via the direct provider; on a linked tenant a quota refusal is final for both the agent and scan_docs even with a provider key entered; a fresh demo tenant installs the AI stack with the guard active; the Manager login prompt appears.

#### 1b: Finish scoping and surface hardening (G01, G02, G03, G04)

Modules: `ab_ai_agent`, `ab_ai_chatbot`, `ab_ai_chatbot_branch (new, saas-branches, auto_install)`, `ab_ghaima_website_chatbot`, `ab_ai_express_signup`, `ab_ai_client`

Steps:
1. ab_ai_chatbot_branch: branch filters for fact_query only (or rebuild the marts on _read_group and drop the bridge)
2. Validate semantic_search extra_domain fields as the user; read chatter in _record_context_block as the user
3. Protected-methods registry (account.move/account.payment action_post, hr.payslip done) blocked in screen_button and act_on_record
4. Route chatbot confirm chips through /ai_agent/action/confirm and delete execute_action
5. Filter requires_pii tools when the agent disallows PII; set the names-only HR roll-call tools to requires_pii=False
6. share_expires_at (default 7 days) and revoke on delete; chatbot.js renders with textContent plus safe markdown; express status checks is_express with a signed token; conversation_lookup calls check_access('read'); entity_token groups='base.group_system'

**Done when:** Tests: a branch-restricted user sees only their branch in fact marts; an invoicing user cannot Post through screen_button; an XSS payload in a reply renders as text; an expired share link returns 404; the default agent can use hr_leave_pending for an HR user.

Depends on: 1a: Re-check every gate on Confirm

#### 1b: Caching on by default, retention, lean context (G09, G22, G43)

Modules: `ab_ai_base`, `ab_ai_agent`

Steps:
1. Seed ab_ai_base.provider_cache_enabled=True (noupdate data) and add a settings toggle
2. Move group-filtered digest sections after CACHE_BREAK
3. Add an @api.autovacuum that blanks the large text columns of ai.agent.run after N days (ICP, default 30) and deletes rows after 180 days; purge usage logs older than M days once reconciled
4. Limit _record_context_block to form-view fields that are stored or related, cap x2many at 20; bound the count in explain_screen

**Done when:** Fresh-install test: the system role is used and the second identical call reports cached_tokens > 0 (mocked provider); after the vacuum, old runs have empty prompt and tool JSON; the record context of a 300-line sale order stays under 6k characters.

#### 1b: Retire the legacy chatbot runtime (G49, G42)

Modules: `ab_ai_chatbot`

Steps:
1. Delete agent_loop.py, the chatbot's own tool_dispatcher.py, chat_response_cache.py and the legacy two-phase write tools
2. Pass on_event explicitly instead of swapping tool_registry.call_tool per request
3. Point eval_runner at runtime.run

**Done when:** Two concurrent requests from different users (threaded test) each receive only their own tool events on the bus; the module installs and its remaining tests pass; grep finds no import of the deleted modules.

Depends on: 1a: Stop the assistant confirming its own writes

### Phase 2 — 8–9 weeks (2 developers)

Agent-core parity: contract tests first, then provider resilience and the parts-based transcript; sessions, ask_user, view adjustment, server-action tools, public-path governance and dependency hygiene run in parallel. Same definition of done as Phase 1.

#### Provider contract tests and eval baseline (G42)

Modules: `ab_ai_base`, `ab_ai_ui`, `ab_ai_agent`, `ab_ai_plan`, `ab_ai_chatbot`

Steps:
1. Recorded-fixture contract tests for 4 providers × (chat, tools, schema, embedding)
2. Hoot tests for AiAgentChat rendering and aiNavigator.sanitizeDirective; ab_ai_plan tests for check_quota, overage and policy
3. Golden set of ≥150 items in English and Arabic, scored against runtime.run only
4. Nightly ir.cron on staging runs odoo-bin --test-tags plus the eval through the gateway with a real provider (closes O1) and stores the results

**Done when:** ab_ai_base and ab_ai_plan have ≥20 tests each; the nightly run stores tool accuracy, grounded rate, p95 latency and cost per run, with English and Arabic reported separately; a baseline is recorded before the transcript work starts.

#### Tenant image and database prerequisites (G16, G20, G46)

Modules: `dockerfile (tenant image)`, `ab_ai_plan (provisioning)`, `ab_ai_agent`

Steps:
1. Add jsonschema and pdfminer.six to dockerfile/requirements-extra.txt and the matching external_dependencies (Odoo 18's requirements pin only PyPDF2, which extracts Arabic poorly)
2. Check the pgvector extension during provisioning and record availability per tenant
3. Verify the container bind-mount for every repo that gains a module (saas-share, saas-client, saas-branches)
4. Roll the rebuilt image out through the cockpit

**Done when:** A probe endpoint on each tenant reports the jsonschema, pdfminer and pgvector versions; module paths resolve after -u on every tenant.

#### Provider resilience, price-book catalogue, structured output (G08)

Modules: `ab_ai_base`, `ab_ai_gateway`, `ab_ai_agent`

Steps:
1. Jittered retry in ab_ai_base (429/500/502/503/529, honour Retry-After, ≤2 retries)
2. Add deprecated_on and replacement_model to ai.usage.price.book; fold ai.token.pricing into it (or derive one from the other) so gateway and direct path read one table
3. Nightly health-check and remap cron over the price-book rows
4. Per-model thinking config (verify whether gemini-2.5-pro accepts thinkingBudget=0 on the text and vision paths)
5. response_schema per provider; pass temperature (where accepted), max_tokens and model_class on the direct path

**Done when:** Contract tests cover retry, schema output and thinking config per provider; a model flagged deprecated is remapped to its replacement with no failed calls; the agent's response_style changes temperature in direct mode on models that accept it.

Depends on: Provider contract tests and eval baseline, 1b: Open feature names and accurate metering

#### Parts-based message transcript (G10)

Modules: `ab_ai_base`, `ab_ai_agent`, `ab_ai_gateway`, `ab_ai_client`

Steps:
1. Define a message structure (role + parts: text, tool_call, tool_result, inline_data, provider_data)
2. Serializers for OpenAI (tool role), Anthropic (tool_use/tool_result with cache_control on the last block) and Gemini (functionCall/functionResponse)
3. Rewrite the runtime hop loop to append parts; keep the string path behind an ICP flag
4. Central adds 'messages_v1' to GATEWAY_CAPABILITIES and accepts messages[] on /analyze and /stream; tenants send messages[] only when config.has_capability('messages_v1')

**Done when:** On the golden set: tool accuracy ≥90% EN and ≥85% AR with no regression against the string path; cached_tokens > 0 on hop 2 and later; zero Gemini MALFORMED_FUNCTION_CALL retries; p95 latency and cost per run reported against the baseline.

Depends on: Provider resilience, price-book catalogue, structured output

#### Sessions in the core (G21)

Modules: `ab_ai_agent`, `ab_ai_chatbot`

Steps:
1. Add ai.agent.session and ai.agent.session.message (envelope_json plus a nullable parts JSON, agent, record anchor, company) with own-row record rules
2. Migrate ai.chat.conversation and ai.chat.message; ab_ai_chatbot delegates storage and keeps the surfaces
3. Summarise history with a cheap model class once it passes the token budget
4. conversation_lookup checks read access first; add retention for sessions

**Done when:** Without ab_ai_chatbot the console keeps its history; with it, migrated conversations replay their charts (dry run on a FAYIAPROD copy); a user cannot open a session for a record they cannot read.

#### ask_user and in-place view adjustment (G12, G17)

Modules: `ab_ai_agent`, `ab_ai_ui`, `ab_ai_command`

Steps:
1. Add an ask_user tool and a 'question' render block (choices, multi-select, free text; the answer posts as the next turn with a question_id)
2. Use it for resolver ambiguity and create_record need_info; force it at max_hops
3. Validate open_list/open_pivot/open_graph domains, group-bys and measures with ai.screen.context._domain_ok and fields_get as the user
4. Optional 'adjust' directive applied to the current SearchModel (check the Odoo 18 API first), sanitised on the client
5. Arabic labels in ar.po

**Done when:** 'Show unpaid invoices for Al-Rajhi grouped by month' narrows the open list in place; an ambiguous partner shows choice chips; a bogus field in a model-supplied domain is rejected on the server.

#### Server actions as tools, with argument validation (G16)

Modules: `ab_ai_agent`

Steps:
1. Validate tool arguments in dispatch() (jsonschema or a minimal validator) and return ok=False errors the model can act on
2. Always confirm first for server-action states that write; pass active_model/active_id when the tool targets a record
3. Add a 'Use in Ghaima AI' toggle (name, description, schema) on the ir.actions.server form, translated

**Done when:** Tests: an invalid argument returns a validation error without running; an object_write action yields a pending action; a code action sees the active record.

Depends on: Tenant image and database prerequisites

#### Govern public paths (G07)

Modules: `ab_ai_gateway`, `ab_ai_plan`, `ab_ghaima_ai_embed`, `ab_ghaima_website_chatbot`, `ab_ai_express_signup`

Steps:
1. Platform budget rows with hard daily USD caps for embed:*, express_signup and website_chatbot; a separate feature for embed
2. Route the website chatbot through process_request with history held on the server
3. Meter /embed (quota, rate limit, usage log)
4. Gate model_override by the plan's allowed model classes; forward max_tokens and temperature

**Done when:** Every public call writes an ai.usage.log row under its own feature; when the cap is reached the widget returns a localized 'busy' message; a Starter-plan tenant cannot force the strongest model.

Depends on: 1b: Open feature names and accurate metering

#### Dependency hygiene: per-app bridges (G50)

Modules: `ab_ai_chatbot`, `ab_ai_chatbot_scan_docs (new, auto_install)`, `ab_manager_agents`, `ab_account_reports_ai`

Steps:
1. Move the attach and camera patch to ab_ai_chatbot_scan_docs
2. Move the finance and sales chatbot tools into per-app bridges
3. Split the ab_manager_agents domain topics into bridges
4. Rebase ab_account_reports_ai onto ab_ai_agent

**Done when:** ab_ai_chatbot installs on a database with only hr; ab_account_reports_ai no longer depends on ab_ai_client; existing tenants upgrade without data loss on a FAYIAPROD copy.

Depends on: 1b: Retire the legacy chatbot runtime

### Phase 3 — 7–8 weeks (2 developers)

Knowledge and surfaces: RAG with citations, chat over files, gateway-routed editor and composer AI, per-app prompt packs over audited reports, bulk proposals, clickable records, web search, Arabic polish. Same definition of done as Phase 1.

#### ab_ai_knowledge: knowledge sources and citations (G20)

Modules: `ab_ai_knowledge (new, saas-share)`, `ab_knowledge_base_ai (extend as the KB source bridge)`, `ab_ai_base`, `ab_ai_gateway`

Steps:
1. Add ai.agent.source (kb_article, attachment, url; tree; status; is_active; restrict_to_sources on ai.agent) and ai.agent.chunk using ai.semantic.index.provision
2. KB articles first (the 10 ab_knowledge_base_* packs), then attachments (index_content; PDF text via pdfminer.six), then URLs
3. URL fetch through a new parameterised guard in ab_ai_base: https only, port 443, no userinfo, globally routable IP, connect to the resolved IP, no redirects, size and content-type caps; admin only; ghaima_base keeps its fixed allow-list
4. Chunk about 2000 characters, dedup by checksum, embed in batches through the metered gateway /embed with a triggered cron
5. Retrieve as the user with hybrid vector + pg_trgm search, filtered by read access to each source, on the first round only
6. Wire citation.apply_numeric_citations; add a SourceList block in ab_ai_ui and a Knowledge tab in the console; Arabic UI

**Done when:** Arabic recall@5 ≥0.8 on a KB question set (target confirmed after the first baseline); answers carry [n] citations linking to sources; a user without access to a restricted article gets no chunks from it; the JSON fallback works without pgvector; the URL guard refuses private IPs, redirects and non-443 ports.

Depends on: Tenant image and database prerequisites, Govern public paths

#### Read attachments in chat (G46)

Modules: `ab_ai_agent`, `ab_ai_base`, `ab_ai_chatbot_scan_docs`

Steps:
1. Add a read_attachment tool to the ab_ai_agent core with no scanner dependency: read access on res_model/res_id checked as the user, page and size caps, ab_ai_base vision path with gateway feature 'document_qa'
2. Accept uploads in /ai_agent/run
3. Chat attach offers 'ask about this file' or 'scan as a document' (the scanner path lives in the scan bridge)

**Done when:** 'Summarise the attached contract' on a 40-page Arabic PDF answers from at most N pages (ICP); an attachment on a record the user cannot read is refused; usage appears under 'document_qa'.

Depends on: Tenant image and database prerequisites

#### ab_ai_composer: editor and mail drafting through the gateway (G24, G25)

Modules: `ab_ai_composer (new, saas-share)`, `ab_ai_composer_account (new bridge, auto_install with account)`, `ab_ai_agent`

Steps:
1. Inherit the html_editor generate_text method (covers /html_editor/generate_text, /web_editor/generate_text and the translate and alternatives dialogs) and route it through llm_adapter with feature 'compose' in the user's locale; debrand the dialog labels
2. Add record context (record fields and recent chatter, read as the user) to the native mail_composer_chatgpt flow
3. Bridge: a draft action in account.move.send.wizard (html_mail body) in the partner's language; never auto-send
4. Register a command_provider for 'Ask Ghaima AI' and slash commands in Ctrl+K

**Done when:** With iap_jsonrpc and website._OLG_api_rpc mocked, no request reaches the OLG host (the website configurator is routed or explicitly out of scope); editor and composer calls appear in ai.usage.local.log under 'compose'; the invoice email draft uses the partner's language and the invoice amounts.

Depends on: 1a: Contain Odoo OLG egress and restore the Claude provider, 1b: Open feature names and accurate metering

#### Prompt packs per app and audited report tools (G23, G34, G40)

Modules: `ab_ai_agent`, `ab_ai_agent_sale`, `ab_ai_agent_purchase`, `ab_ai_agent_stock`, `ab_ai_agent_pos`, `ab_ai_agent_project`, `ab_ai_agent_calendar`, `ab_ai_agent_hr (saas-share)`, `ab_ai_agent_account_reports (new, saas-accounting)`

Steps:
1. Show chatter and floating-assistant chips filtered on the existing context_model plus surfaces
2. Ship data-only auto-install packs with Arabic and English prompts, plus global 'Summarize this chatter' and 'Draft follow-up' skills and restaurant topics (menu engineering, waste, peak hours)
3. ab_ai_agent_account_reports: report_list, get_values, expand_line and open over ab.account.report as the user, allow-listed to audited reports (P&L, Balance Sheet, Trial Balance, VAT), keeping the is_year_end_closing exclusion
4. Merge ab_account_reports_ai into the bridge on a valid feature bucket

**Done when:** On a FAYIAPROD copy, get_values numbers equal the report UI for the same options, with year-end-closing moves excluded from income statements; a non-audited report is not offered; on a sale.order form only skills with context_model sale.order and the chatter surface appear, with Arabic labels; 'لماذا انخفض صافي الربح هذا الشهر؟' calls get_values and expand_line.

Depends on: 1b: Open feature names and accurate metering, Accounting-report audit phases 2–4 (saas-accounting, outside this plan) for any report beyond the allow-list

#### Bulk proposals and clickable records (G47, G48)

Modules: `ab_ai_agent`, `ab_ai_ui`

Steps:
1. Batch pending action carrying a diff data_table: cap 50 records, one confirm, per-record write check, savepoint per record, per-record results; draft-only rules apply
2. row_ref {model, id} on data_table rows, validated on the server with check_access and opened through aiNavigator

**Done when:** 'Assign these 12 leads to Ahmed' produces one proposal and one confirm, and a record the user cannot write is reported as failed while the others succeed; clicking a row opens the record; a forged row_ref to an unreadable record is refused.

Depends on: 1a: Re-check every gate on Confirm

#### Web search through the gateway (G18)

Modules: `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_agent`, `ab_ai_ui`

Steps:
1. Add feature 'web_search' on central using the provider's grounding or search tool (check current API names); plan-gated
2. Add a tenant web_search tool, offered only when agent.allow_web_grounding is set and answers are not restricted to sources
3. Store web sources by uuid and render citations in the SourceList block; never fetch URLs the user supplies

**Done when:** A question about current SAMA or ZATCA news returns cited sources; the web_grounding_calls meter increments; the tool is not offered when the plan does not include it.

Depends on: ab_ai_knowledge: knowledge sources and citations

#### Arabic polish and selective PII masking (G41)

Modules: `ab_ai_agent`, `ab_ai_gateway`, `ab_ai_plan`, `ab_ai_express_signup`

Steps:
1. Move hard-coded AR/EN ternaries into _() and ar.po
2. Replace the all-or-nothing plan.allow_pii with selective masking: keep VAT, CR and phone numbers, still mask card, IBAN and national-ID numbers
3. Add a per-user numeral preference; fix the signup prompt that says 'Odoo 18'

**Done when:** Language-switch tests show no untranslated starters or confirmations; a tenant VAT number reaches the agent unredacted while card, IBAN and national-ID numbers are redacted.

### Phase 4 — 7–10 weeks (2 developers)

Automation and interop: AI fields, AI server actions, scheduled agents and read-only MCP. Backlog, not scheduled: ab_ai_livechat in saas-share (channel-agnostic, with _crm, _website_sale and an inbound WhatsApp adapter), ab_ai_command_crm and ab_ai_agent_crm, the HR agent bridge, MCP OAuth 2.1, and the deferred P3 gaps. Same definition of done as Phase 1.

#### ab_ai_fields (G30)

Modules: `ab_ai_fields (new, saas-share)`, `ab_ai_base`

Steps:
1. Add ai_enabled and ai_prompt (with field placeholders) on ir.model.fields; start with char, text, html, selection and many2one
2. OWL 'Fill with AI' widget: structured output with allowed values (enums for selection and many2one); the user accepts, then it is written as the user
3. Batch cron for empty values within ai.usage.local.budget and a per-run cap; store failures so they are not retried endlessly

**Done when:** A product 'Arabic description' field fills on click and matches the schema; the cron stops when the budget is reached; selection values outside the allowed set are rejected.

Depends on: Provider resilience, price-book catalogue, structured output

#### ab_ai_server_actions (G31)

Modules: `ab_ai_server_actions (new, saas-share; depends base_automation, ab_ai_agent, ab_ai_fields)`

Steps:
1. selection_add an AI state on ir.actions.server with an HTML prompt, a required owner user (not superuser) and an allow-list of tools on the same model
2. Run runtime.run headless with env(user=owner, su=False) and a non-conversational policy that ignores instructions found in documents; refuse to run when env.su or uid == SUPERUSER_ID
3. Only tools flagged automation_safe may write; never post or confirm accounting
4. Log each run to the chatter, linked to ai.agent.run; add an AI-computed evaluation for object_write

**Done when:** A rule without an owner cannot be saved; a run fired by base.automation's scheduled cron executes as the owner, not superuser; a tool outside the allow-list is refused; every run appears in the chatter with a link to its run.

Depends on: ab_ai_fields, Server actions as tools, with argument validation

#### ab_ai_agent_automation: scheduled and event-triggered agents (G32, G11)

Modules: `ab_ai_agent_automation (new, saas-share)`, `ab_ai_agent`

Steps:
1. Add ai.agent.automation (agent; trigger: schedule, on_create, on_write or date; model; domain; prompt; owner; delivery: chatter note, inbox or email; budget)
2. Execute in the background with a fresh cursor and persisted run state, as the owner with su=False; advance the next run even after a failure; add a watchdog for stuck runs
3. Writes become pending actions in the owner's inbox; nothing is auto-approved
4. Add an Automations tab in the console (list, toggle, Run now, history); use feature bucket 'automation'

**Done when:** A daily 08:00 'overdue invoices summary' posts an Arabic note to the owner; a failing run does not re-run on every cron pass; the budget cap stops runaway costs.

Depends on: Sessions in the core, ab_ai_server_actions

#### ab_ai_mcp (read-only) (G33)

Modules: `ab_ai_mcp (new, saas-share; depends ab_ai_agent, ab_api_base)`

Steps:
1. POST /mcp JSON-RPC handling initialize, ping, tools/list and tools/call, behind an 'mcp' scope registered via register_scope_validator
2. Expose ai.agent.tool records flagged mcp_enabled (read tools by default) through tool_dispatcher.dispatch as the token user
3. Add an initial-context tool (tz, company, UTC note), a per-token rate limit on the ab_mobile_ai_api rate_limiter pattern, and usage rows under bucket 'mcp'
4. Write tools return a pending-action link to confirm inside Ghaima; opt-in per company with an audit log and token TTL

**Done when:** An MCP client lists and calls find_records and query_data as the token user; date tools answer in the token user's timezone; a burst above the limit returns 429; a disabled company's token returns 403; a write call never executes without confirmation in the app.

Depends on: Server actions as tools, with argument validation

## Risks

| Risk | Mitigation |
|---|---|
| Licensing: Odoo 20 AI modules are OEEL-1. Copying prompts, schemas or code into our LGPL ab_* modules would contaminate them. | Clean-room rule: this analysis records behaviour only. Implementers must not open the OEEL files while writing code, and prompts and tool schemas are written from scratch. Code review checks this. |
| Cross-border data transfer under PDPL: every gateway and direct call sends ERP data, including customer PII when allow_pii is set, to OpenAI, Google or Anthropic outside KSA. | A data-processing agreement with each provider; a per-tenant consent and data-processing notice in Arabic; a per-plan option to route through Ollama or a KSA-hosted model; PII redaction on by default except for whitelisted business identifiers (G41). |
| Provider model IDs are retired without notice. This has already happened: every Claude ID we offer is retired and the Claude provider fails today. | Phase 1 hotfix to current IDs; then deprecated_on and replacement_model on ai.usage.price.book, a nightly health-check call per configured model, and automatic remapping. |
| Pushing llm_mode='gateway' to linked tenants can cut off tenants that rely on their own keys today, or stall AI during a central outage. | Transport errors still fall back; an explicit, central-controlled ICP opt-in for tenants allowed to use their own keys; announce before rollout; roll out tenant by tenant through the cockpit after the O1 smoke test. |
| The parts-transcript refactor (G10) touches four provider serializers, the runtime and the gateway, and can regress tool calling for every tenant at once. | Contract tests and an eval baseline first; central advertises 'messages_v1' and tenants keep the string path behind an ICP flag; golden-set thresholds gate the release; roll out tenant by tenant. |
| Agent tools over accounting reports that the audit found wrong or broken would give confident wrong answers. | Allow-list audited reports only (P&L, Balance Sheet, Trial Balance, VAT); acceptance compares get_values with the report UI on a FAYIAPROD copy; widen the list only as audit phases 2–4 land. |
| Moving conversations from ab_ai_chatbot into the core (G21) and retiring the legacy runtime are data and behaviour changes on live tenants. | A pre-migration script copies the data and the old models stay read-only for one version. Dry run on a FAYIAPROD copy and verify envelope replay before deploying. |
| Some tenant PostgreSQL clusters may lack the pgvector extension, which slows RAG and semantic search. | Check at provisioning and record availability. Use the JSON cosine fallback with a corpus cap, add the extension to tenant images, and keep the pg_trgm hybrid for Arabic recall. |
| Headless automations and AI fields can run up costs (cron loops, large backfills). | A budget per rule and per run, plus the ai.usage.local.budget pre-check. Advance the next run even after a failure. Batch limits per cron run and a plan-level 'automation' bucket ceiling. |
| Prompt injection through RAG sources, attachments, chatter text or public chat input steering tool-using agents. | Wrap tool results, retrieved chunks and file text in data fences. Keep tool allow-lists per surface (public channels get no write tools). Strip confirmation arguments from model input (G45), keep confirm-first for every write, and add an injection eval set. |
| MCP sends ERP data to external LLM clients, raising PDPL and Saudi data-residency concerns. | Off by default, opt-in per company, read-only tool set, audit log of every call, rate limits, short token TTL, and an admin consent page in Arabic that explains where the data goes. |
| Overriding the native generate_text method, or disabling the OLG endpoints, could break editor features when Odoo 18 updates. | Inherit the controller method rather than replace the route, keep its response contract (a string, or a UserError), show a clean message when disabled, and add a hoot test that drives the native dialog. |
| Changing the gateway feature field from Selection to Char affects reporting, plan gating and existing summaries. | Migrate the values as they are, add a bucket mapping with a 'custom' default, keep plan feature lists as buckets, and backfill ai.usage.summary. |
| Synchronous runs keep tying up HTTP workers until G11 lands. | Keep max_hops at 6, cap tool result sizes, apply statement timeouts in query_data, and move automations to background execution first. |
