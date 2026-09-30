# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

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

    def _ai_assistant_info(self):
        """Assistant flags for the web client (company settings AND the
        user's own preference)."""
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()

        def flag(key, default='True'):
            return str(icp.get_param(key, default)).lower() in ('true', '1', 'yes')

        return {
            'enabled': flag('ab_ai_agent.assistant_enabled'),
            'proactive': (self.ai_proactive_mode
                          if flag('ab_ai_agent.proactive_enabled') else 'off'),
            'voice': flag('ab_ai_agent.voice_enabled'),
            'stt': icp.get_param('ab_ai_agent.stt_provider', 'browser'),
            'tts': icp.get_param('ab_ai_agent.tts_provider', 'browser'),
            'autoplay': bool(self.ai_voice_autoplay),
            'conversation': flag('ab_ai_agent.voice_conversation', 'False'),
            'briefing': (self._ai_briefing() if flag('ab_ai_agent.daily_briefing', 'False')
                         and self.ai_proactive_mode != 'off' else ''),
        }

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['ai_proactive_mode', 'ai_voice_autoplay']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['ai_proactive_mode', 'ai_voice_autoplay']
