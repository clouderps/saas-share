# Ghaima AI — Commands & Agent Capability Plan

Status: **proposal, nothing built yet**
Scope: `ab_ai_agent` (+ `ab_ai_chatbot`, `ab_scan_docs`, `saas-approval`)
Date: 2026-08-03

---

## 1. What already exists

This matters, because most of the risky machinery is already in the
codebase and does not need designing again.

| Building block | Where | State |
|---|---|---|
| Two-phase write confirmation (`requires_confirmation` → `confirm=True`) | `ab_ai_agent/services/tool_dispatcher.py` | working |
| Idempotency + replay protection | `ai.chat.action.log` (`UNIQUE(idempotency_key, tool)`) | working |
| Confirm/cancel chip flow, bypasses the LLM on the second call | `ai_chat.execute_action` | working |
| Per-tool ACL (`group_ids` → `is_invocable_by`) | `ai.agent.tool` | working |
| Tools dispatch **as the requesting user** (record rules apply) | `runtime._resolve_tools` | working, tested |
| Write gate per agent (`allow_write_actions`) | `ai.agent` | working, default **off** |
| pgvector semantic index | `ab_ai_base/models/semantic_index.py` | working |
| Memory / preferences | `ab_ai_chatbot/services/tools/memory.py` | working |
| Approval framework | `saas-approval/ab_approval_base` | working, not wired to AI |
| Scan-docs → chat bridge | `ai_chat._handle_scan_attachment` | working |
| Daily report module | `saas-ai/ab_ai_daily_report` | **stub — `static/` only**, PRD in `saas-ai/improvment_ai.txt` |

Existing write tools: `confirm_sale_order`, `cancel_sale_order`,
`post_invoice`, `create_task`, `record_action`, `remember_fact`,
`remember_note`.

**Nothing creates a document from scratch today.** That is the gap the
command layer fills.

---

## 2. The design tension, and how it resolves

Two requirements pull against each other:

> "added key word like `/create invoice partner name: abdalmola date: 3/8/26; items: …`"

> "need intelligent answer, not built on specific responses"

A rigid grammar is the opposite of intelligent — any deviation fails,
and we end up maintaining a parser that users have to learn.

**Resolution: the command is an accelerator, not a grammar.**

```
/create invoice partner: abdalmola; date: 3/8/26; items: 6281..., 2x latte
   │            │
   │            └─ everything after the verb is FREE TEXT
   └─ only the verb is parsed deterministically
```

Three tiers, in order, stopping at the first that succeeds:

1. **Verb match** — `/create invoice` resolves deterministically to a
   command record. Free, instant, predictable.
2. **Key:value sweep** — a tolerant scan for `key: value` pairs split on
   `;` or newline, with aliases (`partner name` / `partner` / `customer`
   / `عميل` → `partner_id`). Free, no LLM.
3. **LLM extraction** — anything the sweep did not fill is handed to the
   agent, which extracts it from the raw text and asks for what is still
   missing. This is what makes loose input work.

So all of these produce the same draft:

```
/create invoice partner: abdalmola; date: 3/8/26; items: 2x latte
/create invoice for abdalmola tomorrow, two lattes
اعمل فاتورة لعبدالمولى بكرة، لاتيه اثنين
```

The slash form is for people who type it every day. The prose form is
for everyone else. **Neither is privileged.**

---

## 3. Non-negotiable safety rules

These come out of what the tools already do, and out of the fact that
these commands write to accounting.

1. **Draft first, always.** A command NEVER posts, confirms or validates
   in one step. It creates a draft and renders a preview card. Posting is
   a second, explicit action.
2. **Preview shows the resolved reality**, not the input: the actual
   partner record it matched, actual products, computed taxes and total.
   The user confirms what will exist, not what they typed.
3. **Ambiguity stops the flow.** Three partners match "abdalmola" → chips
   to pick one. Never guess on identity.
4. **Dates are confirmed, never assumed.** `3/8/26` is 3 August in KSA
   and 8 March in the US. The preview prints the resolved date in long
   form (`3 August 2026`) so a wrong parse is visible before it matters.
5. **Permission-filtered palette.** `/` lists only commands this user can
   actually run — same rule as `find_menu`. A cashier never sees
   `/create invoice`.
6. **Everything reuses the existing idempotency + audit log.** No new
   write path, no second audit trail.
7. **`allow_write_actions` stays off by default.** Commands are opt-in
   per agent, per tenant.

---

## 4. Phased execution plan

### Phase 1 — Command spine  *(foundation, ~3–4 days)*

| Item | Detail |
|---|---|
| `ai.agent.command` model | `code`, `verb` (`create invoice`), `target_model`, `group_ids`, `is_write_action`, `field_map` (JSON: canonical field → list of aliases), `active` |
| Parser service | `services/command_parser.py` — verb match → key:value sweep → structured dict + `unresolved[]`. Pure function, unit-testable without a model call. |
| `/` palette | OWL autocomplete in the composer, fed by a permission-filtered `/ai_agent/commands` endpoint |
| Preview card | New `command_preview` block in `ab_ai_ui` — resolved fields, line table, total, Confirm / Edit / Cancel |
| Wiring | Preview → existing `execute_action` chip flow, existing idempotency key |

**Exit test:** `/create invoice partner: <name>` produces a draft
`account.move` for the right partner, or a clean "which one?" — and a
user without invoice rights cannot see the command at all.

### Phase 2 — Entity resolution  *(~3 days)*

| Resolver | Strategy |
|---|---|
| Partner | exact name → exact ref/VAT → fuzzy `ilike` → semantic (`ai.semantic.index`). >1 hit ⇒ chips. |
| Product | **barcode exact first** → internal reference → name `ilike` → semantic on description. Barcode must never fuzzy-match. |
| Date | locale-aware (`ar_001`/`ar_SA` ⇒ d/m/y), plus relative words (`tomorrow`, `بكرة`, `نهاية الشهر`) |
| Quantity / price | `2x latte`, `latte x2`, `latte 2` — and never infer a price the user did not give; use the pricelist |

Each resolver returns `{value, confidence, alternatives[]}`. Anything
below threshold becomes a chip, never a silent choice.

**Exit test:** a barcode resolves to exactly one product or fails; it
never resolves to a *similar* product.

### Phase 3 — The command set  *(~4 days)*

Ordered by value ÷ risk:

| Command | Creates | Risk |
|---|---|---|
| `/create quote` | `sale.order` draft | low — draft quotes are harmless |
| `/create customer` | `res.partner` | low |
| `/create task` | `project.task` | low (tool exists) |
| `/create product` | `product.template` | medium — dedupe on barcode first |
| `/create invoice` | `account.move` draft | **high — accounting** |
| `/create bill` | vendor `account.move` draft | high |
| `/create po` | `purchase.order` draft | medium |
| `/post`, `/confirm`, `/validate`, `/cancel` | wraps existing `record_action` | already gated |
| `/refund <ref>` | credit note draft | high |

Batch forms (`/post all draft invoices for August`) render a **list**
preview with per-row checkboxes before a single confirm.

### Phase 4 — Intelligence layer  *(~4 days)*

- **NL equivalence** — the agent recognises create-intent without a
  slash and routes to the same command path. One code path, two syntaxes.
- **Slot-filling** — missing required field ⇒ ask one question, keep the
  partial draft in conversation state, resume on answer.
- **Scan → command** — the scan-docs bridge already turns an attachment
  into extracted data; feed that straight into a prefilled preview card.
  Photograph a supplier invoice, get a bill draft to confirm.
- **Voice → command** — mic already exists; route transcription through
  the same parser.

### Phase 5 — Governance  *(~3 days)*

- **Approval routing** — writes above a configurable value go to
  `ab_approval_base` instead of executing. Ties AI writes into the
  approval chain the business already uses.
- **Undo window** — reverse an agent-created draft within N minutes
  (drafts only; posted documents follow normal accounting reversal).
- **Agent-write audit view** — one list of every write the AI made:
  who asked, what ran, what it created, confirmed or cancelled.
- **Per-user spend guard** — extend the existing budget guard so a
  runaway loop cannot burn a month of tokens.

### Phase 6 — Proactive  *(~5 days)*

- **Daily brief** — implement `ab_ai_daily_report`, which is currently a
  stub with a written PRD (`saas-ai/improvment_ai.txt`). Cron → analysis
  → push to the user's inbox and the mobile app.
- **Anomaly watch** — thresholds on the metrics the tools already
  compute; alert on break, not on schedule.
- **Saved / recurring answers** — pin a good answer, re-run it weekly.
- **Export** — answer → PDF / XLSX (reuse the report engine).

---

## 5. Broader idea catalogue

Everything considered, scored on value against effort. **Phase** column
shows where it lands above, or `—` if I recommend not doing it.

### Worth doing

| # | Idea | Value | Effort | Phase |
|---|---|---|---|---|
| 1 | Slash commands, permission-filtered palette | high | M | 1 |
| 2 | Draft + preview + confirm for every write | high | M | 1 |
| 3 | Barcode-exact product resolution | high | S | 2 |
| 4 | Ambiguity chips instead of guessing identity | high | S | 2 |
| 5 | Locale-aware date confirmation | high | S | 2 |
| 6 | NL equivalence (no slash required) | high | M | 4 |
| 7 | Photo/PDF → prefilled draft (bridge exists) | high | M | 4 |
| 8 | Slot-filling dialogue for missing fields | high | M | 4 |
| 9 | Approval routing for high-value writes | high | M | 5 |
| 10 | Agent-write audit view | high | S | 5 |
| 11 | Daily brief (PRD already written, module is a stub) | high | L | 6 |
| 12 | Company knowledge base — RAG over SOPs/policies | high | M | 6+ |
| 13 | Undo window for agent-created drafts | med | S | 5 |
| 14 | Batch operations with per-row preview | med | M | 3 |
| 15 | Anomaly watch → alert on break | med | M | 6 |
| 16 | Saved / recurring answers | med | M | 6 |
| 17 | Export answer to PDF/XLSX | med | S | 6 |
| 18 | Learn from corrections (memory tools exist) | med | M | 6+ |
| 19 | Voice → command | med | S | 4 |
| 20 | Commands in the mobile POS chat | med | M | 6+ |

### Deliberately not recommended

| Idea | Why not |
|---|---|
| Free-form SQL / ORM execution by the agent | Unbounded blast radius. The tool catalogue is the security boundary; a generic executor destroys it. |
| Auto-posting without confirmation | One hallucinated amount becomes a posted journal entry. The confirm step is the whole safety model. |
| Agent editing existing posted documents | Accounting immutability. Reversal is the correct primitive, and it is already a command. |
| Multi-agent "swarm" for business questions | Cost multiplies, accuracy does not. A single agent with good tools beats several with weak ones. |
| Translating tool descriptions to Arabic | Model-facing text. Degrades tool selection, invisible to users. (Already decided.) |
| Rigid-only command grammar | Fails on any deviation and contradicts the "intelligent, not canned" requirement. |

---

## 6. Sequencing recommendation

Phases 1–2 are the real work; everything after is additive and can be
reordered by business priority.

```
Phase 1 ─ spine ──┐
                  ├─→ Phase 3 ─ command set ─→ Phase 5 ─ governance
Phase 2 ─ resolve ┘                    │
                                       └─→ Phase 4 ─ intelligence ─→ Phase 6 ─ proactive
```

Suggested first slice to prove the whole shape end to end, before
committing to the rest:

> **Phase 1 + Phase 2 partner/date resolvers + `/create quote` only.**
> A quote is a draft with no accounting consequence, so the blast radius
> while the pattern is being validated is nil. If the flow feels right on
> quotes, `/create invoice` is the same code with a different target
> model.

Rough total for phases 1–6: **~22 working days**, assuming the existing
confirm/idempotency/audit machinery holds up — which it should, since it
is already in production use for `post_invoice`.

---

## 7. Open questions for the business

1. **Which commands does a cashier get?** My assumption: none that write
   accounting; `/create quote` and `/create customer` at most.
2. **Value threshold for approval routing?** Needs a number.
3. **Should `/create invoice` be allowed at all on mobile**, or
   back-office only?
4. **Undo window length** — 5 minutes? 30?
5. Is the daily brief wanted as email, in-app, mobile push, or all three?
   The PRD does not say.
