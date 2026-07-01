# -*- coding: utf-8 -*-
"""Public API docs: /api/v1/openapi.json (spec) + /api/v1/docs (Swagger UI).

The spec is filtered to endpoints whose module is installed in the current
database, so a tenant only sees the APIs it actually serves. Gated by the
``ab_api.expose_docs`` system parameter (default enabled).
"""

import json
import logging

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

from .api import ENDPOINT_REGISTRY
from ..lib.openapi import build_openapi_spec

_logger = logging.getLogger(__name__)


def _docs_enabled(env):
    val = env['ir.config_parameter'].sudo().get_param('ab_api.expose_docs', 'True')
    return str(val).lower() in ('true', '1', 'yes')


def _installed_modules(env):
    return set(env['ir.module.module'].sudo().search([
        ('state', '=', 'installed'),
    ]).mapped('name'))


class ApiDocsController(http.Controller):

    @http.route('/api/v1/openapi.json', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    def openapi_json(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)

        installed = _installed_modules(env)
        entries = [e for e in ENDPOINT_REGISTRY
                   if not e['module'] or e['module'] in installed]

        icp = env['ir.config_parameter'].sudo()
        spec = build_openapi_spec(
            entries,
            title=icp.get_param('ab_api.docs_title', 'CloudERPs API'),
            version=icp.get_param('ab_api.docs_version', '1.0.0'),
            description=icp.get_param('ab_api.docs_description', ''),
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


# Swagger UI from a pinned CDN build pointed at our spec.
# ponytail: CDN keeps this a single file; vendor swagger-ui-dist into
# static/ if a tenant must run air-gapped.
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>CloudERPs API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css"/>
  <style>
    body { margin: 0; background: #fafafa; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js" crossorigin></script>
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
