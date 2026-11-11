# Ghaima MCP: Setup and Capabilities Guide

> **Coming soon.** MCP access is being rolled out; the screens below describe the agreed design and may change slightly.

## Status

MCP (Model Context Protocol) lets an outside AI app (Claude Desktop, Cursor, ChatGPT…) use a Ghaima instance's data and actions with the signed-in user's own permissions. Each instance has its own MCP address; each user turns it on with a personal token; the central plan decides who may use it.

**Built (2026-11-11), not yet deployed:**

- **`ab_mcp` core** (saas-share, domain-free): `POST /mcp` on each instance, a stateless JSON-RPC 2.0 server (`initialize`, `ping`, `tools/list`, `tools/call`; protocol 2025-11-25 / 2025-06-18). Every request goes through these checks in order: bearer token, kill switch, `mcp.enabled` (plan ceiling), allowed clients, assistant seat, MCP seats, daily call quota (429). Tools then run as the token's user through the shared `ab_ai_agent` dispatcher, with PII masked unless the plan allows it. Errors carry a `request_id` and never include exception text.
- **Personal tokens** (`mcp.token`): `gmcp_…` tokens, stored as a SHA-256 hash only, shown once, with an expiry (30/90/365 days) and a preset (read-only, manager, or a custom tool list). The owner can revoke a token. Each call is logged with an argument hash only, kept 90 days.
- **Connect wizard** (My Profile ▸ MCP access, or AI ▸ My AI app connections): generates a token and a ready-to-paste config for Claude Desktop, Claude Code, VS Code and others. The instance settings have an MCP block (enable, URL, write tools, local limits, seats/calls status) and an **Exposed tools** list for turning tools on or off.
- **Approvals:** write tools never act directly over MCP. They create a pending action (`origin = mcp`) that the user confirms or rejects under AI ▸ Approvals within 15 minutes. `get_proposal_status` lets the AI app check the result.
- **Plan ceiling:** central `ai.plan` has `mcp_enabled`, `mcp_max_users`, `mcp_calls_per_day` and `mcp_write_tools`. The tenant bridge `ab_ai_agent_plan_ceiling` caps the local settings with them.
- **3 tool packs** (saas-share, auto-install on `[ab_ai_agent, <app>]`, ORM as the user, company-scoped, read-only, exposed by default):
  - `ab_ai_tools_sale`: `sales_totals`, `top_products`, `top_customers`, `sales_by_branch`, `sales_trend_monthly`
  - `ab_ai_tools_account`: `ar_aging`, `top_overdue_partners`, `pl_trend`, `cashflow_daily`, `cashflow_by_journal`, `pl_summary`, `cash_position`, `tax_summary`
  - `ab_ai_tools_pos`: `pos_session_status`, `top_cashiers`, `pos_shift_summary`, `pos_payment_mix`

  These tools used to live in `ab_ai_chatbot` and were moved out. On an existing instance, installing a pack adopts the existing tool rows, so ids and codes stay the same and nothing is duplicated. The in-app assistant still reaches them through the shared registry.

**Not built yet:**

- OAuth 2.1 sign-in for MCP clients (only bearer tokens today).
- Tool packs for the other areas (inventory, purchase, HR, CRM, MRP…). Inventory, customer and record tools are still inside `ab_ai_chatbot` and are not MCP-exposed by default.
- Signed plan delivery: the tenant can currently edit its own plan ceiling.
- A per-user daily quota (the quota is per instance today).
- `ai.usage.local.log` rows with `surface = mcp`.

## How it fits

1. The **AI app** sends the user's MCP token.
2. The **instance** `/mcp` endpoint (`https://company.ghaima.sa/mcp`) checks the token.
3. The **gate** checks the plan, the kill switch, the user's seat and the exposed tools.
4. The **tools run as the user**: read tools answer now; write tools create a proposal.
5. For writes, the **user confirms inside Ghaima** within 15 minutes.

The **central server** signs the plan limits down to the gates and receives only daily counters from the instance. Central never sees questions or answers.

## Activation

Four steps, in order. Skip one and the AI app is refused.

### Step 1: Central (Ghaima team)

SaaS ▸ Plans ▸ *plan* ▸ **AI** tab:

- Tick **MCP access**.
- Set **MCP users**, **MCP calls per day**, and **Allow write tools** (off by default).
- Save. The signed plan reaches the instance on the next sync (minutes).

### Step 2: Instance admin

Settings ▸ Ghaima AI ▸ **MCP**:

- Tick **Enable MCP**. The address is shown: `https://<company>.ghaima.sa/mcp`.
- **Exposed tools**: read tools are ticked by default; write tools stay off unless the plan allows them and you tick them.
- **Who may activate**: *Users themselves* or *Admin only*.
- Save.

### Step 3: Each user

Avatar ▸ My Profile ▸ **Ghaima AI** ▸ **MCP access** ▸ **Create token**:

- Give it a name (e.g. "Claude Desktop – laptop") and an expiry.
- Copy it now: it is shown only once.
- Revoke it any time from the same screen.

### Step 4: AI app configuration

The **Connect an AI app** wizard prints the right snippet for the chosen app, with the URL and token filled in and a copy button. The URL comes from `web.base.url`; Settings ▸ MCP warns when it differs from the host you are browsing. The token is never stored: it travels only in the result dialog, so closing the dialog (Done or X) leaves nothing behind.

**Claude Desktop** — `claude_desktop_config.json` only launches stdio servers, so the remote endpoint is bridged with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) (needs Node.js). The bearer value goes through `env` so the space in `Bearer <token>` survives argument splitting:

```json
{
  "mcpServers": {
    "ghaima": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<company>.ghaima.sa/mcp",
               "--header", "Authorization:${GHAIMA_AUTH}"],
      "env": { "GHAIMA_AUTH": "Bearer <your MCP token>" }
    }
  }
}
```

**Claude Code** — native HTTP transport:

```bash
claude mcp add --transport http ghaima https://<company>.ghaima.sa/mcp --header "Authorization: Bearer <your MCP token>"
```

**VS Code** — `{"servers": {"ghaima": {"type": "http", "url": …, "headers": {…}}}}`.

**Cursor and other URL-capable clients:**

```json
{
  "mcpServers": {
    "ghaima": {
      "url": "https://<company>.ghaima.sa/mcp",
      "headers": {
        "Authorization": "Bearer <your MCP token>"
      }
    }
  }
}
```

Restart the app. It lists Ghaima's tools; try *"what were today's sales?"*.

## Capabilities

The same 66 tools as the in-app assistant (47 read, 19 write). They work only on data the user can already open, and write tools always create a proposal that is confirmed in Ghaima.

| Area | Read tools | Write tools | Example |
|---|---|---|---|
| Sales | sales_totals, sales_trend_monthly, sales_by_branch, top_products, top_customers, customer_activity | confirm_sale_order, cancel_sale_order | "Sales this month by branch vs last month" |
| POS | pos_session_status, top_cashiers | — | "Which POS sessions are still open?" |
| Accounting | pl_summary, pl_trend, cash_position, cashflow_daily, cashflow_by_journal, tax_summary, ar_aging, overdue_receivables, top_overdue_partners | post_invoice, create_journal_entry (draft) | "VAT due this quarter", "Who owes us more than 30 days?" |
| Inventory | inventory_summary, product_stock_status, low_stock_products, out_of_stock_products, reorder_rules | — | "What runs out this week?" |
| HR | hr_attendance_missing_today, hr_attendance_open_shifts, hr_leave_pending | — | "Who hasn't checked in today?" |
| Any data | find_records, search_records, read_record, get_record, count_records, recent_records, query_data, data_analysis, semantic_search, dashboard_metrics, system_snapshot | create_record, update_record, record_action, act_on_record | "Create a draft quote for Al-Noor: 10 × Latte" |
| Work and messages | — | create_task, schedule_activity, post_message, run_command | "Remind me to call this customer Sunday" |
| Help and knowledge | kb_search, kb_read, find_menu, explain_screen, list_my_apps, list_commands, date_reference | remember_fact, remember_note, update_settings | "How do I close a POS session?" |

**Not offered over MCP:** screen-only tools (navigate, open_*, screen_button, update_preference, update_settings), memory tools (remember_fact, remember_note), server-action tools and any write tool that would not ask for confirmation. Settings ▸ MCP ▸ Exposed tools lists only tools MCP can actually offer (`ai.agent.tool.mcp_available`).

**In practice:**

- Ask business questions in Arabic or English and get figures, tables and charts.
- Draft quotes, journal entries, tasks and notes, then confirm them in Ghaima.
- Combine Ghaima data with other tools in the same app (email, spreadsheet, calendar).

## Limits and safety

An MCP token can never do more than its user can.

- **Permissions**: runs as the user; access rights, record rules, allowed companies and branches apply. No admin override.
- **Writes need confirmation**: the pending action is approved inside Ghaima and expires in 15 minutes. A "confirm" sent by the AI app is ignored.
- **Kill switch**: stops the in-app assistant, slash commands and MCP for everyone, immediately.
- **Actions off** (locally or by plan): only read tools are offered.
- **Seats**: a token works only while its user holds an assistant seat; lowering seats removes the most recent activations first.
- **Privacy**: IDs, IBANs and phone numbers are masked unless the plan allows PII; errors give a reference id, never internal details.
- **Tracking**: only counters go to central (calls, tokens, tool names per day), never content.
- **Revoke**: a user or admin can revoke a token at any time; it stops on the next call.

## Troubleshooting

| What the app shows | Cause | Fix |
|---|---|---|
| `401 unauthorized` | Token missing, wrong, expired or revoked | Create a new token (step 3) and update the app config |
| `403 mcp_not_in_plan` | The plan lacks MCP | Upgrade the plan or ask Ghaima (step 1) |
| `403 mcp_disabled` | MCP is off on the instance | Admin ticks Enable MCP (step 2) |
| `403 no_seat` / `inactive` | User has no seat or isn't activated | Admin activates the user or raises seats |
| `403 killed` | Kill switch is on | Admin turns it off |
| Tool missing from the list | Not exposed, or user lacks access to that app | Admin ticks it under Exposed tools, or grants access |
| `429 limit reached` | Daily MCP call limit used up | Wait for the next day or raise the limit |
| "The assistant can't answer right now" | AI provider down or out of credit | Check Settings ▸ AI provider, or the gateway link to central |

## Hardening notes (Phase 0/1 review fixes)

- **Never-execute guarantee.** `ab_mcp.services.catalog.is_mcp_safe` drops, whatever
  `mcp_enabled` says: `dispatch_kind='server_action'` tools, `category='memory'` tools,
  and any `is_write_action` tool that is not confirm-first (`ACTION_TOOLS`,
  `PROPOSAL_TOOLS`, `record_action`, create/update presets). With write off on the
  token/plan, every `is_write_action` tool is hidden. Not listed means not callable.
- **Names are PII over MCP.** `top_customers`, `top_overdue_partners` and `top_cashiers`
  return people's names, which regex masking cannot catch. Over MCP they are offered only
  when `model.allow_pii` is on (owner decision pending: alternative is ids/initials). The
  in-app assistant is unaffected.
- **Quota.** `mcp.usage.day` is counted on its own short READ COMMITTED cursor in UTC days;
  a call that later fails still counts. `last_used_at` is written at most every 5 minutes.
- **Confirm re-check.** Confirming an MCP proposal also requires `mcp.enabled`, an active
  assistant for the user, and a live token of theirs with `allow_write`.
- **Seats.** Archived and portal users hold no seat; archiving a user revokes their tokens.
- **Deploy order.** On an existing tenant run, in the same invocation:
  `-u ab_ai_agent,ab_ai_chatbot -i ab_mcp,ab_ai_tools_sale,ab_ai_tools_account,ab_ai_tools_pos`
  (packs only for installed apps). A plain `-u ab_ai_chatbot` does not auto-install the
  packs, which would leave the moved tool codes without a Python callable. Each pack's
  `post_init_hook` attaches its tools to the Ghaima Assistant.
