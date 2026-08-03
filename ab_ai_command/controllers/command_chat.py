# -*- coding: utf-8 -*-
"""Endpoints for the ``/`` palette and direct command execution.

Running a recognised slash command does NOT go through the model. It is
already unambiguous — the user named the command and the fields — so a
round trip would only add latency, cost and a chance to mis-extract what
was typed literally. The agent stays in the loop for everything the
parser could not fill.
"""
from odoo import http
from odoo.http import request


class AICommandController(http.Controller):

    @http.route('/ai_agent/commands', type='json', auth='user', methods=['POST'])
    def commands(self, **kwargs):
        """Palette contents — this user's runnable commands only."""
        Command = request.env.get('ai.agent.command')
        if Command is None:
            return {'success': True, 'commands': []}
        return {'success': True,
                'commands': Command.palette_for_user(request.env.user)}

    @http.route('/ai_agent/command/run', type='json', auth='user',
                methods=['POST'])
    def run(self, text=None, command=None, fields=None,
            create_missing=None, **kwargs):
        """Execute a slash command and return its preview.

        Permission is enforced in ``ai.agent.command.run`` (group + the
        target model's create ACL), so this route adds no gate of its
        own — a second, weaker check here would be the one that drifts.
        """
        Command = request.env.get('ai.agent.command')
        if Command is None:
            return {'success': False, 'error': 'commands not installed'}

        record, pairs = None, dict(fields or {})
        if command:
            record = Command.sudo().search([('code', '=', command)], limit=1)
        if text:
            parsed, matched = Command.parse_text(text)
            record = record or matched
            if matched:
                merged = dict(parsed['pairs'])
                merged.update(pairs)
                pairs = merged

        if not record:
            return {'success': False, 'error': 'no_such_command',
                    'commands': Command.palette_for_user(request.env.user)}

        if isinstance(create_missing, list):
            create_missing = {f: True for f in create_missing}
        result = record.run(pairs, create_missing=create_missing)
        # Echo the inputs so the client can re-submit verbatim when the
        # user answers a question — it must never have to reconstruct
        # what was typed.
        result['_echo'] = {'command': record.sudo().code, 'fields': pairs}
        return {'success': True, 'result': result}
