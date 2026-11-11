# -*- coding: utf-8 -*-
import hashlib
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression

TOKEN_PREFIX = 'gmcp_'

CLIENT_SELECTION = [
    ('claude_desktop', 'Claude Desktop'),
    ('claude_code', 'Claude Code'),
    ('cursor', 'Cursor'),
    ('vscode', 'VS Code'),
    ('chatgpt', 'ChatGPT'),
    ('other', 'Other'),
]

PRESET_SELECTION = [
    ('readonly', 'Read only'),
    ('manager', 'All allowed tools'),
    ('custom', 'Selected tools'),
]


def hash_token(token):
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


class McpToken(models.Model):
    _name = 'mcp.token'
    _description = 'Ghaima MCP — Access token'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True,
                              ondelete='cascade', default=lambda self: self.env.user)
    client = fields.Selection(CLIENT_SELECTION, required=True, default='other')
    token_hash = fields.Char(required=True, readonly=True, copy=False, groups='base.group_system')
    prefix = fields.Char(readonly=True, copy=False,
                         help='First characters of the token, to recognise it.')
    preset = fields.Selection(PRESET_SELECTION, required=True, default='readonly')
    tool_ids = fields.Many2many('ai.agent.tool', 'mcp_token_tool_rel', 'token_id', 'tool_id',
                                string='Tools', domain=[('mcp_enabled', '=', True)])
    allow_write = fields.Boolean(string='Allow write tools',
                                 help='Write tools still only propose; you confirm each change in Ghaima.')
    expires_at = fields.Datetime(required=True)
    revoked_at = fields.Datetime(readonly=True)
    last_used_at = fields.Datetime(readonly=True)
    last_client = fields.Char(readonly=True)
    state = fields.Selection([('active', 'Active'), ('expired', 'Expired'), ('revoked', 'Revoked')],
                             compute='_compute_state', search='_search_state')

    _sql_constraints = [
        ('token_hash_unique', 'unique(token_hash)', 'Token hashes are unique.'),
    ]

    @api.depends('expires_at', 'revoked_at')
    def _compute_state(self):
        now = fields.Datetime.now()
        for tok in self:
            if tok.revoked_at:
                tok.state = 'revoked'
            elif tok.expires_at and tok.expires_at <= now:
                tok.state = 'expired'
            else:
                tok.state = 'active'

    def _search_state(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        values = [value] if operator in ('=', '!=') else list(value or [])
        now = fields.Datetime.now()
        by_state = {
            'active': [('revoked_at', '=', False), ('expires_at', '>', now)],
            'expired': [('revoked_at', '=', False), ('expires_at', '<=', now)],
            'revoked': [('revoked_at', '!=', False)],
        }
        domain = expression.OR([by_state[v] for v in values if v in by_state] or [[(0, '=', 1)]])
        if operator in ('!=', 'not in'):
            domain = ['!'] + expression.normalize_domain(domain)
        return domain

    @api.model
    def _live_domain(self):
        return [('revoked_at', '=', False), ('expires_at', '>', fields.Datetime.now())]

    @api.model
    def _generate(self, vals):
        """Create a token for the CURRENT user; return ``(record, plaintext)``.

        The plaintext is returned once and never stored.
        """
        user = self.env.user
        holders = self._seat_holder_ids()
        limit = self.env['ai.feature.policy'].get('mcp.max_users')
        if limit and user.id not in holders and len(holders) >= limit:
            raise UserError(_('All MCP seats of your plan are in use. Ask an administrator.'))
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        vals = dict(vals, user_id=user.id, token_hash=hash_token(token),
                    prefix=token[:len(TOKEN_PREFIX) + 6])
        if vals.get('preset') != 'custom':
            vals.pop('tool_ids', None)
        # sudo: users have no create right on tokens (they could otherwise
        # pick a user_id / hash); everything here is pinned to the caller.
        return self.sudo().create(vals).sudo(False), token

    @api.model
    def _seat_holder_ids(self):
        """User ids holding an MCP seat (first ``mcp.max_users`` users that
        have a live token, by their oldest live token)."""
        # sudo: seat counting spans every user's tokens.
        # Archived and portal users never hold a seat.
        rows = self.sudo()._read_group(
            self._live_domain() + [('user_id.active', '=', True), ('user_id.share', '=', False)],
            ['user_id'], ['create_date:min'])
        rows.sort(key=lambda r: (r[1], r[0].id))
        ids = [u.id for u, _d in rows]
        limit = self.env['ai.feature.policy'].get('mcp.max_users')
        return ids[:limit] if limit else ids

    @api.model
    def _resolve(self, plaintext):
        """Live token row for a bearer value, or an empty recordset."""
        if not plaintext or not plaintext.startswith(TOKEN_PREFIX):
            return self.browse()
        # sudo: called before any user is known (auth='none').
        return self.sudo().search([('token_hash', '=', hash_token(plaintext))]
                                  + self._live_domain(), limit=1)

    @api.model
    def _touch(self, token_id, client=None):
        """Record last use (and client) on its own short cursor, at most
        once per 5 minutes unless the client changes: concurrent calls on
        one token must not serialize on the token row."""
        registry = self.env.registry
        with registry.cursor() as cr:
            if not registry.in_test_mode():
                cr.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            if client:
                cr.execute("""UPDATE mcp_token SET last_used_at = now() at time zone 'utc',
                                     last_client = %s
                              WHERE id = %s AND (last_client IS DISTINCT FROM %s
                                    OR last_used_at IS NULL
                                    OR last_used_at < (now() at time zone 'utc') - interval '5 minutes')""",
                           [client, token_id, client])
            else:
                cr.execute("""UPDATE mcp_token SET last_used_at = now() at time zone 'utc'
                              WHERE id = %s AND (last_used_at IS NULL
                                    OR last_used_at < (now() at time zone 'utc') - interval '5 minutes')""",
                           [token_id])
        self.browse(token_id).invalidate_recordset(['last_used_at', 'last_client'])

    @api.model
    def _revoke_for_users(self, user_ids):
        """Revoke every live token of ``user_ids`` (user archived)."""
        # sudo: lifecycle bookkeeping on behalf of the user being archived.
        live = self.sudo().search([('user_id', 'in', list(user_ids))] + self._live_domain())
        live.write({'revoked_at': fields.Datetime.now()})
        return live

    def action_revoke(self):
        mine = self.search([('id', 'in', self.ids)])  # own-rows rule applies
        # sudo: revoked_at is readonly for users; rows matched the rule above.
        mine.filtered(lambda t: not t.revoked_at).sudo().write({'revoked_at': fields.Datetime.now()})
        return True

    @api.model
    def default_expiry(self, days):
        return fields.Datetime.now() + timedelta(days=int(days))
