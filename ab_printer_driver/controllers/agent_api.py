"""Bridge agent HTTP API.

The bridge agent runs **inside the customer's LAN** and reaches the
Odoo server outbound-only over HTTPS. It uses long-polling (not
WebSocket) to keep the path through nginx + the existing HTTP worker
pool — no gevent retrofit, no `Upgrade: websocket` headers to debug.

Endpoints (all type='http', auth='public', JSON body, X-Agent-Token header):

  POST /ab_printer/agent/register
       body  {"agent_name":..., "version":..., "agent_local_ip":...,
              "agent_subnet":...}
       reply {"success":true, "agent_id":N}

  POST /ab_printer/agent/poll      (long-poll up to 25 s)
       body  {}     (heartbeat happens implicitly on every poll)
       reply {"success":true, "kind":"print"|"scan"|null,
              ... job/scan payload ...}

  POST /ab_printer/agent/report
       body  {"job_id":N, "ok":bool, "error":"...", "duration_ms":N}
        or   {"scan_request_id":N, "ok":bool, "result":{...},
              "error":"..."}
       reply {"success":true}

Auth: every request must carry ``X-Agent-Token`` with a value matching
``ab.printer.agent.token``. Tokens are per-row UUID4 hex.
"""
import base64
import json
import logging
import os
import time

from odoo import fields, http, tools
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

POLL_MAX_S = 25      # long-poll wait ceiling — under nginx's 30 s default
POLL_TICK_S = 0.5    # how often to peek the queue while waiting


def _agent_or_401():
    """Look up the agent by X-Agent-Token. Returns (agent_record, error_json|None).
    On miss, error_json is a ready-to-return 401 dict.
    """
    token = request.httprequest.headers.get('X-Agent-Token') or ''
    agent = request.env['ab.printer.agent'].sudo()._resolve_token(token)
    if not agent:
        return None, {'success': False, 'error': 'invalid agent token'}
    return agent, None


def _json_reply(data, status=200):
    """Return a Response object so we control status code (auth=public
    + type=http means we serialise our own JSON)."""
    return Response(
        json.dumps(data), status=status,
        content_type='application/json; charset=utf-8',
    )


def _read_body():
    try:
        raw = request.httprequest.get_data(as_text=True) or '{}'
        return json.loads(raw)
    except Exception:
        return {}


class PrinterAgentController(http.Controller):

    @http.route('/ab_printer/agent/register', type='http',
                auth='public', methods=['POST'], csrf=False)
    def agent_register(self, **_kw):
        agent, err = _agent_or_401()
        if err:
            return _json_reply(err, status=401)
        body = _read_body()
        agent.sudo().write({
            'version': (body.get('version') or '')[:32],
            'agent_local_ip': (body.get('agent_local_ip') or '')[:64],
            'agent_subnet': (body.get('agent_subnet') or '')[:64],
            'last_seen': fields.Datetime.now(),
        })
        return _json_reply({
            'success': True,
            'agent_id': agent.id,
            'agent_name': agent.name,
            'server_time': fields.Datetime.now().isoformat(),
            'poll_timeout_s': POLL_MAX_S,
        })

    @http.route('/ab_printer/agent/poll', type='http',
                auth='public', methods=['POST'], csrf=False)
    def agent_poll(self, **_kw):
        agent, err = _agent_or_401()
        if err:
            return _json_reply(err, status=401)
        # Heartbeat on every poll — commit immediately so concurrent
        # readers (online flag, scan-request inserts) see it right away.
        agent.sudo().last_seen = fields.Datetime.now()
        request.env.cr.commit()

        Job = request.env['ab.printer.job'].sudo()
        ScanReq = request.env['ab.printer.scan.request'].sudo()
        deadline = time.time() + POLL_MAX_S

        while time.time() < deadline:
            # Force a fresh PG snapshot every tick — Odoo's HTTP cursor
            # uses REPEATABLE READ; without this commit the long-poll
            # would never see rows inserted by other transactions after
            # the loop began.
            request.env.cr.commit()
            # Print jobs first.
            job = Job.search(
                [('agent_id', '=', agent.id),
                 ('state', 'in', ('queued', 'retrying'))],
                order='priority desc, create_date', limit=1,
            )
            if job:
                job.write({'state': 'claimed',
                           'claimed_at': fields.Datetime.now(),
                           'attempts': job.attempts + 1})
                request.env.cr.commit()  # release to agent immediately
                printer = job.printer_config_id
                return _json_reply({
                    'success': True, 'kind': 'print',
                    'job_id': job.id,
                    'op_type': job.op_type,
                    'payload_kind': job.payload_kind,
                    'payload_b64': job.payload_b64 or '',
                    'printer': {
                        'id': printer.id,
                        'name': printer.name,
                        'ip': printer.printer_ip,
                        'port': printer.printer_port or 9100,
                        'paper_width_mm': printer.paper_width_mm,
                        'timeout_ms': printer.timeout or 5000,
                    },
                    'attempt': job.attempts,
                })
            # Scan requests.
            scan = ScanReq.search(
                [('agent_id', '=', agent.id), ('state', '=', 'pending')],
                order='create_date', limit=1,
            )
            if scan:
                scan.write({'state': 'claimed',
                            'claimed_at': fields.Datetime.now()})
                request.env.cr.commit()
                return _json_reply({
                    'success': True, 'kind': 'scan',
                    'scan_request_id': scan.id,
                    'params': json.loads(scan.params_json or '{}'),
                })
            # Nothing to do — sleep briefly then peek again.
            time.sleep(POLL_TICK_S)

        return _json_reply({'success': True, 'kind': None})

    @http.route('/ab_printer/agent/report', type='http',
                auth='public', methods=['POST'], csrf=False)
    def agent_report(self, **_kw):
        agent, err = _agent_or_401()
        if err:
            return _json_reply(err, status=401)
        body = _read_body()
        agent.sudo().last_seen = fields.Datetime.now()

        # Print-job report
        if body.get('job_id'):
            Job = request.env['ab.printer.job'].sudo()
            job = Job.browse(int(body['job_id']))
            if not job.exists() or job.agent_id.id != agent.id:
                return _json_reply({'success': False,
                                    'error': 'job not owned by this agent'},
                                   status=403)
            ok = bool(body.get('ok'))
            error = (body.get('error') or '')[:1024]
            duration_ms = int(body.get('duration_ms') or 0)
            vals = {'duration_ms': duration_ms,
                    'last_attempt_at': fields.Datetime.now()}
            if ok:
                vals.update({'state': 'done', 'last_error': ''})
            elif job.attempts < job.max_attempts:
                vals.update({'state': 'retrying', 'last_error': error})
            else:
                vals.update({'state': 'failed', 'last_error': error})
            job.write(vals)
            # Mirror to ab.printer.log for unified audit trail.
            try:
                request.env['ab.printer.log'].sudo().create({
                    'printer_config_id': job.printer_config_id.id,
                    'printer_type': 'agent',
                    'job_status': 'done' if ok else 'failed',
                    'error_message': error,
                    'duration': duration_ms / 1000.0,
                    'source': f'agent:{agent.name}',
                })
            except Exception:
                pass
            job._notify()
            return _json_reply({'success': True, 'state': job.state})

        # Scan-request report
        if body.get('scan_request_id'):
            ScanReq = request.env['ab.printer.scan.request'].sudo()
            sr = ScanReq.browse(int(body['scan_request_id']))
            if not sr.exists() or sr.agent_id.id != agent.id:
                return _json_reply({'success': False,
                                    'error': 'scan request not owned by this agent'},
                                   status=403)
            ok = bool(body.get('ok'))
            result = body.get('result') or {}
            sr.write({
                'state': 'done' if ok else 'failed',
                'result_json': json.dumps(result),
                'error': (body.get('error') or '')[:512],
                'done_at': fields.Datetime.now(),
            })
            return _json_reply({'success': True})

        return _json_reply({'success': False,
                            'error': 'job_id or scan_request_id required'},
                           status=400)

    @http.route('/ab_printer/agent/download', type='http',
                auth='public', methods=['GET'], csrf=False)
    def agent_download(self, **_kw):
        """Serve the agent .py to install_agent.sh on the LAN PC.

        Public on purpose — the script itself is harmless without a
        token. Operators paste the token into the installer's env vars.
        """
        try:
            path = tools.misc.file_path(
                'ab_printer_driver/tools/ab_printer_agent.py'
            )
        except Exception:
            path = None
        if not path or not os.path.exists(path):
            return Response('agent script not found', status=404)
        with open(path, 'rb') as fh:
            payload = fh.read()
        return Response(
            payload, status=200,
            content_type='text/x-python; charset=utf-8',
            headers=[
                ('Content-Disposition',
                 'attachment; filename="ab_printer_agent.py"'),
            ],
        )
