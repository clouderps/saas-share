# -*- coding: utf-8 -*-
"""Turn what the user typed into real records.

Every resolver returns the same envelope::

    {'value': <id|date|list|None>,
     'display': 'human readable',
     'confidence': 'exact' | 'likely' | 'ambiguous' | 'none',
     'alternatives': [{'id':…, 'name':…}, …],
     'note': 'why, when it failed'}

Nothing here guesses on identity. ``ambiguous`` is a first-class result
that the caller turns into a choice for the user — picking the first of
three partners called "abdalmola" and quietly invoicing them is worse
than asking.

All searches run as the requesting user (no sudo), so record rules and
multi-company scoping apply exactly as they would in the UI.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

MAX_ALTERNATIVES = 5


def _envelope(value=None, display='', confidence='none', alternatives=None,
              note='', can_create=False, proposed=None):
    """``can_create`` marks a miss that the user could resolve by making
    the record. It is only ever an *offer* — creation happens on a
    second, explicit call. Silently creating on a miss turns every typo
    into a duplicate partner or a junk product in the catalogue, which
    is why ab_scan_docs gates the same behaviour behind a config flag
    and routes products through an approval workflow."""
    return {
        'value': value,
        'display': display,
        'confidence': confidence,
        'alternatives': alternatives or [],
        'note': note,
        'can_create': can_create,
        'proposed': proposed or {},
    }


# ─── Partner ─────────────────────────────────────────────────────────

def resolve_partner(env, text, customer=None):
    """Name / reference / VAT → res.partner.

    Escalates exact → reference → fuzzy. Stops at the first tier that
    yields exactly one hit; more than one at any tier is ambiguous, and
    ambiguity is returned, never resolved by picking.
    """
    text = (text or '').strip()
    if not text:
        return _envelope(note='no partner given')

    Partner = env['res.partner']
    domain = []
    if customer is True:
        domain = [('customer_rank', '>', 0)]
    elif customer is False:
        domain = [('supplier_rank', '>', 0)]

    def hits(extra, limit=MAX_ALTERNATIVES + 1):
        try:
            return Partner.search(domain + extra, limit=limit)
        except Exception:
            _logger.debug('partner search failed', exc_info=True)
            return Partner.browse()

    # 1. Exact name — the common case when the user copied it.
    found = hits([('name', '=ilike', text)])
    tier = 'exact'
    # 2. Reference or VAT — unambiguous business identifiers.
    if not found:
        found = hits(['|', ('ref', '=ilike', text), ('vat', '=ilike', text)])
    # 3. Fuzzy, the "abdalmola" case.
    if not found:
        found = hits([('name', 'ilike', text)])
        tier = 'likely'

    if not found:
        # Widened search ignoring the customer/supplier filter tells the
        # user something useful: the partner exists but is not set up as
        # a customer, which is a different fix from "does not exist".
        if domain:
            elsewhere = Partner.search([('name', 'ilike', text)], limit=1)
            if elsewhere:
                return _envelope(
                    note=('"%s" exists but is not marked as a %s.'
                          % (text, 'customer' if customer else 'vendor')),
                    can_create=False)
        return _envelope(
            note='no partner matches "%s"' % text,
            can_create=True,
            proposed={'name': text,
                      'customer_rank': 1 if customer is not False else 0,
                      'supplier_rank': 1 if customer is False else 0})

    if len(found) > 1:
        return _envelope(
            confidence='ambiguous',
            alternatives=[{'id': p.id, 'name': p.display_name}
                          for p in found[:MAX_ALTERNATIVES]],
            note='%d partners match "%s"' % (len(found), text))

    return _envelope(found.id, found.display_name, tier)


# ─── Date ────────────────────────────────────────────────────────────

_RELATIVE = {
    'today': 0, 'اليوم': 0,
    'tomorrow': 1, 'غدا': 1, 'غدًا': 1, 'بكرة': 1, 'بكره': 1,
    'yesterday': -1, 'امس': -1, 'أمس': -1,
}

_NUMERIC = re.compile(r'^\s*(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})\s*$')


def resolve_date(env, text, today=None):
    """Parse a date the way the user's locale reads it.

    ``3/8/26`` is 3 August in Saudi Arabia and 8 March in the US. We
    resolve day-first for every locale except ``en_US`` — and the caller
    is expected to print the result in long form so a wrong reading is
    visible before it is committed to anything.
    """
    text = (text or '').strip()
    today = today or date.today()
    if not text:
        return _envelope(note='no date given')

    key = text.lower().strip()
    if key in _RELATIVE:
        d = today + timedelta(days=_RELATIVE[key])
        return _envelope(d, d.strftime('%d %B %Y'), 'exact')

    m = _NUMERIC.match(text)
    if m:
        a, b, c = (int(x) for x in m.groups())

        def build(year, month, day):
            if year < 100:                  # 26 → 2026
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None

        if a > 31:
            # 2026/08/03 — the year is explicit, so there is nothing to
            # guess and nothing to warn about.
            d = build(a, b, c)
            if not d:
                return _envelope(note='"%s" is not a valid date' % text)
            return _envelope(d, d.strftime('%d %B %Y'), 'exact')

        day_first = not (env.user.lang or 'en_US').startswith('en_US')
        primary = build(c, b, a) if day_first else build(c, a, b)
        other = build(c, a, b) if day_first else build(c, b, a)

        if not primary:
            # The locale reading is impossible (25 as a month), so the
            # user obviously meant the other one. Taking it beats
            # rejecting a date whose intent is unambiguous.
            if other:
                return _envelope(other, other.strftime('%d %B %Y'), 'exact')
            return _envelope(note='"%s" is not a valid date' % text)

        # Ambiguous only when the OTHER reading is also a real date and
        # differs — then the user has to confirm which they meant.
        if other and other != primary:
            return _envelope(
                primary, primary.strftime('%d %B %Y'), 'likely',
                note=('read as %s — confirm if you meant %s'
                      % (primary.strftime('%d %B %Y'),
                         other.strftime('%d %B %Y'))))
        return _envelope(primary, primary.strftime('%d %B %Y'), 'exact')

    for fmt in ('%Y-%m-%d', '%d %B %Y', '%d %b %Y', '%B %d %Y', '%b %d %Y'):
        try:
            from datetime import datetime
            d = datetime.strptime(text, fmt).date()
            return _envelope(d, d.strftime('%d %B %Y'), 'exact')
        except ValueError:
            continue

    return _envelope(note='could not read "%s" as a date' % text)


# ─── Products ────────────────────────────────────────────────────────

_QTY_PREFIX = re.compile(r'^\s*(\d+(?:[.,]\d+)?)\s*[x×*]\s*(.+)$', re.I)
_QTY_SUFFIX = re.compile(r'^(.+?)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*$', re.I)
_QTY_PLAIN = re.compile(r'^(.+?)\s+(\d+(?:[.,]\d+)?)\s*$')


_PRICE = re.compile(r'^(.*?)\s*[@]\s*(\d+(?:[.,]\d+)?)\s*$')


def split_price(chunk):
    """``2x latte @ 14`` → (14.0, '2x latte').

    Lets the user price an item inline, which matters when the product
    does not exist yet: creating it with a silent price of 0 puts a
    zero-value line on a real quotation.
    """
    m = _PRICE.match((chunk or '').strip())
    if not m:
        return None, (chunk or '').strip()
    try:
        return float(m.group(2).replace(',', '.')), m.group(1).strip()
    except ValueError:
        return None, (chunk or '').strip()


def split_quantity(chunk):
    """``2x latte`` / ``latte x2`` / ``latte 2`` → (qty, 'latte')."""
    chunk = (chunk or '').strip()
    for rx, qty_first in ((_QTY_PREFIX, True), (_QTY_SUFFIX, False), (_QTY_PLAIN, False)):
        m = rx.match(chunk)
        if m:
            raw_qty = m.group(1) if qty_first else m.group(2)
            name = m.group(2) if qty_first else m.group(1)
            try:
                return float(raw_qty.replace(',', '.')), name.strip()
            except ValueError:
                break
    return 1.0, chunk


def resolve_product(env, text):
    """One product line.

    Barcode is checked first and matched EXACTLY. A barcode that
    fuzzy-matches is a wrong item on an order — scanning 6281000010 must
    never land on 62810000109. Only the name tier is allowed to be
    fuzzy, and only when it returns a single hit.
    """
    text = (text or '').strip()
    if not text:
        return _envelope(note='empty product')

    Product = env['product.product']

    def hits(domain, limit=MAX_ALTERNATIVES + 1):
        try:
            return Product.search(domain, limit=limit)
        except Exception:
            _logger.debug('product search failed', exc_info=True)
            return Product.browse()

    # 1. Barcode — exact only, never ilike.
    found = hits([('barcode', '=', text)], limit=2)
    if found:
        if len(found) > 1:                  # duplicate barcodes in data
            return _envelope(
                confidence='ambiguous',
                alternatives=[{'id': p.id, 'name': p.display_name} for p in found],
                note='barcode %s is on more than one product' % text)
        return _envelope(found.id, found.display_name, 'exact')

    # 2. Internal reference — also exact.
    found = hits([('default_code', '=ilike', text)], limit=2)
    if len(found) == 1:
        return _envelope(found.id, found.display_name, 'exact')

    # 3. Exact name.
    found = hits([('name', '=ilike', text)])
    tier = 'exact'
    # 4. Fuzzy name — the only tier allowed to guess, and only alone.
    if not found:
        found = hits([('name', 'ilike', text)])
        tier = 'likely'

    if not found:
        return _envelope(
            note='no product matches "%s"' % text,
            can_create=True,
            proposed={'name': text})
    if len(found) > 1:
        return _envelope(
            confidence='ambiguous',
            alternatives=[{'id': p.id, 'name': p.display_name}
                          for p in found[:MAX_ALTERNATIVES]],
            note='%d products match "%s"' % (len(found), text))
    return _envelope(found.id, found.display_name, tier)


def resolve_product_lines(env, text):
    """Comma-separated order lines → resolved lines + unresolved chunks.

    Returns ``(lines, problems)`` where a line is
    ``{'product_id':…, 'name':…, 'qty':…}`` and a problem carries the
    original chunk plus the failing envelope, so the caller can ask about
    exactly the item that did not resolve instead of rejecting the whole
    command.
    """
    lines, problems = [], []
    for chunk in re.split(r'[,،]+', text or ''):
        chunk = chunk.strip()
        if not chunk:
            continue
        price, rest = split_price(chunk)
        qty, name = split_quantity(rest)
        res = resolve_product(env, name)
        if res['value'] and res['confidence'] in ('exact', 'likely'):
            line = {'product_id': res['value'], 'name': res['display'],
                    'qty': qty, 'confidence': res['confidence']}
            if price is not None:
                line['price_unit'] = price
            lines.append(line)
        else:
            if res.get('can_create') and price is not None:
                res['proposed']['list_price'] = price
            problems.append({'chunk': chunk, 'query': name,
                             'qty': qty, 'price': price, 'result': res})
    return lines, problems
