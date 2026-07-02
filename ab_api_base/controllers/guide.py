# -*- coding: utf-8 -*-
"""Human-readable API guide: /api/v1/guide.

Rendered from the same ``collect_endpoints`` data as the OpenAPI spec, so
it is always in sync with the modules installed on THIS server — a tenant
shows its tenant APIs, the central server shows its central APIs. It adds
what Swagger doesn't show well: how the pieces fit together (system +
auth-flow diagrams), which credential opens which door, and copy-paste
curl examples per auth mode.

Developer-facing and deliberately English/LTR, like the Swagger UI it
sits next to. Gated by the same ``ab_api.expose_docs`` parameter.
"""

import html
import json

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

from .docs import collect_endpoints, _docs_enabled

METHOD_ORDER = {'GET': 0, 'POST': 1, 'PUT': 2, 'PATCH': 3, 'DELETE': 4}

AUTH_LABEL = {
    'public':  ('Public', 'No credentials — login, docs, webhooks, simulators.'),
    'token':   ('Bearer JWT', 'User access token from the login endpoint '
                '(POS scope on tenants, billing scope on central).'),
    'service': ('Service JWT', 'Per-tenant machine token (payment middleware '
                'link between a tenant server and central).'),
    'admin':   ('Admin token', 'Ops back-office bearer from '
                'ir.config_parameter — never exposed to tenants.'),
}


def _esc(s):
    return html.escape(str(s or ''), quote=True)


def _pretty(obj):
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)


def _flavor(paths):
    if any(p.startswith('/api/v1/saas/me/') for p in paths):
        return 'central'
    if any(p.startswith('/api/v1/pos/') for p in paths):
        return 'tenant'
    return 'generic'


# --------------------------------------------------------------------------
# Diagrams — minimal inline SVG, Ghaima palette, semantic groups.
# --------------------------------------------------------------------------

_SYSTEM_SVG = """
<svg viewBox="0 0 860 340" role="img" aria-label="System map: mobile apps, tenant server, central server and Geidea"
     xmlns="http://www.w3.org/2000/svg" font-family="inherit" font-size="13">
  <defs>
    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#5f6b7a"/>
    </marker>
  </defs>
  <g id="mobile">
    <rect x="20" y="120" width="150" height="90" rx="10" fill="#eef3ff" stroke="#005FF6" stroke-width="1.5"/>
    <text x="95" y="152" text-anchor="middle" font-weight="600" fill="#0D00A2">Mobile apps</text>
    <text x="95" y="172" text-anchor="middle" fill="#42506a">POS · Kitchen · Owner</text>
    <text x="95" y="190" text-anchor="middle" fill="#42506a">dashboard (Flutter)</text>
  </g>
  <g id="tenant">
    <rect x="300" y="40" width="220" height="120" rx="10" fill="#ffffff" stroke="#005FF6" stroke-width="1.5"/>
    <text x="410" y="68" text-anchor="middle" font-weight="600" fill="#0D00A2">Tenant Odoo (per client)</text>
    <text x="410" y="90" text-anchor="middle" fill="#42506a">/api/v1/auth · /pos · /sync</text>
    <text x="410" y="108" text-anchor="middle" fill="#42506a">/dashboard · /ghaima</text>
    <text x="410" y="132" text-anchor="middle" fill="#5f6b7a" font-size="12">POS-scope JWT per device</text>
  </g>
  <g id="central">
    <rect x="300" y="200" width="220" height="120" rx="10" fill="#ffffff" stroke="#5DD8CA" stroke-width="1.5"/>
    <text x="410" y="228" text-anchor="middle" font-weight="600" fill="#0D00A2">Central SaaS server</text>
    <text x="410" y="250" text-anchor="middle" fill="#42506a">/saas/auth · /saas/me · /device</text>
    <text x="410" y="268" text-anchor="middle" fill="#42506a">/saas/payment · /ai · /instances</text>
    <text x="410" y="292" text-anchor="middle" fill="#5f6b7a" font-size="12">billing JWT · service JWT · admin token</text>
  </g>
  <g id="geidea">
    <rect x="660" y="200" width="170" height="90" rx="10" fill="#fff7ec" stroke="#c77b1e" stroke-width="1.5"/>
    <text x="745" y="235" text-anchor="middle" font-weight="600" fill="#7a4a08">Geidea HPP</text>
    <text x="745" y="256" text-anchor="middle" fill="#7a4a08" font-size="12">payment pages</text>
    <text x="745" y="274" text-anchor="middle" fill="#7a4a08" font-size="12">+ webhooks</text>
  </g>
  <g stroke="#5f6b7a" stroke-width="1.5" fill="none">
    <path d="M170,140 C230,110 240,105 300,95" marker-end="url(#arr)"/>
    <path d="M170,185 C230,215 240,230 300,245" marker-end="url(#arr)"/>
    <path d="M410,160 L410,200" marker-end="url(#arr)" marker-start="url(#arr)"/>
    <path d="M520,235 L660,235" marker-end="url(#arr)"/>
    <path d="M660,265 L520,265" marker-end="url(#arr)"/>
  </g>
  <g fill="#5f6b7a" font-size="12">
    <text x="215" y="100">sell, sync, kitchen</text>
    <text x="200" y="238">activate, billing, AI</text>
    <text x="418" y="185">payment links / webhooks (service JWT)</text>
    <text x="545" y="228">create session</text>
    <text x="555" y="282">webhook (HMAC)</text>
  </g>
</svg>
"""

_AUTH_SVG = """
<svg viewBox="0 0 860 240" role="img" aria-label="Auth flow: login returns a JWT, the JWT authorizes API calls, refresh renews it"
     xmlns="http://www.w3.org/2000/svg" font-family="inherit" font-size="13">
  <defs>
    <marker id="arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#005FF6"/>
    </marker>
  </defs>
  <g>
    <rect x="20" y="30" width="130" height="52" rx="9" fill="#eef3ff" stroke="#005FF6" stroke-width="1.5"/>
    <text x="85" y="61" text-anchor="middle" font-weight="600" fill="#0D00A2">App</text>
    <rect x="330" y="20" width="240" height="72" rx="9" fill="#ffffff" stroke="#005FF6" stroke-width="1.5"/>
    <text x="450" y="48" text-anchor="middle" font-weight="600" fill="#0D00A2">1 · POST /api/v1/auth/login</text>
    <text x="450" y="70" text-anchor="middle" fill="#42506a">login + password + device_uid</text>
    <rect x="680" y="20" width="160" height="72" rx="9" fill="#f0fbf9" stroke="#5DD8CA" stroke-width="1.5"/>
    <text x="760" y="48" text-anchor="middle" font-weight="600" fill="#0D00A2">access_token</text>
    <text x="760" y="70" text-anchor="middle" fill="#42506a">+ refresh_token</text>
    <rect x="330" y="140" width="240" height="72" rx="9" fill="#ffffff" stroke="#005FF6" stroke-width="1.5"/>
    <text x="450" y="168" text-anchor="middle" font-weight="600" fill="#0D00A2">2 · Any protected endpoint</text>
    <text x="450" y="190" text-anchor="middle" fill="#42506a">Authorization: Bearer &lt;token&gt;</text>
    <rect x="680" y="140" width="160" height="72" rx="9" fill="#ffffff" stroke="#005FF6" stroke-dasharray="4 3" stroke-width="1.5"/>
    <text x="760" y="168" text-anchor="middle" font-weight="600" fill="#0D00A2">3 · /auth/refresh</text>
    <text x="760" y="190" text-anchor="middle" fill="#42506a">when it expires</text>
  </g>
  <g stroke="#005FF6" stroke-width="1.5" fill="none">
    <path d="M150,56 L330,56" marker-end="url(#arr2)"/>
    <path d="M570,56 L680,56" marker-end="url(#arr2)"/>
    <path d="M85,82 C85,176 210,176 330,176" marker-end="url(#arr2)"/>
    <path d="M760,92 L760,140" marker-end="url(#arr2)"/>
  </g>
</svg>
"""

_PAYMENT_SVG = """
<svg viewBox="0 0 860 260" role="img" aria-label="Payment link flow across tenant, central and Geidea"
     xmlns="http://www.w3.org/2000/svg" font-family="inherit" font-size="13">
  <defs>
    <marker id="arr3" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#5f6b7a"/>
    </marker>
  </defs>
  <g font-weight="600" fill="#0D00A2" text-anchor="middle">
    <text x="120" y="32">POS / Mobile</text>
    <text x="400" y="32">Tenant gateway</text>
    <text x="660" y="32">Central middleware</text>
  </g>
  <g stroke="#c9d2e0" stroke-width="1"><path d="M120,42 V240"/><path d="M400,42 V240"/><path d="M660,42 V240"/></g>
  <g stroke="#5f6b7a" stroke-width="1.5" fill="none">
    <path d="M120,70 L400,70" marker-end="url(#arr3)"/>
    <path d="M400,105 L660,105" marker-end="url(#arr3)"/>
    <path d="M660,140 L400,140" marker-end="url(#arr3)"/>
    <path d="M660,205 L400,205" marker-end="url(#arr3)"/>
    <path d="M400,232 L120,232" marker-end="url(#arr3)"/>
  </g>
  <g fill="#42506a" font-size="12">
    <text x="140" y="62">/pos/gahima_pay/create_link (POS JWT)</text>
    <text x="420" y="97">/saas/payment/link/create (service JWT)</text>
    <text x="420" y="132">checkout_url → customer pays on Geidea page</text>
    <text x="420" y="177" fill="#7a4a08">Geidea webhook → central (HMAC verified)</text>
    <text x="420" y="197">/saas/gateway/geidea/event (fan-out)</text>
    <text x="140" y="224">bus event → order marked paid</text>
  </g>
</svg>
"""


_CURL = {
    'tenant': """# 1 · login (creates/binds the device, returns the POS-scope JWT)
curl -X POST {base}/api/v1/auth/login \\
  -H 'Content-Type: application/json' \\
  -d '{{"login": "cashier@example.com", "password": "…", "device_uid": "tablet-01"}}'

# 2 · call any endpoint with the token
curl -X POST {base}/api/v1/pos/session/open \\
  -H 'Authorization: Bearer <access_token>' \\
  -H 'Content-Type: application/json' \\
  -d '{{"config_id": 2, "opening_balance": 0}}'""",
    'central': """# 1 · login as the customer (partner-scoped billing JWT)
curl -X POST {base}/api/v1/saas/auth/login \\
  -H 'Content-Type: application/json' \\
  -d '{{"login": "owner@example.com", "password": "…", "device_uid": "phone-01"}}'

# 2 · self-service endpoints
curl {base}/api/v1/saas/me/tenants -H 'Authorization: Bearer <access_token>'

# service JWT (tenant server ↔ payment middleware)
curl {base}/api/v1/saas/payment/health -H 'Authorization: Bearer <tenant_service_jwt>'

# AI gateway (per-entity token in its own header)
curl -X POST {base}/api/v1/ai/status \\
  -H 'X-Entity-Token: <entity_token>' -H 'Content-Type: application/json' \\
  -d '{{"jsonrpc": "2.0", "method": "call", "params": {{}}}}'""",
    'generic': """curl -X POST {base}/api/v1/auth/login \\
  -H 'Content-Type: application/json' \\
  -d '{{"login": "user@example.com", "password": "…", "device_uid": "dev-01"}}'""",
}


def _endpoint_card(e):
    methods = sorted(e.get('methods') or ['POST'],
                     key=lambda m: METHOD_ORDER.get(m, 9))
    chips = ''.join('<span class="m m-%s">%s</span>' % (m.lower(), m)
                    for m in methods)
    auth = e.get('auth') or 'token'
    scope = e.get('scope')
    auth_txt = AUTH_LABEL.get(auth, (auth, ''))[0]
    if scope:
        auth_txt += ' · scope %s' % scope
    summary = e.get('summary') or ''
    desc = e.get('description') or ''
    if desc == summary:
        desc = ''
    body = []
    req = e.get('request_example')
    if isinstance(req, dict) and req:
        rows = ''.join(
            '<tr><td><code>%s</code></td><td>%s</td></tr>'
            % (_esc(k), _esc(v) if v not in ('', None) else
               '<span class="dim">—</span>')
            for k, v in req.items())
        body.append('<h4>Request fields</h4>'
                    '<table class="fields"><thead><tr><th>Field</th>'
                    '<th>Example</th></tr></thead><tbody>%s</tbody></table>'
                    % rows)
    elif req:
        body.append('<h4>Request example</h4><pre>%s</pre>' % _esc(_pretty(req)))
    resp = e.get('response_example')
    if resp:
        body.append('<h4>Response example</h4><pre>%s</pre>' % _esc(_pretty(resp)))
    if not resp:
        body.append('<p class="dim">Response: standard envelope '
                    '<code>{"success": true, "data": …}</code> (or '
                    '<code>{"ok": true, …}</code> for payment middleware) — '
                    'errors carry <code>error</code> + <code>code</code> and '
                    'a matching 4xx/5xx status.</p>')
    dep = ' <span class="dep">deprecated</span>' if e.get('deprecated') else ''
    return (
        '<details class="ep"><summary>%s<code class="path">%s</code>'
        '<span class="auth">%s</span>%s<span class="sum">%s</span></summary>'
        '<div class="ep-body">%s%s<p class="dim">Module: <code>%s</code></p>'
        '</div></details>'
        % (chips, _esc(e['path']), _esc(auth_txt), dep, _esc(summary),
           ('<p>%s</p>' % _esc(desc).replace('\n', '<br/>')) if desc else '',
           ''.join(body), _esc(e.get('module') or '—')))


class ApiGuideController(http.Controller):

    @http.route('/api/v1/guide', type='http', auth='public', csrf=False)
    def api_guide(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)
        base = request.httprequest.host_url.rstrip('/')
        return Response(build_guide_html(env, base_url=base),
                        headers=[('Content-Type', 'text/html; charset=utf-8')])


_PAGE_TMPL = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title} — Developer Guide</title>
<style>
  :root {{
    --blue: #005FF6; --navy: #0D00A2; --cyan: #5DD8CA; --bg: #F7F8FC;
    --ink: #1c2434; --dim: #5f6b7a; --line: #e3e8f2; --card: #ffffff;
    --radius: 12px; --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  header {{ background: var(--navy); color: #fff; padding: 2.2rem 1.5rem 2rem; }}
  header .wrap, main {{ max-width: 980px; margin-inline: auto; }}
  header h1 {{ margin: 0 0 .35rem; font-size: 1.6rem; letter-spacing: -.01em; }}
  header p {{ margin: 0; color: #c9d4ff; max-width: 46rem; }}
  header nav {{ margin-top: 1rem; display: flex; gap: .6rem; flex-wrap: wrap; }}
  header nav a {{ color: #fff; text-decoration: none; border: 1px solid #4a55c8;
                  border-radius: 999px; padding: .28rem .9rem; font-size: .85rem; }}
  header nav a:hover {{ background: var(--blue); border-color: var(--blue); }}
  main {{ padding: 1.5rem; }}
  h2 {{ font-size: 1.2rem; margin: 2.2rem 0 .8rem; letter-spacing: -.01em; }}
  h3 {{ font-size: 1.05rem; margin: 1.8rem 0 .6rem; }}
  .card {{ background: var(--card); border: 1px solid var(--line);
           border-radius: var(--radius); padding: 1.1rem 1.25rem; }}
  .card + .card {{ margin-top: .8rem; }}
  figure {{ margin: 0; padding: .5rem 0; overflow-x: auto; }}
  figure svg {{ min-width: 640px; width: 100%; height: auto; }}
  figcaption {{ color: var(--dim); font-size: .85rem; padding-top: .3rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
  td, th {{ border-top: 1px solid var(--line); padding: .5rem .6rem;
            text-align: start; vertical-align: top; }}
  thead th {{ border-top: 0; color: var(--dim); font-weight: 600;
              font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }}
  pre {{ background: #0e1524; color: #dce7ff; border-radius: 10px;
         padding: .9rem 1rem; overflow-x: auto; font: .84rem/1.55 var(--mono); }}
  code {{ font-family: var(--mono); font-size: .88em; }}
  .toc {{ display: flex; flex-wrap: wrap; gap: .45rem; margin: .8rem 0 0; }}
  .toc a {{ text-decoration: none; color: var(--navy); background: #fff;
            border: 1px solid var(--line); border-radius: 999px;
            padding: .22rem .75rem; font-size: .85rem; }}
  .toc a span {{ color: var(--dim); }}
  .toc a:hover {{ border-color: var(--blue); color: var(--blue); }}
  section {{ scroll-margin-top: 1rem; }}
  .count {{ color: var(--dim); font-weight: 400; font-size: .85rem; }}
  details.ep {{ background: var(--card); border: 1px solid var(--line);
                border-radius: 10px; margin: .45rem 0; overflow: hidden; }}
  details.ep > summary {{ list-style: none; cursor: pointer; display: flex;
      align-items: center; gap: .55rem; padding: .55rem .8rem; flex-wrap: wrap; }}
  details.ep > summary::-webkit-details-marker {{ display: none; }}
  details.ep[open] > summary {{ border-bottom: 1px solid var(--line); }}
  .ep-body {{ padding: .8rem 1rem 1rem; }}
  .ep-body h4 {{ margin: .8rem 0 .35rem; font-size: .82rem; color: var(--dim);
                 text-transform: uppercase; letter-spacing: .04em; }}
  .m {{ font: 700 .72rem/1 var(--mono); border-radius: 6px; padding: .3rem .45rem;
        color: #fff; min-width: 3.2em; text-align: center; }}
  .m-get {{ background: #0b7a53; }} .m-post {{ background: var(--blue); }}
  .m-put {{ background: #9a6700; }} .m-patch {{ background: #9a6700; }}
  .m-delete {{ background: #b3261e; }}
  code.path {{ font-size: .88rem; word-break: break-all; }}
  .auth {{ font-size: .72rem; color: var(--navy); background: #eef3ff;
           border-radius: 999px; padding: .18rem .6rem; white-space: nowrap; }}
  .dep {{ font-size: .72rem; color: #b3261e; background: #fdecea;
          border-radius: 999px; padding: .18rem .6rem; }}
  .sum {{ color: var(--dim); font-size: .85rem; flex-basis: 100%; }}
  .dim {{ color: var(--dim); }}
  table.fields {{ margin-top: .2rem; }}
  footer {{ color: var(--dim); font-size: .82rem; text-align: center;
            padding: 2.5rem 1rem 2rem; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #10141f; --ink: #e5eaf5; --dim: #98a4b8; --line: #29324a;
             --card: #171d2d; }}
    header {{ background: #0a0836; }}
    .toc a {{ background: var(--card); color: #aab8ff; }}
    .auth {{ background: #1b2340; color: #aab8ff; }}
    .m-get {{ background: #0e8f62; }}
  }}
</style>
</head>
<body>
<header><div class="wrap">
  <h1>{title} — Developer Guide</h1>
  <p>{flavor_line} All {count} endpoints below are generated from this
     server's live routing table, so what you read here is exactly what is
     deployed.</p>
  <nav>
    <a href="/api/v1/docs">Swagger UI (try it out)</a>
    <a href="/api/v1/openapi.json">OpenAPI spec (JSON)</a>
    <a href="#auth">Authentication</a>
    <a href="#endpoints">Endpoint reference</a>
  </nav>
</div></header>
<main>
  <h2>How the pieces fit together</h2>
  <div class="card"><figure>{system_svg}
    <figcaption>Every client company gets its own tenant Odoo. Mobile apps
    talk to their tenant for selling and to central for activation, billing
    and AI. Payments flow tenant → central → Geidea and come back as
    webhooks.</figcaption></figure></div>

  <h2 id="auth">Authentication</h2>
  <div class="card"><figure>{auth_svg}
    <figcaption>Login once per device, send the access token as
    <code>Authorization: Bearer …</code> on every call, renew with the
    refresh token. Access tokens expire after ~1 hour, refresh tokens after
    ~30 days.</figcaption></figure></div>
  <div class="card">
    <table><thead><tr><th>Credential</th><th>What it opens</th></tr></thead>
    <tbody>{auth_rows}
    <tr><td><strong>X-Entity-Token</strong></td><td>AI gateway endpoints
      (<code>/api/v1/ai/*</code>) — per-entity token issued by the platform.</td></tr>
    <tr><td><strong>X-Saas-Service-Token</strong></td><td>Internal KPI push
      (<code>/api/v1/saas/internal/*</code>) — per-tenant pre-shared token.</td></tr>
    </tbody></table>
  </div>
  <div class="card"><h3 style="margin-top:.2rem">Quick start</h3>
    <pre>{curl}</pre></div>

  {payment_svg_section}

  <h2 id="endpoints">Endpoint reference</h2>
  <p class="dim">Grouped by area. Click an endpoint for its request fields
     and response shape. <code>POST</code> bodies are JSON; endpoints marked
     <em>Public</em> need no token.</p>
  <nav class="toc">{toc}</nav>
  {sections}
</main>
<footer>Generated live from the installed API modules · also available as
  <a href="/api/v1/docs">Swagger UI</a> and
  <a href="/api/v1/openapi.json">OpenAPI JSON</a> ·
  disable with system parameter <code>ab_api.expose_docs</code></footer>
</body>
</html>"""

# The payment diagram only makes sense where payment routes exist; injected
# as a full section (heading + card) or empty string.
_PAYMENT_SECTION = """
  <h2>Payment link flow</h2>
  <div class="card"><figure>%s
    <figcaption>The tenant never talks to Geidea directly — central holds
    the credentials, creates the checkout session and fans the webhook back
    out to the tenant, which raises a bus event the POS listens to.</figcaption>
  </figure></div>
"""


def _render_payment(svg):
    return _PAYMENT_SECTION % svg if svg else ''


def build_guide_html(env, base_url=''):
    entries = collect_endpoints(env)
    entries = [e for e in entries
               if e['path'] not in ('/api/v1/openapi.json', '/api/v1/docs',
                                    '/api/v1/guide')]
    entries.sort(key=lambda e: e['path'])
    flavor = _flavor([e['path'] for e in entries])
    icp = env['ir.config_parameter'].sudo()
    title = icp.get_param('ab_api.docs_title', 'Ghaima APIs')

    groups = {}
    for e in entries:
        tag = (e.get('tags') or ['other'])[0]
        groups.setdefault(tag, []).append(e)

    toc = ''.join('<a href="#g-%s">%s <span>%d</span></a>'
                  % (_esc(t), _esc(t), len(g))
                  for t, g in sorted(groups.items()))
    sections = ''.join(
        '<section id="g-%s"><h3>%s <span class="count">%d endpoints</span></h3>%s</section>'
        % (_esc(t), _esc(t.replace('-', ' ').title()), len(g),
           ''.join(_endpoint_card(e) for e in g))
        for t, g in sorted(groups.items()))

    auth_rows = ''.join(
        '<tr><td><strong>%s</strong></td><td>%s</td></tr>' % (label, desc)
        for label, desc in AUTH_LABEL.values())

    flavor_line = {
        'tenant': 'This is a <strong>tenant server</strong> — the per-client '
                  'Odoo that runs the POS, sync and dashboard APIs used by '
                  'the mobile apps.',
        'central': 'This is the <strong>central SaaS server</strong> — '
                   'customer billing self-service, device management, the '
                   'payment middleware and the AI gateway.',
        'generic': 'Endpoints exposed by the API modules installed on this '
                   'server.',
    }[flavor]

    curl = _CURL[flavor].format(base=base_url or 'https://<server>')

    has_payment = any(e['path'].startswith(('/api/v1/saas/payment',
                                            '/api/v1/pos/gahima_pay'))
                      for e in entries)
    payment_section = _render_payment(_PAYMENT_SVG) if has_payment else ''

    return _PAGE_TMPL.replace('{payment_svg_section}', payment_section).format(
        title=_esc(title), flavor_line=flavor_line, count=len(entries),
        system_svg=_SYSTEM_SVG, auth_svg=_AUTH_SVG,
        auth_rows=auth_rows, curl=_esc(curl), toc=toc, sections=sections)
