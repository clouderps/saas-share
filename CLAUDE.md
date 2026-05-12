# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo scope

`saas-share` holds **pure shared infrastructure modules** that install on **both** the central CloudERPs server (DBCLOUD) **and** tenant entity containers. Domain modules (HR / POS / accounting / branches / approvals / theme) live in their own repos and never depend back into here.

A module belongs in `saas-share` only when **all** of these hold:

1. It runs on both DBCLOUD and tenant entities (or could).
2. It has no dependency on a business-domain repo.
3. It's a tool / backend / integration adapter, not a feature.

If any condition fails, it stays in its existing repo.

## Modules (current contents)

| Module | Type | Notes |
|---|---|---|
| `ab_mobile_api_common` | Library (import-only — no models, no views, no routes) | Shared CORS / JSON / JWT-secret / TTL / request-body helpers. Imported by `ab_mobile_pos_api` (tenant) and `ab_mobile_saas_billing_api` (DBCLOUD). |
| `ab_s3_attachment` | Backend adapter | Redirects `ir.attachment` storage to AWS S3 with safe boto3-missing fallback. |
| `ab_redis_session` | Backend adapter | Stores Odoo sessions + bus notifications in Redis (multi-node HA). |
| `ab_ai_base` | Service layer | Multi-provider AI config (OpenAI / Claude / Gemini / Ollama) + reusable AI service. Author still listed as "AB Solutions" — outside the Ghaima Tech rebrand pass. |

## Architecture details that aren't obvious from the file tree

### `ab_mobile_api_common` is the canonical JWT seam

- `get_jwt_secret()` reads or mints `ir.config_parameter` key **`mobile_api.jwt_secret`**. Both tenant POS API and DBCLOUD billing API sign with this same secret — so a future shared validation gateway needs no extra config.
- `get_access_ttl()` / `get_refresh_ttl()` read `mobile_api.access_token_ttl` / `mobile_api.refresh_token_ttl` (defaults: 1h / 30d).
- The module deliberately **does not** export a `jwt_required` decorator. Each consumer keeps its own:
  - tenant `ab_mobile_pos_api` validates `mobile.device` + `branch_id`,
  - DBCLOUD `ab_mobile_saas_billing_api` validates `partner_id` + `scope=saas_billing`.
  Different auth surfaces, same secret.
- `CORS_HEADERS` sets `Access-Control-Allow-Credentials: false` on purpose — mobile clients don't send `Origin`, and disabling credentials prevents accidental browser-context credential leakage if a route is reused from web.

### `ab_s3_attachment` and `ab_redis_session` are config-driven

Both modules expect their `ir.config_parameter` keys to be **injected by the SaaS provisioning platform**, not entered by hand. Provisioning is the system of record; manual edits get clobbered on the next deploy.

`ab_s3_attachment` keys:
```
ir_attachment.location      = 's3'
ab_s3.bucket                = '<bucket>'
ab_s3.prefix                = 'entity_<id>/filestore'
ab_s3.region                = '<aws-region>'
ab_s3.access_key_id         = 'AKIA...'
ab_s3.secret_access_key     = '...'
ab_s3.max_storage_bytes     = 0   # 0 = unlimited
```

`ab_redis_session` keys:
```
ab_redis.url          = redis://host:6379/0
ab_redis.prefix       = entity_<id>     # session-key isolation prefix
ab_redis.session_ttl  = 86400           # seconds
```

### Tenant container deployment caveat (load-bearing)

Tenant containers were provisioned **before** saas-share existed. They bind-mount each repo individually, so a fresh tenant doesn't pick up `saas-share` from a normal `git pull`. The interim fix:

```
cp -a /home/clouderps/custom-addons/saas-share/  \
      /opt/ghaima_containers/<container>/odoo_source_code/saas-share/
```

The copy persists across container restart but a new `git pull saas-share` requires re-running the `cp -a`. The long-term fix (tracked as task #84) is to register an `odoo.addon.path` record on the `odoo.image` so future containers get the bind mount automatically. Until then, after pulling here you must propagate to tenant containers explicitly.

### Activation

The path goes into the central server's `clouderps-odoo.conf` and `/opt/ghaima.conf` inside each tenant container:

```
addons_path = ...,/home/clouderps/custom-addons/saas-share,...
```

In this dev workspace the equivalent line is in `clouderps-apps/odoo.conf` (already configured).

## Repo helpers

`git-pull.sh` and `git-push.sh` operate across **every** CloudERPs repo on the host (saas-erp, saas-accounting, ghaima-api, saas-ai, saas-approval, saas-branches, saas-client, saas-dashboard, saas-hr, saas-pos, saas-server, **saas-share**, saas-theme). Use them when you need a workspace-wide pull rather than per-repo:

```bash
sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh         # main server only
sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh --all   # main + Apps server
sudo -u clouderps bash /home/clouderps/custom-addons/git-pull.sh --apps  # Apps server only
```

`--all` and `--apps` propagate the same pulls to the Apps server (`root@10.0.128.20:/opt/ghaima_source_code/18.0/`) over SSH. Tenant containers bind-mount the source so most changes go live without a rebuild — but call `_reload_odoo_entity_registry` on each tenant after pulling code that affects the registry.

## Local install / update commands (dev workspace)

From the workspace root (`clouderps-apps/`), using the project venv:

```bash
# Install one of the shared modules into a tenant DB
saas-venv/bin/python odoo-18.0/odoo-bin -c odoo.conf -d <database> -i ab_s3_attachment --stop-after-init
saas-venv/bin/python odoo-18.0/odoo-bin -c odoo.conf -d <database> -i ab_redis_session --stop-after-init
saas-venv/bin/python odoo-18.0/odoo-bin -c odoo.conf -d <database> -i ab_ai_base --stop-after-init

# ab_mobile_api_common is import-only — installing it is harmless but
# the consumer modules pick it up via their `depends` lists, so
# normally you just update the consumer:
saas-venv/bin/python odoo-18.0/odoo-bin -c odoo.conf -d <database> -u ab_mobile_pos_api --stop-after-init
saas-venv/bin/python odoo-18.0/odoo-bin -c odoo.conf -d <database> -u ab_mobile_saas_billing_api --stop-after-init
```

External Python deps the modules pull in: `boto3` (S3), `redis` (Redis), `jwt` (JWT helpers), `requests` (AI providers).

## MODULE_CLEANUP_PLAN.md

The historical record of how `saas-share` came into existence on 2026-05-06 — what was unified, what was deleted, what was deferred. Useful when reviving any of the deferred items (D10 theme merges, container bind-mount task #84, etc.). Don't treat its earlier sections as live TODO; check `§0 Execution Log` for current status before acting on any item.
