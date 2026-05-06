"""Shared mobile-API helpers.

Used by both the tenant-side ab_mobile_pos_api and the DBCLOUD-side
ab_mobile_saas_billing_api. Strictly import-only — keep stateless and
free of any tenant- or billing-specific model dependency.

Each consumer module keeps its own jwt_required decorator (tenant API
validates mobile.device + branch_id; billing API validates partner_id
+ scope) since the auth surfaces differ.
"""

import json
import secrets

from odoo.http import Response, request


DEFAULT_ACCESS_TTL = 3600        # 1 hour
DEFAULT_REFRESH_TTL = 2592000    # 30 days


# CORS: Allow-Origin '*' is intentional — mobile (Flutter) clients do
# not send Origin, and browsers enforce CORS while mobile HTTP clients
# don't. Credentials disabled to prevent any browser-based credential
# leakage if a route is reused from a web context by accident.
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Allow-Credentials': 'false',
    'Access-Control-Max-Age': '86400',
}


def get_jwt_secret():
    """Read or mint the shared mobile_api.jwt_secret system parameter.

    Both the tenant POS API and the DBCLOUD billing API sign tokens
    with the same secret so a future shared validation gateway needs
    no extra config.
    """
    icp = request.env['ir.config_parameter'].sudo()
    secret = icp.get_param('mobile_api.jwt_secret', False)
    if not secret:
        secret = secrets.token_hex(64)
        icp.set_param('mobile_api.jwt_secret', secret)
    return secret


def get_ttl(key, default):
    icp = request.env['ir.config_parameter'].sudo()
    try:
        return int(icp.get_param(key, str(default)))
    except (TypeError, ValueError):
        return default


def get_access_ttl():
    return get_ttl('mobile_api.access_token_ttl', DEFAULT_ACCESS_TTL)


def get_refresh_ttl():
    return get_ttl('mobile_api.refresh_token_ttl', DEFAULT_REFRESH_TTL)


def api_response(data=None, error=None, code=None, status=200, request_id=None):
    """Standardized JSON API response with CORS headers.

    Shape: ``{success, [data], [error], [code], [request_id]}``.
    Pass ``request_id`` to echo back a correlation id; the X-Request-ID
    header is set on the response too.
    """
    body = {'success': error is None}
    if data is not None:
        body['data'] = data
    if error is not None:
        body['error'] = error
    if code is not None:
        body['code'] = code
    if request_id:
        body['request_id'] = request_id
    headers = [('Content-Type', 'application/json')]
    headers.extend(CORS_HEADERS.items())
    if request_id:
        headers.append(('X-Request-ID', request_id))
    return Response(json.dumps(body, default=str), status=status, headers=headers)


def cors_preflight():
    """Empty 200 for OPTIONS preflight."""
    headers = list(CORS_HEADERS.items())
    headers.append(('Content-Type', 'text/plain'))
    return Response('', status=200, headers=headers)


def get_request_data():
    """Extract JSON body, supporting both raw JSON and jsonrpc {params}."""
    try:
        data = json.loads(request.httprequest.data or b'{}')
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(data, dict) and 'params' in data:
        params = data['params']
        return params if isinstance(params, dict) else {}
    return data if isinstance(data, dict) else {}
