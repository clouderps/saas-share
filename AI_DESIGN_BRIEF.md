# Ask AI — design pass brief

Status: **not started.** Written 2026-08-03 as a handoff so a fresh
session can begin without re-deriving anything.

Start here: `saas-share/ab_ai_agent/static/src/scss/ai_agent.scss` and
`ab_ai_agent/static/src/components/ai_agent_chat/ai_agent_chat.xml`.

---

## 1. What the user actually said

> "the design isn't modern … can test using browser to improve the
> UI/UX and also agent performance"

Asked to pick what reads as dated, they selected **all four**:

| # | Complaint | What it means concretely |
|---|---|---|
| 1 | Too plain / low contrast | Flat white cards, thin grey borders, no visual hierarchy — the eye lands nowhere |
| 2 | Dated typography & spacing | Cramped, generic sizes; no real type scale or vertical rhythm |
| 3 | Empty / boring landing state | Panel opens to a near-blank card plus chips. No sense of what the assistant can do |
| 4 | Feels like a form, not a product | Result tables and chrome read as raw Odoo, not Linear/Stripe |

Treat 3 and 4 as the highest value — they are the first and last things a
user sees. 1 and 2 fall out of fixing them properly.

---

## 2. Current state (what exists, so you do not rebuild it)

The **structure** was reworked earlier this session and is sound. The
problem is purely visual, not architectural. Do not revert to bubbles.

* A turn renders as a quiet **question line** + an **answer card**
  (`.o_ai_answer`) with header / block body / action footer. Chat
  bubbles, avatars and typing dots were deliberately removed — the agent
  is for decision support and reporting, not conversation.
* Card bodies delegate to `<AiResponse/>` from `ab_ai_ui`. Do NOT
  re-implement block rendering; that duplication was just deleted.
* Waiting state is a skeleton that mirrors the answer's shape
  (`.o_ai_skeleton`), honouring `prefers-reduced-motion`.
* Slash commands render their own result block
  (`ab_ai_command/static/src/command_palette.scss`) — draft badge,
  header table, line table, total, create-offer buttons.
* Starter chips come from `/ai_agent/starters`, derived from the user's
  real menu access. They are not a fixed list; keep it that way.

Surfaces the design must survive, all three:

1. chatter side panel (~320px, narrow)
2. expanded dialog
3. full-page console (`ab_manager_agents.action_manager_console`)

---

## 3. Constraints (from the operator's standing rules)

* **No generic AI aesthetic.** No purple→pink gradients, no centered
  hero cards as a default, no glassmorphism without purpose, no Inter on
  everything, no emoji as icons.
* **Reference real systems**: Odoo native, IBM Carbon, Radix, Linear,
  Stripe, Material 3. Not Bootstrap defaults.
* **RTL is first-class.** Every directional rule must be logical
  (`margin-inline-start`, `border-inline-end`, …). Verify at
  `dir="rtl"` before calling it done — the existing SCSS already
  follows this, keep it.
* **Accessibility is not optional**: contrast, visible focus states,
  semantic HTML, touch targets ≥24px web.
* **Ghaima tokens only** — never hardcode brand colour. Defined at the
  top of `ai_agent.scss` and sourced from
  `ab_ghaima_theme/static/src/css/ghaima_variables.css`:

  ```
  --ghaima-blue  #005FF6      --ghaima-navy  #0D00A2
  --ghaima-cyan  #5DD8CA      --ghaima-bg    #F7F8FC
  font body: Vazirmatn        font heading: Drystick
  ```

* Dark mode exists (`ab_ghaima_theme`, `ghaima_color_mode` service,
  flips `data-bs-theme` + `.ghaima-dark`). Check the pass in both.

---

## 4. Plan first

The operator's rules require **2–3 directions in text before producing
files**. Do not skip this. Show them as ASCII mockups via
AskUserQuestion previews — that worked well for the answer-card
decision earlier and they picked from it immediately.

---

## 5. How to verify (this is the part that catches real bugs)

Playwright + system Chrome. A working harness is described below; the
earlier session used exactly this and it found a bug the unit tests
could not (palette visibility read a stale value because `t-model`
updates state *after* keydown).

```python
b  = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
pg = await b.new_page(viewport={'width': 1440, 'height': 950})
# login at /web/login, then:
await pg.goto(f'{BASE}/odoo/action-ab_manager_agents.action_manager_console')
```

* Test account: `uiqa@ghaima.local` / `ghaima123` on **FAYIAPROD**,
  port 8015. It holds Sales + Purchase + HR + Invoicing so the whole
  command palette is visible. **Disable it again when finished** — it
  carries `base.group_system`. It cannot be deleted (its `ai_agent_run`
  rows are audit history); archive + scramble the password instead.
* Assets are cached: after editing SCSS/XML,
  `DELETE FROM ir_attachment WHERE res_model='ir.ui.view' AND name LIKE '%assets%'`,
  then `-u <module>`, then restart. `--dev=assets` alone is not enough.
* Always assert `console errors == 0` in the harness. OWL `t-inherit`
  failures surface **only** in the browser, never at upgrade time.
* Screenshot light + dark + RTL.

---

## 6. Agent performance — measured, not yet fixed

Real numbers from `ai_agent_run` on FAYIAPROD (67 runs):

```
hops  runs   avg      worst    tokens
  1     26   2.3s     4.2s      2,731
  2     32   4.5s     9.0s      6,582
  3      7   4.7s     6.6s      9,847
  4      1   9.4s     9.4s     23,197
  6      1  12.5s    12.5s     33,150
```

≈ **2.2s per hop, linear.** And:

```
avg prompt tokens     5,977
avg completion tokens    96     ← the answer is 1/62nd of the request
prompt share            98%
cache hit rate           0%
```

**Root cause:** every hop re-sends a ~6k-token system prompt (persona +
live business snapshot + RAG + topics). `cached_tokens` is only ever
*read* from the provider response — nothing in the codebase ever *sends*
`cache_control` (Anthropic) or `cachedContent` (Gemini). Caching is
instrumented but never requested.

Fixes, ranked:

1. **Enable provider prompt caching.** The system prompt is byte-identical
   across hops within a run. Touches `ab_ai_agent/services/llm_adapter.py`
   and the provider calls in `ab_ai_base` / `ab_ai_gateway`. Highest
   impact, needs care — it is the live request path for every provider.
2. **Trim the always-on snapshot** (`_business_snapshot_block` in
   `runtime.py`) — injected on every hop even when the question needs
   none of it.
3. **Fewer hops.** The 2-hop average is one tool call + one answer.

Already won, no work needed: the slowest recorded run was
`/create invoice partner abdalmola` at 6 hops / 33,150 tokens / 12.5s.
That input now goes through the command path — **zero tokens, no model
call**. Slash commands are the biggest latency win available for the
operations done most often.

Still unmeasured: "wrong or vague answers" and "too many clarifying
questions". Those need examples, not aggregates. `ai_agent_run` stores
every question, reply and tool trace — ask the operator for two or three
answers that disappointed them and trace which tool fired.

---

## 7. Do not regress these

Hard-won this session; each has a test or a live verification behind it.

* Answer cards, not chat bubbles.
* One block renderer (`AiResponse`), never a second copy.
* Starter chips derived from real menu access, never a fixed list.
* Commands create **drafts only**; nothing posts.
* Barcodes match exactly; only product *names* may fuzzy-match.
* Ambiguity is a question, never a guess.
* Dates print long-form (`3/8/26` reads differently per locale).
* Every directional CSS rule stays logical.
