# -*- coding: utf-8 -*-
"""Agent actions — the assistant can DO things, within the user's rights.

Tools: act_on_record, create_record, update_record, post_message,
schedule_activity. Every one is two-phase, exactly like record_action:

  1. called by the model it only *proposes*: it resolves the record, checks
     the user's access, validates every field, and records an
     ai.agent.pending.action whose Confirm / Cancel chips the user sees;
  2. the user's click re-enters the same function with ``_ai_confirmed``
     (stripped from model arguments by the dispatcher) and the change runs
     AS THE USER — ACL, record rules and Odoo's business checks decide.

Field values from the model are never trusted: only stored, readable,
writable fields; many2one values are resolved by name and must match one
record the user can read; selections must be valid keys.
"""
from __future__ import annotations

import logging
from datetime import date

from odoo import fields as ofields
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

FORBIDDEN_FIELDS = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
                    'message_ids', 'activity_ids', 'access_token',
                    'password', 'groups_id'}
LINE_FIELDS = ('order_line', 'invoice_line_ids', 'move_ids_without_package')

# Fields the assistant may never set on financial / payroll documents:
# a draft is the whole safety model, so state and anything that makes a
# record look already-posted stays out of reach whatever the model sends.
DRAFT_GUARD = {
    # auto_post* would let Odoo's autopost cron post the draft as superuser.
    'account.move': {'state', 'posted_before', 'name', 'payment_state',
                     'auto_post', 'auto_post_until', 'auto_post_origin_id', 'checked'},
    'account.payment': {'state'},
    'hr.payslip': {'state'},
}
INVOICE_TYPES = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund')
# Required in the schema but filled by create() itself (resource.mixin…).
AUTO_FILLED = {'resource_id'}


# ── Resolution helpers ─────────────────────────────────────────────────

def _model(env, name):
    from .tool_dispatcher import _resolve_model
    screen = env.context.get('ai_screen') or {}
    model = _resolve_model(env, name) if name else screen.get('model')
    Model = env.get(model) if model else None
    return model, Model


def _record(env, Model, ref):
    """One record the user can read, by id, exact name/reference, or the
    record open on screen. Returns (record, error)."""
    screen = env.context.get('ai_screen') or {}
    if ref in (None, '', False) and screen.get('model') == Model._name:
        ref = screen.get('res_id')
    if ref in (None, '', False):
        return None, 'which record? give its number or name'
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        rec = Model.browse(int(ref)).exists()
        return (rec, None) if rec else (None, 'record not found')
    name = str(ref).strip()
    fields_ = [f for f in ('name', 'display_name', 'ref', 'client_order_ref', 'default_code')
               if f in Model._fields and Model._fields[f].store]
    for f in fields_:
        found = Model.search([(f, '=ilike', name)], limit=2)
        if len(found) == 1:
            return found, None
        if len(found) > 1:
            return None, f'more than one record is called "{name}"; ask which one'
    hits = Model.name_search(name, limit=3)
    if len(hits) == 1:
        return Model.browse(hits[0][0]), None
    if len(hits) > 1:
        return None, (f'several records match "{name}": '
                      + ', '.join(h[1] for h in hits) + '; ask which one')
    return None, f'no record matches "{name}"'


def _m2o(env, comodel, value):
    """A many2one value → id of the single readable record it names."""
    Co = env[comodel]
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        rec = Co.browse(int(value)).exists()
        return (rec.id, None) if rec else (None, f'{comodel} {value} not found')
    rec, err = _record(env, Co, value)
    return (rec.id, None) if rec else (None, err)


def _own_company(env, company_id):
    return company_id in env.user.company_ids.ids


def _invoice_tax(env, tax, move_type):
    """Tax named on an invoice line, restricted to the document's side.

    A KSA chart has a sale AND a purchase "VAT 15%"; a customer invoice
    must never pick the purchase one (VAT return / ZATCA mismatch).
    """
    use = 'purchase' if move_type in ('in_invoice', 'in_refund') else 'sale'
    dom = [('type_tax_use', '=', use), ('active', '=', True),
           ('company_id', 'in', env.companies.ids)]
    Tax = env['account.tax']
    if isinstance(tax, int) or (isinstance(tax, str) and tax.isdigit()):
        rec = Tax.search(dom + [('id', '=', int(tax))], limit=1)
        return (rec.id, None) if rec else (None, f'no {use} tax {tax}')
    text = str(tax).strip()
    hits = Tax.search(dom + [('name', 'ilike', text)])
    if not hits:
        num = text.replace('%', '').replace('٪', '').strip()
        try:
            hits = Tax.search(dom + [('amount', '=', float(num)), ('amount_type', '=', 'percent')])
        except ValueError:
            pass
    if len(hits) == 1:
        return hits.id, None
    if not hits:
        return None, f'no {use} tax matches "{text}"'
    return None, 'which one? ' + ', '.join(hits.mapped('display_name')[:8])


def _values(env, Model, values):
    """Validated vals + human preview lines, or (None, error)."""
    if isinstance(values, str):
        # Free-form objects travel to Gemini as a JSON string.
        import json
        try:
            values = json.loads(values or '{}')
        except ValueError:
            return None, None, 'values must be a JSON object of field: value'
    if not isinstance(values, dict):
        return None, None, 'values must be an object of field: value'
    info = Model.fields_get(attributes=['type', 'string', 'readonly', 'store',
                                        'relation', 'selection'])
    vals, preview = {}, []
    guarded = DRAFT_GUARD.get(Model._name, set())
    for key, raw in values.items():
        if key in FORBIDDEN_FIELDS or key in guarded or key not in info:
            return None, None, f'field "{key}" cannot be set here'
        meta = info[key]
        if not meta.get('store') or meta['type'] in ('one2many', 'many2many', 'binary'):
            return None, None, f'field "{key}" cannot be set here'
        t = meta['type']
        if t == 'many2one':
            val, err = _m2o(env, meta['relation'], raw)
            if err:
                return None, None, f'{meta["string"]}: {err}'
            if key == 'company_id' and not _own_company(env, val):
                return None, None, f'{meta["string"]}: not one of your companies'
            shown = env[meta['relation']].browse(val).display_name
        elif t == 'selection':
            keys = dict(meta.get('selection') or [])
            match = next((k for k, lbl in keys.items()
                          if str(raw).lower() in (str(k).lower(), str(lbl).lower())), None)
            if match is None:
                return None, None, f'{meta["string"]}: "{raw}" is not a valid choice'
            val, shown = match, keys[match]
        elif t in ('date', 'datetime'):
            try:
                val = ofields.Date.to_date(raw) if t == 'date' else ofields.Datetime.to_datetime(raw)
            except Exception:
                return None, None, f'{meta["string"]}: "{raw}" is not a date'
            shown = str(val)
        elif t in ('integer', 'float', 'monetary'):
            try:
                val = float(raw) if t != 'integer' else int(raw)
            except (TypeError, ValueError):
                return None, None, f'{meta["string"]}: "{raw}" is not a number'
            shown = str(val)
        elif t == 'boolean':
            val = str(raw).lower() in ('1', 'true', 'yes', 'نعم')
            shown = str(val)
        else:
            val, shown = str(raw), str(raw)
        vals[key] = val
        preview.append(f'{meta["string"]}: {shown}')
    return vals, preview, None


def _lines(env, Model, lines, move_type=None):
    """[{product, quantity, price}] → (line field, one2many commands, preview, error)."""
    field = next((f for f in LINE_FIELDS if f in Model._fields), None)
    if not lines:
        return None, [], [], None
    if not field:
        return None, [], [], 'this kind of record has no lines'
    Product = env['product.product']
    cmds, preview = [], []
    for ln in lines if isinstance(lines, list) else []:
        prod, err = _record(env, Product, (ln or {}).get('product'))
        if err:
            return None, [], [], f'product: {err}'
        try:
            qty = float((ln or {}).get('quantity') or 1)
        except (TypeError, ValueError):
            return None, [], [], 'quantity must be a number'
        qty_field = {'sale.order': 'product_uom_qty', 'purchase.order': 'product_qty'}.get(
            Model._name, 'quantity')
        vals = {'product_id': prod.id, qty_field: qty}
        if (ln or {}).get('price') not in (None, ''):
            try:
                vals['price_unit'] = float(ln['price'])
            except (TypeError, ValueError):
                return None, [], [], 'price must be a number'
        tax = (ln or {}).get('tax')
        if tax not in (None, '', False) and Model._name == 'account.move':
            tax_id, err = _invoice_tax(env, tax, move_type)
            if err:
                return None, [], [], f'tax: {err}'
            vals['tax_ids'] = [(6, 0, [tax_id])]
        cmds.append((0, 0, vals))
        preview.append(f'• {prod.display_name} × {qty:g}'
                       + (f' @ {vals["price_unit"]:g}' if 'price_unit' in vals else ''))
    if not cmds:
        return None, [], [], 'no valid lines'
    return field, cmds, preview, None


def _form_action(rec):
    return {'type': 'ir.actions.act_window', 'res_model': rec._name, 'res_id': rec.id,
            'views': [[False, 'form']], 'view_mode': 'form', 'target': 'current'}


def _propose(env, tool, args, target, summary, details):
    proposal = env['ai.agent.pending.action'].propose(tool, args, target=target, summary=summary,
                                                      details=details)
    proposal.update({
        'message': summary + ('\n' + '\n'.join(details) if details else '')
                   + '\nNothing has changed yet: the user must press Confirm.',
    })
    if target:
        proposal['action'] = _form_action(target)
    return proposal


def _run(fn, label, rec=None):
    """Execute a confirmed change; business errors are for users."""
    try:
        return fn()
    except UserError as e:
        return {'error': f'{label}: {e}'}
    except AccessError:
        return {'error': f'{label}: not permitted for this user'}
    except Exception:
        _logger.exception('agent action %s failed', label)
        return {'error': f'{label} could not be completed.'}


# ── Tools ──────────────────────────────────────────────────────────────

def act_on_record(env, agent=None, model=None, record=None, button=None,
                  _ai_confirmed=False, **_kw):
    """Press a button on ANY record the user can open (not only the one on
    screen): "approve Ahmed's leave", "confirm SO00045", "send quotation
    S00012". Delegates to screen_button, which only accepts buttons the
    user's own form view shows."""
    from .tool_dispatcher import _builtin_screen_button
    model, Model = _model(env, model)
    if Model is None:
        return {'error': 'unknown kind of record'}
    from .generic_data import model_blocked
    blocked = model_blocked(env, model, write=True)
    if blocked:
        return {'error': 'not permitted', 'note': blocked}
    rec, err = _record(env, Model, record or _kw.get('record_id') or _kw.get('id'))
    if err:
        return {'error': err}
    return _builtin_screen_button(env, model=model, record_id=rec.id,
                                  button=button or _kw.get('button_name') or _kw.get('action'),
                                  _ai_confirmed=_ai_confirmed)


def _spec_values(env, Model, values):
    """Resolve the fields a command spec knows (``ai.command.mixin``).

    Chat and slash commands then read names the same way: a customer is
    looked up among customers, "next Sunday" / "3/8/26" parse as dates,
    "Sales" finds the one department. Returns ``(vals, preview,
    remaining, spec, questions)``; ``remaining`` goes through the generic
    validator.
    """
    if not hasattr(Model, '_ai_command_spec') or not isinstance(values, dict):
        return {}, [], values, {}, []
    ctx = {}
    if Model._name == 'account.move' and values.get('move_type') in INVOICE_TYPES:
        ctx['ai_command_move_type'] = values['move_type']
    Model = Model.with_context(**ctx)
    spec = Model._ai_command_spec() or {}
    handled = {f: raw for f, raw in values.items()
               if f in spec and spec[f].get('resolver') in ('partner', 'date', 'many2one')
               and raw not in (None, '', False) and not isinstance(raw, int)}
    if not handled:
        return {}, [], values, spec, []
    resolved, questions = Model._ai_command_resolve(handled)
    questions = [q for q in questions if q.get('kind') not in ('missing', 'confirm')]
    # A partner that exists but was never sold to / bought from is still
    # the one the user named: the chat path accepts the single readable
    # match rather than asking "is this a customer?".
    for q in list(questions):
        if q.get('kind') == 'partner' and not q.get('options') and q['field'] in handled:
            pid, err = _m2o(env, 'res.partner', handled[q['field']])
            if not err:
                resolved[q['field']] = pid
                questions.remove(q)
    meta = Model.fields_get(list(resolved))
    vals, preview = {}, []
    for f, v in resolved.items():
        vals[f] = v
        fmeta = meta.get(f) or {}
        if fmeta.get('type') == 'many2one' and isinstance(v, int):
            shown = env[fmeta['relation']].browse(v).display_name
        else:
            shown = str(v)
        preview.append(f'{fmeta.get("string") or f}: {shown}')
    remaining = {f: raw for f, raw in values.items() if f not in handled}
    return vals, preview, remaining, spec, questions


def _required_missing(env, Model, vals, spec=None, line_field=None):
    """Required fields still empty after the user's values and Odoo's
    defaults — asked BEFORE a card is shown, never discovered as a NOT
    NULL error after the user pressed Confirm. Returns ``(missing,
    defaults)``."""
    info = Model.fields_get(attributes=['type', 'string', 'required', 'selection', 'relation'])
    inherits_links = set(Model._inherits.values())
    candidates = []
    for name, meta in info.items():
        field = Model._fields.get(name)
        if not field or not meta.get('required') or name in inherits_links:
            continue
        if field.compute and not field.inherited:
            continue                       # stored compute fills it
        if field.related and not field.inherited:
            continue
        if field.type in ('one2many', 'many2many', 'boolean') or name in FORBIDDEN_FIELDS \
                or name in AUTO_FILLED:
            continue
        candidates.append(name)
    for name, rule in (spec or {}).items():
        if rule.get('required') and name in info and name not in candidates \
                and rule.get('resolver') != 'product_lines':
            candidates.append(name)
    if Model._name == 'account.move' and vals.get('move_type') in INVOICE_TYPES \
            and 'partner_id' not in candidates:
        candidates.append('partner_id')
    try:
        defaults = Model.default_get(list(info)) if info else {}
    except Exception:
        _logger.info('default_get failed on %s', Model._name, exc_info=True)
        defaults = {}
    missing = []
    for name in candidates:
        if name == line_field or vals.get(name) not in (None, False, '') \
                or defaults.get(name) not in (None, False, ''):
            continue
        meta = info[name]
        item = {'field': name, 'label': meta.get('string') or name, 'type': meta.get('type')}
        if meta.get('selection'):
            item['selection'] = [lbl for _k, lbl in meta['selection']]
        missing.append(item)
    return missing, {k: v for k, v in defaults.items() if k in info}


def _default_preview(env, Model, vals, defaults, limit=4):
    """The defaults the user will get, shown on the card and marked."""
    out = []
    info = Model.fields_get(list(defaults), attributes=['type', 'string', 'relation',
                                                        'required', 'selection'])
    keyish = {'journal_id', 'company_id', 'currency_id', 'move_type', 'date', 'invoice_date',
              'department_id', 'user_id', 'pricelist_id', 'resource_calendar_id'}
    for name, value in defaults.items():
        meta = info.get(name) or {}
        if name in vals or value in (None, False, '') or meta.get('type') in (
                'one2many', 'many2many', 'boolean', 'binary', 'html', 'text'):
            continue
        if name == 'state' or not (name in keyish or (
                meta.get('required') and meta.get('type') == 'many2one')):
            continue
        if meta.get('type') == 'many2one':
            rid = value[0] if isinstance(value, (list, tuple)) else value
            shown = env[meta['relation']].browse(rid).display_name
        elif meta.get('type') == 'selection':
            shown = dict(meta.get('selection') or []).get(value, value)
        else:
            shown = value
        out.append(f'{meta.get("string") or name}: {shown} ({env._("default")})')
        if len(out) >= limit:
            break
    return out


def record_url(rec):
    """Shareable link to a record in the Odoo 18 web client."""
    return f'/odoo/{rec._name}/{rec.id}'


def create_record(env, agent=None, model=None, values=None, lines=None,
                  _ai_confirmed=False, **_kw):
    """Create a record (quotation, RFQ, lead, task, leave request, contact…).

    Before anything is proposed: values the command spec knows are
    resolved like a slash command would; Odoo's defaults are merged; the
    required fields still empty come back as ONE ``need_info`` question
    instead of a card that would fail after Confirm.
    """
    model, Model = _model(env, model)
    if Model is None:
        return {'error': 'unknown kind of record'}
    from .generic_data import model_blocked
    blocked = model_blocked(env, model, write=True)
    if blocked:
        return {'error': 'not permitted', 'note': blocked}
    if not Model.has_access('create'):
        return {'error': 'not permitted', 'note': 'The user cannot create these records.'}
    if isinstance(values, str):
        import json
        try:
            values = json.loads(values or '{}')
        except ValueError:
            return {'error': 'values must be a JSON object of field: value'}
    values = values or {}
    guarded = DRAFT_GUARD.get(Model._name, set()) & set(values if isinstance(values, dict) else ())
    if guarded:
        return {'error': f'field "{sorted(guarded)[0]}" cannot be set here',
                'note': 'Documents are created as drafts; the user posts them.'}
    spec_vals, spec_preview, rest, spec, questions = _spec_values(env, Model, values)
    if questions:
        return {'status': 'need_info', 'questions': questions,
                'note': ('Nothing was proposed. Ask the user ONE short question covering '
                         'every item, offering the options verbatim. Never pick for them.')}
    # Spec-resolved values skip _values(); hold them to the same rules.
    guarded_all = DRAFT_GUARD.get(Model._name, set())
    for key, val in spec_vals.items():
        if key in FORBIDDEN_FIELDS or key in guarded_all:
            return {'error': f'field "{key}" cannot be set here'}
        if key == 'company_id' and not _own_company(env, val):
            return {'error': 'company: not one of your companies'}
    vals, preview, err = _values(env, Model, rest or {})
    if err:
        return {'error': err}
    vals.update(spec_vals)
    preview = spec_preview + preview
    line_field, cmds, line_preview, err = _lines(env, Model, lines, move_type=vals.get('move_type'))
    if err:
        return {'error': err}
    missing, defaults = _required_missing(env, Model, vals, spec, line_field)
    if missing:
        return {'status': 'need_info', 'missing': missing,
                'note': ('Nothing was proposed. Ask the user for ALL of these in ONE short '
                         'question, using the labels, then call create_record again with '
                         'the same values plus the answers.')}
    if line_field:
        vals[line_field] = cmds
    title = env['ir.model']._get(model).name or model
    if Model._name == 'account.move' and vals.get('move_type'):
        # "Journal Entry" is the model's name; the user asked for an invoice.
        title = dict(Model._fields['move_type']._description_selection(env)).get(
            vals['move_type'], title)
    if not _ai_confirmed:
        return _propose(env, 'create_record', {'model': model, 'values': values,
                                               'lines': lines or []},
                        None, env._('Create %(what)s?', what=title),
                        preview + line_preview + _default_preview(env, Model, vals, defaults))

    def do():
        with env.cr.savepoint():
            rec = Model.create(vals)
            if Model._name in DRAFT_GUARD and 'state' in rec._fields \
                    and rec.state not in ('draft', False) \
                    or ('auto_post' in rec._fields and rec.auto_post not in ('no', False)):
                # Raising inside the savepoint undoes the create.
                raise UserError(env._('The record was not left as a draft; nothing was saved.'))
        url = record_url(rec)
        return {'message': env._('%(what)s created: %(name)s', what=title, name=rec.display_name)
                + f'\n{url}',
                'done': True, 'url': url, 'action': _form_action(rec)}
    return _run(do, title)


def update_record(env, agent=None, model=None, record=None, values=None,
                  _ai_confirmed=False, **_kw):
    """Change fields on one record: "set the delivery date of S00012 to 5 Oct"."""
    model, Model = _model(env, model)
    if Model is None:
        return {'error': 'unknown kind of record'}
    from .generic_data import model_blocked
    blocked = model_blocked(env, model, write=True)
    if blocked:
        return {'error': 'not permitted', 'note': blocked}
    rec, err = _record(env, Model, record or _kw.get('record_id'))
    if err:
        return {'error': err}
    try:
        rec.check_access('write')
    except AccessError:
        return {'error': 'not permitted', 'note': 'The user cannot edit this record.'}
    vals, preview, err = _values(env, Model, values or {})
    if err or not vals:
        return {'error': err or 'nothing to change'}
    if not _ai_confirmed:
        return _propose(env, 'update_record', {'model': model, 'record': rec.id, 'values': values},
                        rec, env._('Update %(name)s?', name=rec.display_name), preview)
    def do():
        rec.write(vals)
        return {'message': env._('%(name)s updated.', name=rec.display_name), 'done': True,
                'action': _form_action(rec)}
    return _run(do, rec.display_name, rec)


def post_message(env, agent=None, model=None, record=None, body=None,
                 send_to_customer=False, _ai_confirmed=False, **_kw):
    """Log a note, or send a message by email to the record's contact."""
    model, Model = _model(env, model)
    if Model is None or 'message_post' not in dir(Model):
        return {'error': 'these records have no messages'}
    rec, err = _record(env, Model, record or _kw.get('record_id'))
    if err:
        return {'error': err}
    body = (body or '').strip()
    if not body:
        return {'error': 'message text required'}
    partner = rec.partner_id if send_to_customer and 'partner_id' in rec._fields else None
    if send_to_customer and not partner:
        return {'error': 'this record has no contact to send to'}
    if not _ai_confirmed:
        what = (env._('Send to %(who)s by email?', who=partner.display_name) if partner
                else env._('Log a note on %(name)s?', name=rec.display_name))
        return _propose(env, 'post_message', {'model': model, 'record': rec.id, 'body': body,
                                              'send_to_customer': bool(partner)},
                        rec, what, [body[:500]])
    def do():
        rec.check_access('read')
        if partner:
            rec.message_post(body=body, partner_ids=partner.ids, message_type='comment',
                             subtype_xmlid='mail.mt_comment')
        else:
            rec.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')
        return {'message': env._('Done.'), 'done': True, 'action': _form_action(rec)}
    return _run(do, rec.display_name, rec)


def schedule_activity(env, agent=None, model=None, record=None, summary=None,
                      date_deadline=None, assign_to=None, _ai_confirmed=False, **_kw):
    """Schedule a to-do on a record, for the user or a colleague."""
    model, Model = _model(env, model)
    if Model is None or 'activity_schedule' not in dir(Model):
        return {'error': 'activities are not available on these records'}
    rec, err = _record(env, Model, record or _kw.get('record_id'))
    if err:
        return {'error': err}
    try:
        deadline = ofields.Date.to_date(date_deadline) if date_deadline else ofields.Date.context_today(rec)
    except Exception:
        return {'error': f'"{date_deadline}" is not a date'}
    user = env.user
    if assign_to:
        uid, err = _m2o(env, 'res.users', assign_to)
        if err:
            return {'error': f'assignee: {err}'}
        user = env['res.users'].browse(uid)
    text = (summary or '').strip() or env._('Follow up')
    if not _ai_confirmed:
        return _propose(env, 'schedule_activity',
                        {'model': model, 'record': rec.id, 'summary': text,
                         'date_deadline': str(deadline), 'assign_to': user.id},
                        rec, env._('Schedule "%(what)s" for %(who)s on %(when)s?',
                                   what=text, who=user.name, when=deadline), [])
    def do():
        rec.activity_schedule('mail.mail_activity_data_todo', date_deadline=deadline,
                              summary=text, user_id=user.id)
        return {'message': env._('Activity scheduled.'), 'done': True, 'action': _form_action(rec)}
    return _run(do, rec.display_name, rec)


TOOLS = {
    'act_on_record': act_on_record,
    'create_record': create_record,
    'update_record': update_record,
    'post_message': post_message,
    'schedule_activity': schedule_activity,
}
