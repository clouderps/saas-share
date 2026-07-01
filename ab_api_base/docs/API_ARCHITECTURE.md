# Ghaima APIs — Architecture & Flow

How the unified API works across the **client (tenant)** and **central (DBCLOUD)**
servers: one token system, one decorator seam (`ab_api_base`), auto-generated
Swagger on each server.

- Rendering: Mermaid (GitHub / VS Code Mermaid preview render these directly).
- Palette (Ghaima tokens): client = blue `#005FF6` / navy `#0D00A2`,
  central = teal `#0E9F8E` / cyan `#5DD8CA`, scope-guard = amber, external = rose,
  docs = slate. Dark text on light tints (WCAG-AA contrast).
- Token: HS256 JWT signed with `ir.config_parameter` key `mobile_api.jwt_secret`;
  claims `uid, device_id, branch_id, type='access', scope`.

**Legend** — 🟦 client · 🟩 central server · 🟨 scope validator · 🟥 external provider · ⬜ Swagger docs

---

## 1. System map — who talks to what

```mermaid
flowchart TB
    subgraph CLIENTS["CLIENTS"]
        MOB["📱 Ghaima mobile app<br/>(Flutter)"]
        POS["🖥️ POS / kitchen devices"]
        WEB["🌐 Website visitor"]
    end

    subgraph TENANT["CLIENT / TENANT server — :8015"]
        direction TB
        TDOCS["Swagger · /api/v1/docs"]
        TAUTH["/api/v1/auth/*<br/>login · pin-token · refresh"]
        TAPI["/api/v1/pos · /sync · /dashboard<br/>/ai · /pos/geidea"]
        TVAL{{"@jwt_required → ab_api_base<br/>POS scope validator<br/>(device + branch)"}}
        TGW["gateway.geidea<br/>(tenant payment API)"]
    end

    subgraph CENTRAL["CENTRAL / DBCLOUD server — :8016"]
        direction TB
        CDOCS["Swagger · /api/v1/docs"]
        CAUTH["/api/v1/saas/auth/*"]
        CAPI["/api/v1/saas/me/*<br/>billing · cards · credit · checkout"]
        CVAL{{"billing scope validator<br/>(partner + scope)"}}
        MID["payment middleware<br/>vault · PayFac · webhooks"]
    end

    GEIDEA["💳 Geidea HPP"]

    MOB -->|"Bearer JWT"| TAUTH
    POS -->|"Bearer JWT"| TAPI
    MOB -->|"Bearer JWT"| TAPI
    WEB -->|"public · rate-limited"| TAPI
    TAPI --> TVAL
    TAUTH -->|"mint token"| TVAL

    MOB -->|"Bearer JWT (billing)"| CAUTH
    MOB -->|"Bearer JWT (billing)"| CAPI
    CAPI --> CVAL

    TGW -->|"tenant↔central JWT"| MID
    MID -->|"create link"| GEIDEA
    GEIDEA -->|"HMAC webhook"| MID
    MID -->|"event fan-out (JWT)"| TGW

    classDef client fill:#E8EEFC,stroke:#0D00A2,stroke-width:1.5px,color:#0D00A2;
    classDef tenant fill:#E6F0FF,stroke:#005FF6,stroke-width:1.5px,color:#0A2540;
    classDef central fill:#DCF6F1,stroke:#0E9F8E,stroke-width:1.5px,color:#06403A;
    classDef valid  fill:#FFF1C2,stroke:#B8860B,stroke-width:1.5px,color:#4A3B00;
    classDef ext    fill:#FCE0EA,stroke:#C2185B,stroke-width:1.5px,color:#4A0E28;
    classDef docs   fill:#E7ECF0,stroke:#4E6472,stroke-width:1.5px,color:#22303A;

    class MOB,POS,WEB client;
    class TAUTH,TAPI,TGW tenant;
    class CAUTH,CAPI,MID central;
    class TVAL,CVAL valid;
    class GEIDEA ext;
    class TDOCS,CDOCS docs;

    style CLIENTS fill:#F7F8FC,stroke:#0D00A2,color:#0D00A2;
    style TENANT  fill:#F4F8FF,stroke:#005FF6,color:#005FF6;
    style CENTRAL fill:#EEFBF8,stroke:#0E9F8E,color:#0B7A6C;
```

**Key idea:** `ab_api_base` installs on *both* servers. Its Swagger builds the
spec from **that server's own routing map**, so the tenant docs show tenant APIs
(115 paths) and the central docs show central APIs (52 paths) — one module, no
per-server config.

---

## 2. Getting a token & calling an endpoint (the auth loop)

```mermaid
%%{init: {'theme':'base','themeVariables':{
  'primaryColor':'#E6F0FF','primaryBorderColor':'#005FF6','primaryTextColor':'#0A2540',
  'actorBkg':'#E6F0FF','actorBorder':'#005FF6','actorTextColor':'#0A2540',
  'signalColor':'#0D00A2','signalTextColor':'#0D00A2','noteBkgColor':'#FFF1C2','noteBorderColor':'#B8860B'
}}}%%
sequenceDiagram
    autonumber
    participant App as Mobile app / Swagger
    participant Auth as /auth/login (public)
    participant Base as ab_api_base
    participant Val as POS scope validator
    participant API as /api/v1/pos/... (protected)

    App->>Auth: POST {login, password, device_uid}
    Auth->>Auth: authenticate user + register device
    Auth-->>App: { access_token, refresh_token, expires_in }
    Note over App: paste access_token into Swagger "Authorize"
    App->>API: POST {..} + Authorization: Bearer <JWT>
    API->>Base: @jwt_required
    Base->>Base: decode JWT + type=access + user active
    Base->>Val: scope='pos' → validate
    Val->>Val: device active? stamp uid/device/branch
    alt valid
        Val-->>API: OK → run handler as the cashier
        API-->>App: 200 { success:true, data }
    else invalid
        Val-->>App: 401 { TOKEN_INVALID / DEVICE_INACTIVE }
    end
```

**Scope-gating:** every token is decoded by the same seam, but the scope
validator decides acceptance. A POS token (has `device_id`) is rejected by
billing endpoints; a billing token (`scope=saas_billing`, no device) is rejected
by POS endpoints — even though both are signed with the same secret. "One token
system" never means "one key opens every door".

---

## 3. Three ways to get a token to test

```mermaid
flowchart LR
    A["Backend wizard<br/>POS ▸ API Test Token"] -->|"one click"| T((Bearer<br/>token))
    B["Swagger: POST /auth/login"] -->|"credentials"| T
    C["Swagger: POST /auth/pin-token"] -->|"employee PIN"| T
    T --> AUTH["Swagger ▸ Authorize<br/>(paste token)"] --> TRY["Try any endpoint"]

    classDef src fill:#E6F0FF,stroke:#005FF6,stroke-width:1.5px,color:#0A2540;
    classDef tok fill:#FFF1C2,stroke:#B8860B,stroke-width:2px,color:#4A3B00;
    classDef act fill:#DCF6F1,stroke:#0E9F8E,stroke-width:1.5px,color:#06403A;
    class A,B,C src;
    class T tok;
    class AUTH,TRY act;
```

---

## 4. How the docs describe each endpoint

`ab_api_base` builds each endpoint's OpenAPI entry from, in priority order:

1. **`register_doc(path, summary, description, request_example, response_example)`**
   — explicit, hand-written docs (most precise).
2. **Handler docstring** — auto-extracted as summary/description.
3. **Handler source** — body params auto-extracted from
   `data.get()/body.get()/kwargs.get()` so "Try it out" shows the fields.

Auth mode per route: `token` (Bearer) unless the path is public
(login / pin-token / refresh / webhooks / simulator), shown without `bearerAuth`.
