# -*- coding: utf-8 -*-
"""Phase H — tool dispatcher.

Maps a tool's `code` to its Python implementation. Vertical modules
register their callables here via `register()` on their __init__
hook. Built-in tools (text utilities, date helpers) live in this
module directly.

Dispatch is JSON-schema-validated, ACL-checked, and replay-safe for
write actions (idempotency_key + audit log lookup).
"""
from __future__ import annotations

import json
import logging
import time

from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


# Module-level registry. Domain modules call `register()` on install.
_REGISTRY: dict = {}


# Confirm-first tools contributed by bridge modules (journal entry,
# settings…). Like the core ACTION_TOOLS they only propose; the
# ``ab_ai_agent.actions_enabled`` switch hides them all at once.
PROPOSAL_TOOLS = set()


def register(code: str, fn):
    """Register a Python callable under a stable tool code.

    `fn` signature: `fn(env, agent, **arguments) -> dict | str | list`.
    Return value is JSON-serialised before being fed back to the LLM.

    Idempotent — re-registering the same code overwrites the previous
    entry. Useful for hot-reload during development.
    """
    _REGISTRY[code] = fn
    _logger.debug("Registered AI tool: %s", code)


def get(code: str):
    """Return the registered callable or None."""
    return _REGISTRY.get(code)


def all_tools():
    """Snapshot of the registry. Used by views to validate that every
    ai.agent.tool record has a corresponding implementation."""
    return dict(_REGISTRY)


def dispatch(env, tool_record, arguments, *, agent=None, agent_run=None):
    """Run a tool by record.

    Validates ACL, dispatches to the registered callable or the
    ir.actions.server target. Returns ``{'ok': bool, 'result': ...,
    'error': str, 'duration_ms': int}``. Never raises — every failure
    becomes part of the LLM context so the model can recover.
    """
    started = time.perf_counter()

    # ── ACL ────────────────────────────────────────────────────
    if not tool_record.is_invocable_by(env.user):
        return _error('forbidden', tool_record, time.perf_counter() - started,
                      f'You do not have permission to invoke {tool_record.code}.')

    # ── PII gate ───────────────────────────────────────────────
    if tool_record.requires_pii and (not agent or not agent.allow_pii):
        return _error('pii_blocked', tool_record, time.perf_counter() - started,
                      'This tool reads personal data and the assistant is not allowed '
                      'to (the "Allow Pii" setting is off on this agent). Tell the user '
                      'exactly that, and that an administrator can turn it on in '
                      'AI > Agents > All Agents. Do NOT say there is no data.')

    # ── Write-action gate ──────────────────────────────────────
    if tool_record.is_write_action and (not agent or not agent.allow_write_actions):
        return _error('write_blocked', tool_record, time.perf_counter() - started,
                      'Agent is not allowed to invoke write actions.')

    # ── Strip the __end_message helper from arguments ──────────
    arguments = dict(arguments or {})
    end_message = arguments.pop('__end_message', None)
    # `_ai_*` kwargs are server-side flags (e.g. `_ai_confirmed`, set
    # only by ai.agent.pending.action.resolve after the user's click).
    # A model — or text injected into a record it read — must never be
    # able to pass them and skip the confirmation step.
    arguments = {k: v for k, v in arguments.items()
                 if not str(k).startswith('_ai_')}
    arguments = _coerce_json_args(tool_record, arguments)

    # ── Dispatch ───────────────────────────────────────────────
    try:
        if tool_record.dispatch_kind == 'server_action':
            result = _dispatch_server_action(env, tool_record, arguments, agent=agent)
        else:
            result = _dispatch_python(env, tool_record, arguments, agent=agent)
    except UserError as ue:
        return _error('user_error', tool_record, time.perf_counter() - started,
                      str(ue), end_message=end_message)
    except Exception as e:
        _logger.exception("Tool %s failed", tool_record.code)
        return _error('exception', tool_record, time.perf_counter() - started,
                      f'{type(e).__name__}: {e}', end_message=end_message)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        'ok': True,
        'tool': tool_record.code,
        'result': result,
        'duration_ms': duration_ms,
        'end_message': end_message,
    }


def _coerce_json_args(tool_record, arguments):
    """Turn JSON-string values back into the objects/arrays the schema declares.

    Gemini rejects a free-form OBJECT parameter, so ``_gemini_schema`` sends
    it as a JSON string; without this every create/update/command tool got
    ``fields='{"name": ...}'`` and failed on ``dict(fields)``.
    """
    try:
        props = (json.loads(tool_record.schema or '{}') or {}).get('properties') or {}
    except (ValueError, TypeError):
        return arguments
    for key, spec in props.items():
        value = arguments.get(key)
        if not isinstance(value, str) or not isinstance(spec, dict):
            continue
        if spec.get('type') not in ('object', 'array'):
            continue
        text = value.strip()
        if not text:
            arguments[key] = None
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue    # the tool reports the bad value itself
        if isinstance(parsed, (dict, list)):
            arguments[key] = parsed
    return arguments


def _dispatch_python(env, tool, arguments, agent=None):
    if tool.preset_json:
        # Console-builder tool: a preset over the generic data tools.
        from .generic_data import run_preset
        return run_preset(env, tool, agent=agent, **arguments)
    fn = get(tool.code)
    if not fn:
        raise UserError(
            f'No Python implementation registered for tool "{tool.code}". '
            f'Vertical module not installed?'
        )
    return fn(env, agent=agent, **arguments)


def _dispatch_server_action(env, tool, arguments, agent=None):
    if not tool.server_action_id:
        raise UserError(f'Tool {tool.code} has no server_action_id.')
    action = tool.server_action_id.with_context(
        ai_tool_arguments=arguments,
        ai_tool_agent_id=agent.id if agent else False,
    )
    result = action.run()
    # ir.actions.server typically returns the next action dict or None.
    # We pass it through so the LLM can see what happened.
    return result


def _error(kind, tool, duration_s, message, end_message=None):
    return {
        'ok': False,
        'tool': tool.code if tool else '',
        'error': kind,
        'message': message,
        'duration_ms': int(duration_s * 1000),
        'end_message': end_message,
    }


# ─── Built-in tools — minimal, registered on import ──────────────

def _builtin_date_reference(env, agent=None, **kwargs):
    """Return a date-calculation cheat-sheet so the LLM doesn't do
    its own math. Mirrors Odoo 19 native's pattern (§3.8)."""
    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    month_end = next_month - timedelta(days=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    quarter = (today.month - 1) // 3 + 1
    q_start_month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    q_start = today.replace(month=q_start_month, day=1)
    return {
        'today': str(today),
        'yesterday': str(yesterday),
        'tomorrow': str(tomorrow),
        'this_week': f'{week_start} to {week_end}',
        'this_month': f'{month_start} to {month_end}',
        'last_month': f'{last_month_start} to {last_month_end}',
        'this_quarter_start': str(q_start),
        'this_year': f'{today.replace(month=1, day=1)} to {today.replace(month=12, day=31)}',
    }


def _builtin_echo(env, agent=None, **kwargs):
    """Sanity tool — returns its arguments. Used by golden-set tests."""
    return {'echo': kwargs}


# ─── Navigation tools ─────────────────────────────────────────────────
# Each returns an action descriptor in `action` — the runtime lifts that
# onto envelope.action and the chat surface paints an "Open" button.

def _builtin_open_record(env, agent=None, model=None, id=None,
                        view_type='form', **_kw):
    """Open a specific record in its default form view.

    Args:
      model: technical model name (e.g. 'sale.order', 'account.move');
             defaults to the model on the user's screen
      id:    record id
      view_type: 'form' (default) | 'kanban' | 'list'
    """
    screen = env.context.get('ai_screen') or {}
    model = model or _kw.get('res_model') or screen.get('model')
    id = id or _kw.get('record_id') or _kw.get('res_id')
    if not model or not id:
        return {'error': 'model + id are required'}
    if model not in env:
        return {'error': f'unknown model: {model}'}
    try:
        rec = env[model].browse(int(id))
        if not rec.exists():
            return {'error': f'{model} id={id} not found'}
        rec.check_access('read')
        display = rec.display_name
    except Exception:
        return {'error': 'not permitted or not found'}
    return {
        'message': f'Opening {display}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': display,
            'res_model': model,
            'res_id': int(id),
            'view_mode': view_type,
            'views': [[False, view_type]],
            'target': 'current',
        },
    }


def _builtin_open_list(env, agent=None, model=None, domain=None,
                     group_by=None, name=None, **_kw):
    """Open a filtered list view of a model.

    Args:
      model:    technical model name
      domain:   Odoo domain (list of tuples) or empty for all records
      group_by: list of field names to group by
      name:     optional display label for the list
    """
    if not model:
        return {'error': 'model is required'}
    if model not in env:
        return {'error': f'unknown model: {model}'}
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {}
    if group_by:
        if isinstance(group_by, str):
            group_by = [group_by]
        ctx['group_by'] = group_by
    return {
        'message': f'Opening {name or model} list ({len(safe_domain)} filter(s))',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or env[model]._description or model,
            'res_model': model,
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_pivot(env, agent=None, model=None, measures=None,
                       row_groupbys=None, col_groupbys=None,
                       domain=None, name=None, **_kw):
    """Open a pivot analytics view."""
    if not model or model not in env:
        return {'error': f'unknown model: {model}'}
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {
        'pivot_measures': measures or [],
        'pivot_row_groupby': row_groupbys or [],
        'pivot_column_groupby': col_groupbys or [],
    }
    return {
        'message': f'Opening pivot of {model}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or f'{env[model]._description or model} — Pivot',
            'res_model': model,
            'view_mode': 'pivot,list',
            'views': [[False, 'pivot'], [False, 'list']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_graph(env, agent=None, model=None, measure=None,
                       mode='bar', group_by=None, domain=None,
                       name=None, **_kw):
    """Open a graph view (bar / line / pie)."""
    if not model or model not in env:
        return {'error': f'unknown model: {model}'}
    if mode not in ('bar', 'line', 'pie'):
        mode = 'bar'
    safe_domain = []
    if domain:
        try:
            from ast import literal_eval
            safe_domain = literal_eval(domain) if isinstance(domain, str) else list(domain)
        except Exception:
            safe_domain = []
    ctx = {'graph_mode': mode}
    if measure:
        ctx['graph_measure'] = measure
    if group_by:
        if isinstance(group_by, str):
            group_by = [group_by]
        ctx['graph_groupbys'] = group_by
    return {
        'message': f'Opening {mode} chart of {model}',
        'action': {
            'type': 'ir.actions.act_window',
            'name': name or f'{env[model]._description or model} — {mode.title()}',
            'res_model': model,
            'view_mode': 'graph,list',
            'views': [[False, 'graph'], [False, 'list']],
            'domain': safe_domain,
            'context': ctx,
            'target': 'current',
        },
    }


def _builtin_open_action(env, agent=None, xmlid=None, **_kw):
    """Open a server-registered action by xmlid.

    Useful for built-in reports: 'account.action_account_pl_report',
    'account.action_account_balance_report', 'sale.action_orders', etc.
    """
    if not xmlid:
        return {'error': 'xmlid required'}
    try:
        action = env.ref(xmlid, raise_if_not_found=False)
        if not action:
            return {'error': f'action {xmlid} not found'}
        if not action._name.startswith('ir.actions.'):
            return {'error': f'{xmlid} is not an action'}
        # An action restricted to groups the user lacks is exactly the
        # screen the menu hides from them — the assistant must not be a
        # side door to it. Read as the user (actions are readable by
        # internal users; no sudo), and honour the target model's ACL.
        groups = action.sudo().groups_id if 'groups_id' in action._fields else False
        if groups and not (groups & env.user.groups_id):
            return {'error': 'not available for this user',
                    'note': 'Tell the user this screen is not available to them.'}
        res_model = getattr(action, 'res_model', False)
        if res_model and (env.get(res_model) is None
                          or not env[res_model].has_access('read')):
            return {'error': 'not available for this user',
                    'note': 'Tell the user this screen is not available to them.'}
        action_dict = action._get_action_dict() if hasattr(action, '_get_action_dict') \
            else action.read()[0]
        # Strip sentinel keys that aren't part of the act_window contract.
        for k in ('create_uid', 'write_uid', 'create_date', 'write_date'):
            action_dict.pop(k, None)
        return {
            'message': f'Opening {action.name}',
            'action': action_dict,
        }
    except Exception:
        _logger.info('open_action %s failed', xmlid, exc_info=True)
        return {'error': f'could not open {xmlid}'}


# ─── System guidance ─────────────────────────────────────────────────
# "What can I do here?" / "Where do I do X?" / "What is this screen?"
#
# Every one of these reads the menu tree and model metadata AS THE
# REQUESTING USER — never sudo. ir.ui.menu already filters itself by
# groups_id, and ir.model.fields respects field-level groups, so an
# accountant and a cashier get genuinely different answers and the
# assistant can never point someone at a screen they cannot open.

def _menu_path(menu):
    """'Sales / Orders / Quotations' — walked with the user's own
    access, so a hidden ancestor truncates the path rather than
    leaking its name."""
    parts, node, guard = [], menu, 0
    while node and guard < 12:
        try:
            parts.append(node.name)
            node = node.parent_id
        except Exception:
            break
        guard += 1
    return ' / '.join(reversed(parts))


def _builtin_list_my_apps(env, agent=None, **_kw):
    """Top-level apps this user can actually open.

    The grounding for "what can I do in the system?". Without it the
    model invents plausible Odoo menus the user has no access to.
    """
    Menu = env.get('ir.ui.menu')
    if Menu is None:
        return {'error': 'ir.ui.menu unavailable'}
    try:
        # No sudo: the ORM applies the menu's groups_id for us.
        roots = Menu.search([('parent_id', '=', False)], order='sequence, id')
    except AccessError:
        # Portal/public users can't read the backend menu tree at all.
        # That IS the answer — "you have no back-office apps" — not a
        # failure, so return it as data the model can explain.
        return {
            'user': env.user.name,
            'app_count': 0,
            'apps': [],
            'note': ('This user has no back-office access at all. Explain '
                     'that they use the customer portal, not the back '
                     'office, and do not list any app.'),
        }
    except Exception as e:
        return {'error': f'could not read menus: {type(e).__name__}'}

    apps = []
    for root in roots:
        children = root.child_id.filtered(lambda m: m.name)
        apps.append({
            'name': root.name,
            'xmlid': root.get_external_id().get(root.id) or '',
            'sections': children.mapped('name')[:12],
        })
    return {
        'user': env.user.name,
        'app_count': len(apps),
        'apps': apps,
        'note': 'Only apps this user may open. Do not mention anything absent.',
    }


def _menu_search(Menu, q, cap):
    """Menus whose own name matches, else whose action name does.

    Users ask for "credit note" when the menu is called "Refunds", so a
    miss on the menu name is not a miss on the destination.
    """
    menus = Menu.search([('name', 'ilike', q)], limit=cap)
    if menus:
        return menus
    return Menu.search([('action', '!=', False)], limit=400).filtered(
        lambda m: q.lower() in (m.action.name or '').lower()
    )[:cap]


# Arabic business words → the English words menus are usually named with.
# Substring keys, so plurals and "ال" prefixes still hit (فواتير, العملاء).
_MENU_GLOSSARY = (
    ('فاتور', ('invoice',)), ('فواتير', ('invoice',)), ('عميل', ('customer',)),
    ('عملاء', ('customer',)), ('مورد', ('vendor', 'bill')), ('مرتجع', ('credit note', 'refund')),
    ('عرض', ('quotation',)), ('عروض', ('quotation',)), ('سعر', ('quotation', 'pricelist')),
    ('مبيع', ('sale', 'order')), ('بيع', ('sale',)), ('مشتري', ('purchase',)), ('شراء', ('purchase',)),
    ('منتج', ('product',)), ('صنف', ('product',)), ('موظف', ('employee',)), ('إجاز', ('time off', 'leave')),
    ('اجاز', ('time off', 'leave')), ('حضور', ('attendance',)), ('راتب', ('payslip', 'payroll')),
    ('رواتب', ('payslip', 'payroll')), ('مخزون', ('inventory', 'stock')), ('مستودع', ('warehouse',)),
    ('دفع', ('payment',)), ('مدفوع', ('payment',)), ('قيد', ('journal entr',)), ('قيود', ('journal entr',)),
    ('حساب', ('account',)), ('تقرير', ('report',)), ('تقارير', ('report',)), ('اتصال', ('contact',)),
    ('نقاط البيع', ('point of sale',)), ('كاشير', ('point of sale',)), ('طلب', ('order',)),
)
_MENU_STOPWORDS = {
    'وين', 'اين', 'أين', 'كيف', 'اسوي', 'أسوي', 'سوي', 'اعمل', 'أعمل', 'انشئ', 'أنشئ', 'اضيف', 'أضيف',
    'جديد', 'جديدة', 'في', 'من', 'على', 'الى', 'إلى', 'ابي', 'أبي', 'ابغى', 'أبغى', 'لو', 'سمحت',
    'where', 'how', 'do', 'i', 'a', 'an', 'the', 'new', 'create', 'add', 'make', 'can', 'to', 'is',
}


def _menu_search_words(Menu, q, cap):
    """Rank openable menus by how many of the question's words they carry.

    The whole-phrase search misses "وين أسوي فاتورة عميل جديدة" because no
    menu is called that; "فواتير العملاء" / "Customer Invoices" carries two
    of its words. Arabic words also try their usual English menu names,
    since menus are often stored in English only.
    """
    words = [w.strip('؟?.,،!') for w in q.split()]
    words = [w for w in words if len(w) >= 3 and w.lower() not in _MENU_STOPWORDS]
    terms = set()
    for w in words:
        base = w[2:] if w.startswith('ال') and len(w) > 4 else w
        terms.add(base.lower())
        for key, english in _MENU_GLOSSARY:
            if key in w:
                terms.update(english)
    if not terms:
        return Menu.browse()
    candidates = Menu.browse()
    for term in terms:
        for M in (Menu, Menu.with_context(lang='en_US')):
            candidates |= Menu.browse(
                M.search([('name', 'ilike', term), ('action', '!=', False)], limit=40).ids)
    if not candidates:
        return Menu.browse()

    # Score on the whole path, in both languages: "Customer Invoices" lives
    # at Accounting / Customers / Invoices — the leaf alone says only
    # "Invoices", its parent says "Customers".
    def haystack(menu):
        return ' '.join((_menu_path(menu), _menu_path(menu.with_context(lang='en_US')))).lower()

    def rank(menu):
        text = haystack(menu)
        hits = sum(1 for t in terms if t.lower() in text)
        model = getattr(menu.action, 'res_model', '') or ''
        # A business document beats a report / wizard about it.
        doc = 0 if ('report' in model or 'wizard' in model or not model) else 1
        return (hits, doc, -len(_menu_path(menu)))
    ranked = sorted(candidates, key=rank, reverse=True)
    return Menu.browse([m.id for m in ranked[:cap]])


def _builtin_find_menu(env, agent=None, query=None, limit=6, **_kw):
    """Resolve "where do I do X?" to real, openable menu entries.

    Returns the menu path plus its action, so the answer can carry a
    working "take me there" button instead of a prose breadcrumb the
    user has to hunt for.
    """
    if not query or not str(query).strip():
        return {'error': 'query required'}
    Menu = env.get('ir.ui.menu')
    if Menu is None:
        return {'error': 'ir.ui.menu unavailable'}

    q = str(query).strip()
    cap = int(limit) * 3
    try:
        menus = _menu_search(Menu, q, cap)
        if not menus and not (env.lang or '').startswith('en'):
            # Whether a menu name is English or Arabic depends on which
            # catalogues this tenant happens to have loaded, and BOTH
            # directions miss:
            #   menus English, query Arabic  -> the note sends the model
            #     back with an English term, which then hits;
            #   menus Arabic, query English  -> nothing sends it back,
            #     and it concluded "you have no access to invoices" for
            #     an administrator who had just created one.
            # The en_US value is always present in the jsonb alongside
            # any translation, so retrying there covers the second case
            # without the model needing to know anything.
            menus = Menu.browse(
                _menu_search(Menu.with_context(lang='en_US'), q, cap).ids)
        if not menus:
            menus = _menu_search_words(Menu, q, cap)
    except Exception as e:
        return {'error': f'menu search failed: {type(e).__name__}'}

    hits = []
    for menu in menus:
        if not menu.action:
            continue           # a folder, not a destination
        hits.append({
            'label': menu.name,
            'path': _menu_path(menu),
            'menu_id': menu.id,
            'action_xmlid': menu.action.get_external_id().get(menu.action.id) or '',
            'model': getattr(menu.action, 'res_model', '') or '',
        })
        if len(hits) >= int(limit):
            break

    if not hits:
        # An empty result is ambiguous: it means "no access" only if the
        # query was in the language the menus are actually stored in.
        # Menus are English on most tenants, so an Arabic question
        # forwarded verbatim ("فاتورة") matches nothing — and the agent
        # used to read that as a permission problem and tell the user to
        # go ask an administrator for access they already had. Make the
        # retry explicit before any conclusion is allowed.
        return {
            'query': q,
            'matches': [],
            'note': ('No menu matched this WORD — that is not the same as '
                     'no access. Menu names are usually stored in English. '
                     'If you searched in another language, call find_menu '
                     'again with the English term (فاتورة → "invoice", '
                     'عميل → "customer") before saying anything. Only after '
                     'an English search also comes back empty may you tell '
                     'the user they lack access — and never invent a path.'),
        }
    return {'query': q, 'matches': hits}


def _resolve_model(env, name):
    """Turn whatever the user called a screen into a real model name.

    People say "the invoices screen", not "account.move". Resolving that
    here rather than asking them to supply a technical name keeps the
    conversation in their language — and stops the assistant replying
    with tool mechanics, which is a leak of our internals into a
    business user's answer.
    """
    if not name:
        return None
    raw = str(name).strip()
    if env.get(raw) is not None:          # already a model name
        return raw

    # Menu label → the action's model. This is how users actually refer
    # to screens: by the words in their own navigation.
    Menu = env.get('ir.ui.menu')
    if Menu is not None:
        try:
            for menu in Menu.search([('name', 'ilike', raw)], limit=20):
                target = getattr(menu.action, 'res_model', None)
                if target and env.get(target) is not None:
                    return target
        except Exception:
            pass

    # Fall back to the model's own human description ("Journal Entry").
    IrModel = env.get('ir.model')
    if IrModel is not None:
        try:
            hit = IrModel.sudo().search(
                ['|', ('name', '=ilike', raw), ('name', 'ilike', raw)], limit=1)
            if hit and env.get(hit.model) is not None:
                return hit.model
        except Exception:
            pass
    return None


def _builtin_explain_screen(env, agent=None, model=None, screen=None, **_kw):
    """Describe a screen from live metadata rather than guessing.

    Reads the model's own fields, its state/stage vocabulary and the
    server actions bound to it — as the user, so field-level groups are
    honoured and a restricted field never surfaces in the explanation.

    Accepts either a technical model name or whatever the user called
    the screen; see _resolve_model.
    """
    requested = model or screen
    model = _resolve_model(env, requested)
    if not model:
        return {
            'error': 'could not identify that screen',
            'requested': requested or '',
            'note': ('Ask the user which screen they mean in THEIR words '
                     '(e.g. "the invoices list", "the customer form"). '
                     'Never ask for a technical model name and never '
                     'mention this tool by name.'),
        }
    Model = env.get(model)
    if Model is None:
        return {'error': f'model {model} is not installed'}

    try:
        Model.check_access('read')
    except Exception:
        return {'error': f'no read access to {model}',
                'note': 'Tell the user they lack access to this screen.'}

    fields_meta = Model.fields_get()   # already group-filtered per user
    interesting, states = [], []
    for name, meta in fields_meta.items():
        if name.startswith('_') or meta.get('type') in (
                'binary', 'one2many', 'many2many'):
            continue
        if meta.get('type') == 'selection' and name in ('state', 'stage_id', 'status'):
            states = [lbl for _v, lbl in (meta.get('selection') or [])]
        if meta.get('required') or name in (
                'name', 'partner_id', 'date', 'state', 'company_id',
                'amount_total', 'user_id'):
            interesting.append({
                'field': name,
                'label': meta.get('string') or name,
                'type': meta.get('type'),
                'required': bool(meta.get('required')),
                'readonly': bool(meta.get('readonly')),
                'help': (meta.get('help') or '')[:160],
            })

    try:
        can_write = Model.has_access('write')
        can_create = Model.has_access('create')
        can_unlink = Model.has_access('unlink')
    except Exception:
        can_write = can_create = can_unlink = False

    return {
        'model': model,
        'title': Model._description or model,
        'record_count': Model.search_count([]),
        'key_fields': interesting[:18],
        'lifecycle': states,
        'permissions': {
            'create': can_create, 'write': can_write, 'delete': can_unlink,
        },
        'note': ('Permissions describe THIS user. If write is false, do not '
                 'tell them to edit anything — explain who can.'),
    }


# ─── HR domain tools ─────────────────────────────────────────────────
# Defensive: skipped when hr / hr.attendance modules aren't installed.
#
# These read OTHER employees' attendance and leave, so they need the
# same role the native screens need (attendance officer / time-off
# officer) and run as the user — no sudo — so record rules (company,
# department managers) still scope the answer. They used to sudo()
# behind the agent's `allow_pii` flag alone, which let any user of a
# PII-enabled agent read company-wide attendance.

_HR_ROLE = {
    'attendance': ('hr_attendance.group_hr_attendance_officer',
                   'hr.group_hr_user'),
    'leave': ('hr_holidays.group_hr_holidays_responsible',
              'hr_holidays.group_hr_holidays_user', 'hr.group_hr_user'),
}


def _hr_denied(env, role):
    user = env.user
    for xmlid in _HR_ROLE[role]:
        if env.ref(xmlid, raise_if_not_found=False) and user.has_group(xmlid):
            return None
    return {'error': 'not permitted',
            'note': ('This user does not have the HR role needed to see other '
                     'employees\' records. Say so plainly; do not guess numbers.')}

def _builtin_hr_attendance_missing_today(env, agent=None, limit=50, **_kw):
    """Employees with no check-in for today. The "morning roll call"."""
    Emp = env.get('hr.employee')
    Att = env.get('hr.attendance')
    if Emp is None or Att is None:
        return {'error': 'hr.attendance not installed on this instance'}
    denied = _hr_denied(env, 'attendance')
    if denied:
        return denied
    from odoo import fields as _fields
    today = _fields.Date.context_today(env['res.users'])
    today_start = f'{today} 00:00:00'
    try:
        with env.cr.savepoint(flush=False):
            attended_ids = Att.search([
                ('check_in', '>=', today_start),
            ]).mapped('employee_id').ids
            missing = Emp.search([
                ('active', '=', True),
                ('id', 'not in', attended_ids),
            ], limit=int(limit))
    except Exception:
        _logger.info('hr_attendance_missing_today failed', exc_info=True)
        return {'error': 'could not read attendance'}
    rows = [{
        'id': e.id,
        'name': e.name,
        'department': e.department_id.name if e.department_id else '',
        'job': e.job_title or '',
    } for e in missing]
    return {
        'count': len(rows),
        'date': str(today),
        'employees': rows,
    }


def _builtin_hr_leave_pending(env, agent=None, limit=50, **_kw):
    """Leave requests awaiting approval."""
    Leave = env.get('hr.leave')
    if Leave is None:
        return {'error': 'hr.leave not installed'}
    denied = _hr_denied(env, 'leave')
    if denied:
        return denied
    try:
        with env.cr.savepoint(flush=False):
            rows = Leave.search([('state', '=', 'confirm')],
                                       limit=int(limit), order='date_from')
    except Exception as e:
        return {'error': str(e)}
    return {
        'count': len(rows),
        'leaves': [{
            'id': l.id,
            'employee': l.employee_id.name if l.employee_id else '',
            'type': l.holiday_status_id.name if l.holiday_status_id else '',
            'date_from': str(l.date_from) if l.date_from else '',
            'date_to': str(l.date_to) if l.date_to else '',
            'days': l.number_of_days,
        } for l in rows],
    }


def _builtin_hr_attendance_open_shifts(env, agent=None, **_kw):
    """Currently clocked-in employees who haven't clocked out yet."""
    Att = env.get('hr.attendance')
    if Att is None:
        return {'error': 'hr.attendance not installed'}
    denied = _hr_denied(env, 'attendance')
    if denied:
        return denied
    try:
        with env.cr.savepoint(flush=False):
            rows = Att.search([('check_out', '=', False)],
                                     order='check_in desc', limit=100)
    except Exception as e:
        return {'error': str(e)}
    return {
        'count': len(rows),
        'open_attendances': [{
            'id': a.id,
            'employee': a.employee_id.name if a.employee_id else '',
            'check_in': str(a.check_in) if a.check_in else '',
            'department': a.employee_id.department_id.name if a.employee_id and a.employee_id.department_id else '',
        } for a in rows],
    }


# ─── Analysis tools ──────────────────────────────────────────────────
# Numbers come straight from the ORM/SQL — NEVER from the model. The
# tool returns a `render` envelope (chart + KPI grid + peak callout);
# runtime.py lifts that onto envelope.render verbatim (same path as
# `action`). The LLM only writes the surrounding narrative paragraph.

_DA_METRICS = {
    # key: (table, amount_col, date_col, state_sql, label)
    'pos_sales': ("pos_order", "amount_total", "date_order",
                  "state IN ('paid','done','invoiced')", "POS sales"),
    'sale_orders': ("sale_order", "amount_total", "date_order",
                    "state IN ('sale','done')", "Sales orders"),
    'invoiced_revenue': ("account_move", "amount_total_signed", "invoice_date",
                         "move_type = 'out_invoice' AND state = 'posted'",
                         "Invoiced revenue"),
}
_DA_GROUPS = {'day', 'week', 'month'}


def _builtin_data_analysis(env, agent=None, metric='pos_sales',
                           period_days=30, group='day', **_kw):
    """Deterministic timeseries analysis → render envelope.

    Args:
      metric:      pos_sales | sale_orders | invoiced_revenue
      period_days: lookback window (1–365, default 30)
      group:       day | week | month (bucket granularity)
    """
    from datetime import timedelta
    from odoo import fields as _fields

    spec = _DA_METRICS.get(metric)
    if not spec:
        return {'error': f'unknown metric {metric!r}; '
                         f'choose one of {sorted(_DA_METRICS)}'}
    table, amt_col, date_col, state_sql, label = spec
    group = group if group in _DA_GROUPS else 'day'
    _ = env._
    # What the user reads is translated; `summary` (for the model) stays English.
    ui_label = {'pos_sales': _('POS sales'), 'sale_orders': _('Sales orders'),
                'invoiced_revenue': _('Invoiced revenue')}[metric]
    ui_group = {'day': _('day'), 'week': _('week'), 'month': _('month')}[group]
    try:
        period_days = max(1, min(365, int(period_days)))
    except (TypeError, ValueError):
        period_days = 30

    today = _fields.Date.context_today(env['res.users'])
    start = today - timedelta(days=period_days)
    prev_start = start - timedelta(days=period_days)
    unit = (env.company.currency_id.symbol or 'SAR')

    # Guard: table may not exist on every tenant (no POS, no accounting).
    env.cr.execute("SELECT to_regclass(%s)", (f'public.{table}',))
    if not (env.cr.fetchone() or [None])[0]:
        return {'error': f'{metric}: table {table} not present on this instance'}

    q = (
        f"SELECT date_trunc(%s, {date_col})::date d, "
        f"       COALESCE(SUM({amt_col}), 0) amt, COUNT(*) n "
        f"  FROM {table} "
        f" WHERE {state_sql} AND {date_col} >= %s AND {date_col} < %s "
        f" GROUP BY 1 ORDER BY 1"
    )
    try:
        with env.cr.savepoint(flush=False):
            env.cr.execute(q, (group, start, today))
            rows = env.cr.fetchall()
            env.cr.execute(
                f"SELECT COALESCE(SUM({amt_col}), 0) FROM {table} "
                f"WHERE {state_sql} AND {date_col} >= %s AND {date_col} < %s",
                (prev_start, start),
            )
            prev_total = float((env.cr.fetchone() or [0])[0] or 0)
    except Exception as e:  # never raise into the hop loop
        return {'error': f'{metric} query failed: {type(e).__name__}: {e}'}

    if not rows:
        return {
            'render': {
                'layout': 'report',
                'title': _('%(label)s — last %(days)s days', label=ui_label, days=period_days),
                'blocks': [{
                    'type': 'callout', 'tone': 'warn',
                    'title': _('No data'),
                    'body': _('No %(label)s between %(start)s and %(end)s.',
                              label=ui_label, start=start, end=today),
                }],
            },
            'summary': f'No {label.lower()} in the last {period_days} days.',
        }

    x = [r[0].isoformat() for r in rows]
    amounts = [round(float(r[1]), 2) for r in rows]
    counts = [int(r[2]) for r in rows]
    total = round(sum(amounts), 2)
    txn = sum(counts)
    avg = round(total / len(x), 2)
    peak = max(rows, key=lambda r: r[1])
    delta = (((total - prev_total) / prev_total * 100.0)
             if prev_total else None)
    tone = 'good' if (delta is None or delta >= 0) else 'bad'
    delta_txt = (f'{delta:+.1f}%' if delta is not None else '—')
    if delta is None:
        insight = _('No comparable prior period.')
    elif delta >= 0:
        insight = _('Up %(pct)s%% vs the previous %(days)s days.',
                    pct=f'{abs(delta):.1f}', days=period_days)
    else:
        insight = _('Down %(pct)s%% vs the previous %(days)s days.',
                    pct=f'{abs(delta):.1f}', days=period_days)

    kpis = [
        {'label': _('Total'), 'value': f'{total:,.0f} {unit}',
         'delta_pct': delta_txt, 'tone': tone},
        {'label': _('Transactions'), 'value': f'{txn:,}'},
        {'label': _('Average per %(group)s', group=ui_group), 'value': f'{avg:,.0f} {unit}'},
    ]
    return {
        'render': {
            'layout': 'report',
            'title': _('%(label)s — last %(days)s days', label=ui_label, days=period_days),
            'blocks': [
                {'type': 'kpi_grid', 'items': kpis},
                {'type': 'chart', 'chart': 'area',
                 'title': _('%(label)s by %(group)s', label=ui_label, group=ui_group), 'x': x,
                 'series': [
                     {'name': f'{ui_label} ({unit})', 'data': amounts},
                     {'name': _('Transactions'), 'data': counts, 'axis': 'right'},
                 ],
                 'unit': unit, 'tone': tone, 'insight': insight},
                {'type': 'callout', 'tone': 'info', 'title': _('Peak'),
                 'body': _('%(date)s: %(amount)s %(unit)s across %(count)s transactions.',
                           date=peak[0], amount=f'{float(peak[1]):,.0f}', unit=unit,
                           count=int(peak[2]))},
            ],
        },
        # Compact factual line the LLM bases its narrative on. The model
        # is told NOT to restate the table — just interpret this.
        'summary': (
            f'{label}: {total:,.0f} {unit} over {len(x)} {group}-buckets '
            f'({txn} transactions), {delta_txt} vs prior {period_days}d, '
            f'peak {peak[0]} at {float(peak[1]):,.0f} {unit}.'
        ),
    }


# key -> (model, date_field, [(label, fname), ...], extra_domain, title)
_RECENT_KINDS = {
    'invoices': ('account.move', 'invoice_date',
                 [('Number', 'name'), ('Customer', 'partner_id'),
                  ('Date', 'invoice_date'), ('Total', 'amount_total'),
                  ('Status', 'state')],
                 [('move_type', '=', 'out_invoice')], 'Latest customer invoices'),
    'bills': ('account.move', 'invoice_date',
              [('Number', 'name'), ('Vendor', 'partner_id'),
               ('Date', 'invoice_date'), ('Total', 'amount_total'),
               ('Status', 'state')],
              [('move_type', '=', 'in_invoice')], 'Latest vendor bills'),
    'sale_orders': ('sale.order', 'date_order',
                    [('Order', 'name'), ('Customer', 'partner_id'),
                     ('Date', 'date_order'), ('Total', 'amount_total'),
                     ('Status', 'state')], [], 'Latest sales orders'),
    'pos_orders': ('pos.order', 'date_order',
                   [('Receipt', 'name'), ('Customer', 'partner_id'),
                    ('Date', 'date_order'), ('Total', 'amount_total'),
                    ('Status', 'state')], [], 'Latest POS orders'),
    'purchase_orders': ('purchase.order', 'date_order',
                        [('Order', 'name'), ('Vendor', 'partner_id'),
                         ('Date', 'date_order'), ('Total', 'amount_total'),
                         ('Status', 'state')], [], 'Latest purchase orders'),
    'customers': ('res.partner', 'create_date',
                  [('Name', 'name'), ('Email', 'email'),
                   ('Phone', 'phone'), ('City', 'city')],
                  [('customer_rank', '>', 0)], 'Most recently added customers'),
}


def _builtin_recent_records(env, agent=None, kind=None, model=None,
                            limit=10, **_kw):
    """The N most recently ADDED records of a business object.

    Answers "latest invoice added", "last 5 sale orders", "newest
    customers" — questions the model otherwise recycles stale context
    for. Numbers/IDs come straight from the ORM under the caller's
    access rights (record rules / branch isolation respected).

    Args:
      kind:  invoices | bills | sale_orders | pos_orders |
             purchase_orders | customers
      model: technical model name (advanced; overrides kind, ordered
             by create_date desc)
      limit: 1-50 (default 10)
    """
    try:
        limit = max(1, min(50, int(limit)))
    except (TypeError, ValueError):
        limit = 10

    if kind and kind in _RECENT_KINDS:
        mname, date_field, cols, domain, title = _RECENT_KINDS[kind]
    elif model:
        mname, date_field, cols, domain, title = (
            model, 'create_date',
            [('Name', 'display_name'), ('Created', 'create_date')],
            [], f'Latest {model} records')
    else:
        return {'error': 'kind required, one of %s (or a model=)'
                         % sorted(_RECENT_KINDS)}

    if mname not in env:
        return {'error': f'{mname} not installed on this instance'}
    Model = env[mname]
    try:
        Model.check_access('read')
    except Exception as e:
        return {'error': f'no read access to {mname}: {e}'}
    if date_field not in Model._fields:
        date_field = 'create_date'

    try:
        recs = Model.search(domain or [], order=f'{date_field} desc, id desc',
                            limit=limit)
    except Exception as e:
        return {'error': f'{mname} query failed: {type(e).__name__}: {e}'}
    if not recs:
        return {'render': {'layout': 'report', 'title': title,
                           'blocks': [{'type': 'callout', 'tone': 'warn',
                                       'title': 'Nothing found',
                                       'body': f'No {kind or mname} records.'}]},
                'summary': f'No {kind or mname} records found.'}

    def _cell(rec, fname):
        if fname not in rec._fields:
            return ''
        val = rec[fname]
        f = rec._fields[fname]
        if f.type == 'many2one':
            return val.display_name or '' if val else ''
        if f.type in ('date', 'datetime'):
            return str(val) if val else ''
        if f.type in ('float', 'monetary'):
            return f'{val:,.2f}'
        return '' if val in (False, None) else str(val)

    headers = [c[0] for c in cols]
    rows = [[_cell(r, c[1]) for c in cols] for r in recs]
    newest = recs[0]
    nd = newest[date_field] if date_field in newest._fields else None
    return {
        'render': {
            'layout': 'report', 'title': title,
            'blocks': [{
                'type': 'data_table',
                'title': f'{len(recs)} most recent (newest first)',
                'headers': headers, 'rows': rows,
            }],
        },
        'summary': (
            f'{len(recs)} most recent {kind or mname}; newest: '
            f'{newest.display_name} ({nd}).'
        ),
    }


# ─── Write action: confirm / validate / post a record by its number ──
# "INV/2026/00001 please post", "SO00047 confirm", "WH/IN/00012
# validate", "PBNK1/2026/0003 post". Domain-agnostic: resolves the
# reference across the standard business docs and runs the one
# canonical finalize method per model. WRITE action — the dispatcher
# blocks it unless agent.allow_write_actions is True.

# (model, [number-ish fields], finalize method, already-done predicate)
_RECORD_ACTION_SPECS = (
    ('sale.order',     ('name', 'client_order_ref'),
     'action_confirm', lambda r: r.state in ('sale', 'done')),
    ('purchase.order', ('name', 'partner_ref'),
     'button_confirm', lambda r: r.state in ('purchase', 'done')),
    ('account.move',   ('name', 'ref', 'payment_reference'),
     'action_post',    lambda r: r.state == 'posted'),
    ('stock.picking',  ('name', 'origin'),
     'button_validate', lambda r: r.state == 'done'),
    ('account.payment', ('name',),
     'action_post',    lambda r: r.state == 'posted'),
)


def _builtin_record_action(env, agent=None, reference=None, action=None,
                           _ai_confirmed=False, **_kw):
    """Find a record by its number and finalize it (confirm SO/PO,
    post invoice/bill/payment, validate picking). Returns an `action`
    so the chat shows an Open chip.

    Two-phase: called by the model it only PROPOSES (resolves the
    record, checks rights, records an ai.agent.pending.action and
    returns a Confirm/Cancel chip). The finalize method runs only when
    the user clicks Confirm, which re-enters here with
    ``_ai_confirmed=True`` (the dispatcher strips that flag from model
    arguments, so the model cannot set it).
    """
    ref = (reference or '').strip()
    if not ref:
        return {'error': 'reference required, e.g. "INV/2026/00001" or "SO00047"'}
    for model, fnames, method, is_done in _RECORD_ACTION_SPECS:
        if model not in env:
            continue
        # Exact (case-insensitive) match only. A substring `ilike` could
        # finalize the WRONG record — "INV/2026/0004" must never resolve to
        # "INV/2026/00045" and post it.
        dom = ['|'] * (len(fnames) - 1) + [(f, '=ilike', ref) for f in fnames]
        try:
            rec = env[model].search(dom, limit=1)
        except Exception:
            rec = None
        if not rec:
            continue
        label = rec.display_name
        descriptor = {
            'type': 'ir.actions.act_window', 'name': label,
            'res_model': model, 'res_id': rec.id,
            'view_mode': 'form', 'views': [[False, 'form']],
            'target': 'current',
        }
        if is_done(rec):
            return {'message': f'{label} is already finalized — nothing to do.',
                    'already_done': True, 'action': descriptor}
        # Enforce write access AS THE REQUESTING USER (env is not sudo here)
        # so the agent can never finalize a record the user couldn't post
        # through the UI. Mirrors native Odoo 19 AI, which runs tool bodies
        # su=False precisely so record rules / ACLs still apply.
        try:
            rec.check_access('write')
        except Exception as e:
            return {'error': f'{label}: not permitted ({type(e).__name__}).',
                    'action': descriptor}
        # Posting books the entry: only accounting managers may ask the
        # assistant to do it (users with lower rights post from the form,
        # where Odoo's own checks and the full document are in front of them).
        if method == 'action_post' and model in ('account.move', 'account.payment') \
                and not env.user.has_group('account.group_account_manager'):
            return {'error': env._('Only accounting managers can post through the '
                                   'assistant. Open %s and post it from the form.', label),
                    'action': descriptor}
        verb_key = {'action_confirm': 'confirm', 'button_confirm': 'confirm',
                    'action_post': 'post', 'button_validate': 'validate'}[method]
        if not _ai_confirmed:
            summary = {
                'confirm': env._('Confirm %s?', label),
                'post': env._('Post %s?', label),
                'validate': env._('Validate %s?', label),
            }[verb_key]
            proposal = env['ai.agent.pending.action'].propose(
                'record_action', {'reference': ref, 'action': action},
                target=rec, summary=str(summary))
            proposal.update({
                'message': (f'{label} is ready to {verb_key}. Nothing has '
                            f'changed yet: the user must press Confirm.'),
                'action': descriptor,
            })
            return proposal
        try:
            getattr(rec, method)()
        except UserError as e:
            # Business rule messages (missing tax, locked period…) are
            # written for users; anything else is not.
            return {'error': f'{label}: {e}', 'action': descriptor}
        except Exception:
            _logger.exception('record_action %s on %s failed', method, label)
            return {'error': f'{label} could not be completed.',
                    'action': descriptor}
        verb = {'action_confirm': 'confirmed', 'button_confirm': 'confirmed',
                'action_post': 'posted', 'button_validate': 'validated'}[method]
        return {'message': f'{label} {verb}.', 'done': True,
                'action': descriptor}
    return {'error': f'No sale order, purchase order, invoice/bill, '
                     f'picking or payment matches "{ref}".'}


# ─── Screen button: press a button the user can see — after Confirm ──
# "confirm this order", "اعتمد الطلب", "validate it" on an open record.
# Only a `type="object"` button that the user's OWN form view shows in its
# header qualifies (get_views applies their groups), so the assistant can
# never reach a method the UI would not offer them. Like record_action it
# is two-phase: the model only proposes; the click on Confirm runs it, as
# the user, with Odoo's own business checks inside the method.

def _header_object_buttons(Model):
    from lxml import etree
    arch = Model.get_views([(False, 'form')])['views']['form']['arch']
    doc = etree.fromstring(arch.encode() if isinstance(arch, str) else arch)
    out = {}
    for btn in doc.xpath('//header//button[@type="object"][@name]'):
        out[btn.get('name')] = btn.get('string') or btn.findtext('span') or btn.get('name')
    return out


def _builtin_screen_button(env, agent=None, model=None, record_id=None,
                           button=None, _ai_confirmed=False, **_kw):
    from odoo.models import check_method_name
    screen = env.context.get('ai_screen') or {}
    record_id = record_id or _kw.get('res_id') or _kw.get('id') or screen.get('res_id')
    button = button or _kw.get('button_name') or _kw.get('name') or _kw.get('label')
    model = model or _kw.get('res_model') or screen.get('model')
    Model = env.get(model) if isinstance(model, str) else None
    if Model is None or not record_id or not button:
        return {'error': 'model, record_id and button are required',
                'note': 'Take model and the open record id from "Current screen", '
                        'and the button from "Buttons visible on screen".'}
    button = str(button).strip()
    rec = Model.browse(int(record_id)).exists()
    if not rec:
        return {'error': 'record not found'}
    try:
        rec.check_access('read')
        buttons = _header_object_buttons(Model)
    except AccessError:
        return {'error': 'not permitted',
                'note': 'Tell the user this record is not available to them.'}
    if button not in buttons:
        # Users (and the model) name a button by what it SAYS: accept the
        # label when it identifies exactly one method.
        by_label = {n for n, lbl in buttons.items()
                    if (lbl or '').strip().lower() == button.lower()}
        if len(by_label) == 1:
            button = by_label.pop()
        else:
            return {'error': 'that button is not available on this screen for this user',
                    'available': sorted(set(buttons.values()))[:15]}
    try:
        check_method_name(button)
    except Exception:
        return {'error': 'that button is not available'}
    label = buttons[button]
    descriptor = {'type': 'ir.actions.act_window', 'res_model': model,
                  'res_id': rec.id, 'views': [[False, 'form']],
                  'view_mode': 'form', 'target': 'current'}
    if not _ai_confirmed:
        proposal = env['ai.agent.pending.action'].propose(
            'screen_button', {'model': model, 'record_id': rec.id, 'button': button},
            target=rec, summary=f'{label}: {rec.display_name}?')
        proposal.update({
            'message': (f'Ready to press "{label}" on {rec.display_name}. '
                        f'Nothing has changed yet: the user must press Confirm.'),
            'action': descriptor,
        })
        return proposal
    try:
        result = getattr(rec, button)()
    except UserError as e:
        return {'error': f'{label}: {e}', 'action': descriptor}
    except AccessError:
        return {'error': f'{label}: not permitted', 'action': descriptor}
    except Exception:
        _logger.exception('screen_button %s on %s failed', button, rec)
        return {'error': f'{label} could not be completed.', 'action': descriptor}
    # A button may answer with its own action (a wizard, a report): the
    # user lands there, exactly as clicking it in the form would do.
    if isinstance(result, dict) and str(result.get('type', '')).startswith('ir.actions'):
        return {'message': f'{label}: done.', 'done': True, 'action': result}
    return {'message': f'{label}: done.', 'done': True, 'action': descriptor}


# ─── T.2a — semantic search (pgvector keystone) ──────────────────────
# One generic tool replaces three always-on context blocks once the
# corresponding flags are flipped: ``_org_knowledge_block`` (today's
# ai.chat.fact retrieval), ``_record_context_block`` (record dump),
# and ``_business_snapshot_block`` (when each metric model gets an
# embedding column). Calls ``ai.semantic.index.search`` and returns
# pipe-CSV the LLM can parse cheaply.

def _builtin_semantic_search(env, agent=None, model=None, query=None,
                             limit=5, extra_domain=None,
                             vector_col='ai_embedding',
                             name_field='display_name',
                             hint_fields=None,
                             min_similarity=0.35, **_kw):
    """Find records semantically similar to a natural-language query.

    Args:
      model:           Odoo model name, e.g. 'crm.lead', 'res.partner',
                       'ai.chat.fact'. Must have an embedding column
                       (provisioned via ``ai.semantic.index.provision``).
      query:           the natural-language question / search text.
      limit:           how many hits (1-20, default 5).
      extra_domain:    optional Odoo domain ANDed with the result.
      vector_col:      embedding column name (default 'ai_embedding';
                       legacy 'embedding' for ai.chat.fact).
      name_field:      display field, default 'display_name'.
      hint_fields:     extra fields the LLM may want — list of names.
                       Returned as part of each row's hints dict.
      min_similarity:  cosine floor (0..1, default 0.35).

    Returns:
      ``{'rows': [...], 'csv': '...'}`` — the LLM should prefer 'csv'.
    """
    if not model or not query:
        return {'error': 'model + query are required'}
    Index = env.get('ai.semantic.index')
    if Index is None:
        return {'error': 'ai.semantic.index service not installed'}
    Model = env.get(model)
    if Model is None:
        return {'error': f'model {model} is not installed'}
    try:
        Model.check_access('read')
    except AccessError:
        return {'error': 'not permitted',
                'note': 'Tell the user they cannot see these records.'}
    # Every argument here is model-chosen (and a record's text can steer
    # the model), while the index builds raw SQL from the column names.
    # Only real, readable, stored fields and the two known vector
    # columns get through.
    if vector_col not in ('ai_embedding', 'embedding'):
        return {'error': 'unsupported vector column'}
    readable = Model.fields_get(attributes=['type'])      # group-filtered
    hint_fields = [f for f in (hint_fields or [])
                   if isinstance(f, str) and f in readable
                   and Model._fields[f].store
                   and Model._fields[f].type not in ('one2many', 'many2many', 'binary')]
    if name_field != 'display_name' and name_field not in readable:
        name_field = 'display_name'
    try:
        rows = Index.sudo().search(
            model, query,
            # fetch extra: hits the user may not see are dropped below
            limit=min(int(limit) * 5, 200), extra_domain=extra_domain,
            vector_col=vector_col, name_field=name_field,
            hint_fields=hint_fields or [],
            min_similarity=float(min_similarity),
        )
    except Exception:
        _logger.info('semantic_search failed on %s', model, exc_info=True)
        return {'error': 'search is unavailable right now'}
    # The index scans the raw table (sudo), so apply the user's record
    # rules to the hits: only rows they could open in the UI survive.
    if rows:
        visible = set(Model.search([('id', 'in', [r['id'] for r in rows])]).ids)
        rows = [r for r in rows if r['id'] in visible][:int(limit)]
    csv = Index.sudo().to_csv(rows, hint_keys=hint_fields or None)
    return {'rows': rows, 'csv': csv, 'count': len(rows), 'model': model}


register('semantic_search', _builtin_semantic_search)

register('date_reference', _builtin_date_reference)
register('echo', _builtin_echo)
register('record_action', _builtin_record_action)
register('screen_button', _builtin_screen_button)
from .query_data import query_data as _builtin_query_data  # noqa: E402
register('query_data', _builtin_query_data)
from .agent_actions import TOOLS as _ACTION_TOOLS  # noqa: E402
for _code, _fn in _ACTION_TOOLS.items():
    register(_code, _fn)
from .generic_data import TOOLS as _GENERIC_TOOLS  # noqa: E402
for _code, _fn in _GENERIC_TOOLS.items():
    register(_code, _fn)
register('data_analysis', _builtin_data_analysis)
register('recent_records', _builtin_recent_records)
register('open_record', _builtin_open_record)
register('open_list', _builtin_open_list)
register('open_pivot', _builtin_open_pivot)
register('open_graph', _builtin_open_graph)
register('open_action', _builtin_open_action)
register('list_my_apps', _builtin_list_my_apps)
register('find_menu', _builtin_find_menu)
from .navigate import navigate as _builtin_navigate  # noqa: E402
register('navigate', _builtin_navigate)
register('explain_screen', _builtin_explain_screen)
register('hr_attendance_missing_today', _builtin_hr_attendance_missing_today)
register('hr_leave_pending', _builtin_hr_leave_pending)
register('hr_attendance_open_shifts', _builtin_hr_attendance_open_shifts)
