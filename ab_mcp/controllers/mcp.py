# -*- coding: utf-8 -*-
"""Stateless MCP endpoint (Streamable HTTP, JSON responses only)."""
import hashlib
import json
import logging
import time
import uuid

import psycopg2.errors

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..services import catalog
from odoo.addons.ab_ai_agent.services import tool_dispatcher

_logger = logging.getLogger(__name__)

SUPPORTED_VERSIONS = ('2025-11-25', '2025-06-18')  # newest first
SERVER_INFO = {'name': 'ghaima', 'version': '18.0.1.0.0'}
APPROVALS_PATH = '/odoo/action-ab_mcp.action_mcp_approvals'


class McpError(Exception):
    def __init__(self, http_status, code, message, data=None):
        super().__init__(message)
        self.http_status, self.code, self.message, self.data = http_status, code, message, data


class _RollBack(Exception):
    def __init__(self, out):
        super().__init__('tool failed')
        self.out = out


def _summary(result, limit=1500):
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, default=str, ensure_ascii=False, separators=(',', ':'))
    return text if len(text) <= limit else text[:limit] + '…'


class McpController(http.Controller):

    @http.route('/mcp', type='http', auth='none', methods=['GET', 'POST', 'DELETE'],
                csrf=False, readonly=False, save_session=False)
    def mcp(self, **_kw):
        if request.httprequest.method != 'POST':
            return request.make_response('', status=405, headers=[('Allow', 'POST')])
        try:
            msg = json.loads(request.httprequest.get_data(as_text=True) or 'null')
        except ValueError:
            return self._rpc_error(None, -32700, 'Parse error', status=400)
        if isinstance(msg, list):
            return self._rpc_error(None, -32600, 'Batch requests are not supported', status=400)
        if not isinstance(msg, dict) or msg.get('jsonrpc') != '2.0' or not isinstance(msg.get('method'), str):
            return self._rpc_error(msg.get('id') if isinstance(msg, dict) else None,
                                   -32600, 'Invalid request', status=400)
        rid = msg.get('id')
        is_notification = 'id' not in msg
        try:
            token = self._authenticate()
            self._gate(token)
            result = self._handle(token, msg['method'], msg.get('params') or {})
        except McpError as e:
            if e.http_status == 401:
                resp = self._rpc_error(rid, -32001, e.message, status=401, data=e.data)
                resp.headers['WWW-Authenticate'] = 'Bearer realm="ghaima", error="invalid_token"'
                return resp
            return self._rpc_error(rid, e.code, e.message, status=e.http_status, data=e.data)
        except (psycopg2.errors.SerializationFailure, psycopg2.errors.LockNotAvailable,
                psycopg2.errors.DeadlockDetected):
            # Let Odoo's request retry loop replay the whole request.
            raise
        except Exception:
            request_id = uuid.uuid4().hex[:12]
            _logger.exception('MCP request failed [request %s]', request_id)
            return self._rpc_error(rid, -32603, 'Internal error',
                                   data={'request_id': request_id}, status=500)
        if is_notification:
            return request.make_response('', status=202)
        return request.make_json_response({'jsonrpc': '2.0', 'id': rid, 'result': result})

    # ── helpers ────────────────────────────────────────────────

    def _rpc_error(self, rid, code, message, status=200, data=None):
        err = {'code': code, 'message': message}
        if data is not None:
            err['data'] = data
        return request.make_json_response({'jsonrpc': '2.0', 'id': rid, 'error': err}, status=status)

    def _authenticate(self):
        header = request.httprequest.headers.get('Authorization') or ''
        bearer = header[7:].strip() if header[:7].lower() == 'bearer ' else ''
        if not bearer or not request.db:
            raise McpError(401, -32001, 'Missing or invalid token')
        token = request.env(user=SUPERUSER_ID)['mcp.token']._resolve(bearer)
        user = token.user_id
        if not token or not user.active or user.share:
            raise McpError(401, -32001, 'Missing or invalid token')
        request.update_env(user=user.id, context=dict(
            request.env.context, lang=user.lang or 'en_US', tz=user.tz,
            allowed_company_ids=[user.company_id.id], ai_origin='mcp'))
        return token.with_env(request.env)

    def _gate(self, token):
        env = request.env
        Policy = env['ai.feature.policy']

        def deny(code, message):
            raise McpError(403, -32003, message, data={'code': code})
        if Policy.get('kill'):
            deny('killed', env._('Ghaima AI is switched off on this system.'))
        if not Policy.get('mcp.enabled'):
            if Policy._local('mcp.enabled'):
                deny('mcp_not_in_plan', env._('MCP access is not included in your plan.'))
            deny('mcp_disabled', env._('MCP access is turned off on this system.'))
        clients = Policy.get('mcp.clients')
        if clients is not None and token.client not in clients:
            deny('mcp_not_in_plan', env._('This AI app is not included in your plan.'))
        reason = env.user._ai_assistant_block_reason()
        if reason:
            mapping = {'killed': 'killed', 'disabled': 'mcp_disabled', 'no_seat': 'no_seat'}
            deny(mapping.get(reason, 'inactive'), env._('Ghaima AI is not active for this user.'))
        if Policy.get('mcp.max_users') and env.user.id not in env['mcp.token']._seat_holder_ids():
            deny('no_seat', env._('All MCP seats of your plan are in use.'))

    def _handle(self, token, method, params):
        if method == 'initialize':
            asked = params.get('protocolVersion')
            info = params.get('clientInfo') or {}
            if info.get('name'):
                token._touch(token.id, client=str(info.get('name'))[:64])
            return {
                'protocolVersion': asked if asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': SERVER_INFO,
            }
        if method.startswith('notifications/'):
            return {}
        if method == 'ping':
            return {}
        policy = catalog.mcp_policy(request.env, token)
        if method == 'tools/list':
            tools = catalog.tools_for(request.env, token, policy)
            return {'tools': [t.as_mcp_schema() for t in tools]}
        if method == 'tools/call':
            return self._call(token, policy, params)
        raise McpError(200, -32601, 'Method not found')

    def _call(self, token, policy, params):
        env = request.env
        name = params.get('name')
        args = params.get('arguments') or {}
        if not isinstance(args, dict):
            raise McpError(200, -32602, 'arguments must be an object')
        tool = catalog.tools_for(env, token, policy).filtered(lambda t: t.code == name)[:1]
        if not tool:
            raise McpError(200, -32602, env._('Unknown tool.'))
        limit = env['ai.feature.policy'].get('mcp.max_calls_day')
        if not env['mcp.usage.day']._consume(limit):
            raise McpError(429, -32029, env._('Daily MCP call limit reached.'),
                           data={'code': 'limit_reached', 'limit': limit})
        started = time.perf_counter()
        # A failing tool must leave nothing behind: roll its writes back,
        # as ai.agent.pending.action.resolve() does for confirmed actions.
        try:
            with env.cr.savepoint():
                out = tool_dispatcher.dispatch(env, tool, args, policy=policy)
                if not out.get('ok'):
                    raise _RollBack(out)
        except _RollBack as rb:
            out = rb.out
        ok = bool(out.get('ok'))
        result = out.get('result') if ok else None
        request_id = out.get('request_id') or uuid.uuid4().hex[:12]
        # sudo: append-only audit row; users have no create right.
        env['mcp.call.log'].sudo().create({
            'user_id': env.uid, 'company_id': env.company.id, 'token_id': token.id,
            'tool_code': tool.code, 'client': token.last_client or token.client,
            'ok': ok, 'error_kind': out.get('error') or False,
            'duration_ms': int((time.perf_counter() - started) * 1000),
            'request_id': request_id,
            'args_hash': hashlib.sha256(json.dumps(args, sort_keys=True, default=str)
                                        .encode('utf-8')).hexdigest(),
        })
        token._touch(token.id)
        if not ok:
            message = out.get('message') or env._('The tool failed.')
            if out.get('error') not in ('user_error',) and 'Reference' not in message:
                message = f'{message} (reference {request_id})'
            return {'content': [{'type': 'text', 'text': message}],
                    'structuredContent': {'error': out.get('error') or 'failed',
                                          'message': message, 'request_id': request_id},
                    'isError': True}
        if isinstance(result, dict) and result.get('requires_confirmation'):
            # mask_result() keeps the opaque 'key' intact, so the key and the
            # (masked) summary come straight from this call's own result.
            conf = dict(result.get('confirmation') or {})
            base = env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
            url = base + APPROVALS_PATH
            text = env._('Proposal created, nothing has changed yet: "%(summary)s". The user must '
                          'confirm it in Ghaima within 15 minutes: %(url)s . Check it with '
                          'get_proposal_status (key %(key)s).',
                          summary=conf.get('summary') or tool.code, url=url, key=conf.get('key'))
            return {'content': [{'type': 'text', 'text': text}],
                    'structuredContent': {'status': 'proposed', 'key': conf.get('key'),
                                          'summary': conf.get('summary'),
                                          'details': conf.get('details') or [],
                                          'approvals_url': url, 'expires_in_minutes': 15},
                    'isError': False}
        structured = result if isinstance(result, dict) else {'result': result}
        return {'content': [{'type': 'text', 'text': _summary(result)}],
                'structuredContent': structured, 'isError': False}
