# -*- coding: utf-8 -*-
"""Human-readable API reference: /api/v1/guide.

Rendered from the same ``collect_endpoints`` data as the OpenAPI spec, so
it is always in sync with the modules installed on THIS server — a tenant
shows its tenant APIs, the central server shows its central APIs.

Layout follows the developer-portal standard the team referenced
(docs.geidea.net / ReadMe-style, see docs/apis at the workspace root):
a sticky sidebar with search + grouped endpoint navigation, a content
column with per-endpoint documentation, and a code column with generated
cURL and response samples — all in the Ghaima brand palette.

Developer-facing and deliberately English/LTR, like the Swagger UI it
sits next to. Gated by the same ``ab_api.expose_docs`` parameter.
"""

import html
import json

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

from .docs import collect_endpoints, _docs_enabled

METHOD_ORDER = {'GET': 0, 'POST': 1, 'PUT': 2, 'PATCH': 3, 'DELETE': 4}
_BODY_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

AUTH_LABEL = {
    'public':  ('Public', 'No credentials — login, onboarding, webhooks, '
                'the dev payment simulator and these docs.'),
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


_CURL_QUICKSTART = {
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


# --------------------------------------------------------------------------
# Per-endpoint sample generation
# --------------------------------------------------------------------------

def _auth_header_for(e):
    path = e['path']
    if path.startswith('/api/v1/ai/'):
        return "-H 'X-Entity-Token: <entity_token>'"
    if path.startswith('/api/v1/saas/internal/'):
        return "-H 'X-Saas-Service-Token: <service_token>'"
    auth = e.get('auth') or 'token'
    if auth == 'public':
        return ''
    placeholder = {'token': '<access_token>', 'service': '<service_jwt>',
                   'admin': '<admin_token>'}.get(auth, '<token>')
    return "-H 'Authorization: Bearer %s'" % placeholder


def _sample_body(e):
    """Best-effort JSON body from the extracted request fields."""
    ex = e.get('request_example')
    if not isinstance(ex, dict) or not ex:
        return {}
    return {k: (v if v not in ('', None) else '…') for k, v in ex.items()}


def _curl_for(e, base):
    methods = sorted(e.get('methods') or ['POST'],
                     key=lambda m: METHOD_ORDER.get(m, 9))
    m = 'POST' if 'POST' in methods else methods[0]
    url = base + e['path'].replace('<', '{').replace('>', '}')
    lines = ['curl -X %s %s' % (m, url)] if m != 'GET' else ['curl %s' % url]
    auth_h = _auth_header_for(e)
    if auth_h:
        lines.append('  ' + auth_h)
    if m in _BODY_METHODS:
        body = _sample_body(e)
        if e.get('route_type') == 'json':
            body = {'jsonrpc': '2.0', 'method': 'call', 'params': body}
        lines.append("  -H 'Content-Type: application/json'")
        payload = json.dumps(body, indent=2, ensure_ascii=False, default=str)
        lines.append("  -d '%s'" % payload)
    return ' \\\n'.join(lines)


def _response_sample(e):
    resp = e.get('response_example')
    if resp:
        return _pretty(resp)
    if e['path'].startswith('/api/v1/saas/payment'):
        return '{\n  "ok": true,\n  "…": "…"\n}'
    if e.get('route_type') == 'json':
        return ('{\n  "jsonrpc": "2.0",\n  "id": null,\n'
                '  "result": {\n    "success": true,\n    "…": "…"\n  }\n}')
    return '{\n  "success": true,\n  "data": { "…": "…" },\n  "request_id": "…"\n}'


# --------------------------------------------------------------------------
# HTML building blocks
# --------------------------------------------------------------------------

def _anchor(e):
    slug = e['path'].strip('/').replace('/', '-')
    slug = ''.join(c if c.isalnum() or c == '-' else '' for c in slug)
    return 'ep-' + slug


def _title_of(e):
    summary = (e.get('summary') or '').strip().rstrip('.')
    if summary:
        return summary
    # fall back to the last meaningful path segments
    segs = [s for s in e['path'].split('/') if s and not s.startswith('<')]
    return ' / '.join(segs[2:]) or e['path']


def _nav_item(e):
    methods = sorted(e.get('methods') or ['POST'],
                     key=lambda m: METHOD_ORDER.get(m, 9))
    m = methods[0] if len(methods) == 1 else (
        'POST' if 'POST' in methods else methods[0])
    short = e['path'].replace('/api/v1', '') or e['path']
    return ('<a class="nav-ep" href="#%s" data-q="%s">'
            '<span class="m m-%s">%s</span><span class="lbl">%s</span></a>'
            % (_anchor(e), _esc((e['path'] + ' ' + (e.get('summary') or '')).lower()),
               m.lower(), m, _esc(short)))


def _fields_table(e):
    ex = e.get('request_example')
    if isinstance(ex, dict) and ex:
        rows = ''.join(
            '<tr><td><code>%s</code></td><td>%s</td></tr>'
            % (_esc(k), _esc(v) if v not in ('', None)
               else '<span class="dim">—</span>')
            for k, v in ex.items())
        return ('<h4>Body parameters</h4>'
                '<table class="fields"><thead><tr><th>Field</th>'
                '<th>Example</th></tr></thead><tbody>%s</tbody></table>' % rows)
    if ex:
        return '<h4>Request example</h4><pre class="light">%s</pre>' % _esc(_pretty(ex))
    return ''


def _endpoint_article(e, base):
    methods = sorted(e.get('methods') or ['POST'],
                     key=lambda m: METHOD_ORDER.get(m, 9))
    chips = ''.join('<span class="m m-%s">%s</span>' % (m.lower(), m)
                    for m in methods)
    auth = e.get('auth') or 'token'
    auth_txt = AUTH_LABEL.get(auth, (auth, ''))[0]
    if e.get('scope'):
        auth_txt += ' · scope %s' % e['scope']
    desc = (e.get('description') or '').strip()
    summary = (e.get('summary') or '').strip()
    if desc == summary:
        desc = ''
    dep = ('<span class="dep">deprecated</span>'
           if e.get('deprecated') else '')
    envelope_note = ('JSON-RPC envelope — wrap the body in '
                     '<code>{"jsonrpc": "2.0", "method": "call", '
                     '"params": {…}}</code>.'
                     if e.get('route_type') == 'json' else '')
    return '''
<article class="ep" id="%(anchor)s" data-q="%(q)s">
  <div class="ep-doc">
    <h3>%(title)s %(dep)s</h3>
    <div class="urlbar">%(chips)s<code>%(path)s</code></div>
    <p class="meta"><span class="auth">%(auth)s</span>
      <span class="mod">module <code>%(module)s</code></span></p>
    %(desc)s
    %(envelope)s
    %(fields)s
  </div>
  <div class="ep-code">
    <div class="panel"><div class="panel-h"><span>cURL</span>
      <button class="copy" type="button">Copy</button></div>
      <pre>%(curl)s</pre></div>
    <div class="panel"><div class="panel-h"><span>Response</span></div>
      <pre>%(resp)s</pre></div>
  </div>
</article>''' % {
        'anchor': _anchor(e),
        'q': _esc((e['path'] + ' ' + summary).lower()),
        'title': _esc(_title_of(e)),
        'dep': dep,
        'chips': chips,
        'path': _esc(e['path']),
        'auth': _esc(auth_txt),
        'module': _esc(e.get('module') or '—'),
        'desc': ('<p>%s</p>' % _esc(desc).replace('\n', '<br/>')) if desc else '',
        'envelope': ('<p class="note">%s</p>' % envelope_note) if envelope_note else '',
        'fields': _fields_table(e),
        'curl': _esc(_curl_for(e, base)),
        'resp': _esc(_response_sample(e)),
    }


def build_guide_html(env, base_url=''):
    entries = collect_endpoints(env)
    entries = [e for e in entries
               if e['path'] not in ('/api/v1/openapi.json', '/api/v1/docs',
                                    '/api/v1/guide')]
    entries.sort(key=lambda e: e['path'])
    flavor = _flavor([e['path'] for e in entries])
    icp = env['ir.config_parameter'].sudo()
    title = icp.get_param('ab_api.docs_title', 'Gahima APIs')
    base = base_url or 'https://<server>'

    groups = {}
    for e in entries:
        tag = (e.get('tags') or ['other'])[0]
        groups.setdefault(tag, []).append(e)

    nav_groups, sections = [], []
    for tag, grp in sorted(groups.items()):
        gtitle = tag.replace('-', ' ').replace('_', ' ').title()
        nav_groups.append(
            '<div class="group"><div class="g-title">%s</div>%s</div>'
            % (_esc(gtitle), ''.join(_nav_item(e) for e in grp)))
        sections.append(
            '<h2 class="g-head" id="g-%s">%s <span class="count">%d</span></h2>%s'
            % (_esc(tag), _esc(gtitle), len(grp),
               ''.join(_endpoint_article(e, base) for e in grp)))

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

    # Environments: production + sandbox base URLs (config-driven, same defaults
    # as the OpenAPI servers block). Lets a reader point their calls at either.
    prod_url = icp.get_param('ab_api.server_production_url', 'https://www.ghaima.sa')
    sandbox_url = icp.get_param('ab_api.server_sandbox_url', 'https://demo.ghaima.sa')
    flavor_line += (
        '<p style="margin-top:.8rem">'
        '<strong>Environments.</strong> Production <code>%s</code> — live data. '
        'Sandbox <code>%s</code> — safe for testing; reads work, but '
        'state-changing billing/provisioning calls are disabled. Every response '
        'carries <code>meta.environment</code> so you always know which one answered.'
        '</p>' % (_esc(prod_url), _esc(sandbox_url)))

    has_payment = any(e['path'].startswith(('/api/v1/saas/payment',
                                            '/api/v1/pos/gahima_pay'))
                      for e in entries)
    payment_section = ('''
  <section class="prose" id="payment-flow">
    <h2>Payment link flow</h2>
    <figure>%s<figcaption>The tenant never talks to Geidea directly —
      central holds the credentials, creates the checkout session and fans
      the webhook back out to the tenant, which raises a bus event the POS
      listens to.</figcaption></figure>
  </section>''' % _PAYMENT_SVG) if has_payment else ''
    payment_nav = ('<a href="#payment-flow">Payment link flow</a>'
                   if has_payment else '')

    page = (_PAGE_TMPL
            .replace('__TITLE__', _esc(title))
            .replace('__FLAVOR_LINE__', flavor_line)
            .replace('__COUNT__', str(len(entries)))
            .replace('__SYSTEM_SVG__', _SYSTEM_SVG)
            .replace('__AUTH_SVG__', _AUTH_SVG)
            .replace('__AUTH_ROWS__', auth_rows)
            .replace('__QUICKSTART__',
                     _esc(_CURL_QUICKSTART[flavor].format(base=base)))
            .replace('__PAYMENT_SECTION__', payment_section)
            .replace('__PAYMENT_NAV__', payment_nav)
            .replace('__NAV_GROUPS__', ''.join(nav_groups))
            .replace('__SECTIONS__', ''.join(sections)))
    return page


class ApiGuideController(http.Controller):

    @http.route('/api/v1/guide', type='http', auth='public', csrf=False)
    def api_guide(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)
        base = request.httprequest.host_url.rstrip('/')
        return Response(build_guide_html(env, base_url=base),
                        headers=[('Content-Type', 'text/html; charset=utf-8')])


# --------------------------------------------------------------------------
# Page template — token-substituted (no str.format, CSS/JS braces stay raw).
# --------------------------------------------------------------------------

_PAGE_TMPL = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__ — API Reference</title>
<style>
  :root {
    --blue: #005FF6; --navy: #0D00A2; --cyan: #5DD8CA; --bg: #ffffff;
    --bg2: #F7F8FC; --ink: #1c2434; --dim: #5f6b7a; --line: #e3e8f2;
    --code-bg: #0e1524; --code-ink: #dce7ff; --sidebar-w: 300px;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; scroll-padding-top: 70px; }
  body { margin: 0; background: var(--bg); color: var(--ink);
         font: 15px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }

  /* ---------- top bar ---------- */
  .top { position: fixed; inset-inline: 0; top: 0; z-index: 30; height: 56px;
         background: var(--navy); color: #fff; display: flex; align-items: center;
         gap: 1rem; padding-inline: 1.1rem; }
  .brand { display: flex; align-items: center; gap: .6rem; font-weight: 700;
           font-size: 1.02rem; letter-spacing: -.01em; }
  .brand .dot { width: 22px; height: 22px; border-radius: 7px;
                background: linear-gradient(135deg, var(--blue), var(--cyan)); }
  .brand small { font-weight: 400; color: #b9c4ff; }
  .top nav { margin-inline-start: auto; display: flex; gap: .4rem; }
  .top nav a { color: #dfe5ff; text-decoration: none; font-size: .86rem;
               padding: .3rem .8rem; border-radius: 999px; }
  .top nav a.act, .top nav a:hover { background: rgba(255,255,255,.14); color: #fff; }

  /* ---------- shell ---------- */
  .shell { display: flex; padding-top: 56px; }

  /* ---------- sidebar ---------- */
  aside { width: var(--sidebar-w); flex: none; position: sticky; top: 56px;
          height: calc(100vh - 56px); overflow-y: auto; background: var(--bg2);
          border-inline-end: 1px solid var(--line); padding: 1rem .9rem 2rem; }
  .search { position: sticky; top: 0; background: var(--bg2); padding-bottom: .6rem; }
  .search input { width: 100%; border: 1px solid var(--line); border-radius: 8px;
                  background: var(--bg); color: var(--ink);
                  padding: .5rem .75rem; font-size: .9rem; }
  .search input:focus { outline: 2px solid var(--blue); outline-offset: 1px; border-color: var(--blue); }
  .group { margin-top: 1.05rem; }
  .g-title { font-size: .72rem; font-weight: 700; letter-spacing: .08em;
             text-transform: uppercase; color: var(--dim); padding: .2rem .5rem; }
  aside a { display: flex; align-items: center; gap: .5rem; color: var(--ink);
            text-decoration: none; font-size: .86rem; border-radius: 7px;
            padding: .32rem .5rem; }
  aside a:hover { background: #e9eefb; }
  aside a.on { background: #e2eaff; color: var(--navy); font-weight: 600; }
  aside a .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  aside .hid { display: none; }

  /* ---------- method chips ---------- */
  .m { font: 700 .66rem/1 var(--mono); border-radius: 5px; padding: .25rem .4rem;
       color: #fff; min-width: 3.4em; text-align: center; flex: none; }
  .m-get { background: #0b7a53; } .m-post { background: var(--blue); }
  .m-put { background: #9a6700; } .m-patch { background: #9a6700; }
  .m-delete { background: #b3261e; }

  /* ---------- main ---------- */
  main { flex: 1; min-width: 0; padding: 1.6rem 2rem 4rem; max-width: 1160px; }
  .prose { max-width: 860px; }
  h1 { font-size: 1.7rem; margin: .4rem 0 .5rem; letter-spacing: -.015em; }
  h2 { font-size: 1.25rem; margin: 2.4rem 0 .7rem; letter-spacing: -.01em; }
  h2.g-head { border-top: 1px solid var(--line); padding-top: 1.6rem;
              margin-top: 2.6rem; }
  .count { color: var(--dim); font-weight: 400; font-size: .85rem; }
  figure { margin: .8rem 0 0; padding: 1rem; background: var(--bg2);
           border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }
  figure svg { min-width: 640px; width: 100%; height: auto; }
  figcaption { color: var(--dim); font-size: .85rem; padding-top: .5rem; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  td, th { border-top: 1px solid var(--line); padding: .5rem .6rem;
           text-align: start; vertical-align: top; }
  thead th { border-top: 0; color: var(--dim); font-weight: 600; font-size: .78rem;
             text-transform: uppercase; letter-spacing: .05em; }
  pre { background: var(--code-bg); color: var(--code-ink); border-radius: 10px;
        padding: .9rem 1rem; overflow-x: auto; font: .82rem/1.6 var(--mono);
        margin: 0; }
  pre.light { background: var(--bg2); color: var(--ink);
              border: 1px solid var(--line); }
  code { font-family: var(--mono); font-size: .88em; }
  .dim { color: var(--dim); }
  .card { background: var(--bg); border: 1px solid var(--line);
          border-radius: 12px; padding: 1rem 1.2rem; margin-top: .8rem; }

  /* ---------- endpoint article: doc + code columns ---------- */
  article.ep { display: grid; grid-template-columns: minmax(0, 1fr) 400px;
               gap: 1.6rem; padding: 1.7rem 0; border-top: 1px solid var(--line); }
  article.ep:first-of-type { border-top: 0; }
  .ep-doc h3 { margin: 0 0 .6rem; font-size: 1.08rem; letter-spacing: -.01em; }
  .urlbar { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;
            background: var(--bg2); border: 1px solid var(--line);
            border-radius: 9px; padding: .45rem .7rem; }
  .urlbar code { font-size: .86rem; word-break: break-all; }
  .meta { display: flex; gap: .6rem; align-items: center; flex-wrap: wrap;
          margin: .6rem 0 0; }
  .auth { font-size: .72rem; color: var(--navy); background: #eef3ff;
          border-radius: 999px; padding: .2rem .65rem; white-space: nowrap; }
  .mod { color: var(--dim); font-size: .78rem; }
  .dep { font-size: .7rem; color: #b3261e; background: #fdecea;
         border-radius: 999px; padding: .18rem .6rem; vertical-align: middle; }
  .note { color: var(--dim); font-size: .88rem; background: var(--bg2);
          border-inline-start: 3px solid var(--cyan); border-radius: 6px;
          padding: .5rem .8rem; }
  .ep-doc h4 { margin: 1.1rem 0 .35rem; font-size: .78rem; color: var(--dim);
               text-transform: uppercase; letter-spacing: .05em; }
  .ep-code { min-width: 0; position: sticky; top: 70px; align-self: start; }
  .ep-code .panel { position: relative; margin-bottom: .8rem; }
  .panel-h { display: flex; justify-content: space-between; align-items: center;
             background: #1b2436; color: #9fb0d0; font: 600 .72rem/1 var(--mono);
             text-transform: uppercase; letter-spacing: .07em;
             border-radius: 10px 10px 0 0; padding: .5rem .9rem; }
  .panel-h + pre { border-radius: 0 0 10px 10px; }
  .copy { background: none; border: 1px solid #3a4763; color: #9fb0d0;
          border-radius: 6px; font: .7rem var(--mono); padding: .2rem .55rem;
          cursor: pointer; }
  .copy:hover { color: #fff; border-color: #6b7ca3; }

  footer { color: var(--dim); font-size: .82rem; padding: 2rem;
           border-top: 1px solid var(--line); text-align: center; }

  @media (max-width: 1080px) {
    article.ep { grid-template-columns: 1fr; }
    .ep-code { position: static; }
  }
  @media (max-width: 820px) {
    aside { display: none; }
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #10141f; --bg2: #171d2d; --ink: #e5eaf5; --dim: #98a4b8;
            --line: #29324a; --code-bg: #0b1020; }
    .top { background: #0a0836; }
    aside a:hover { background: #1e2740; }
    aside a.on { background: #223055; color: #aab8ff; }
    .auth { background: #1b2340; color: #aab8ff; }
    .m-get { background: #0e8f62; }
  }
</style>
</head>
<body>
<header class="top">
  <div class="brand"><span class="dot"></span>__TITLE__ <small>· API Reference</small></div>
  <nav>
    <a class="act" href="/api/v1/guide">Reference</a>
    <a href="/api/v1/docs">Swagger</a>
    <a href="/api/v1/openapi.json">OpenAPI</a>
  </nav>
</header>
<div class="shell">
<aside>
  <div class="search"><input id="q" type="search"
       placeholder="Search endpoints…" autocomplete="off"/></div>
  <div class="group"><div class="g-title">Getting started</div>
    <a href="#welcome">Welcome</a>
    <a href="#system">How it fits together</a>
    <a href="#auth">Authentication</a>
    <a href="#quickstart">Quick start</a>
    __PAYMENT_NAV__
  </div>
  __NAV_GROUPS__
</aside>
<main>
  <section class="prose" id="welcome">
    <h1>__TITLE__</h1>
    <p>__FLAVOR_LINE__ All <strong>__COUNT__ endpoints</strong> below are
       generated from this server's live routing table, so what you read
       here is exactly what is deployed. Prefer to experiment? Open the
       <a href="/api/v1/docs">Swagger UI</a> and hit endpoints directly.</p>
  </section>

  <section class="prose" id="system">
    <h2>How the pieces fit together</h2>
    <figure>__SYSTEM_SVG__<figcaption>Every client company gets its own
      tenant Odoo. Mobile apps talk to their tenant for selling and to
      central for activation, billing and AI. Payments flow tenant →
      central → Geidea and come back as webhooks.</figcaption></figure>
  </section>

  <section class="prose" id="auth">
    <h2>Authentication</h2>
    <figure>__AUTH_SVG__<figcaption>Login once per device, send the access
      token as <code>Authorization: Bearer …</code> on every call, renew
      with the refresh token. Access tokens expire after ~1 hour, refresh
      tokens after ~30 days.</figcaption></figure>
    <div class="card">
      <table><thead><tr><th>Credential</th><th>What it opens</th></tr></thead>
      <tbody>__AUTH_ROWS__
      <tr><td><strong>X-Entity-Token</strong></td><td>AI gateway endpoints
        (<code>/api/v1/ai/*</code>) — per-entity token issued by the
        platform.</td></tr>
      <tr><td><strong>X-Saas-Service-Token</strong></td><td>Internal KPI push
        (<code>/api/v1/saas/internal/*</code>) — per-tenant pre-shared
        token.</td></tr>
      </tbody></table>
    </div>
  </section>

  <section class="prose" id="quickstart">
    <h2>Quick start</h2>
    <div class="panel"><div class="panel-h"><span>cURL</span>
      <button class="copy" type="button">Copy</button></div>
    <pre>__QUICKSTART__</pre></div>
  </section>
  __PAYMENT_SECTION__

  __SECTIONS__
</main>
</div>
<footer>Generated live from the installed API modules · also available as
  <a href="/api/v1/docs">Swagger UI</a> and
  <a href="/api/v1/openapi.json">OpenAPI JSON</a> ·
  disable with system parameter <code>ab_api.expose_docs</code></footer>
<script>
(function () {
  // sidebar search — filters endpoint links and hides emptied groups
  var q = document.getElementById('q');
  var links = Array.prototype.slice.call(document.querySelectorAll('aside a.nav-ep'));
  var groups = Array.prototype.slice.call(document.querySelectorAll('aside .group'));
  q.addEventListener('input', function () {
    var v = q.value.trim().toLowerCase();
    links.forEach(function (a) {
      a.classList.toggle('hid', v && (a.getAttribute('data-q') || '').indexOf(v) === -1);
    });
    groups.forEach(function (g) {
      var eps = g.querySelectorAll('a.nav-ep');
      if (!eps.length) return; // getting-started group stays
      var any = Array.prototype.some.call(eps, function (a) {
        return !a.classList.contains('hid');
      });
      g.classList.toggle('hid', !any);
    });
  });

  // scrollspy — highlight the nav link of the section in view
  var map = {};
  links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
  var current = null;
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      var a = map[en.target.id];
      if (!a) return;
      if (current) current.classList.remove('on');
      a.classList.add('on');
      current = a;
    });
  }, { rootMargin: '-20% 0px -70% 0px' });
  document.querySelectorAll('article.ep').forEach(function (el) { obs.observe(el); });

  // copy buttons
  document.querySelectorAll('button.copy').forEach(function (b) {
    b.addEventListener('click', function () {
      var pre = b.closest('.panel').querySelector('pre');
      navigator.clipboard.writeText(pre.textContent).then(function () {
        b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1200);
      });
    });
  });
})();
</script>
</body>
</html>"""
