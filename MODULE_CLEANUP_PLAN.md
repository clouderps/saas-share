# Module & Model Cleanup Plan

**Audit Date:** 2026-05-06
**Scope:** All 151 custom modules across 13 sub-repositories
**Status:** Phase 1 + most of Phase 2 EXECUTED on 2026-05-06.

This plan consolidates a deep audit of the CloudERPs / Ghaima codebase. Each finding is tagged with a severity and an explicit decision request. Outcomes from the 2026-05-06 execution session are recorded in §0 below; the remaining sections preserve the original analysis as a historical record.

---

## 0. Execution Log (2026-05-06)

### Done
- 🟢 **saas-share repo created** (`git@github.com:clouderps/saas-share.git`) — added to addons_path on main + tenant containers.
- 🟢 **`ab_s3_attachment` unified** — apps copy (with boto3-missing fallback bugfix) is canonical; saas-client copy deleted; `saas-erp/apps` copy deleted.
- 🟢 **`ab_redis_session` unified** — saas-client copy is canonical; broken double-nested `saas-erp/apps/ab_redis_session/ab_redis_session/` deleted.
- 🟢 **`bytekol_db_filter` deleted** — replaced by patched `odoo/http.py` in fork (X-Odoo-Dbfilter header).
- 🟢 **`ab_ai_base` moved** from `saas-ai/` to `saas-share/`.
- 🟢 **7 empty HR `_account` stubs deleted** (`ab_hr_attendance_account`, `_disciplinary_account`, `_expense_account`, `_gosi_account`, `_leave_account`, `_loan_account`, `_wps_account`) — all confirmed uninstalled across DBCLOUD + 5 tenants and zero incoming deps.
- 🟢 **`ab_dashboard_ai` retired** — orphan with no incoming deps; `ab_dashboard_ai_insights` is the canonical AI-on-dashboards path.
- 🟢 **POS PIN audit** — no field duplication: `ab_pos_security` owns `hr.employee.pos_pin_hash`, `ab_pos_pin_gateway` owns gateway flags, `ab_user_pos` owns `res.users.pos_pin`. Removed orphan `ab_pos_pin_gateway/models/res_users.py` (comment-only stub).
- 🟢 **`ab_mobile_api_common` extracted** to saas-share — shared CORS/JSON/JWT helpers; `ab_mobile_pos_api` + `ab_mobile_saas_billing_api` now import from it (-183 +62 lines net). API contract verified via curl: response shape, error codes, CORS preflight all unchanged.
- 🟢 **Smoke tested** — main + 5 tenants HTTP 200 after every change.

### Skipped (explicit user direction)
- ❌ Move `saas-approval/*` into saas-share — already separate repo.
- ❌ Move `saas-branches/*` into saas-share — already separate repo.
- ❌ Move accounting modules — out of scope for shared infra.
- ❌ Theme modules — entire saas-theme repo excluded.

### Done (continued, 2026-05-06 evening)
- 🔴 **D1 — Geidea webhook HMAC verification hoisted to controller boundary.** Model-level `_process_notification_data` always verified the HMAC (forgery was not possible), but the controller acked 200 OK on any POST and let the model flip a real customer's tx into `error` state — a DoS vector for anyone who learned a `merchantReferenceId`. The controller now rejects unsigned/unknown/bad-signed webhooks with 400/401/404 before the tx record is ever touched. Verified with 8 curl scenarios including a synthetic valid-HMAC payload (tx transitioned `draft`→`cancel` as expected).
- **D8 — Investigated, no action needed.** The audit's framing was incorrect: `ab_saas_admin_dashboard` (real ~420-LOC dashboard widget with 2 models, JS, CSS, security) and `ab_saas_unified_dashboard` (1-XML-file menu-reparenting bridge with no Python) are **complementary, not competing**. Unified depends on admin and reparents its menu under Odoo's "Dashboards" root. Both stay.

### Deferred / not yet started
- **D9** — Merge `ab_approval_flow` into `ab_approval_base`
- **D10** — Merge `ab_ghaima_responsive` into `ab_ghaima_theme` (theme repo, excluded for now)
- **D11** — Mass author rebrand "Bytekol" → "Ghaima Tech" across `bk_*` manifests
- **D12** — `@abstractmethod` on `bk_odoo_entity_sale` framework hooks + JSON error boundaries
- **Followup** — proper bind mount for saas-share at next container rebuild (currently a `cp -a` static copy; task #84)

### Architectural note (lessons from Phase 2)
- Tenant containers were deployed before saas-share existed; they bind-mount each repo individually. The interim fix is a `cp -a` of saas-share into the container's host-mapped dir at `/opt/ghaima_containers/<container>/odoo_source_code/saas-share/`. Files persist across container restart but a fresh `git pull saas-share` requires re-running the `cp -a`. Long-term fix: register an `odoo.addon.path` record on the `odoo.image` so future containers get the bind mount automatically.

---

This plan consolidates a deep audit of the CloudERPs / Ghaima codebase. Each finding is tagged with a severity and an explicit decision request. **Nothing is implemented yet.** Pick what to act on, what to defer, what to drop.

Severity legend: **🔴 High** (security/correctness/dual-maintenance) · **🟡 Medium** (real cleanup value) · **🟢 Low** (cosmetic / cohesion)

---

## 1. Headline Findings (read these first)

| # | Finding | Severity | Area |
|---|---|---|---|
| H1 | `ab_s3_attachment` is duplicated as **two diverging copies** (saas-client vs saas-erp/apps) — bug fixes do not propagate | 🔴 | Shared infra |
| H2 | Geidea payment webhook in `ab_saas_geidea_checkout` lacks signature verification | 🔴 | Billing |
| H3 | JWT auth + response wrapper duplicated between `ab_mobile_pos_api/common.py` and `ab_mobile_saas_billing_api/common.py` | 🟡 | Mobile API |
| H4 | 7 empty `_account` HR satellites (`ab_hr_attendance_account`, `_disciplinary_account`, `_expense_account`, `_gosi_account`, `_leave_account`, `_loan_account`, `_wps_account`) — manifest + ACL stubs only | 🟡 | HR |
| H5 | `ab_dashboard_ai` and `ab_dashboard_ai_insights` overlap — purpose split is unclear, one likely retirable | 🟡 | Dashboards |
| H6 | Stub modules in `saas-erp/apps/`: `ab_redis_session`, `ab_s3_attachment` — real logic lives in saas-client / `ab_s3_storage_management` | 🟡 | Server cleanup |
| H7 | `bk_odoo_entity_sale` has 3× `raise NotImplementedError` framework hooks not declared abstract | 🟢 | API hygiene |
| H8 | Mixed `bk_*` (Bytekol) author/branding still on actively maintained modules — rebrand pending | 🟢 | Naming |

---

## 2. Detailed Findings by Area

### 2.1 Main-Server (saas-erp + saas-ai server-side) — 57 modules

#### 🔴 Critical
- **Geidea webhook signature verification missing** (`ab_saas_geidea_checkout`)
  - Risk: any attacker can confirm fake payments by POSTing to the callback URL.
  - Action: Add HMAC-SHA256 verification on incoming Geidea callbacks. Reject unsigned/invalid.
  - **Decision needed:** treat as P0 security fix or schedule.

#### 🟡 Cleanup
- **`bk_saas_revenue_metrics` (1 model)**: only `bk_saas_menu_enhance` references it; AI metric fetch hardcodes model names → silent break risk.
  - **Decision:** make `auto_install=True` so menu and metrics ship together, or document manual activation, or fold into `ab_ai_plan`.
- **`ab_saas_admin_dashboard` vs `ab_saas_unified_dashboard`**: unified is the new single root; admin dashboard is being superseded but still installed.
  - **Decision:** retire `ab_saas_admin_dashboard` once the unified dashboard reaches feature parity.
- **`bk_saas_menu_enhance` ↔ `ab_ghaima_menu_enhance`**: hard-coded cross-dependency at `views` line 226 (references `menu_ghaima_root`). If `ab_ghaima_menu_enhance` ever uninstalls, SaaS admin AI Provider Config breaks.
  - **Decision:** either merge them or document the coupling; current state is brittle.

#### 🟢 Hygiene
- **`bk_odoo_entity_sale`** lines 132 / 177 / 330: three `raise NotImplementedError` hooks meant for subclass implementation. Add `@abstractmethod` or comment block; current state confuses readers.
- **JSON `@route` endpoints** (across `bk_odoo_entity_sale`, `ab_saas_geidea_checkout`) leak tracebacks — wrap in try/except returning `{error, code}` with proper HTTP status.
- **`ab_saas_monitor` `/metrics`**: deprecated URL-token fallback. Plan a 6-month sunset.
- **`bk_*` author fields**: some still say "Bytekol". Mass-rebrand to "Ghaima Tech".

---

### 2.2 Tenant Business — saas-hr / saas-pos / saas-accounting / saas-dashboard

#### HR (35 modules) — 🟡

**Empty `_account` satellites** — pure stubs (manifest + ACL only, NO `models/`):
| Module | Verdict |
|---|---|
| `ab_hr_attendance_account` | empty |
| `ab_hr_disciplinary_account` | empty |
| `ab_hr_expense_account` | empty |
| `ab_hr_gosi_account` | empty |
| `ab_hr_leave_account` | empty |
| `ab_hr_loan_account` | empty |
| `ab_hr_wps_account` | empty |

**Decision needed:** delete all 7, or commit to filling them with real GL-posting logic.

**Vendored OCA modules** — `payroll` (13 models, OCA) + `payroll_account` (5 models, OCA): keep but track upstream regressions, especially around Saudi salary calc.

**Justified triplets** — `ab_hr_eos / _eos_account / _eos_payroll` actually contain code in each layer; the split-by-integration pattern is real here. Don't merge.

#### POS (15–19 modules) — 🟡

- **Employee PIN field is likely defined in 2–3 places**: `ab_pos_security`, `ab_pos_pin_gateway`, and `ab_user_pos` each touch employee/user PIN. Needs targeted code diff to confirm; if duplicated, consolidate into one module.
- **`ab_pos_printer_manager` ↔ `ab_pos_printer_network`**: clean hierarchy (manager = config, network = execution). No merge.
- **Geidea trio (`ab_payment_geidea`, `ab_pos_geidea`, `ab_pos_geidea_link`)**: exemplary three-layer separation. Leave as-is.
- **`ab_pos_hr_bridge` (`auto_install=True`)**: hard couples POS↔HR. If a customer adds HR later, this auto-installs and may collide. Document the install-order risk.

#### Accounting (4 modules) — 🟢

- `ab_account_reports` (meta builder, 14 models) and `dynamic_accounts_report` (concrete reports, 9 models) are different layers — no merge. Both should stay.
- `base_accounting_kit` (22 models) is large but cohesive. Don't split.

#### Dashboards (5 modules) — 🟡

- **`ab_dashboard_ai` has zero incoming dependencies** and is not in the global auto-install set. Its sibling `ab_dashboard_ai_insights` (`auto_install=True`) appears to cover the same ground.
- **Decision needed:** merge `ab_dashboard_ai` into `ab_dashboard_ai_insights` (wizard + engine in one) **or** retire `ab_dashboard_ai` outright.

---

### 2.3 Client-side / Mobile API / Shared

#### 🔴 `ab_s3_attachment` is duplicated

- `/home/clouderps/custom-addons/saas-client/ab_s3_attachment/` (302 lines, tenant install)
- `/home/clouderps/custom-addons/saas-erp/apps/ab_s3_attachment/` (325 lines, server install)
- Identical method surface (`_is_s3_storage`, `_file_read/_write/_delete`, quota), with the server copy ~5 lines longer (extra quota tracking).
- **Drift hazard:** a fix in one is not auto-applied to the other. This is the single biggest correctness risk in the audit.
- **Options:**
  1. Promote one copy to canonical, delete the other, add an `auto_install` toggle by environment.
  2. Extract `ab_s3_attachment_core` and make both copies thin wrappers.
- **Decision needed:** which copy is canonical? My recommendation: keep the saas-client copy as canonical (smaller surface, used in 5+ tenants), delete the apps copy, fold the extra quota lines into `ab_s3_storage_management` where they belong.

Same dual-copy pattern likely exists for `ab_redis_session` — quick check:
- `/home/clouderps/custom-addons/saas-client/ab_redis_session/`
- `/home/clouderps/custom-addons/saas-erp/apps/ab_redis_session/ab_redis_session/` (oddly nested)
- The nested apps copy looks like a placeholder. **Decision needed:** delete the apps copy if it is in fact unused.

#### 🟡 Mobile API consolidation

- **JWT/auth duplication:** `ab_mobile_pos_api/controllers/common.py` and `ab_mobile_saas_billing_api/controllers/common.py` reimplement `api_response()`, `_get_jwt_secret()`, TTL parsing — both reading the same `mobile_api.jwt_secret` config key.
  - **Action:** extract into `ab_mobile_api_common` (or fold into `ab_ghaima_base`); both modules depend on it.
- **`ab_mobile_pos_api_branch` is a 5-line bridge** (one mixin inherit). Either:
  - Merge into `ab_mobile_pos_api` with a conditional inherit, or
  - Keep as the canonical "branch overlay" pattern (it's a clear example).
- **Route map (no conflicts found)**: pos_api (51) + branch_api (34) + ai_api (6) + dashboard_api (8) + chatbot_api (4) + saas_billing_api (18). Distinct path prefixes. ✅
- Response shape is consistent (`api_response(...)` wrapper everywhere).

#### 🟡 Client Dashboards — satellite collapse

- `ab_client_dashboard_pos`, `ab_client_dashboard_stock` are **0-Python data-only** modules.
- `ab_client_unified_dashboard{_ai,_dynamic,_hr,_pos}` are also data-only menu reparents, all `auto_install=True`.
- **Decision needed:** keep as fine-grained bridges (defensible) or collapse into 1–2 unified modules. Lean towards keep — they're cheap and the auto_install gives clean conditional menu reparenting.

#### 🟡 Themes — possible merges

- `ab_ghaima_responsive` (0 models, CSS only) **could fold into** `ab_ghaima_theme` if responsive is now standard. Currently a separate optional install.
- `ab_ghaima_branch_theme` (0 models, just a sidebar icon) — thin bridge; leave or fold into `ab_branch_base`'s UI extensions.
- `ab_ghaima_core_rebrand` vs `ab_ghaima_theme`: different purposes (terminology vs visual). Keep separate but document the boundary.

#### 🟡 Approval system

- **`ab_approval_flow` (3 models) into `ab_approval_base` (5 models)**: flow is a core concept, not optional. Merge candidate. `ab_approval_integration_hr` stays separate (real domain bridge).

#### 🟢 Branches (6 modules)

- `ab_branch_account/_pos/_sale/_stock/_purchase` are each 3–5 real models. Justified fanout. **No merge.**

#### AI client modules — no overlap

- `ab_ai_client` (10 models) = AI core for tenant
- `ab_ai_chatbot` (2 models) = chat UI, depends on client
- `ab_chatter_ai` (2 models) = chatter tab, plugs into records
- All defer provider config to `ab_ai_base` + `ab_ai_gateway`. Boundary is clean. **Leave as-is.**

---

## 3. Proposed Action Phases

### Phase 1 — Critical (1 week)
1. **Geidea webhook signature verification** — implement HMAC-SHA256 verification on all `payment.transaction` callback routes.
2. **Unify `ab_s3_attachment`** — pick canonical copy, delete the other, ensure all 5 tenants + DBCLOUD use the same source.
3. **Delete `ab_redis_session` apps-side stub** (if confirmed unused).

### Phase 2 — Cleanup (2 weeks)
4. **Delete the 7 empty HR `_account` stubs** OR plan their implementation (decision required).
5. **Decide between `ab_dashboard_ai` and `ab_dashboard_ai_insights`** — retire one.
6. **Extract `ab_mobile_api_common`** — consolidate JWT + response wrapper.
7. **Audit POS PIN field duplication** in `ab_pos_security` / `ab_pos_pin_gateway` / `ab_user_pos` — confirm and consolidate.

### Phase 3 — Hygiene (1 week, low risk)
8. **Mark `bk_odoo_entity_sale` framework hooks `@abstractmethod`** with docstrings.
9. **Wrap JSON endpoints in error-boundary handlers** (no traceback leakage).
10. **Mass author rebrand** `Bytekol` → `Ghaima Tech` across `bk_*` manifests.
11. **Sunset `ab_saas_monitor` URL-token fallback** with a deprecation notice.

### Phase 4 — Architectural (deferred, needs discussion)
12. **Merge `ab_approval_flow` into `ab_approval_base`** (3 models).
13. **Retire `ab_saas_admin_dashboard`** in favour of `ab_saas_unified_dashboard`.
14. **`ab_mobile_pos_api_branch` merge or keep** as canonical bridge example.
15. **Theme merges** (`ab_ghaima_responsive` into `ab_ghaima_theme`?).

---

## 4. Items Explicitly NOT Recommended for Change

These were considered and found justified — listing so they aren't re-debated later:

- HR module triplet pattern where each layer has real code (e.g., `ab_hr_eos/_eos_account/_eos_payroll`) — **keep separated**.
- Branch fanout (6 modules) — **keep separated**.
- Geidea trio (`ab_payment_geidea/_pos_geidea/_pos_geidea_link`) — **exemplary design, keep**.
- Mobile API split (pos / branch / ai / dashboard / chatbot / billing) — **clean, no conflicts**.
- AI client triad (`ab_ai_client / _ai_chatbot / _chatter_ai`) — **distinct UI surfaces**.
- Accounting reports split (`ab_account_reports` builder + `dynamic_accounts_report` concrete) — **two layers, both needed**.
- `bk_*` core modules (`bk_infrastructure_base`, `bk_server_management`, `bk_odoo_entity`, `bk_odoo_entity_sale`, `bk_odoo_saas_kit_pro`, `bk_acme`) — **active core, don't rename**.

---

## 5. Decisions Required (please review)

Tick what you want to do; I'll plan implementation per item.

- [x] **D1** — Geidea webhook HMAC verification hoisted to controller boundary (was already enforced at model level; controller now rejects unsigned/bad-sig before touching tx state)
- [x] **D2** — Unify `ab_s3_attachment` (canonical = apps copy with boto3 fallback fix; now in saas-share)
- [x] **D3** — Delete `ab_redis_session` apps-side copy (was double-nested + dead; saas-client copy is canonical, now in saas-share)
- [x] **D4** — Delete the 7 empty HR `_account` stubs
- [x] **D5** — Retire `ab_dashboard_ai`
- [x] **D6** — Extract `ab_mobile_api_common` (lives in saas-share)
- [x] **D7** — Audit POS PIN fields — no duplication; removed one orphan file
- [x] **D8** — Investigated; no action. Admin and unified are complementary layers (admin = dashboard widget, unified = menu reparenting). Both stay.
- [ ] **D9** — Merge `ab_approval_flow` into `ab_approval_base` — *deferred*
- [ ] **D10** — Merge `ab_ghaima_responsive` into `ab_ghaima_theme` — *deferred (theme repo excluded)*
- [ ] **D11** — Mass author rebrand to "Ghaima Tech" — *deferred*
- [ ] **D12** — Add `@abstractmethod` to `bk_odoo_entity_sale` hooks + JSON error boundaries — *deferred*

Bonus done: **`ab_ai_base` moved** from `saas-ai` → `saas-share`, and **`bytekol_db_filter`** dead module deleted (fork patch in `odoo/http.py` replaced its DB-routing role).

---

## 6. Stats

| Repo | Modules | Avg models/mod | Avg controllers/mod |
|---|---:|---:|---:|
| saas-erp | 56 | varies (1–22) | 0–3 |
| saas-hr | 35 | 0–3 | 0 |
| saas-pos | 19 | 1–9 | 0–2 |
| saas-client | 17 | 0–10 | 0–3 |
| ghaima-api | 7 | 0–6 | 2–10 |
| saas-theme | 7 | 0–3 | 0–2 |
| saas-branches | 6 | 3–7 | 0–2 |
| saas-ai | 5 | 1–10 | 0–2 |
| saas-dashboard | 5 | 1–4 | 0–2 |
| saas-accounting | 4 | 2–22 | 0–1 |
| saas-approval | 3 | 3–5 | 0 |
| **TOTAL** | **151** | | |

Empty / stub modules: 7 (HR `_account` satellites) + 2 (`ab_redis_session` apps + `ab_s3_attachment` apps stub) + 1 (`ab_dashboard_ai` orphan) = **10 candidates for removal or completion.**

---

*Generated 2026-05-06. No code changes have been made — this document exists only to drive the discussion.*
