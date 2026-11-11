# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PROACTIVE_MODES = [
    ('off', 'Off'),
    ('quiet', 'Quiet: a dot on the assistant'),
    ('on', 'On: short tips as I move between screens'),
]


class ResUsers(models.Model):
    _inherit = 'res.users'

    ai_proactive_mode = fields.Selection(
        PROACTIVE_MODES, string='Ghaima AI tips', default='on', required=True,
        # 'on' by default (owner 2026-09-29): the hint for the current
        # screen must appear without asking. Users can lower it.
        help='How much Ghaima AI tells you on its own when you open a screen. '
             'It never interrupts: tips are one or two lines from your own '
             'data and disappear by themselves.')
    ai_voice_autoplay = fields.Boolean(
        string='Read answers aloud',
        help='Speak every answer automatically. Off: press Listen on an answer.')
    ai_cursor_animation = fields.Boolean(
        string='Show the assistant pointer', default=True,
        help='When Ghaima AI opens a screen for you, a pointer moves to it first. '
             'Off: the screen opens straight away.')

    ai_assistant_active = fields.Boolean(
        string='Use Ghaima AI', copy=False,
        default=lambda self: self._ai_default_assistant_active(),
        help='This user can open the Ghaima AI assistant. Each active user '
             'takes one assistant seat.')
    ai_assistant_activated_on = fields.Datetime(readonly=True, copy=False)

    ai_briefing_text = fields.Text(readonly=True, copy=False)
    ai_briefing_date = fields.Date(readonly=True, copy=False)

    def _ai_briefing(self):
        """Today's briefing for this user: a few counts, as the user (their
        record rules), computed once a day and cached. No AI call."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.ai_briefing_date == today:
            return self.ai_briefing_text or ''
        env = self.env(user=self.id)
        _ = env._
        lines = []

        def count(model, domain):
            M = env.get(model)
            if M is None or not M.has_access('read'):
                return 0
            try:
                return M.search_count(domain)
            except Exception:
                return 0
        overdue = count('mail.activity', [('user_id', '=', self.id), ('date_deadline', '<', today)])
        due = count('mail.activity', [('user_id', '=', self.id), ('date_deadline', '=', today)])
        if overdue or due:
            lines.append(_('%(due)s activities due today, %(late)s overdue.', due=due, late=overdue))
        quotes = count('sale.order', [('user_id', '=', self.id), ('state', '=', 'sent')])
        if quotes:
            lines.append(_('%(n)s sent quotations waiting for the customer.', n=quotes))
        if self.has_group('account.group_account_invoice'):
            late_inv = count('account.move', [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                                              ('payment_state', 'in', ('not_paid', 'partial')),
                                              ('invoice_date_due', '<', today)])
            if late_inv:
                lines.append(_('%(n)s customer invoices are overdue.', n=late_inv))
        if self.has_group('hr_holidays.group_hr_holidays_responsible') if \
                env.ref('hr_holidays.group_hr_holidays_responsible', raise_if_not_found=False) else False:
            leaves = count('hr.leave', [('state', '=', 'confirm')])
            if leaves:
                lines.append(_('%(n)s leave requests to approve.', n=leaves))
        text = '\n'.join(lines)
        try:
            self.sudo().write({'ai_briefing_text': text, 'ai_briefing_date': today})
        except Exception:
            _logger.debug('briefing cache write skipped', exc_info=True)
        return text

    # ── Per-user activation (feature policy) ─────────────────────

    ai_assistant_self_service = fields.Boolean(
        compute='_compute_ai_assistant_self_service',
        help="Users may switch the assistant on or off themselves.")

    def _compute_ai_assistant_self_service(self):
        value = self.env['ai.feature.policy'].get('assistant.activation') == 'self'
        for user in self:
            user.ai_assistant_self_service = value

    @api.model
    def _ai_default_assistant_active(self):
        # Self activation: on by default while a seat is free, so new users
        # keep the behaviour from before activation existed. Admin
        # activation: an administrator turns each user on.
        Policy = self.env['ai.feature.policy']
        if Policy.get('assistant.activation') != 'self':
            return False
        limit = Policy.get('assistant.max_users')
        return not limit or self._ai_seats_used() < limit

    @api.model
    def _ai_seats_used(self):
        # sudo: a seat count over every internal user, not only readable ones.
        return self.sudo().search_count([
            ('share', '=', False), ('ai_assistant_active', '=', True)])

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        Policy = self.env['ai.feature.policy']
        default_on = Policy.get('assistant.activation') == 'self'
        limit = Policy.get('assistant.max_users')
        # Seats left are counted once for the whole batch: an import of N
        # users with fewer free seats leaves the overflow rows switched off
        # instead of failing the seat constraint.
        free = (limit - self._ai_seats_used()) if limit else None
        for vals in vals_list:
            if 'ai_assistant_active' not in vals:
                vals['ai_assistant_active'] = default_on and (free is None or free > 0)
            if vals['ai_assistant_active']:
                vals.setdefault('ai_assistant_activated_on', now)
                if free is not None:
                    free -= 1
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('ai_assistant_active') and 'ai_assistant_activated_on' not in vals:
            # sudo: the activation date is not self-writeable on purpose (a
            # user could back-date their seat rank); the flag write above
            # already passed the access checks.
            self.sudo().write({'ai_assistant_activated_on': fields.Datetime.now()})
        return res

    @api.constrains('ai_assistant_active', 'share', 'active')
    def _check_ai_assistant_seats(self):
        if self.env.context.get('install_mode') or self.env.context.get('module'):
            return
        if not any(u.ai_assistant_active and not u.share and u.active for u in self):
            return
        limit = self.env['ai.feature.policy'].get('assistant.max_users')
        if limit and self._ai_seats_used() > limit:
            raise ValidationError(_(
                'All %(limit)s Ghaima AI seats are in use. Turn the assistant off '
                'for another user first, or raise the number of seats.', limit=limit))

    def _ai_seat_holder_ids(self):
        """Ids of active users within the seat limit, or None when unlimited.
        After a downgrade the earliest activations keep working."""
        limit = self.env['ai.feature.policy'].get('assistant.max_users')
        if not limit:
            return None
        # sudo: seat ranking needs every internal user, see _ai_seats_used.
        return set(self.sudo().search(
            [('share', '=', False), ('ai_assistant_active', '=', True)],
            order='ai_assistant_activated_on asc nulls first, id asc', limit=limit).ids)

    def _ai_assistant_block_reason(self):
        """Why this user may not use the assistant now, or '' when allowed."""
        self.ensure_one()
        Policy = self.env['ai.feature.policy']
        if Policy.get('kill'):
            return 'killed'
        if not Policy.get('assistant.enabled'):
            return 'disabled'
        if self.id == 1 or self._is_superuser():
            return ''  # OdooBot / cron: background runs are not a seat
        if self.share or not self.ai_assistant_active:
            return 'inactive'
        holders = self._ai_seat_holder_ids()
        if holders is not None and self.id not in holders:
            return 'no_seat'
        return ''

    def _ai_assistant_allowed(self):
        return not self._ai_assistant_block_reason()

    def _ai_plan_allows(self, what):
        """False only when the central plan explicitly withholds ``what``."""
        from odoo.addons.ab_ai_agent.services.llm_adapter import gateway_policy
        return gateway_policy(self.env).get(what) is not False

    def _ai_assistant_info(self):
        """Assistant flags for the web client (company settings AND the
        user's own preference)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()

        def flag(key, default='True'):
            return str(icp.get_param(key, default)).lower() in ('true', '1', 'yes')

        Policy = self.env['ai.feature.policy']
        allowed = self._ai_assistant_allowed()
        return {
            'enabled': allowed,
            'proactive': (self.ai_proactive_mode
                          if flag('ab_ai_agent.proactive_enabled') else 'off'),
            'voice': allowed and Policy.get('assistant.voice') and self._ai_plan_allows('voice'),
            'stt': icp.get_param('ab_ai_agent.stt_provider', 'browser'),
            'tts': icp.get_param('ab_ai_agent.tts_provider', 'browser'),
            'autoplay': bool(self.ai_voice_autoplay),
            'cursor': bool(self.ai_cursor_animation),
            'conversation': flag('ab_ai_agent.voice_conversation', 'False'),
            'voice_confirm': flag('ab_ai_agent.voice_confirm', 'False'),
            'briefing': (self._ai_briefing() if flag('ab_ai_agent.daily_briefing', 'False')
                         and self.ai_proactive_mode != 'off' else ''),
        }

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['ai_proactive_mode', 'ai_voice_autoplay',
                                                'ai_cursor_animation', 'ai_assistant_active',
                                                'ai_assistant_self_service']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        extra = ['ai_proactive_mode', 'ai_voice_autoplay', 'ai_cursor_animation']
        if self.env['ai.feature.policy'].get('assistant.activation') == 'self':
            extra.append('ai_assistant_active')
        return super().SELF_WRITEABLE_FIELDS + extra
