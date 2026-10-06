# -*- coding: utf-8 -*-
"""``create_journal_entry`` — a sentence becomes a balanced DRAFT entry.

Two-phase like every agent action: called by the model it resolves each
account as the user, checks the entry balances in the company currency
and records an ``ai.agent.pending.action``; the user's Confirm re-enters
with ``_ai_confirmed`` and creates ``move_type='entry'`` as the user.
``action_post`` is never called.
"""
from __future__ import annotations

import logging
import re

from odoo import fields as ofields
from odoo.tools import float_compare, float_is_zero

from odoo.addons.ab_ai_agent.services import agent_actions, tool_dispatcher

_logger = logging.getLogger(__name__)

_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def _amount(raw):
    """5000 / "5,000 SAR" / "٥٠٠٠" → float; None when absent."""
    if raw in (None, '', False):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).translate(_DIGITS).replace('٫', '.').replace('٬', '').replace(',', '')
    m = re.search(r'-?\d+(?:\.\d+)?', text)
    return float(m.group()) if m else None


def _account_domain(env):
    Account = env['account.account']
    dom = [('deprecated', '=', False)] if 'deprecated' in Account._fields else []
    if 'company_ids' in Account._fields:
        return dom + [('company_ids', 'in', env.company.ids)]
    return dom + [('company_id', '=', env.company.id)]


def _resolve_account_in(env, text, fuzzy):
    """One pass in env.lang. Returns (account, options) — both empty on a miss.
    Exact tiers (code, name, bank/cash journal) run for every language
    before any fuzzy pass, so "Bank" finds the Bank journal's account
    rather than "Bank Suspense Account"."""
    Account = env['account.account']
    base = _account_domain(env)
    if text.isdigit():
        found = Account.search(base + [('code', '=', text)], limit=2)
        if len(found) != 1:
            found = Account.search(base + [('code', '=like', text + '%')], limit=6)
        return (found, Account.browse()) if len(found) == 1 else (None, found)
    if fuzzy:
        found = Account.search(base + ['|', ('name', 'ilike', text),
                                       ('code', '=like', text + '%')], limit=6)
        return (found, Account.browse()) if len(found) == 1 else (None, found)
    found = Account.search(base + [('name', '=ilike', text)], limit=2)
    if len(found) == 1:
        return found, Account.browse()
    # "from the bank" / "من الصندوق": a bank or cash journal named so.
    journals = env['account.journal'].search([
        ('company_id', '=', env.company.id), ('type', 'in', ('bank', 'cash')),
        ('name', '=ilike', text)], limit=2)
    if len(journals) == 1 and journals.default_account_id:
        return journals.default_account_id, Account.browse()
    return None, found if len(found) > 1 else Account.browse()


def resolve_account(env, text):
    """Code, code prefix, name, or bank/cash journal → one account.

    Names are tried in the user's language, then in English: an Arabic
    user typing "Rent" or an English one typing "إيجار" both land.
    Returns ``(account, options, note)``; several hits are a question.
    """
    text = str(text or '').strip().translate(_DIGITS)
    if not text:
        return None, [], env._('Account is missing.')
    options = env['account.account']
    langs = list(dict.fromkeys([env.lang or 'en_US', 'en_US', 'ar_001']))
    for fuzzy, lang in [(False, lg) for lg in langs] + [(True, lg) for lg in langs]:
        account, found = _resolve_account_in(env(context=dict(env.context, lang=lang)), text,
                                             fuzzy)
        if account:
            return account.with_env(env), [], ''
        if found and not options:
            options = found
    if options:
        return None, [{'id': a.id, 'name': a.with_env(env).display_name} for a in options], \
            env._('Several accounts match "%s". Which one?', text)
    return None, [], env._('No account matches "%s".', text)


def _journal(env, text):
    Journal = env['account.journal']
    if isinstance(text, int):
        found = Journal.search([('id', '=', text), ('company_id', '=', env.company.id)])
        return (found, None) if found else (None, env._('Journal not found.'))
    if text:
        found = Journal.search([('company_id', '=', env.company.id), '|',
                                ('name', '=ilike', text), ('code', '=ilike', text)], limit=2)
        if len(found) == 1:
            return found, None
        return None, env._('No single journal called "%s".', text)
    found = Journal.search([('company_id', '=', env.company.id), ('type', '=', 'general')],
                           order='sequence, id', limit=1)
    return (found, None) if found else (None, env._('There is no general journal.'))


def create_journal_entry(env, agent=None, lines=None, date=None, journal=None, ref=None,
                         _ai_confirmed=False, **_kw):
    Move = env['account.move']
    if not Move.has_access('create'):
        return {'error': 'not permitted', 'note': 'The user cannot create journal entries.'}
    if isinstance(lines, str):
        import json
        try:
            lines = json.loads(lines)
        except ValueError:
            return {'error': 'lines must be a list of {account, debit, credit}'}
    if not isinstance(lines, list) or len(lines) < 2:
        return {'status': 'need_info',
                'missing': [{'field': 'lines', 'label': env._('Debit and credit accounts')}],
                'note': 'An entry needs at least two lines. Ask which account is debited '
                        'and which is credited, in ONE question.'}
    currency = env.company.currency_id
    rounding = currency.rounding
    questions, cmds, rows = [], [], []
    total_d = total_c = 0.0
    for idx, ln in enumerate(lines, 1):
        ln = ln or {}
        account, options, note = resolve_account(env, ln.get('account'))
        if not account:
            questions.append({'line': idx, 'field': 'account', 'query': ln.get('account'),
                              'message': note, 'options': options})
            continue
        debit, credit = _amount(ln.get('debit')) or 0.0, _amount(ln.get('credit')) or 0.0
        if debit < 0 or credit < 0 or (debit and credit) or \
                (float_is_zero(debit, precision_rounding=rounding)
                 and float_is_zero(credit, precision_rounding=rounding)):
            questions.append({'line': idx, 'field': 'amount', 'query': account.display_name,
                              'message': env._('Line %s needs either a debit or a credit amount.',
                                               idx), 'options': []})
            continue
        vals = {'account_id': account.id, 'debit': currency.round(debit),
                'credit': currency.round(credit)}
        if ln.get('label'):
            vals['name'] = str(ln['label'])[:250]
        if ln.get('partner'):
            pid, err = agent_actions._m2o(env, 'res.partner', ln['partner'])
            if err:
                questions.append({'line': idx, 'field': 'partner', 'query': ln['partner'],
                                  'message': err, 'options': []})
                continue
            vals['partner_id'] = pid
        total_d += vals['debit']
        total_c += vals['credit']
        cmds.append((0, 0, vals))
        rows.append(f'{account.display_name} | {vals["debit"]:,.2f} | {vals["credit"]:,.2f}')
    if questions:
        return {'status': 'need_info', 'questions': questions,
                'note': 'Nothing was proposed. Ask ALL of these in ONE short message; '
                        'offer the options verbatim and never pick for the user.'}
    if float_compare(total_d, total_c, precision_rounding=rounding) != 0:
        return {'status': 'need_info',
                'missing': [{'field': 'balance',
                             'label': env._('Debits %(d)s ≠ credits %(c)s',
                                            d=f'{total_d:,.2f}', c=f'{total_c:,.2f}')}],
                'note': 'The entry does not balance. Fix the lines or ask the user which '
                        'amount is right.'}
    journal_rec, err = _journal(env, journal)
    if err:
        return {'status': 'need_info', 'missing': [{'field': 'journal', 'label': err}]}
    try:
        move_date = ofields.Date.to_date(date) if date else ofields.Date.context_today(Move)
    except Exception:
        from odoo.addons.ab_ai_command.services import resolvers
        res = resolvers.resolve_date(env, date)
        if not res['value']:
            return {'status': 'need_info', 'missing': [{'field': 'date', 'label': res['note']}]}
        move_date = res['value']
    vals = {'move_type': 'entry', 'date': move_date, 'journal_id': journal_rec.id,
            'line_ids': cmds}
    if ref:
        vals['ref'] = str(ref)[:250]

    if not _ai_confirmed:
        details = [env._('Journal: %s', journal_rec.display_name),
                   env._('Date: %s', move_date)]
        if ref:
            details.append(env._('Reference: %s', ref))
        details.append(env._('Account | Debit | Credit'))
        details += rows
        details.append(env._('Total | %(d)s | %(c)s', d=f'{total_d:,.2f}', c=f'{total_c:,.2f}'))
        details.append(env._('It will be saved as a DRAFT; nothing is posted.'))
        return agent_actions._propose(
            env, 'create_journal_entry',
            {'lines': lines, 'date': str(move_date), 'journal': journal_rec.id, 'ref': ref},
            None, env._('Create draft journal entry for %(amount)s %(cur)s?',
                        amount=f'{total_d:,.2f}', cur=currency.name),
            details)

    def do():
        with env.cr.savepoint():
            move = Move.create(vals)
            if move.state != 'draft':
                from odoo.exceptions import UserError
                raise UserError(env._('The entry was not left as a draft; nothing was saved.'))
        url = agent_actions.record_url(move)
        return {'message': env._('Draft journal entry created: %s', move.display_name)
                + f'\n{url}', 'done': True, 'url': url,
                'action': agent_actions._form_action(move)}
    return agent_actions._run(do, env._('Journal entry'))


tool_dispatcher.register('create_journal_entry', create_journal_entry)
tool_dispatcher.PROPOSAL_TOOLS.add('create_journal_entry')
