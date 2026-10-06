# -*- coding: utf-8 -*-
"""``update_settings`` — whitelisted settings, old → new, Confirm first.

Runs ``res.config.settings.create(vals).execute()`` as the user, which
is exactly what pressing Save on the Settings screen does: module
installs, group implications and company writes all follow Odoo's own
path. No sudo, no ``ir.config_parameter``.
"""
from __future__ import annotations

import json
import logging

from odoo.addons.ab_ai_agent.services import agent_actions, tool_dispatcher

_logger = logging.getLogger(__name__)

_TRUE = ('1', 'true', 'yes', 'on', 'enable', 'enabled', 'نعم', 'فعل', 'فعّل', 'تفعيل', 'شغل')
_FALSE = ('0', 'false', 'no', 'off', 'disable', 'disabled', 'لا', 'عطل', 'عطّل', 'تعطيل', 'اطفئ')


def _shown(env, field, value):
    if field.type == 'boolean':
        return env._('On') if value else env._('Off')
    if field.type == 'selection':
        sel = field._description_selection(env)
        return dict(sel).get(value, value or '')
    if field.type == 'many2one':
        if not value:
            return '—'
        rid = value.id if hasattr(value, 'id') else (value[0] if isinstance(value, (list, tuple))
                                                     else value)
        return env[field.comodel_name].browse(rid).display_name
    return str(value)


def _parse(env, field, raw):
    """User value → settings value, or (None, error)."""
    if field.type == 'boolean':
        if isinstance(raw, bool):
            return raw, None
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True, None
        if text in _FALSE:
            return False, None
        return None, env._('"%s" is not on or off.', raw)
    if field.type == 'selection':
        sel = field._description_selection(env)
        text = str(raw).strip().lower()
        for key, label in sel:
            if text in (str(key).lower(), str(label).lower()):
                return key, None
        return None, env._('Choose one of: %s', ', '.join(lbl for _k, lbl in sel))
    if field.type == 'many2one':
        rid, err = agent_actions._m2o(env, field.comodel_name, raw)
        return (rid, None) if not err else (None, err)
    return None, env._('This setting cannot be changed here.')


def update_settings(env, agent=None, settings=None, _ai_confirmed=False, **_kw):
    Option = env['ai.agent.setting.option']
    options = Option.options_for_user(env.user)
    if not env.user.has_group('base.group_system'):
        return {'error': 'not permitted',
                'note': 'Only administrators can change settings. Tell the user.'}
    Settings = env['res.config.settings']
    if isinstance(settings, str):
        try:
            settings = json.loads(settings or '{}')
        except ValueError:
            return {'error': 'settings must be an object of {code: value}'}
    try:
        current = Settings.default_get([o.field_name for o in options])
    except Exception:
        _logger.info('settings default_get failed', exc_info=True)
        current = {}
    if not settings:
        return {'options': [{
            'code': o.code, 'name': o.name,
            'type': Settings._fields[o.field_name].type,
            'current': _shown(env, Settings._fields[o.field_name], current.get(o.field_name)),
            'choices': [lbl for _k, lbl in Settings._fields[o.field_name]
                        ._description_selection(env)]
            if Settings._fields[o.field_name].type == 'selection' else None,
            'warning': o.warning or None,
        } for o in options]}
    by_code = {o.code: o for o in options}
    vals, details, warnings = {}, [], []
    for code, raw in settings.items():
        opt = by_code.get(code)
        if not opt:
            return {'error': f'"{code}" is not a setting the assistant may change',
                    'allowed': list(by_code)}
        field = Settings._fields[opt.field_name]
        value, err = _parse(env, field, raw)
        if err:
            return {'status': 'need_info',
                    'questions': [{'field': code, 'message': f'{opt.name}: {err}'}]}
        old = current.get(opt.field_name)
        vals[opt.field_name] = value
        details.append(f'{opt.name}: {_shown(env, field, old)} → {_shown(env, field, value)}')
        if opt.warning:
            warnings.append(f'⚠ {opt.warning}')
    if not _ai_confirmed:
        return agent_actions._propose(env, 'update_settings', {'settings': settings}, None,
                                      env._('Change these settings?'), details + warnings)

    def do():
        wizard = Settings.create(vals)
        wizard.execute()
        return {'message': env._('Settings saved.') + '\n' + '\n'.join(details),
                'done': True}
    return agent_actions._run(do, env._('Settings'))


tool_dispatcher.register('update_settings', update_settings)
tool_dispatcher.PROPOSAL_TOOLS.add('update_settings')
