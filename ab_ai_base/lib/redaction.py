# -*- coding: utf-8 -*-
"""Pure PII redaction library — no Odoo, no gateway dependency.

Ported from saas-ai/ab_ai_gateway/models/ai_guardrails.py so the direct
provider path in ab_ai_base (tenant with its own key) gets the same
protection the central gateway applies. The gateway can switch to this
module with ``from odoo.addons.ab_ai_base.lib import redaction`` (it
already depends on ab_ai_base) and drop its private pattern table.

Differences from the gateway copy (deliberate):
  * Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits are matched
    too — they are normalised to ASCII on a shadow copy, matches are
    located there and the same spans are replaced in the original text
    (the translation is 1:1 per character, so spans line up).
  * Digit patterns use ``(?<!\\d)``/``(?!\\d)`` instead of ``\\b`` — in
    Arabic text a number glued to a word (``رقم1012345678``) has no word
    boundary because both sides are ``\\w``.
"""

import re

_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate('٠١٢٣٤٥٦٧٨٩')}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate('۰۱۲۳۴۵۶۷۸۹')})

# (label, regex, placeholder). Order matters: specific before generic so
# an IBAN isn't half-eaten by the card / national-id patterns.
PII_PATTERNS = [
    ('iban', re.compile(r'(?<![A-Za-z0-9])SA\d{2}(?:[ ]?[0-9A-Z]{4}){5}(?![0-9A-Za-z])', re.IGNORECASE),
     '[REDACTED_IBAN]'),
    ('email', re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}'),
     '[REDACTED_EMAIL]'),
    ('credit_card', re.compile(r'(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)'), '[REDACTED_CARD]'),
    ('vat_tin', re.compile(r'(?<!\d)3\d{13}3(?!\d)'), '[REDACTED_VAT]'),
    ('saudi_national_id', re.compile(r'(?<!\d)[12]\d{9}(?!\d)'), '[REDACTED_ID]'),
    ('phone_intl', re.compile(r'(?<![\d+])\+\d[\d \-()]{7,}\d(?!\d)'), '[REDACTED_PHONE]'),
    ('phone_ksa', re.compile(r'(?<!\d)05\d{8}(?!\d)'), '[REDACTED_PHONE]'),
]

PROMPT_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(?:all\s+)?(?:previous|prior|the\s+above)\s+(?:instructions?|rules?|prompts?)', re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+", re.IGNORECASE),
    re.compile(r'(?:disregard|forget)\s+(?:all\s+)?(?:previous|prior|the\s+above)', re.IGNORECASE),
    re.compile(r'reveal\s+(?:your\s+)?(?:system\s+)?prompt', re.IGNORECASE),
    re.compile(r'(?:DAN|do\s+anything\s+now)\s+mode', re.IGNORECASE),
    re.compile(r'تجاهل\s+(?:كل|جميع)?\s*(?:التعليمات|الأوامر)\s+(?:السابقة|أعلاه)'),
]


def luhn_ok(candidate):
    digits = [int(d) for d in candidate if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def normalize_digits(text):
    return text.translate(_DIGIT_MAP)


def redact(text):
    """Return ``(redacted_text, count, types_set)``. Non-str/empty → as-is."""
    if not text or not isinstance(text, str):
        return text or '', 0, set()
    original, shadow = text, normalize_digits(text)
    count, types = 0, set()
    for label, pattern, placeholder in PII_PATTERNS:
        spans = [m.span() for m in pattern.finditer(shadow)
                 if label != 'credit_card' or luhn_ok(m.group(0).translate(_DIGIT_MAP))]
        if not spans:
            continue
        count += len(spans)
        types.add(label)
        for start, end in reversed(spans):
            original = original[:start] + placeholder + original[end:]
            shadow = shadow[:start] + placeholder + shadow[end:]
    return original, count, types


def detect_prompt_injection(text):
    """Return ``(is_suspicious, snippet)`` — heuristic, never blocks."""
    if not text or not isinstance(text, str):
        return False, ''
    for pattern in PROMPT_INJECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            return True, m.group(0)[:80]
    return False, ''
