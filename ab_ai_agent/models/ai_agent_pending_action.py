# -*- coding: utf-8 -*-
"""A state change the assistant proposed and the user has not yet approved.

Every tool that changes business data (post, confirm, validate, cancel…)
runs in two phases. The first call only resolves the target and records
one of these rows; the answer carries a Confirm / Cancel chip bound to
its ``key``. The change itself runs from :meth:`resolve`, reached from
the chip through ``/ai_agent/action/confirm`` — never from the model. So
a mis-read intent, a prompt injection in a record's text, or a voice
transcript can at most *propose* a change; only a click performs it.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# A proposal is a question asked in a conversation, not a standing order:
# after this long the user is looking at something else.
PROPOSAL_TTL = timedelta(minutes=15)


class AiAgentPendingAction(models.Model):
    _name = 'ai.agent.pending.action'
    _description = 'AI Proposed Action (awaiting confirmation)'
    _order = 'id desc'
    _rec_name = 'summary'

    key = fields.Char(required=True, index=True, readonly=True, copy=False)
    user_id = fields.Many2one('res.users', required=True, readonly=True,
                              default=lambda self: self.env.user,
                              ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', readonly=True,
                                 default=lambda self: self.env.company)
    tool_code = fields.Char(required=True, readonly=True)
    args_json = fields.Text(readonly=True)
    target_model = fields.Char(readonly=True)
    target_id = fields.Integer(readonly=True)
    summary = fields.Char(readonly=True)
    agent_run_id = fields.Many2one('ai.agent.run', readonly=True,
                                   ondelete='set null')
    state = fields.Selection([
        ('proposed', 'Awaiting confirmation'),
        ('executed', 'Executed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ], default='proposed', required=True, readonly=True, index=True)
    result_json = fields.Text(readonly=True)
    error = fields.Char(readonly=True)
    decided_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ('key_unique', 'unique(key)', 'Proposal keys are unique.'),
    ]

    # ── Proposal ───────────────────────────────────────────────

    @api.model
    def propose(self, tool_code, args, *, target=None, summary='', agent_run=None, details=None):
        """Record a proposal for the CURRENT user and return the chip payload.

        Created as the user (the ACL grants create on own rows), so a
        proposal can never be minted on someone else's behalf.
        """
        row = self.create({
            'key': secrets.token_urlsafe(18),
            'tool_code': tool_code,
            'args_json': json.dumps(args or {}, default=str),
            'target_model': target._name if target else False,
            'target_id': target.id if target else 0,
            'summary': (summary or '')[:250],
            'agent_run_id': agent_run.id if agent_run else False,
        })
        return {
            'requires_confirmation': True,
            'confirmation': {'key': row.key, 'summary': row.summary,
                             # what exactly will happen, shown on the card
                             'details': [str(d)[:200] for d in (details or [])][:12]},
        }

    # ── Decision ───────────────────────────────────────────────

    @api.model
    def resolve(self, key, confirm):
        """Apply the user's click. Returns ``{'ok', 'message', 'result'}``.

        Runs as the clicking user: the record rule limits the lookup to
        their own proposals, and the tool re-checks access on the target
        at execution time, so rights removed in between are honoured.
        """
        row = self.search([('key', '=', key or ''),
                           ('user_id', '=', self.env.uid)], limit=1)
        if not row:
            return {'ok': False, 'message': _('This confirmation is no longer valid.')}
        if row.state == 'executed':
            # Double click / retried request: report, never re-run.
            return {'ok': True, 'replayed': True,
                    'message': _('Already done.'),
                    'result': json.loads(row.result_json or '{}')}
        if row.state != 'proposed':
            return {'ok': False, 'message': {
                'cancelled': _('This action was already cancelled.'),
                'failed': _('This action already failed. Ask again.'),
                'expired': _('This confirmation expired. Ask again.'),
            }.get(row.state, _('This confirmation is no longer valid.'))}
        now = fields.Datetime.now()
        if row.create_date and now - row.create_date > PROPOSAL_TTL:
            row.sudo().write({'state': 'expired', 'decided_at': now})
            return {'ok': False, 'message': _('This confirmation expired. Ask again.')}
        if not confirm:
            # sudo: the fields are readonly for the user by design; the
            # row was already matched against the user's own-rows rule.
            row.sudo().write({'state': 'cancelled', 'decided_at': now})
            return {'ok': True, 'cancelled': True,
                    'message': _('Cancelled. Nothing was changed.')}

        from ..services import tool_dispatcher
        fn = tool_dispatcher.get(row.tool_code)
        if not fn:
            row.sudo().write({'state': 'failed', 'decided_at': now,
                              'error': 'tool unavailable'})
            return {'ok': False, 'message': _('That action is not available any more.')}
        args = json.loads(row.args_json or '{}')
        try:
            with self.env.cr.savepoint():
                result = fn(self.env, agent=None, _ai_confirmed=True, **args)
        except Exception as e:
            _logger.info('Confirmed AI action %s failed: %s', row.tool_code, e)
            row.sudo().write({'state': 'failed', 'decided_at': now,
                              'error': str(e)[:250]})
            return {'ok': False, 'message': _('That action could not be completed.')}
        result = result if isinstance(result, dict) else {'result': result}
        if result.get('error'):
            row.sudo().write({'state': 'failed', 'decided_at': now,
                              'error': str(result['error'])[:250]})
            return {'ok': False, 'message': result['error'], 'result': result}
        row.sudo().write({'state': 'executed', 'decided_at': now,
                          'result_json': json.dumps(result, default=str)})
        return {'ok': True, 'executed': True,
                'message': result.get('message') or _('Done.'),
                'result': result}

    @api.autovacuum
    def _gc_old_proposals(self):
        """Expire stale proposals and drop decided rows after 90 days."""
        now = fields.Datetime.now()
        self.sudo().search([('state', '=', 'proposed'),
                            ('create_date', '<', now - PROPOSAL_TTL)]).write(
            {'state': 'expired', 'decided_at': now})
        self.sudo().search([('state', '!=', 'proposed'),
                            ('create_date', '<', now - timedelta(days=90))]).unlink()
