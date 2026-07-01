# -*- coding: utf-8 -*-
"""Public API docs: /api/v1/openapi.json (spec) + /api/v1/docs (Swagger UI).

The spec is built from TWO sources, merged:
  1. Explicit @api_route registrations (rich metadata: summaries, examples),
     filtered to modules installed in the current database.
  2. Auto-discovery of every route on this server's live werkzeug routing map
     whose path matches the configured API prefixes (default ``/api/``).

Because the routing map only contains the routes of the modules installed on
THIS instance, a client/tenant shows its tenant APIs and the central server
shows its central APIs — the same module, no per-server config. Explicit
registrations win over auto-discovered ones for the same path.

Gated by the ``ab_api.expose_docs`` system parameter (default enabled).
"""

import re
import json
import logging

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

from .api import ENDPOINT_REGISTRY, DOC_OVERLAY
from ..lib.openapi import build_openapi_spec

_logger = logging.getLogger(__name__)


# Paths that are reachable without a bearer token (login/onboarding, docs,
# provider webhooks, the dev simulator). Everything else is documented as
# requiring bearerAuth so "Authorize" in Swagger applies the token.
_PUBLIC_PATH_MARKERS = (
    '/auth/login', '/auth/pin-token', '/auth/refresh',
    '/openapi.json', '/docs', '/redoc',
    '/verify-pin', '/device-auth', '/device-features',
    '/webhook/', '/sim/pay',
)


def _docs_enabled(env):
    val = env['ir.config_parameter'].sudo().get_param('ab_api.expose_docs', 'True')
    return str(val).lower() in ('true', '1', 'yes')


def _installed_modules(env):
    return set(env['ir.module.module'].sudo().search([
        ('state', '=', 'installed'),
    ]).mapped('name'))


def _doc_prefixes(env):
    raw = env['ir.config_parameter'].sudo().get_param('ab_api.doc_path_prefixes', '/api/')
    return tuple(p.strip() for p in raw.split(',') if p.strip())


def _tags_from_path(path):
    segs = [s for s in path.strip('/').split('/')
            if s and s != 'api' and not re.fullmatch(r'v\d+', s)]
    return [segs[0]] if segs else ['default']


def _discover_api_entries(env, prefixes):
    """Walk this server's live routing map and emit registry-shaped entries
    for every route under the configured API prefixes. Only installed
    modules' routes are on the map, so this is inherently instance-scoped."""
    from odoo.http import root
    out = []
    try:
        router = root.get_db_router(env.cr.dbname)
        rules = list(router.iter_rules())
    except Exception:
        _logger.warning("ab_api_base: could not read routing map for OpenAPI discovery",
                        exc_info=True)
        return out
    for rule in rules:
        path = rule.rule or ''
        if not any(path.startswith(p) for p in prefixes):
            continue
        methods = sorted((rule.methods or {'POST'}) - {'HEAD', 'OPTIONS'})
        if not methods:
            continue
        fn = rule.endpoint
        module = ''
        parts = (getattr(fn, '__module__', '') or '').split('.')
        if len(parts) > 2 and parts[0] == 'odoo':
            module = parts[2]
        is_public = any(marker in path for marker in _PUBLIC_PATH_MARKERS)
        out.append({
            'path': path, 'methods': methods, 'scope': None,
            'auth': 'public' if is_public else 'token',
            'summary': '', 'description': '', 'tags': _tags_from_path(path),
            'deprecated': False, 'module': module,
            'request_example': None, 'response_example': None,
        })
    return out


class ApiDocsController(http.Controller):

    @http.route('/api/v1/openapi.json', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    def openapi_json(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)

        # Auto-discovered from the live routing map (instance-scoped)...
        merged = {e['path']: e for e in _discover_api_entries(env, _doc_prefixes(env))}
        # ...overridden by explicit @api_route entries (richer metadata).
        installed = _installed_modules(env)
        for e in ENDPOINT_REGISTRY:
            if not e['module'] or e['module'] in installed:
                merged[e['path']] = dict(e)  # copy — never mutate the shared registry
        # ...enriched with doc overlays (params via request_example + response_example).
        for path, entry in merged.items():
            ov = DOC_OVERLAY.get(path)
            if not ov:
                continue
            for k in ('summary', 'description', 'request_example', 'response_example'):
                if ov.get(k) is not None:
                    entry[k] = ov[k]
            if ov.get('tags'):
                entry['tags'] = ov['tags']

        icp = env['ir.config_parameter'].sudo()
        spec = build_openapi_spec(
            list(merged.values()),
            title=icp.get_param('ab_api.docs_title', 'Ghaima APIs'),
            version=icp.get_param('ab_api.docs_version', '1.0.0'),
            description=icp.get_param(
                'ab_api.docs_description',
                'Auto-generated from this server\'s installed API modules. '
                'Click Authorize and paste a Bearer token to try endpoints.'),
        )
        return Response(json.dumps(spec, default=str),
                        headers=[('Content-Type', 'application/json'),
                                 ('Access-Control-Allow-Origin', '*')])

    @http.route('/api/v1/docs', type='http', auth='public', csrf=False)
    def swagger_ui(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)
        return Response(_SWAGGER_HTML, headers=[('Content-Type', 'text/html')])


# Swagger UI assets vendored locally under static/lib/swagger-ui/ (Odoo serves
# them at /ab_api_base/static/...), so the docs render fully offline / air-gapped.
# Pinned to swagger-ui-dist@5.17.14.
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Ghaima APIs</title>
  <link rel="stylesheet" href="/ab_api_base/static/lib/swagger-ui/swagger-ui.css"/>
  <style>
    body { margin: 0; background: #fafafa; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="/ab_api_base/static/lib/swagger-ui/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: '/api/v1/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        docExpansion: 'list',
        defaultModelsExpandDepth: 0,
        persistAuthorization: true,
        tryItOutEnabled: true,
      });
    };
  </script>
</body>
</html>"""
