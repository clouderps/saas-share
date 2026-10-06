# -*- coding: utf-8 -*-
"""`navigate` — resolve "open invoice INV/2026/0012" / "افتح العميل عبدالمولى" /
"show unpaid invoices" / "go to employees" into a typed navigation directive.

Everything resolves AS THE USER (no sudo): a model the user cannot read is
"not available", and search() applies their record rules, so a record they
cannot see is never found — not even its id leaks.

The directive is the only thing the web client executes, and it accepts
three shapes (record / list / menu). The model never supplies a domain,
URL or action dict: lists come from named server-side presets, menus go
through the user's own visible menu tree.
"""
import logging
import re

from odoo import fields

_logger = logging.getLogger(__name__)

CHOICE_LIMIT = 6

# alias word -> (model, base domain). Arabic and English, singular/plural.
_INVOICE = ('account.move', [('move_type', 'in', ('out_invoice', 'out_refund'))])
_BILL = ('account.move', [('move_type', 'in', ('in_invoice', 'in_refund'))])
_PARTNER = ('res.partner', [])
_EMPLOYEE = ('hr.employee', [])
_SALE = ('sale.order', [])
_PURCHASE = ('purchase.order', [])
_PRODUCT = ('product.template', [])
_LEAD = ('crm.lead', [])
_PAYMENT = ('account.payment', [])
_PICKING = ('stock.picking', [])
_POS_ORDER = ('pos.order', [])
_ENTRY = ('account.move', [])

TARGETS = {
    'invoice': _INVOICE, 'invoices': _INVOICE, 'credit note': _INVOICE,
    'فاتورة': _INVOICE, 'فاتوره': _INVOICE, 'الفاتورة': _INVOICE, 'فواتير': _INVOICE,
    'bill': _BILL, 'bills': _BILL, 'vendor bill': _BILL, 'فاتورة مورد': _BILL, 'فاتورة شراء': _BILL,
    'contact': _PARTNER, 'contacts': _PARTNER, 'customer': _PARTNER, 'customers': _PARTNER,
    'vendor': _PARTNER, 'supplier': _PARTNER, 'partner': _PARTNER,
    'عميل': _PARTNER, 'العميل': _PARTNER, 'عملاء': _PARTNER, 'جهة اتصال': _PARTNER,
    'جهة الاتصال': _PARTNER, 'مورد': _PARTNER, 'المورد': _PARTNER, 'شريك': _PARTNER,
    'employee': _EMPLOYEE, 'employees': _EMPLOYEE, 'موظف': _EMPLOYEE, 'الموظف': _EMPLOYEE,
    'sale order': _SALE, 'sales order': _SALE, 'quotation': _SALE, 'order': _SALE,
    'أمر بيع': _SALE, 'امر بيع': _SALE, 'عرض سعر': _SALE, 'طلب': _SALE,
    'purchase order': _PURCHASE, 'purchase': _PURCHASE, 'أمر شراء': _PURCHASE, 'امر شراء': _PURCHASE,
    'product': _PRODUCT, 'products': _PRODUCT, 'منتج': _PRODUCT, 'المنتج': _PRODUCT, 'صنف': _PRODUCT,
    'lead': _LEAD, 'opportunity': _LEAD, 'فرصة': _LEAD,
    'payment': _PAYMENT, 'دفعة': _PAYMENT, 'سند': _PAYMENT,
    'transfer': _PICKING, 'delivery': _PICKING, 'receipt': _PICKING, 'picking': _PICKING,
    'تحويل': _PICKING, 'توصيل': _PICKING, 'استلام': _PICKING,
    'pos order': _POS_ORDER, 'طلب نقطة بيع': _POS_ORDER,
    'journal entry': _ENTRY, 'entry': _ENTRY, 'قيد': _ENTRY,
}
ALLOWED_MODELS = frozenset(m for m, _d in TARGETS.values())


def _today(env):
    return fields.Date.context_today(env.user)


# preset code -> (model, label, domain builder). The ONLY list domains the
# client will ever receive: the model chooses a name, never a domain.
PRESETS = {
    'unpaid_invoices': ('account.move', 'Unpaid invoices', lambda env: [
        ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
        ('payment_state', 'in', ('not_paid', 'partial'))]),
    'overdue_invoices': ('account.move', 'Overdue invoices', lambda env: [
        ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
        ('payment_state', 'in', ('not_paid', 'partial')),
        ('invoice_date_due', '<', _today(env))]),
    'draft_invoices': ('account.move', 'Draft invoices', lambda env: [
        ('move_type', '=', 'out_invoice'), ('state', '=', 'draft')]),
    'customer_invoices': ('account.move', 'Customer invoices', lambda env: [
        ('move_type', 'in', ('out_invoice', 'out_refund'))]),
    'unpaid_bills': ('account.move', 'Unpaid bills', lambda env: [
        ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
        ('payment_state', 'in', ('not_paid', 'partial'))]),
    'vendor_bills': ('account.move', 'Vendor bills', lambda env: [
        ('move_type', 'in', ('in_invoice', 'in_refund'))]),
    'customers': ('res.partner', 'Customers', lambda env: [('customer_rank', '>', 0)]),
    'vendors': ('res.partner', 'Vendors', lambda env: [('supplier_rank', '>', 0)]),
    'contacts': ('res.partner', 'Contacts', lambda env: []),
    'employees': ('hr.employee', 'Employees', lambda env: []),
    'quotations': ('sale.order', 'Quotations', lambda env: [('state', 'in', ('draft', 'sent'))]),
    'sale_orders': ('sale.order', 'Sales orders', lambda env: [('state', '=', 'sale')]),
    'my_quotations': ('sale.order', 'My quotations', lambda env: [
        ('state', 'in', ('draft', 'sent')), ('user_id', '=', env.uid)]),
    'purchase_orders': ('purchase.order', 'Purchase orders', lambda env: []),
    'products': ('product.template', 'Products', lambda env: []),
    'pending_leaves': ('hr.leave', 'Leave requests to approve', lambda env: [('state', '=', 'confirm')]),
}

_NOT_AVAILABLE = {'found': False, 'error': 'not available for this user',
                  'note': 'Tell the user this is not available to them. Do not guess.'}


def _resolve_target(target):
    key = re.sub(r'\s+', ' ', str(target or '').strip().lower())
    if key in TARGETS:
        return TARGETS[key]
    if key in ALLOWED_MODELS:               # a technical name from the screen
        return key, []
    for word, spec in TARGETS.items():      # "the invoice", "فاتورة العميل"
        if word in key.split(' ') or (len(word) > 3 and word in key):
            return spec
    return None


def _readable(env, model):
    M = env.get(model)
    return M if M is not None and M.has_access('read') else None


def _record_directive(rec):
    return {'type': 'record', 'model': rec._name, 'res_id': rec.id,
            'label': rec.display_name}


def _detail(rec):
    """A short distinguishing hint for same-named records (fields the
    user can already read on this record)."""
    for fname in ('email', 'phone', 'city', 'ref', 'invoice_date', 'date_order', 'date'):
        fld = rec._fields.get(fname)
        if fld and rec[fname]:
            return str(rec[fname])
    return f'#{rec.id}'


def _record_action(directive):
    return {'type': 'ir.actions.act_window', 'name': directive['label'],
            'res_model': directive['model'], 'res_id': directive['res_id'],
            'view_mode': 'form', 'views': [[False, 'form']], 'target': 'current'}


def _list_action(directive):
    return {'type': 'ir.actions.act_window', 'name': directive['label'],
            'res_model': directive['model'], 'domain': directive['domain'],
            'view_mode': 'list,form', 'views': [[False, 'list'], [False, 'form']],
            'target': 'current'}


def resolve_record(env, target, query):
    spec = _resolve_target(target)
    if not spec:
        return {'found': False, 'error': f'unknown kind of record: {target}',
                'note': 'Use kind="menu" for screens, or ask what they mean.'}
    model, base = spec
    M = _readable(env, model)
    if M is None:
        return dict(_NOT_AVAILABLE)
    q = str(query or '').strip()
    if not q:
        return {'found': False, 'error': 'query required'}
    recs = M.browse()
    try:
        if 'name' in M._fields and M._fields['name'].store:
            recs = M.search(base + [('name', '=ilike', q)], limit=CHOICE_LIMIT)
        if not recs:
            ids = [i for i, _n in M.name_search(q, args=base, operator='ilike',
                                                limit=CHOICE_LIMIT)]
            recs = M.browse(ids)
        if not recs and ' ' in q:
            # "عبدالمولى مصطفى" vs "Abdalmola Mustafa Co." — every word must hit
            dom = list(base)
            for w in q.split():
                dom.append(('display_name', 'ilike', w))
            recs = M.search(dom, limit=CHOICE_LIMIT)
    except Exception:
        _logger.info('navigate: search %s %r failed', model, q, exc_info=True)
        return {'found': False, 'error': 'search failed'}
    if not recs:
        return {'found': False, 'query': q,
                'note': f'Nothing called "{q}" was found. Say so plainly; do not guess another record.'}
    if len(recs) > 1:
        exact = recs.filtered(lambda r: (r.display_name or '').strip().lower() == q.lower())
        if len(exact) == 1:
            recs = exact
    if len(recs) > 1:
        choices = [_record_directive(r) for r in recs]
        labels = [c['label'] for c in choices]
        for c, r in zip(choices, recs):
            if labels.count(c['label']) > 1:       # same name twice: say which is which
                c['label'] = f"{c['label']} · {_detail(r)}"
        return {'found': True, 'ambiguous': True, 'choices': choices,
                'note': 'Several match. Ask which one, listing these names; '
                        'the user can also tap one.'}
    directive = _record_directive(recs)
    return {'found': True, 'navigate': directive, 'action': _record_action(directive),
            'message': f'Opening {directive["label"]}'}


def resolve_list(env, preset):
    spec = PRESETS.get(str(preset or '').strip().lower())
    if not spec:
        return {'found': False, 'error': f'unknown list: {preset}',
                'available': sorted(PRESETS),
                'note': 'Pick one of the available lists, or use kind="menu".'}
    model, label, build = spec
    if _readable(env, model) is None:
        return dict(_NOT_AVAILABLE)
    directive = {'type': 'list', 'model': model, 'preset': preset,
                 'label': env._(label), 'domain': build(env)}
    return {'found': True, 'navigate': directive, 'action': _list_action(directive),
            'message': f'Opening {directive["label"]}'}


def resolve_menu(env, query):
    from .tool_dispatcher import _builtin_find_menu, _builtin_open_action
    found = _builtin_find_menu(env, query=query, limit=CHOICE_LIMIT)
    matches = found.get('matches') or []
    if not matches:
        return {'found': False, **{k: v for k, v in found.items() if k != 'matches'}}
    for m in matches:
        opened = _builtin_open_action(env, xmlid=m['action_xmlid']) if m.get('action_xmlid') else {}
        if opened.get('action'):
            directive = {'type': 'menu', 'menu_id': m['menu_id'], 'label': m['path'] or m['label']}
            return {'found': True, 'navigate': directive, 'action': opened['action'],
                    'message': f'Opening {m["path"]}',
                    'other_matches': [x['path'] for x in matches if x is not m][:3]}
    return dict(_NOT_AVAILABLE)


def navigate(env, agent=None, kind=None, target=None, query=None, preset=None, **_kw):
    """Tool entry point. Never raises."""
    kind = (kind or '').strip().lower()
    if not kind:
        kind = 'list' if preset else ('record' if target and query else 'menu')
    if kind == 'record':
        return resolve_record(env, target or _kw.get('model'), query)
    if kind == 'list':
        return resolve_list(env, preset or query)
    if kind == 'menu':
        return resolve_menu(env, query or target)
    return {'found': False, 'error': 'kind must be record, list or menu'}
