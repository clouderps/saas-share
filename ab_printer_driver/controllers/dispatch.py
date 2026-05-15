# -*- coding: utf-8 -*-
"""Generic dispatch endpoint.

Any consumer (POS, accounting portal, sale order Quick-Print) can POST
here to enqueue a print job. The endpoint:

  1. Resolves the target ab.printer.config (by id, or by use+hint).
  2. Builds an ab.printer.job row with the right payload_kind.
  3. Tries immediate dispatch (best-effort) — if it fails, the job stays
     in 'retrying' state and the drain cron picks it up.
  4. Returns {success, job_id, state, error?}.

Consumer modules can also call ab.printer.config.print_bytes() /
print_image() / print_report() directly when they don't need queue
semantics.
"""
import base64
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PrinterDispatchController(http.Controller):

    @http.route('/ab_printer/dispatch', type='json', auth='user', methods=['POST'])
    def dispatch(self, **kw):
        kind = kw.get('payload_kind') or 'escpos'
        use = kw.get('printer_use') or 'receipt'
        driver_id = kw.get('driver_id')
        payload = kw.get('payload')
        priority = int(kw.get('priority') or 10)
        sync = bool(kw.get('sync', True))           # try immediate dispatch
        source = kw.get('source') or 'http_api'

        env = request.env
        Driver = env['ab.printer.config'].sudo()

        if driver_id:
            driver = Driver.browse(int(driver_id))
            if not driver.exists():
                return {'success': False, 'error': f'driver {driver_id} not found'}
        else:
            driver = Driver.get_default(use=use)
        if not driver:
            return {'success': False,
                    'error': f'No printer configured for use={use}'}

        # 'report' kind — render an ir.actions.report and rasterise.
        # Bypasses the job queue because it's a synchronous backend
        # action (operator clicked Print — wants the result now).
        if kind == 'report':
            report_ref = (payload or {}).get('report_ref')
            res_ids = (payload or {}).get('res_ids') or []
            if not report_ref or not res_ids:
                return {'success': False,
                        'error': 'payload must include report_ref + res_ids'}
            model_name = env['ir.actions.report'].sudo()._get_report(
                report_ref).model if isinstance(report_ref, str) else None
            if not model_name:
                # Fall back: caller can hint the model
                model_name = (payload or {}).get('model')
            if not model_name:
                return {'success': False, 'error': 'cannot resolve report model'}
            records = env[model_name].sudo().browse([int(i) for i in res_ids])
            res = driver.print_report(report_ref, records, render_kind='raster')
            return res

        # Normalise payload to base64 string for storage.
        if isinstance(payload, dict):
            payload_b64 = base64.b64encode(
                json.dumps(payload).encode('utf-8')
            ).decode('ascii')
        elif isinstance(payload, str):
            # Caller might send raw base64 or a 'data:...' URI.
            payload_b64 = (payload.split(',', 1)[1]
                           if ',' in payload[:30] else payload)
        else:
            return {'success': False, 'error': 'payload must be str/dict'}

        job = env['ab.printer.job'].sudo().create({
            'printer_config_id': driver.id,
            'agent_id': driver.agent_id.id or False,
            'op_type': 'print',
            'payload_kind': kind,
            'payload_b64': payload_b64,
            'priority': priority,
            'source': source,
        })
        # Agent path: the agent's /poll picks the job up; HTTP returns
        # immediately. Caller can subscribe to bus channel
        # 'ab_printer_job_<id>' for the final state.
        if driver.agent_id:
            return {
                'success': True, 'queued': True,
                'job_id': job.id, 'state': job.state,
                'agent_id': driver.agent_id.id,
                'agent_online': bool(driver.agent_id.online),
                'agent_name': driver.agent_id.name,
                'error': '' if driver.agent_id.online
                         else 'Agent offline — job will run when it reconnects',
            }
        if sync:
            job._dispatch_one()

        return {
            'success': job.state == 'done',
            'job_id': job.id,
            'state': job.state,
            'error': job.last_error,
            'duration_ms': job.duration_ms,
        }
