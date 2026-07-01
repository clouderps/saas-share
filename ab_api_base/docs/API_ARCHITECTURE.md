# Ghaima APIs — Architecture & Flow

How the unified API works across the **client (tenant)** and **central (DBCLOUD)**
servers: one token system, one decorator seam (`ab_api_base`), auto-generated
Swagger on each server.

- Rendering: Mermaid (GitHub / VS Code Mermaid preview render these directly).
- Scope: the REST/JSON API layer — auth, endpoints, docs, and the payment bridge.
- Token: HS256 JWT signed with the shared `ir.config_parameter` key
  `mobile_api.jwt_secret`; claims `uid, device_id, branch_id, type='access', scope`.

---

## 1. System map — who talks to what

```mermaid
flowchart TB
    subgraph Clients
        MOB["📱 Ghaima mobile app<br/>(Flutter)"]
        POS["🖥️ POS / kitchen devices"]
        WEB["🌐 Website visitor"]
    end

    subgraph TENANT["CLIENT / TENANT server (e.g. FAYIAPROD :8015)"]
        direction TB
        TDOCS["/api/v1/docs · /openapi.json<br/>Swagger (ab_api_base)"]
        TAUTH["/api/v1/auth/* — login · pin-token · refresh"]
        TAPI["/api/v1/pos/* · /sync/* · /dashboard/* · /ai/* · /pos/geidea/*"]
        TVAL{{"@jwt_required → ab_api_base<br/>POS scope validator<br/>(device active + branch)"}}
        TGW["gateway.geidea<br/>(tenant payment API)"]
    end

    subgraph CENTRAL["CENTRAL / DBCLOUD server (CLOUDLOCAL :8016)"]
        direction TB
        CDOCS["/api/v1/docs · /openapi.json<br/>Swagger (ab_api_base)"]
        CAUTH["/api/v1/saas/auth/* — login · client-number · refresh"]
        CAPI["/api/v1/saas/me/* — billing · cards · credit · checkout"]
        CVAL{{"billing scope validator<br/>(partner match + scope)"}}
        MID["ab_saas_payment_middleware<br/>vault + PayFac + webhooks"]
    end

    GEIDEA["💳 Geidea HPP"]

    MOB & POS -->|"Bearer JWT"| TAUTH
    MOB & POS -->|"Bearer JWT"| TAPI
    WEB -->|"public, rate-limited"| TAPI
    TAPI --> TVAL
    TAUTH -->|"mint token"| TVAL

    MOB -->|"Bearer JWT (billing scope)"| CAUTH
    MOB -->|"Bearer JWT (billing scope)"| CAPI
    CAPI --> CVAL

    TGW -->|"tenant↔central JWT (service)"| MID
    MID -->|"create link"| GEIDEA
    GEIDEA -->|"HMAC webhook"| MID
    MID -->|"event fan-out (JWT)"| TGW

    TDOCS -. "documents THIS server's routes" .- TAPI
    CDOCS -. "documents THIS server's routes" .- CAPI
```

**Key idea:** `ab_api_base` installs on *both* servers. Its Swagger builds the
spec from **that server's own routing map**, so the tenant docs show tenant APIs
(115 paths) and the central docs show central APIs (52 paths) — one module, no
per-server config.

---

## 2. Getting a token & calling an endpoint (the auth loop)

```mermaid
sequenceDiagram
    autonumber
    participant App as Mobile app / Swagger
    participant Auth as /api/v1/auth/login (public)
    participant Base as ab_api_base (unified auth)
    participant Val as POS scope validator
    participant API as /api/v1/pos/... (protected)

    App->>Auth: POST {login, password, device_uid}
    Auth->>Auth: authenticate user + register mobile.device
    Auth-->>App: { access_token (JWT), refresh_token, expires_in }
    Note over App: paste access_token into Swagger "Authorize"

    App->>API: POST {..} + Authorization: Bearer <JWT>
    API->>Base: @jwt_required
    Base->>Base: decode JWT (mobile_api.jwt_secret) + type=access + user active
    Base->>Val: scope='pos' → validate
    Val->>Val: device exists + active? stamp uid/device/branch
    alt valid
        Val-->>API: OK → run handler as the cashier
        API-->>App: 200 { success:true, data }
    else invalid
        Val-->>App: 401 { code: TOKEN_INVALID / DEVICE_INACTIVE }
    end
```

**How scope-gating protects boundaries:** every token is decoded by the same
seam, but the *scope validator* decides acceptance. A POS token (has `device_id`)
is rejected by billing endpoints; a billing token (`scope=saas_billing`, no
device) is rejected by POS endpoints — even though both are signed with the same
secret. So "one token system" never means "one key opens every door".

---

## 3. Three ways to get a token to test

```mermaid
flowchart LR
    A["Backend wizard<br/>POS ▸ API Test Token"] -->|"one click"| T((Bearer token))
    B["Swagger: POST /auth/login<br/>Try it out"] -->|"creds"| T
    C["Swagger: POST /auth/pin-token<br/>Try it out"] -->|"employee PIN"| T
    T --> AUTH["Swagger ▸ Authorize<br/>paste token"] --> TRY["Try any endpoint"]
```

---

## 4. How the docs describe each endpoint

`ab_api_base` builds each endpoint's OpenAPI entry from, in priority order:

1. **`register_doc(path, summary, description, request_example, response_example)`**
   — explicit, hand-written docs (most precise; used for auth + key flows).
2. **Handler docstring** — auto-extracted as summary/description.
3. **Handler source** — body params auto-extracted from `data.get()/body.get()/kwargs.get()`
   so "Try it out" shows the fields to send.

Auth mode per route: `token` (Bearer) unless the path is public
(login / pin-token / refresh / webhooks / simulator), which are shown without
`bearerAuth`.
