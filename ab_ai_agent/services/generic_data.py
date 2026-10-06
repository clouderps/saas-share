# -*- coding: utf-8 -*-
"""Generic data tools — search / count / read any business model.

These make the default assistant useful on every installed app without a
hand-written tool per model. They are deliberately NOT a privilege path:

* everything runs as the calling user (``env`` is the user's env, never
  sudo): model ACLs, record rules, multi-company and branch isolation
  decide what comes back, exactly as in the UI;
* fields come from ``fields_get`` as that user, so ``groups=`` on a field
  hides it; binary and secret-looking fields are dropped on top;
* a domain may only filter on fields the user may read (no probing a
  hidden column through a filter);
* technical / security models are refused outright (``model_blocked``);
* results are capped (rows, fields, text length).

Writes are not here: ``create_record`` / ``update_record`` (agent_actions)
already propose confirm-first changes on any model, and the builder's
create/update presets route to them.
"""
from __future__ import annotations

import json
import logging
import re
from ast import literal_eval

from odoo.exceptions import AccessError
from odoo.osv import expression

_logger = logging.getLogger(__name__)

MAX_ROWS = 50
DEFAULT_ROWS = 20
MAX_FIELDS = 20
MAX_TEXT = 300
MAX_X2MANY = 10

PRESET_OPS = ('search', 'count', 'read', 'open', 'create', 'update')
WRITE_OPS = ('create', 'update')

# Never reachable through the assistant, whoever asks: framework,
# security, AI configuration and mail plumbing.
BLOCKED_PREFIXES = ('ir.', 'base.', 'base_import.', 'bus.', 'auth_', 'auth.',
                    'res.users.', 'ai.agent', 'ai.usage', 'ai.gateway', 'web_editor.',
                    'web_tour.', 'iap.', 'fetchmail.', 'mail.mail', 'mail.notification',
                    'mail.tracking', 'mail.alias', 'mail.followers', 'mail.message',
                    'mail.render', 'mail.template', 'mail.blacklist', 'sms.', 'snailmail.',
                    'payment.provider', 'payment.token', 'saas.payment', 'gateway.')
BLOCKED_MODELS = {'res.groups', 'res.config', 'res.config.settings', 'res.config.installer',
                  'report.base.report_irmodulereference', 'res.device', 'res.device.log',
                  'publisher_warranty.contract', 'change.password.wizard'}
# Readable (with the field filter) but never written by the assistant.
READ_ONLY_MODELS = {'res.users'}
# Base settings: administrators only.
ADMIN_ONLY_MODELS = {'res.company', 'res.currency', 'res.country', 'res.lang',
                     'decimal.precision', 'uom.category'}

_SECRET = re.compile(
    r'(password|passwd|token|secret|api_?key|signature|totp|oauth|otp|_hash$|'
    r'^pin$|private_key|credential|jwt|salt|cipher|encrypted)', re.I)
_SKIP_FIELDS = {'message_ids', 'activity_ids', 'website_message_ids', 'message_follower_ids',
                'message_partner_ids', 'rating_ids', 'access_token', 'access_url',
                'access_warning', 'groups_id', '__last_update'}
_DEFAULT_PICK = ('display_name', 'name', 'state', 'partner_id', 'date', 'date_order',
                 'invoice_date', 'amount_total', 'amount_residual', 'user_id',
                 'employee_id', 'product_id', 'quantity', 'create_date')


def model_blocked(env, model, write=False):
    """Reason the assistant may not touch ``model`` (None = allowed)."""
    if not model or env.get(model) is None:
        return 'unknown model'
    Model = env[model]
    if Model._transient or Model._abstract:
        return 'technical model'
    if model in BLOCKED_MODELS or model.startswith(BLOCKED_PREFIXES):
        return 'the assistant cannot use this kind of record'
    if model in ADMIN_ONLY_MODELS and not env.user.has_group('base.group_system'):
        return 'only administrators can use this kind of record'
    if write and (model in READ_ONLY_MODELS or not Model._auto):
        return 'the assistant cannot change this kind of record'
    return None


def readable_fields(env, Model):
    """{name: meta} the user may read and the assistant may show."""
    info = Model.fields_get(attributes=['type', 'string', 'relation', 'store',
                                        'selection', 'searchable'])
    out = {}
    for name, meta in info.items():
        if name in _SKIP_FIELDS or _SECRET.search(name):
            continue
        if meta.get('type') in ('binary', 'image', 'html', 'properties',
                                'properties_definition', 'json'):
            continue
        out[name] = meta
    out.setdefault('id', {'type': 'integer', 'string': 'ID', 'store': True, 'searchable': True})
    return out


def _resolve(env, model):
    from .tool_dispatcher import _resolve_model
    screen = env.context.get('ai_screen') or {}
    name = _resolve_model(env, model) if model else screen.get('model')
    return name


def _open(env, model, write=False):
    """(Model, allowed fields, error) for the user, read access checked."""
    name = _resolve(env, model)
    if not name:
        return None, None, {'error': 'unknown kind of record',
                            'note': 'Use the technical model name (e.g. sale.order) '
                                    'or the name of the menu the user sees.'}
    why = model_blocked(env, name, write=write)
    if why:
        return None, None, {'error': 'not permitted', 'note': why}
    Model = env[name]
    if not Model.has_access('read'):
        return None, None, {'error': 'not permitted',
                            'note': 'The user cannot read these records.'}
    return Model, readable_fields(env, Model), None


def _parse(value, default):
    if value in (None, '', False):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            try:
                return literal_eval(value)
            except (ValueError, SyntaxError):
                return None
    return value


def _check_path(path, allowed, Model):
    """Every hop of a dotted path must be a field the user may read on a
    model the assistant may use; relations into blocked / unreadable
    models are refused (a count would otherwise probe them)."""
    parts = str(path).split('.')
    fields_ok, current = allowed, Model
    for i, part in enumerate(parts):
        if part not in fields_ok or part in _SKIP_FIELDS or _SECRET.search(part):
            raise ValueError(f'cannot filter on "{path}"')
        if i == len(parts) - 1:
            return
        if current is None:
            raise ValueError(f'cannot filter on "{path}"')
        comodel = fields_ok[part].get('relation')
        if not comodel:
            raise ValueError(f'cannot filter on "{path}"')
        env = current.env
        if model_blocked(env, comodel) or not env[comodel].has_access('read'):
            raise ValueError(f'cannot filter on "{path}"')
        current = env[comodel]
        fields_ok = readable_fields(env, current)


def safe_domain(domain, allowed, Model=None):
    """Validated domain or raises ValueError. Every leaf must filter on a
    path whose every hop the user may read; values are plain data.
    Without ``Model`` only plain (undotted) fields are accepted."""
    domain = _parse(domain, [])
    if domain is None or not isinstance(domain, (list, tuple)):
        raise ValueError('domain must be a list like [["state", "=", "sale"]]')
    out = []
    for el in domain:
        if isinstance(el, str):
            if el not in ('&', '|', '!'):
                raise ValueError(f'bad domain operator {el!r}')
            out.append(el)
            continue
        if not isinstance(el, (list, tuple)) or len(el) != 3:
            raise ValueError(f'bad domain leaf {el!r}')
        path, op, val = el
        _check_path(path, allowed, Model)
        if op not in expression.TERM_OPERATORS:
            raise ValueError(f'bad operator {op!r}')
        out.append((str(path), op, val))
    if out:
        expression.normalize_domain(out)   # raises on an unbalanced prefix
    return out


def _pick_fields(fields, allowed, Model):
    fields = _parse(fields, [])
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(',') if f.strip()]
    if fields:
        bad = [f for f in fields if f not in allowed]
        if bad:
            raise ValueError('unknown or hidden field(s): ' + ', '.join(map(str, bad[:5])))
        return list(dict.fromkeys(fields))[:MAX_FIELDS]
    picked = [f for f in _DEFAULT_PICK if f in allowed]
    rec = Model._rec_name
    if rec and rec in allowed and rec not in picked:
        picked.insert(1, rec)
    return picked[:MAX_FIELDS]


def _plain(value, meta):
    t = meta.get('type')
    if t == 'many2one':
        return value[1] if value else None
    if t in ('one2many', 'many2many'):
        return list(value or [])[:MAX_X2MANY]
    if t == 'selection' and value:
        return dict(meta.get('selection') or []).get(value, value)
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + '…'
    if value is False and t not in ('boolean',):
        return None
    return value


def _rows(records, names, allowed):
    data = records.read([n for n in names if n != 'display_name'] or ['id'])
    out = []
    for rec, row in zip(records, data):
        item = {'id': rec.id}
        if 'display_name' in names:
            item['display_name'] = rec.display_name
        for n in names:
            if n in ('id', 'display_name'):
                continue
            item[n] = _plain(row.get(n), allowed.get(n, {}))
        out.append(item)
    return out


def search_records(env, agent=None, model=None, domain=None, fields=None, limit=None,
                   order=None, query=None, **_kw):
    """Find records of any model the user can read (record rules apply).
    ``query`` = free text matched on the record name."""
    Model, allowed, err = _open(env, model)
    if err:
        return err
    try:
        dom = safe_domain(domain, allowed, Model)
        if query:
            rec = Model._rec_name if Model._rec_name in allowed else 'display_name'
            dom = expression.AND([dom, [(rec, 'ilike', str(query))]])
        names = _pick_fields(fields, allowed, Model)
    except ValueError as e:
        return {'error': str(e)}
    try:
        limit = max(1, min(MAX_ROWS, int(limit or DEFAULT_ROWS)))
    except (TypeError, ValueError):
        limit = DEFAULT_ROWS
    sort = None
    if order:
        parts = str(order).split()
        if parts[0] in allowed and allowed[parts[0]].get('store') \
                and (len(parts) == 1 or parts[1].lower() in ('asc', 'desc')) and len(parts) <= 2:
            sort = f'{parts[0]} {parts[1] if len(parts) > 1 else "asc"}'
    records = Model.search(dom, limit=limit, order=sort)
    total = Model.search_count(dom) if len(records) == limit else len(records)
    return {
        'model': Model._name,
        'model_label': Model._description,
        'count': len(records),
        'total': total,
        'truncated': total > len(records),
        'fields': {n: allowed[n].get('string', n) for n in names if n in allowed},
        'records': _rows(records, names, allowed),
    }


def count_records(env, agent=None, model=None, domain=None, **_kw):
    Model, allowed, err = _open(env, model)
    if err:
        return err
    try:
        dom = safe_domain(domain, allowed, Model)
    except ValueError as e:
        return {'error': str(e)}
    return {'model': Model._name, 'model_label': Model._description,
            'count': Model.search_count(dom)}


def get_record(env, agent=None, model=None, record=None, id=None, fields=None, **_kw):
    """All (or the given) readable fields of ONE record."""
    from .agent_actions import _record
    Model, allowed, err = _open(env, model)
    if err:
        return err
    rec, why = _record(env, Model, record if record not in (None, '') else id)
    if why:
        return {'error': why}
    try:
        rec.check_access('read')
    except AccessError:
        return {'error': 'not permitted', 'note': 'The user cannot open this record.'}
    try:
        if fields:
            names = _pick_fields(fields, allowed, Model)
        else:
            names = ['display_name'] + [n for n, m in allowed.items()
                                        if m.get('store') and n not in ('id',)][:MAX_FIELDS * 2]
    except ValueError as e:
        return {'error': str(e)}
    row = _rows(rec, names, allowed)[0]
    return {'model': Model._name, 'model_label': Model._description,
            'fields': {n: allowed[n].get('string', n) for n in names if n in allowed},
            'record': {k: v for k, v in row.items() if v not in (None, [], '')}}


# ── Builder presets ──────────────────────────────────────────────────

def preset_schema(op):
    """Parameter schema the LLM sees for a builder tool."""
    props = {}
    if op in ('search', 'count', 'open'):
        props['domain'] = {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'string'}},
                           'description': 'Extra filter, e.g. [["state","=","sale"]] '
                                          '(added to the tool\'s own filter)'}
    if op == 'search':
        props['limit'] = {'type': 'integer', 'description': f'1-{MAX_ROWS}'}
        props['order'] = {'type': 'string', 'description': 'e.g. "date_order desc"'}
    if op in ('read', 'update'):
        props['record'] = {'type': 'string', 'description': 'Record id, number or name; '
                                                            'empty = the record on screen'}
    if op in ('create', 'update'):
        props['values'] = {'type': 'object', 'description': 'Field values as {field: value}'}
    required = ['values'] if op == 'create' else []
    return {'type': 'object', 'properties': props, 'required': required}


def write_gate(env, agent):
    """Reason a write preset may not propose (None = allowed). Re-checked
    at dispatch so a cached/replayed call cannot skip the runtime filter."""
    icp = env['ir.config_parameter'].sudo()
    if str(icp.get_param('ab_ai_agent.actions_enabled', 'True')).lower() not in ('1', 'true', 'yes'):
        return 'actions are turned off on this system'
    from .llm_adapter import gateway_policy
    if gateway_policy(env).get('actions') is False:
        return 'actions are not included in the subscription plan'
    if agent is not None and agent and not agent.allow_write_actions:
        return 'this assistant is not allowed to make changes'
    return None


def run_preset(env, tool, agent=None, **arguments):
    """Dispatch a builder tool: its preset fixes model, op, base filter and
    fields; the model may only narrow (AND) the filter, never widen it."""
    preset = json.loads(tool.preset_json or '{}')
    model, op = preset.get('model'), preset.get('op')
    fixed = preset.get('domain') or []
    write = op in WRITE_OPS
    why = model_blocked(env, model, write=write)
    if why:
        return {'error': 'not permitted', 'note': why}
    if op in ('search', 'count', 'open'):
        Model = env[model]
        if not Model.has_access('read'):
            return {'error': 'not permitted', 'note': 'The user cannot read these records.'}
        allowed = readable_fields(env, Model)
        try:
            dom = expression.AND([safe_domain(fixed, allowed, Model),
                                  safe_domain(arguments.get('domain'), allowed, Model)])
        except ValueError as e:
            return {'error': str(e)}
        if op == 'count':
            return count_records(env, agent, model=model, domain=dom)
        if op == 'open':
            from .tool_dispatcher import _builtin_open_list
            return _builtin_open_list(env, agent, model=model, domain=dom, name=tool.name)
        return search_records(env, agent, model=model, domain=dom,
                              fields=preset.get('fields') or None,
                              limit=min(int(arguments.get('limit') or preset.get('limit')
                                            or DEFAULT_ROWS), MAX_ROWS),
                              order=arguments.get('order') or preset.get('order'))
    if op == 'read':
        return get_record(env, agent, model=model, record=arguments.get('record'),
                          fields=preset.get('fields') or None)
    why = write_gate(env, agent)
    if why:
        return {'error': 'not permitted', 'note': why}
    from . import agent_actions
    values = _parse(arguments.get('values'), {}) or {}
    defaults = preset.get('values') or {}
    if op == 'create':
        return agent_actions.create_record(env, agent, model=model,
                                           values={**values, **defaults})
    if op == 'update':
        return agent_actions.update_record(env, agent, model=model,
                                           record=arguments.get('record'), values=values)
    return {'error': f'unknown operation {op}'}


# Codes differ from ab_ai_chatbot's legacy allow-listed search_records /
# get_record (which it re-registers and re-syncs on every upgrade).
TOOLS = {
    'find_records': search_records,
    'count_records': count_records,
    'read_record': get_record,
}
