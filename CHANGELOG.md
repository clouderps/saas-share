# saas-share — CHANGELOG

> Per-repo tracking log. Seeded 2026-05-31 from manifest inventory + last 90 days of `git log`. Append new entries on top as work lands.

## Modules

| Module | Version | License | Summary |
|---|---|---|---|
| `ab_ai_agent` | 18.0.1.10.0 | LGPL-3 | AI Agent Runtime — Cross-instance AI agent runtime — personas, tools, RAG, metering. Gateway-indepe |
| `ab_ai_base` | 18.0.1.2.0 | LGPL-3 | AI Provider Base — Base AI provider configuration for OpenAI, Claude, Gemini, and local LLMs |
| `ab_ai_ui` | 18.0.1.2.0 | LGPL-3 | AB AI UI — Shared response renderer — OWL <AiResponse/> + block kit (KPI grid, highlight list, data table, callout, ac |
| `ab_mobile_api_common` | 18.0.1.0.0 | LGPL-3 | Mobile API Common — Shared HTTP/JWT helpers for Ghaima mobile APIs |
| `ab_printer_driver` | 18.0.2.0.0 | LGPL-3 | Printer Driver — Base printer driver — detect, verify, dispatch, log. Bridge agent for cloud-host |
| `ab_redis_session` | 18.0.1.0.0 | LGPL-3 | Redis Session & Bus — Store Ghaima sessions and bus notifications in Redis for multi-node HA |
| `ab_reports_hub_base` | 18.0.1.0.0 | LGPL-3 | AB Reports Hub — Base — Top-level Reports app icon + role groups, shared by tenant and central report bu |
| `ab_s3_attachment` | 18.0.1.0.0 | LGPL-3 | S3 Attachment Storage — Store Ghaima filestore attachments on AWS S3 |

## Recent changes (since 2026-03-02)

### 2026-06-22
- security(ab_ai_agent): hardened the agent against two findings, aligned to native Odoo 19 `ai` patterns (run tool bodies as the requesting user; raise on failure). `record_action` now matches a document EXACTLY (dropped the substring `ilike` fallback that could finalize the WRONG invoice) and calls `check_access('write')` as the requesting user before posting/confirming/validating. The LLM adapter (`llm_adapter.call_llm`) no longer masks a *configured* provider/gateway failure as a fake "simulation" success — it raises `AiProviderError` and the runtime finalizes the run `state='error'` (visible to monitoring); a truly unconfigured dev box still simulates. Added `ab_ai_agent/tests/` (was zero): record-action safety + provider-failure-surfaced — 9 tests green on a fresh tenant DB.

### 2026-06-11
- i18n(ab_printer_driver): re-point Bridge Agent selection msgid to "Bridge Agent (LAN proxy for cloud Ghaima)" after source debranding (Arabic unchanged).

### 2026-06-11
- chore(ab_printer_driver): debrand user-facing strings (Odoo → Ghaima) in printer help texts, selection labels, and connection errors.


### 2026-06-11
- i18n: **SaaS portal & backend Arabic pass + KSA terminology review** (2026-06-11). ~2,900 strings authored/harvested for the 16 SaaS modules (menus, actions, fields, selections, portal templates, JS/code messages). KSA terminology applied platform-wide: الفوترة→الحسابات (native menu override in ab_ghaima_core_rebrand), Entity/الكيان→التطبيق, أودو→غيمة, لوحة المعلومات→لوحة البيانات, مرشح→تصفية. **Stale .pot files removed everywhere** — PoFileReader merge-gates po entries against the pot (obsoleting anything missing), which was silently dropping DB terms AND runtime JS code translations (the "JS reports not translating" bug). Code occurrences need a `:0` line suffix or the reader crashes on int(""). HTML email-template bodies deferred (need proper RTL email treatment).


### 2026-06-11
- i18n: **full field-label & selection-value Arabic pass** (2026-06-11) — every `ir.model.fields` label and selection value in tenant-facing modules translated (native-Odoo corpus + authored Saudi business Arabic); brand names / technical identifiers intentionally kept Latin.


### 2026-06-11
- i18n: **Arabic (ar.po) translations for menu & window-action names** — part of the cross-repo i18n pass (2026-06-11) closing the RTL-audit gap: custom app menus rendered English inside the Arabic UI. Standard Saudi business Arabic, loaded automatically on module update for ar_* languages.


### 2026-06-10
- `2b46944` feat(icons): Ghaima Squircle module icons — unified SVG identity + 140px PNG across all ab_*/bk_* modules

### 2026-05-25
- `d2557e1` feat(ab_reports_hub_base): add shared Reports app kernel
- `9e44de4` feat(ab_ai_base,ab_ai_agent): T.1/3 — provider-native tools slot
- `5f7358f` feat(ab_ai_base,ab_ai_agent): T.2a — pgvector keystone (semantic_search)
- `c4f9f33` feat(ab_ai_agent): T.1 — CSV-everywhere business snapshot
- `507f2a5` feat(ab_ai_base): T.1 — provider-native system slot + Anthropic cache_control
- `b083370` feat(ab_ai_agent): inline AI panel alongside Send Message / Log Note
- `75f7f02` fix(ab_ai_agent): chip dropdown hidden behind chat body
- `e22a9da` fix(ab_ai_agent): chatter Ask AI handler — correct Chatter import path

### 2026-05-17
- `58dd488` ab_ai_agent (18.0.1.10.0): record_action tool — "INV/2026/00001 please post"
- `1f4d7fa` ab_ai_agent (18.0.1.9.3): merge multi-tool renders — compound "X and Y and Z" questions
- `13533ed` ab_ai_agent (18.0.1.9.2): #3 grounding retry — force a tool before accepting an ungrounded data answer
- `4a818d9` ab_ai_agent (18.0.1.9.1): recent_records tool — fix "latest X added" answers
- `efcb550` ab_ai_agent (18.0.1.9.0): request/response monitor + grounding signal
- `c523cbd` ab_ai_agent (18.0.1.8.2): wire RAG knowledge grounding into the unified runtime
- `dfd77fd` ab_ai_ui+ab_ai_agent: analytical chart responses (Hybrid C)

### 2026-05-15
- `f6c3dd4` test(ab_printer_driver): ePOS-Print end-to-end smoke
- `a0e40cf` feat(ab_printer_driver): ePOS-Print mode (browser-direct printing), now the default
- `cef2708` fix(ab_printer_driver): avoid String() in OWL template — t-att-value="\x27\x27 + a.id"
- `e85a0ab` feat(ab_printer_driver): bridge agent for cloud-to-LAN printing
- `6e2762b` feat(ab_printer_driver): Live Monitor + Diagnose + scanner shows registered
- `06b67ae` feat(ab_printer_driver): lib gains format_receipt + dispatch handles 'report' kind
- `087aa38` feat(ab_printer_driver): app icon + named Reliability group for inherits
- `061ad7e` feat(ab_printer_driver): new domain-agnostic printer base module

### 2026-05-14
- `3fd94f0` ab_ai_agent: navigation + HR tools — "open the report", "who's not in"
- `c13329e` ab_ai_agent: voice in/out for manager surface
- `7d5bc30` ab_ai_agent: gate agent surfaces to designers; Ask AI stays casual
- `7a49150` ab_ai_agent: relax single-active-agent rule
- `f9fefcc` ab_ai_agent: full-page chrome + empty-state chips + sound + actions
- `cbf215f` ab_ai_agent: skip dead gateway + lift render envelope onto reply
- `5c1991f` ab_ai_agent: comprehensive system context + report rendering
- `d089b72` ab_ai_agent: persistent chatter conversations + tenant-active-agent rule
- `39ee6ce` ab_ai_agent: chatter Ask AI button + consolidated AI menu + tokenizer fix
- `283a609` ab_ai_agent: fix kanban_image() — removed in Odoo 18
- `adbdebf` ab_ai_agent: fix aiAgentService bootstrap on Odoo 18
- `e135791` Phase H — ab_ai_agent: cross-instance agent runtime
- `cc19066` Phase G — model routing + cost provenance

### 2026-05-13
- `4a991dd` AiResponse: hideProvenance prop for cleaner consumer surfaces
- `45b95c3` SuggestionChips: pass structured action payload on pick
- `8a03c6a` Fix Gemini embedding endpoint — gemini-embedding-001 single-call loop
- `d97ada8` Add embedding API to ai.service (Phase B foundation)
- `0163911` chore(ab_ai_ui): bump version 1.0.0 → 1.0.1
- `9ad8eb7` Verdict chip on ProvenanceBar + picked-state on SuggestionChips
- `c68e74f` Add SuggestionChips block for clarification UX
- `93f6ddf` Add AiMarkdown block + disable Gemini 2.5 thinking mode
- `f896f18` fix(ab_ai_base): drop dead Gemini model options + add 2.5-flash-lite / flash-latest
- `d22cca2` fix(ab_ai_ui): JSON is not in OWL render ctx — move to JS getter
- `d95715c` fix(ab_ai_ui): drop legacy rpc service dep — import rpc directly
- `979a86d` refactor(ab_ai_ui): promote ai_response_envelope form widget from ab_ai_client
- `dc533ae` feat(ab_ai_ui): Phase A — shared OWL <AiResponse/> + block kit
- `81c8171` feat(ab_ai_base): streaming + tool-calling provider hooks (SAAS_AI_PLAN Phases 6+7)

### 2026-05-12
- `cfa722a` Add saas-share CLAUDE.md — repo scope + JWT seam + activation notes
- `3b7b825` ab_ai_base Phase 2: simulation toggle + fallback provider chain
- `0b6ca57` fix(ab_s3_attachment): deferred _file_delete + harden read/write paths

### 2026-05-11
- `00d83ff` ab_s3_attachment: log-loud on S3 miss instead of silent empty bytes

### 2026-05-06
- `6ab2e44` Track git-pull.sh + git-push.sh in saas-share
- `d3d198c` MODULE_CLEANUP_PLAN: log #95 (approval views Odoo 18 migration done)
- `f94f0ab` MODULE_CLEANUP_PLAN: D9, D11, D12 done
- `5505ddd` MODULE_CLEANUP_PLAN: close D8 — no action needed
- `74114d6` MODULE_CLEANUP_PLAN: mark D1 done
- `8fbb6ab` Add MODULE_CLEANUP_PLAN with 2026-05-06 execution log
- `f81b4c1` Add ab_mobile_api_common — shared HTTP/JWT helpers
- `2d29f78` Add ab_ai_base — base AI provider config (moved from saas-ai)
- `bed0baf` Initial commit: shared infra modules

---

_For older history: `git log --since=<date>` in this repo._
