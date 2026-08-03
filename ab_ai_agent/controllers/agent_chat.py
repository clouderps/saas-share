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

import json
import logging

from odoo import http, _
from odoo.api import Environment as Env
from odoo.http import request
from odoo.modules.registry import Registry as registry

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

    # ── Conversation starters ──────────────────────────────────

    @http.route('/ai_agent/starters', type='json', auth='user',
                methods=['POST'])
    def starters(self, record_model=None, **kwargs):
        """Opening suggestions built from what this user can reach.

        The panel used to ship a fixed list — "P&L report for this
        month", "cash position" — regardless of who was looking at it.
        A cashier was invited to open screens they have no access to,
        and every suggestion failed for them.

        These are derived from the user's real menu access instead
        (same source the find_menu tool reads), so the panel never
        offers a door that is locked. Record context wins when present:
        on a form the useful openers are about that record.
        """
        env = request.env
        arabic = (env.user.lang or '').startswith('ar')

        if record_model:
            Model = env.get(record_model)
            label = (Model._description or record_model) if Model is not None \
                else record_model
            return {'success': True, 'starters': [
                {'icon': 'fa-question-circle',
                 'text': (f'ما معنى شاشة {label}؟' if arabic
                          else f'What is this {label} screen for?')},
                {'icon': 'fa-compress',
                 'text': 'لخّص هذا السجل' if arabic else 'Summarise this record'},
                {'icon': 'fa-lightbulb-o',
                 'text': ('ما الذي يجب أن أفعله الآن؟' if arabic
                          else 'What should I do next?')},
            ]}

        # Grouped by what the opener DOES. A flat list showed the
        # assistant's range as "some sentences"; the groups tell a new
        # user what it is for in one glance. Contents stay derived from
        # real access — the grouping is presentation, not a fixed menu.
        groups = [
            {'code': 'ask',
             'title': 'اسأل عن بياناتك' if arabic else 'Ask about your data',
             'items': []},
            {'code': 'create',
             'title': 'أنشئ مستنداً' if arabic else 'Create a document',
             'items': []},
            {'code': 'learn',
             'title': 'تعرّف على النظام' if arabic else 'Find your way around',
             'items': []},
        ]
        by_code = {g['code']: g for g in groups}

        by_code['learn']['items'].append(
            {'icon': 'fa-th-large',
             'text': ('ما الذي يمكنني فعله في النظام؟' if arabic
                      else 'What can I do in the system?')})
        by_code['learn']['items'].append(
            {'icon': 'fa-map-signs',
             'text': ('وين أسوي فاتورة؟' if arabic
                      else 'Where do I create an invoice?')})

        # Only commands this user may actually run, same filter the
        # palette uses — never offer a door that is locked.
        Command = env.get('ai.agent.command')
        if Command is not None:
            for cmd in Command.palette_for_user(env.user)[:3]:
                by_code['create']['items'].append(
                    {'icon': cmd.get('icon') or 'fa-plus-circle',
                     'text': '/%s ' % cmd['verb']})

        out = []

        from ..services.tool_dispatcher import _builtin_list_my_apps
        apps = (_builtin_list_my_apps(env) or {}).get('apps') or []
        # Skip the shells every user has — they make dull suggestions.
        skip = {'Discuss', 'Calendar', 'Contacts', 'To-do', 'Dashboard',
                'Settings', 'Apps', 'Ghaima AI'}
        for app in apps:
            if app['name'] in skip:
                continue
            by_code['ask']['items'].append({
                'icon': 'fa-arrow-circle-o-right',
                'text': (f"ما الجديد في {app['name']}؟" if arabic
                         else f"What's happening in {app['name']}?"),
            })
            if len(by_code['ask']['items']) >= 3:
                break

        if not by_code['ask']['items']:
            # No back-office apps at all (portal user).
            by_code['learn']['items'].append({
                'icon': 'fa-question-circle',
                'text': ('كيف أستخدم بوابة العملاء؟' if arabic
                         else 'How do I use the customer portal?'),
            })

        groups = [g for g in groups if g['items']]
        # Flat list kept for callers that predate the grouping.
        out = [i for g in groups for i in g['items']]
        return {'success': True, 'starters': out, 'groups': groups}

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

    # ── Conversations ──────────────────────────────────────────
    #
    # The console used to be stateless: every visit started from a blank
    # welcome, and nothing it said was ever written down. Meanwhile the
    # floating bubble and the old full-page chat both persisted to
    # ai.chat.conversation — so the same user, asking the same assistant,
    # had two different memories depending on which door they came in.
    #
    # These endpoints put the console on those same rows. They live here
    # rather than calling /ai_chat/* directly because ab_ai_agent ships in
    # saas-share and must install with no chatbot module present; when
    # ai.chat.conversation is absent every one of them degrades to
    # "unavailable" and the console simply behaves as it did before.

    @http.route('/ai_agent/conversation/list', type='json', auth='user',
                methods=['POST'])
    def conversation_list(self, limit=30, **_kw):
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': True, 'available': False, 'conversations': []}
        convs = Conv.search(
            [('user_id', '=', request.env.uid), ('record_ref', '=', False)],
            limit=int(limit))
        return {
            'success': True,
            'available': True,
            'conversations': [{
                'id': c.id,
                'name': c.name or _('New Chat'),
                'message_count': c.message_count,
                'updated': str(c.write_date or ''),
            } for c in convs],
        }

    @http.route('/ai_agent/conversation/messages', type='json', auth='user',
                methods=['POST'])
    def conversation_messages(self, conversation_id=None, **_kw):
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None or not conversation_id:
            return {'success': True, 'available': False, 'messages': []}
        conv = Conv.browse(int(conversation_id))
        # Ownership is checked by the record rule; browse + read raises
        # for someone else's chat rather than leaking it.
        if not conv.exists():
            return {'success': False, 'error': 'not_found'}
        conv.check_access('read')
        return {
            'success': True,
            'available': True,
            'conversation_id': conv.id,
            'name': conv.name or '',
            'agent_id': conv.agent_id.id if conv.agent_id else False,
            'messages': _serialise_messages(conv),
        }

    @http.route('/ai_agent/conversation/new', type='json', auth='user',
                methods=['POST'])
    def conversation_new(self, agent_code=None, **_kw):
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': True, 'available': False, 'conversation_id': 0}
        vals = {'name': _('New Chat')}
        if agent_code:
            agent = request.env['ai.agent'].get_by_code(agent_code)
            if agent:
                vals['agent_id'] = agent.id
        conv = Conv.create(vals)
        return {'success': True, 'available': True, 'conversation_id': conv.id}

    @http.route('/ai_agent/conversation/open', type='json', auth='user',
                methods=['POST'])
    def conversation_open(self, conversation_id=None, agent_code=None, **_kw):
        """The console's landing call: resume where the user left off.

        Reopening the assistant and finding an empty screen is the thing
        that made the console feel like a different product from the
        bubble. Pick up the most recent chat instead, and only start a
        fresh one when there is genuinely nothing to resume.
        """
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': True, 'available': False, 'conversation_id': 0,
                    'messages': []}
        conv = Conv.browse(int(conversation_id)) if conversation_id else Conv
        if conv and conv.exists():
            conv.check_access('read')
        else:
            conv = Conv.search(
                [('user_id', '=', request.env.uid),
                 ('record_ref', '=', False)], limit=1)
        if not conv:
            return self.conversation_new(agent_code=agent_code)
        return {
            'success': True,
            'available': True,
            'conversation_id': conv.id,
            'name': conv.name or '',
            'agent_id': conv.agent_id.id if conv.agent_id else False,
            'messages': _serialise_messages(conv),
        }

    @http.route('/ai_agent/conversation/share', type='json', auth='user',
                methods=['POST'])
    def conversation_share(self, conversation_id=None, revoke=False, **_kw):
        """Mint (or revoke) a public link to a conversation.

        Sharing an answer with a colleague is how these get used in
        practice — someone asks for the month's numbers and forwards
        what came back. The link is a capability: anyone holding it can
        read the chat, so revoking has to be as easy as creating.
        """
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': False, 'error': 'sharing_unavailable'}
        if not conversation_id:
            return {'success': False, 'error': 'bad_request'}
        conv = Conv.browse(int(conversation_id))
        if not conv.exists():
            return {'success': False, 'error': 'not_found'}
        # write, not read: only the owner may publish a conversation.
        conv.check_access('write')
        if revoke:
            conv.action_unshare()
            return {'success': True, 'shared': False, 'share_url': ''}
        result = conv.action_share() or {}
        return {'success': True, 'shared': True,
                'share_url': result.get('share_url', '')}

    @http.route('/ai_agent/action/confirm', type='json', auth='user',
                methods=['POST'])
    def action_confirm(self, conversation_id=None, action=None, **_kw):
        """Run a write the assistant proposed, after the user agreed.

        Confirmation chips carry a structured payload rather than a
        prompt, and running them must not go back through the model: the
        user already agreed to a specific captured call, so re-asking
        risks executing something subtly different from what was shown.
        This replays the captured tool with confirm=true — deterministic
        and idempotent through the audit log.
        """
        Conv = request.env.get('ai.chat.conversation')
        if Conv is None:
            return {'success': False, 'error': 'confirmation_unavailable'}
        if not (conversation_id and isinstance(action, dict)):
            return {'success': False, 'error': 'bad_request'}
        conv = Conv.browse(int(conversation_id))
        if not conv.exists():
            return {'success': False, 'error': 'not_found'}
        conv.check_access('write')
        try:
            result = conv.execute_action(action)
        except Exception:
            _logger.exception('Confirmed action failed')
            # Never surface the raw exception: it can carry SQL, record
            # ids and field names the user has no business seeing.
            return {'success': False,
                    'error': _('That action could not be completed.')}
        return {'success': True, 'result': result or {}}

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
        # Live progress. Off unless the caller asked for it, so the
        # public widget and server-to-server callers pay nothing.
        on_event = _make_stream_emitter(request.env) \
            if kwargs.get('stream') else None

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
        elif Conv is not None and kwargs.get('conversation_id'):
            # The console now carries a real conversation id. Routing the
            # turn through it is what makes the answer visible from the
            # bubble and from Discuss — the three surfaces stopped being
            # three separate memories the moment this branch existed.
            try:
                candidate = Conv.browse(int(kwargs['conversation_id']))
                if candidate.exists():
                    candidate.check_access('write')
                    conv = candidate
            except Exception:
                conv = None
        if conv is not None:
            # Stamp the conversation's agent in case it was created
            # with a different default earlier.
            if conv.agent_id != agent:
                conv.sudo().agent_id = agent.id
            # Run goes through ai.chat.conversation → which delegates
            # to ab_ai_agent.runtime when the flag is ON (it is).
            result = conv.sudo().with_user(request.env.user).send_message(
                question, on_event=on_event)
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
            on_event=on_event,
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


#: Bus notification type the console subscribes to for live progress.
STREAM_TYPE = 'ai.agent.stream'


def _make_stream_emitter(env):
    """Fan run progress onto the bus as it happens.

    bus.bus._sendone queues into cr.precommit/postcommit, so events sent
    from inside the request transaction only reach the browser when that
    transaction commits — i.e. at the same moment as the finished answer.
    That is what the previous implementation did, which meant the whole
    "stream" arrived in one burst after the wait it was meant to fill.

    Each event therefore gets its own short-lived cursor that commits
    immediately. The side effect is deliberate: progress already shown to
    the user should survive even if the run itself later fails and the
    main transaction rolls back.
    """
    db = env.cr.dbname
    uid = env.uid
    partner_id = env.user.partner_id.id
    if not partner_id:
        return lambda *a, **k: None

    def emit(kind, **kw):
        payload = {'kind': kind}
        # Only forward what the UI paints. Tool args can carry customer
        # names and amounts, and this leaves the request transaction.
        for key in ('hop', 'tool', 'ok', 'state', 'agent'):
            if key in kw:
                payload[key] = kw[key]
        try:
            with registry(db).cursor() as cr:
                Env(cr, uid, {})['bus.bus']._sendone(
                    Env(cr, uid, {})['res.partner'].browse(partner_id),
                    STREAM_TYPE, payload)
        except Exception:
            # Progress is a nicety; never let it break the answer.
            _logger.debug('stream emit failed', exc_info=True)

    return emit


def _serialise_messages(conv):
    """Past turns in the shape the console renders live ones.

    envelope_json is the reason history is worth reopening: without it a
    reloaded chart or KPI grid degrades to the plain sentence beside it,
    so yesterday's answer looks poorer than it was when it arrived.
    """
    out = []
    for m in conv.message_ids.sorted('id'):
        envelope = None
        if m.envelope_json:
            try:
                envelope = json.loads(m.envelope_json)
            except (ValueError, TypeError):
                envelope = None      # plain text is a fine fallback
        out.append({
            'id': m.id,
            'role': m.role,
            'text': m.content or '',
            'envelope': envelope,
            'rating': m.user_rating,
            'created': str(m.create_date or ''),
        })
    return out


def _persona_accent(persona):
    return {
        'assistant': 'blue',
        'analyst':   'navy',
        'coach':     'cyan',
        'bot':       'gold',
        'extractor': 'green',
    }.get(persona, 'blue')
