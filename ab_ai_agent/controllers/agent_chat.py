# -*- coding: utf-8 -*-
"""Phase H — agent chat HTTP endpoints.

Three JSON endpoints power every chat surface (Discuss chatbot,
chatter button, composer, public widget):

  POST /ai_agent/list        → list of agents visible to the user
  POST /ai_agent/run         → execute one agent invocation
  POST /ai_agent/rate        → user rating of a previous run
  POST /ai_agent/usage/live  → current live meter snapshot

All endpoints use type='json' so they go through Odoo's JSON-RPC
dispatcher (auto kwargs unpack). auth='user' on internal endpoints;
the public website widget hits a separate auth='public' route.
"""
from __future__ import annotations

import logging

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class AIAgentController(http.Controller):

    # ── List ───────────────────────────────────────────────────

    @http.route('/ai_agent/list', type='json', auth='user', methods=['POST'])
    def list_agents(self, **kwargs):
        """Return agents visible to the current user. Used to populate
        the persona picker in the chat header."""
        Agent = request.env['ai.agent']
        agents = Agent.search([('active', '=', True)])
        visible = agents.filtered(lambda a: a.is_visible_to(request.env.user))
        return {
            'success': True,
            'agents': [{
                'id': a.id,
                'code': a.code,
                'name': a.name,
                'persona': a.persona,
                'description': a.description or '',
                'avatar_url': f'/web/image/ai.agent/{a.id}/avatar' if a.avatar else '',
                'accent': _persona_accent(a.persona),
                'skill_count': len(a.skill_ids),
                'is_default': a.code == 'ghaima_assistant',
            } for a in visible],
        }

    # ── Per-record conversation lookup ─────────────────────────

    @http.route('/ai_agent/conversation/lookup', type='json',
                auth='user', methods=['POST'])
    def conversation_lookup(self, record_model=None, record_id=None,
                            agent_code=None, **_kw):
        """Find-or-create the conversation anchored to (user, record).

        Returns the conversation_id + the last N messages so the
        chatter Ask AI dialog can paint prior history on mount.

        Falls back to a stateless conversation when ab_ai_chatbot
        isn't installed (e.g. central DBCLOUD)."""
        if not (record_model and record_id):
            return {'success': False, 'error': 'record_required'}
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': True, 'conversation_id': 0, 'messages': []}
        agent_id = False
        if agent_code:
            agent = request.env['ai.agent'].get_by_code(agent_code)
            if agent:
                agent_id = agent.id
        conv = Conv.sudo().find_or_create_for_record(
            record_model, int(record_id), agent_id=agent_id,
        )
        msgs = []
        if conv:
            for m in conv.message_ids.sorted('id'):
                msgs.append({
                    'id': m.id,
                    'role': m.role,
                    'text': m.content or '',
                    'created': str(m.create_date),
                })
        return {
            'success': True,
            'conversation_id': conv.id if conv else 0,
            'messages': msgs,
            'agent_id': conv.agent_id.id if conv and conv.agent_id else False,
        }

    # ── Run ────────────────────────────────────────────────────

    @http.route('/ai_agent/run', type='json', auth='user', methods=['POST'])
    def run_agent(self, **kwargs):
        """Execute one agent run. Returns the response envelope.

        Params:
          agent_code (str, optional) — defaults to ghaima_assistant
          agent_id (int, optional) — alternative to agent_code
          message (str, required) — the user prompt
          skill_code (str, optional) — pre-built prompt from a skill card
          surface (str, default 'chat')
          record_model (str, optional) — for chatter context
          record_id (int, optional)
          conversation_id (str, optional) — loose pointer to the chat conv
          locale (str, default 'en')
        """
        message = (kwargs.get('message') or '').strip()
        if not message and not kwargs.get('skill_code'):
            return {'success': False, 'error': 'message_or_skill_required'}

        # Resolve agent
        Agent = request.env['ai.agent']
        agent = Agent.browse(kwargs.get('agent_id') or 0)
        if not agent.exists():
            agent = Agent.get_by_code(kwargs.get('agent_code'))
        if not agent:
            agent = Agent.get_default()
        if not agent:
            return {'success': False, 'error': 'no_agent_available'}
        if not agent.is_visible_to(request.env.user):
            return {'success': False, 'error': 'agent_forbidden'}

        # Resolve optional skill
        skill = request.env['ai.agent.skill']
        if kwargs.get('skill_code'):
            skill = skill.search([
                ('agent_id', '=', agent.id),
                ('code', '=', kwargs['skill_code']),
                ('active', '=', True),
            ], limit=1)

        # Resolve optional record
        record_ref = None
        if kwargs.get('record_model') and kwargs.get('record_id'):
            try:
                record_ref = request.env[kwargs['record_model']].browse(
                    int(kwargs['record_id']))
                record_ref.check_access('read')
            except Exception:
                record_ref = None

        # Resolve final user_question — either the raw message or the
        # skill's templated prompt.
        if skill:
            try:
                question = skill.render_prompt({
                    'message': message,
                    'model': record_ref._name if record_ref else '',
                    'id': record_ref.id if record_ref else 0,
                    'record_name': record_ref.display_name if record_ref else '',
                })
            except Exception as e:
                return {'success': False, 'error': 'skill_render_failed',
                        'message': str(e)}
        else:
            question = message

        # When the chatbot module is installed AND the call has a
        # record context, route through ai.chat.conversation so the
        # turn lands as ai.chat.message rows (persistent history,
        # Cache lookup, Validator verdict). This is the path the
        # chatter Ask AI button takes.
        Conv = request.env.get('ai.chat.conversation')
        surface = kwargs.get('surface') or 'chat'
        conv = None
        if Conv is not None and record_ref and surface == 'chatter':
            try:
                conv = Conv.sudo().find_or_create_for_record(
                    record_ref._name, record_ref.id, agent_id=agent.id,
                )
            except Exception:
                conv = None
        if conv is not None:
            # Stamp the conversation's agent in case it was created
            # with a different default earlier.
            if conv.agent_id != agent:
                conv.sudo().agent_id = agent.id
            # Run goes through ai.chat.conversation → which delegates
            # to ab_ai_agent.runtime when the flag is ON (it is).
            result = conv.sudo().with_user(request.env.user).send_message(question)
            env_dict = result.get('envelope') or {}
            env_dict.update({
                'success': True,
                'conversation_id': conv.id,
                'message_id': result.get('id'),
            })
            return env_dict

        # Stateless path (Discuss chat, public website, central diagnostics).
        from ..services import runtime as runtime_svc
        response_text, run, envelope = runtime_svc.run(
            request.env,
            agent=agent,
            user_question=question,
            conversation=kwargs.get('conversation_id'),
            surface=surface,
            record_ref=record_ref,
            skill=skill or None,
            locale=kwargs.get('locale') or 'en',
        )
        envelope['success'] = True
        envelope['run_id'] = run.id
        return envelope

    # ── Rating ─────────────────────────────────────────────────

    @http.route('/ai_agent/rate', type='json', auth='user', methods=['POST'])
    def rate(self, run_id=None, feedback=None, note=None, **_kw):
        if not run_id or feedback not in ('up', 'down', 1, -1, '1', '-1'):
            return {'success': False, 'error': 'bad_request'}
        run = request.env['ai.agent.run'].browse(int(run_id))
        if not run.exists() or run.user_id.id != request.env.uid:
            return {'success': False, 'error': 'forbidden'}
        run.rate(feedback, note=note)
        return {'success': True}

    # ── Live meter ─────────────────────────────────────────────

    @http.route('/ai_agent/usage/live', type='json', auth='user', methods=['POST'])
    def usage_live(self, period='today', **_kw):
        if period not in ('today', 'week', 'month'):
            period = 'today'
        return {
            'success': True,
            'period': period,
            'summary': request.env['ai.usage.local.log'].sudo().usage_summary(period),
        }


def _persona_accent(persona):
    return {
        'assistant': 'blue',
        'analyst':   'navy',
        'coach':     'cyan',
        'bot':       'gold',
        'extractor': 'green',
    }.get(persona, 'blue')
