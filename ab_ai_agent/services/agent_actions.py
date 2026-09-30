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
                    'company_id', 'message_ids', 'activity_ids', 'access_token',
                    'password', 'groups_id'}
LINE_FIELDS = ('order_line', 'invoice_line_ids', 'move_ids_without_package')


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
    for key, raw in values.items():
        if key in FORBIDDEN_FIELDS or key not in info:
            return None, None, f'field "{key}" cannot be set here'
        meta = info[key]
        if not meta.get('store') or meta['type'] in ('one2many', 'many2many', 'binary'):
            return None, None, f'field "{key}" cannot be set here'
        t = meta['type']
        if t == 'many2one':
            val, err = _m2o(env, meta['relation'], raw)
            if err:
                return None, None, f'{meta["string"]}: {err}'
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


def _lines(env, Model, lines):
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
    rec, err = _record(env, Model, record or _kw.get('record_id') or _kw.get('id'))
    if err:
        return {'error': err}
    return _builtin_screen_button(env, model=model, record_id=rec.id,
                                  button=button or _kw.get('button_name') or _kw.get('action'),
                                  _ai_confirmed=_ai_confirmed)


def create_record(env, agent=None, model=None, values=None, lines=None,
                  _ai_confirmed=False, **_kw):
    """Create a record (quotation, RFQ, lead, task, leave request, contact…)."""
    model, Model = _model(env, model)
    if Model is None:
        return {'error': 'unknown kind of record'}
    if not Model.has_access('create'):
        return {'error': 'not permitted', 'note': 'The user cannot create these records.'}
    vals, preview, err = _values(env, Model, values or {})
    if err:
        return {'error': err}
    line_field, cmds, line_preview, err = _lines(env, Model, lines)
    if err:
        return {'error': err}
    if line_field:
        vals[line_field] = cmds
    title = env['ir.model']._get(model).name or model
    if not _ai_confirmed:
        return _propose(env, 'create_record', {'model': model, 'values': values or {},
                                               'lines': lines or []},
                        None, env._('Create %(what)s?', what=title), preview + line_preview)
    def do():
        rec = Model.create(vals)
        return {'message': env._('%(what)s created: %(name)s', what=title, name=rec.display_name),
                'done': True, 'action': _form_action(rec)}
    return _run(do, title)


def update_record(env, agent=None, model=None, record=None, values=None,
                  _ai_confirmed=False, **_kw):
    """Change fields on one record: "set the delivery date of S00012 to 5 Oct"."""
    model, Model = _model(env, model)
    if Model is None:
        return {'error': 'unknown kind of record'}
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
