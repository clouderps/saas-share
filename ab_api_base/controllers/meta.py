# -*- coding: utf-8 -*-
"""Public meta endpoints — health & version.

Installed on every server that carries ab_api_base (tenant + central), so a
mobile client can, before authenticating, confirm the API is reachable, learn
which environment answered (sandbox/production), and read the API version to
gate features / show a build banner. Both are `auth='public'` and appear in
the generated Swagger under the `system` tag.
"""

import time

from odoo import http, release
from odoo.http import request

from .api import api_route, api_response, current_environment


class ApiMetaController(http.Controller):

    @api_route('/api/v1/health', methods=['GET'], auth='public', tags=['system'],
               summary='Health / readiness probe',
               description='Returns 200 + {status:"ok"} when the API worker and '
                           'its database are reachable; 503 + status:"degraded" '
                           'if the database cursor is unusable. No auth.',
               response_example={'success': True,
                                 'data': {'status': 'ok', 'database': True,
                                          'environment': 'production'}})
    def health(self, **kwargs):
        db_ok = True
        try:
            request.env.cr.execute('SELECT 1')
            request.env.cr.fetchone()
        except Exception:
            db_ok = False
        return api_response(
            data={'status': 'ok' if db_ok else 'degraded',
                  'database': db_ok,
                  'environment': current_environment()},
            status=200 if db_ok else 503,
            message='ok' if db_ok else 'database unavailable')

    @api_route('/api/v1/version', methods=['GET'], auth='public', tags=['system'],
               summary='API & platform version',
               description='API version, Odoo platform version, environment and '
                           'server time (UTC ISO-8601). Call on app boot. No auth.',
               response_example={'success': True,
                                 'data': {'api_version': '1.0.0',
                                          'odoo_version': '18.0',
                                          'environment': 'production'}})
    def version(self, **kwargs):
        icp = request.env['ir.config_parameter'].sudo()
        return api_response(data={
            'api_version': icp.get_param('ab_api.docs_version', '1.0.0'),
            'odoo_version': release.version,
            'environment': current_environment(),
            'server_time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })
