# -*- coding: utf-8 -*-
"""What the assistant knows about THIS ERP before the first question.

A nightly (and on -u) digest per company and language: installed apps,
journals, taxes, departments, job positions, the most-used products and
the required fields of the documents users create most. Structure only —
no amounts, no partners — so it is safe to share across the users of a
company, and it is byte-stable between rebuilds when nothing changed,
which is what lets it sit inside the provider's cached prompt prefix.
"""
from __future__ import annotations

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Documents users ask the assistant to create. Required fields are listed
# so the model asks for them up front instead of after a failed create.
_CORE_MODELS = ('hr.employee', 'res.partner', 'product.template', 'account.move',
                'sale.order', 'purchase.order', 'hr.leave', 'crm.lead', 'project.task')
MAX_CHARS = 9000            # ~2–3k tokens


class AiAgentKnowledgeDigest(models.Model):
    _name = 'ai.agent.knowledge.digest'
    _description = 'AI Agent ERP Knowledge Digest'
    _order = 'company_id, lang'

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade', index=True)
    lang = fields.Char(required=True, index=True)
    content = fields.Text()
    built_at = fields.Datetime()

    _sql_constraints = [('company_lang_unique', 'unique(company_id, lang)',
                         'One digest per company and language.')]

    # ── Build ──────────────────────────────────────────────────

    @api.model
    def _section(self, title, items):
        items = [i for i in items if i]
        return f'### {title}\n' + '\n'.join(f'- {i}' for i in items) if items else ''

    @api.model
    def _build_content(self, company, lang):
        # sudo + explicit company: the digest is company structure, built
        # by the cron for every user of the company. Only names/types —
        # nothing a user of the company could not see in a dropdown.
        env = self.sudo().with_company(company).with_context(lang=lang).env
        parts = ['## This ERP (structure only; query tools for live data)']

        apps = env['ir.module.module'].search([('state', '=', 'installed'),
                                               ('application', '=', True)], order='name')
        parts.append(self._section('Installed apps', [a.shortdesc for a in apps]))

        if 'account.journal' in env:
            journals = env['account.journal'].search([('company_id', '=', company.id)],
                                                     order='type, sequence, id')
            parts.append(self._section('Journals', [f'{j.name} ({j.type}, {j.code})'
                                                    for j in journals[:30]]))
            taxes = env['account.tax'].search([('company_id', '=', company.id),
                                               ('active', '=', True)], order='type_tax_use, sequence')
            parts.append(self._section('Taxes', [f'{t.name} ({t.type_tax_use})'
                                                 for t in taxes[:20]]))
            parts.append(self._section('Accounting', [
                f'Currency: {company.currency_id.name}',
                f'Fiscal year ends: {company.fiscalyear_last_day}/{company.fiscalyear_last_month}'
                if 'fiscalyear_last_month' in company._fields else '',
                f'Lock date (all users): {company.fiscalyear_lock_date}'
                if 'fiscalyear_lock_date' in company._fields and company.fiscalyear_lock_date
                else '',
            ]))
        if 'hr.department' in env:
            deps = env['hr.department'].search([('company_id', 'in', (company.id, False))],
                                               order='complete_name')
            parts.append(self._section('Departments', [d.complete_name for d in deps[:40]]))
            jobs = env['hr.job'].search([('company_id', 'in', (company.id, False))], order='name')
            parts.append(self._section('Job positions', [j.name for j in jobs[:40]]))
        if 'product.product' in env and 'sale_ok' in env['product.template']._fields:
            prods = env['product.template'].search([('sale_ok', '=', True),
                                                    ('company_id', 'in', (company.id, False))],
                                                   order='write_date desc, id', limit=25)
            parts.append(self._section('Products (sample, sellable)',
                                       sorted(p.name for p in prods)))
        req = []
        for model in _CORE_MODELS:
            if model not in env:
                continue
            Model = env[model]
            names = []
            for fname, field in sorted(Model._fields.items()):
                if field.required and field.store and not field.compute and not field.related \
                        and field.type not in ('one2many', 'many2many', 'boolean') \
                        and fname not in ('id', 'company_id', 'currency_id') \
                        and fname not in Model._inherits.values() and not fname.startswith('_'):
                    names.append(f'{field.get_description(env).get("string")} ({fname})')
            if names:
                req.append(f'{env["ir.model"]._get(model).name} [{model}]: ' + ', '.join(names))
        parts.append(self._section('Required fields when creating', req))
        text = '\n\n'.join(p for p in parts if p)
        return text[:MAX_CHARS]

    @api.model
    def _rebuild(self):
        """(Re)build every company × active language. Idempotent: a row is
        rewritten only when its text changed, so the prompt prefix — and
        the provider cache keyed on it — survives a no-op rebuild."""
        langs = [code for code, _n in self.env['res.lang'].sudo().get_installed()]
        for company in self.env['res.company'].sudo().search([]):
            for lang in langs:
                try:
                    content = self._build_content(company, lang)
                except Exception:
                    _logger.exception('knowledge digest failed for %s/%s', company.name, lang)
                    continue
                row = self.sudo().search([('company_id', '=', company.id),
                                          ('lang', '=', lang)], limit=1)
                if row and row.content == content:
                    continue
                vals = {'content': content, 'built_at': fields.Datetime.now()}
                if row:
                    row.write(vals)
                else:
                    self.sudo().create(dict(vals, company_id=company.id, lang=lang))
        return True

    @api.model
    def _cron_rebuild(self):
        return self._rebuild()

    @api.model
    def _schedule_rebuild(self):
        """Called on -u. Building right here would see a half-loaded
        registry (account / hr load after ab_ai_agent), so ask the cron
        to run as soon as the server is up instead."""
        cron = self.env.ref('ab_ai_agent.ir_cron_knowledge_digest', raise_if_not_found=False)
        if cron:
            cron._trigger()
        self.sudo().search([]).unlink()     # stale until rebuilt; prompt_block rebuilds lazily
        return True

    # Section title → group the reader must hold. The row is built once
    # per company (sudo); these sections are stripped per user so a
    # cashier never sees journal/tax/HR names their rights hide.
    _SECTION_GROUPS = {
        'Journals': 'account.group_account_readonly',
        'Taxes': 'account.group_account_readonly',
        'Accounting': 'account.group_account_readonly',
        'Departments': 'hr.group_hr_user',
        'Job positions': 'hr.group_hr_user',
    }

    @api.model
    def _filter_for_user(self, env, content):
        if not content:
            return ''
        blocks = content.split('\n\n')
        kept = []
        for block in blocks:
            title = block[4:].split('\n', 1)[0].strip() if block.startswith('### ') else ''
            group = self._SECTION_GROUPS.get(title)
            if group and not (env.ref(group, raise_if_not_found=False)
                              and env.user.has_group(group)):
                continue
            kept.append(block)
        return '\n\n'.join(kept)

    @api.model
    def prompt_block(self, env):
        """Digest for the caller's company and language, cut to their rights."""
        return self._filter_for_user(env, self._prompt_block_raw(env))

    @api.model
    def _prompt_block_raw(self, env):
        row = self.sudo().search([('company_id', '=', env.company.id),
                                  ('lang', '=', env.lang or 'en_US')], limit=1)
        if not row:
            content = self._build_content(env.company, env.lang or 'en_US')
            try:
                with self.env.cr.savepoint():
                    self.sudo().create({'company_id': env.company.id,
                                        'lang': env.lang or 'en_US', 'content': content,
                                        'built_at': fields.Datetime.now()})
            except Exception:
                _logger.info('digest row not stored (concurrent build?)', exc_info=True)
            return content
        return row.content or ''
