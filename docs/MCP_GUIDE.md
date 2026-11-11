# Ghaima MCP: Setup and Capabilities Guide

> **Coming soon.** MCP access is being rolled out; the screens below describe the agreed design and may change slightly.

## Status

MCP (Model Context Protocol) lets an outside AI app (Claude Desktop, Cursor, ChatGPT…) use a Ghaima instance's data and actions with the signed-in user's own permissions. Each instance has its own MCP address; each user turns it on with a personal token; the central plan decides who may use it.

**Built today (2026-11-11): groundwork only.** Each of the 66 assistant tools has an **Expose over MCP** switch, can describe itself as an MCP tool (name, inputs, read-only/destructive hint), and every call is checked against the plan, the kill switch and the user's permissions.

**Not built yet:** the `/mcp` server address, per-user MCP tokens, the MCP settings screen, and the plan options on central.

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

**Not offered over MCP (screen-only):** navigate, open_*, screen_button, update_preference.

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
