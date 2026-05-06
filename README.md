# saas-share

Shared infrastructure modules used by **both** the Ghaima SaaS main server (DBCLOUD) and tenant entity containers.

## Scope

This repository holds **pure tools / integration / attachment-style** modules — cross-cutting infrastructure that has no domain-specific business logic. Domain modules (HR, POS, accounting, branches, approvals, themes) stay in their dedicated repos.

## Modules

| Module | Purpose |
|---|---|
| `ab_s3_attachment` | Redirects `ir.attachment` storage to AWS S3 (with safe boto3-missing fallback). |
| `ab_redis_session` | Stores Odoo session + bus notifications in Redis for multi-node HA. |

## Adding a module here

A module belongs in `saas-share` when **all** of the following are true:

1. It is installed on both DBCLOUD and tenant entities (or could be).
2. It has no dependency on a business-domain repo (`saas-hr`, `saas-pos`, `saas-accounting`, `saas-branches`, `saas-approval`, `saas-theme`).
3. It is a tool / backend / integration adapter, not a feature.

Anything else stays in its existing repo.

## Activation

Add the path to `addons_path` in `clouderps-odoo.conf` and `/opt/ghaima.conf` (in tenant containers):

```
addons_path = ...,/home/clouderps/custom-addons/saas-share,...
```
