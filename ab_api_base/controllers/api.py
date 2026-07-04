# -*- coding: utf-8 -*-
"""Unified API seam.

``@api_route`` replaces ``@http.route`` + a per-module ``@jwt_required``.
It owns CORS, correlation ids, the standard JSON envelope, scope-gated
auth, and OpenAPI registration -- so every ``ab_api_*`` module declares
an endpoint the same way and the docs stay in sync with the code.

Auth modes (``auth=`` on the decorator):
  token   -- user JWT (HS256, shared ``mobile_api.jwt_secret``). The generic
             flow decodes + checks ``type=='access'`` + user active, then
             hands the payload to a domain-registered scope validator
             (device for POS, partner for billing, ...).
  service -- opaque bearer resolved by a registered resolver (payment
             gateway's per-tenant hash lookup -- no JWT decode).
  admin   -- constant-time compare against a config-param token.
  public  -- no auth; optional in-process rate limit.

Domain modules wire their boundary in at import time via
``register_scope_validator`` / ``register_service_resolver`` /
``register_admin_check`` -- keeping this module domain-free.
"""

import time
import uuid
import hmac
import logging
import functools

import jwt

from odoo import http, SUPERUSER_ID
from odoo.http import request

# Re-export the shared primitives so domain modules import everything from
# one place (`from odoo.addons.ab_api_base.controllers.api import ...`).
from odoo.addons.ab_mobile_api_common.controllers.common import (  # noqa: F401
    api_response,
    cors_preflight,
    get_jwt_secret,
    get_request_data,
    CORS_HEADERS,
    current_environment,
    is_sandbox,
    paginate,
)

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Registries -- populated at controller import time, read at spec-build time.
# --------------------------------------------------------------------------

# List of endpoint metadata dicts for OpenAPI generation.
ENDPOINT_REGISTRY = []

# path -> doc-enrichment overlay {summary, description, tags, request_example,
# response_example}. Lets any module attach params/examples to an
# auto-discovered route WITHOUT rewriting its @http.route to @api_route.
DOC_OVERLAY = {}

# scope (str) -> callable(payload: dict, sudo_env) -> Response|None
#   Return an error Response to reject, or None to allow. The validator owns
#   the env switch (`request.update_env(user=uid)`) and any request stamping
#   its handlers rely on (e.g. request._mobile_uid).
_SCOPE_VALIDATORS = {}

# callable() -> bool  (stamps request principal on success, e.g. request._api_tenant)
_SERVICE_RESOLVER = [None]

# config-parameter name holding the expected admin bearer token
_ADMIN_TOKEN_PARAM = [None]


def register_scope_validator(scope, fn):
    """Register the domain check for a token scope (idempotent per scope)."""
    _SCOPE_VALIDATORS[scope] = fn


def register_service_resolver(fn):
    """Register the opaque-bearer resolver for ``auth='service'`` routes."""
    _SERVICE_RESOLVER[0] = fn


def register_admin_check(config_param):
    """Register the ir.config_parameter key holding the admin bearer token."""
    _ADMIN_TOKEN_PARAM[0] = config_param


def register_doc(path, summary=None, description=None, tags=None,
                 request_example=None, response_example=None):
    """Attach OpenAPI doc metadata (params via request_example, and a
    response_example) to an existing route by path — so Swagger shows what to
    send and what comes back, with no change to the route's decorator."""
    DOC_OVERLAY[path] = {
        'summary': summary, 'description': description, 'tags': tags,
        'request_example': request_example, 'response_example': response_example,
    }


# --------------------------------------------------------------------------
# Correlation id
# --------------------------------------------------------------------------

def _set_request_id():
    """Trust a UUID-shaped client X-Request-ID (keeps retries correlated),
    else mint one. Stamped early so even auth failures echo it back."""
    incoming = request.httprequest.headers.get('X-Request-ID', '')
    try:
        request._api_request_id = str(uuid.UUID(incoming)) if incoming else uuid.uuid4().hex
    except (ValueError, AttributeError):
        request._api_request_id = uuid.uuid4().hex
    # Mirror onto the legacy attr some handlers read.
    request._mobile_request_id = request._api_request_id


def current_request_id():
    return getattr(request, '_api_request_id', None)


# --------------------------------------------------------------------------
# Rate limiting -- ponytail: per-worker in-memory; move to Redis if you run
# multiple workers and need a shared limit. Fine for onboarding endpoints.
# --------------------------------------------------------------------------

_RATE_BUCKET = {}


def check_rate_limit(key, max_calls, window_s):
    """True if the call is allowed, False if over the limit for this worker."""
    now = time.time()
    bucket = _RATE_BUCKET.setdefault(key, [])
    cutoff = now - window_s
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= max_calls:
        return False
    bucket.append(now)
    return True


# --------------------------------------------------------------------------
# Auth flows
# --------------------------------------------------------------------------

def _bearer():
    auth = request.httprequest.headers.get('Authorization', '') or ''
    return auth[7:].strip() if auth.startswith('Bearer ') else None


def _auth_token(scope):
    """JWT decode + generic user check + domain scope validator.
    Returns an error Response, or None on success."""
    token = _bearer()
    if not token:
        return api_response(error='Missing or invalid Authorization header',
                            code='AUTH_MISSING', status=401)
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return api_response(error='Token expired', code='TOKEN_EXPIRED', status=401)
    except jwt.InvalidTokenError:
        return api_response(error='Invalid token', code='TOKEN_INVALID', status=401)

    if payload.get('type') != 'access':
        return api_response(error='Invalid token type', code='TOKEN_INVALID', status=401)

    uid = payload.get('uid')
    sudo_env = request.env(user=SUPERUSER_ID)
    user = sudo_env['res.users'].browse(uid)
    if not uid or not user.exists() or not user.active:
        return api_response(error='User not found or inactive',
                            code='USER_INACTIVE', status=401)

    validator = _SCOPE_VALIDATORS.get(scope)
    if validator is not None:
        # Validator owns extra checks + env switch + request stamping.
        err = validator(payload, sudo_env)
        if err is not None:
            return err
        return None

    if scope:
        # A scope was required but no module registered a validator for it.
        return api_response(error='Scope not available', code='SCOPE_UNAVAILABLE', status=403)

    # No scope required -- generic authenticated access.
    request._api_uid = uid
    request.update_env(user=uid)
    return None


def _auth_service():
    resolver = _SERVICE_RESOLVER[0]
    if resolver is None:
        return api_response(error='Service auth unavailable',
                            code='SERVICE_UNAVAILABLE', status=503)
    try:
        ok = resolver()
    except Exception:
        _logger.exception('api: service resolver crashed')
        ok = False
    if not ok:
        return api_response(error='Unauthorized', code='AUTH_FAILED', status=401)
    return None


def _auth_admin():
    param = _ADMIN_TOKEN_PARAM[0]
    if not param:
        return api_response(error='Admin auth unavailable',
                            code='ADMIN_UNAVAILABLE', status=503)
    expected = request.env(user=SUPERUSER_ID)['ir.config_parameter'].sudo().get_param(param)
    presented = _bearer()
    if not expected or not presented or not hmac.compare_digest(str(expected), presented):
        return api_response(error='Unauthorized', code='AUTH_FAILED', status=401)
    return None


def _run_auth(auth, scope, rate_limit):
    if rate_limit:
        max_calls, window_s = rate_limit
        ip = request.httprequest.remote_addr or 'unknown'
        if not check_rate_limit(f'{auth}:{scope}:{ip}', max_calls, window_s):
            return api_response(error='Rate limit exceeded',
                                code='RATE_LIMITED', status=429)
    if auth == 'public':
        return None
    if auth == 'token':
        return _auth_token(scope)
    if auth == 'service':
        return _auth_service()
    if auth == 'admin':
        return _auth_admin()
    return api_response(error='Unknown auth mode', code='SERVER_ERROR', status=500)


# Public aliases: legacy per-module decorators (ab_mobile_pos_api /
# ab_mobile_saas_billing_api) delegate to these to run on the one token
# system without any importer churn.
set_request_id = _set_request_id
authenticate_token = _auth_token


# --------------------------------------------------------------------------
# The decorator
# --------------------------------------------------------------------------

def _addon_of(func):
    # 'odoo.addons.ab_api_pos.controllers.pos_order' -> 'ab_api_pos'
    parts = (func.__module__ or '').split('.')
    return parts[2] if len(parts) > 2 and parts[0] == 'odoo' else (parts[0] if parts else '')


def _default_tags(func, path):
    # '/api/v1/pos/order/create' -> ['pos']
    segs = [s for s in path.split('/') if s and s not in ('api',) and not s.startswith('v')]
    return [segs[0]] if segs else ['default']


def api_route(path, methods=('POST',), scope=None, auth='token', summary='',
              description='', tags=None, cors='*', csrf=False, deprecated=False,
              rate_limit=None, request_example=None, response_example=None):
    """Register + protect + document an API endpoint in one decorator.

    Applies ``http.route(path, type='http', auth='none', cors=cors, ...)`` and
    wraps the handler with the ``auth`` flow + envelope. ``rate_limit`` is an
    ``(max_calls, window_seconds)`` tuple. ``request_example`` /
    ``response_example`` are plain dicts surfaced in the OpenAPI doc.
    """
    methods = list(methods)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _set_request_id()
            if request.httprequest.method == 'OPTIONS':
                return cors_preflight()
            err = _run_auth(auth, scope, rate_limit)
            if err is not None:
                return err
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _logger.exception('api: handler crashed route=%s', path)
                return api_response(error=str(e), code='SERVER_ERROR', status=500)

        ENDPOINT_REGISTRY.append({
            'path': path,
            'methods': methods,
            'scope': scope,
            'auth': auth,
            'summary': summary,
            'description': description,
            'tags': list(tags) if tags else _default_tags(func, path),
            'deprecated': deprecated,
            'module': _addon_of(func),
            'request_example': request_example,
            'response_example': response_example,
        })

        return http.route(path, type='http', auth='none', methods=methods,
                          csrf=csrf, cors=cors)(wrapper)

    return decorator
