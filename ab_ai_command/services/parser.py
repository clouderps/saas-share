# -*- coding: utf-8 -*-
"""Tolerant command parser.

Only the *verb* is parsed deterministically. Everything after it is free
text that gets a best-effort ``key: value`` sweep; whatever the sweep
cannot fill is left for the agent to extract from the raw remainder.

That split is deliberate. A rigid grammar fails on any deviation and
forces users to learn our syntax, which is the opposite of what the
assistant is for. These must all reach the same place::

    /create quote partner: abdalmola; date: 3/8/26; items: 2x latte
    /create quote for abdalmola tomorrow, two lattes
    اعمل عرض سعر لعبدالمولى بكرة

The first is fast to type for someone who does it daily. The second and
third are what everyone else writes. Neither is privileged.

No Odoo imports here on purpose — the parser is a pure function so it
can be unit-tested without a database.
"""
from __future__ import annotations

import re

#: Pair separators. Newline counts so a pasted multi-line order works.
_SPLIT = re.compile(r'[;\n]+')

#: ``key: value`` — the key is short and wordy ("partner name", "تاريخ"),
#: the colon may be padded ("date :3/8/26" is common when typing fast).
_PAIR = re.compile(r'^\s*([\w؀-ۿ][\w؀-ۿ \-_/]{0,28}?)\s*[:：]\s*(.*)$',
                   re.UNICODE)

#: Leading slash is optional — "/create quote" and "create quote" are
#: the same command.
_VERB_PREFIX = re.compile(r'^\s*[/\\]?\s*')


def normalise_key(key):
    """Fold a user-typed key to its comparison form.

    Lowercase, collapse whitespace, drop Arabic diacritics and unify
    alef/ya variants so "عميل" typed three different ways still matches
    one alias.
    """
    if not key:
        return ''
    k = key.strip().lower()
    k = re.sub(r'[ً-ٟـ]', '', k)      # tashkeel + tatweel
    k = k.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    k = k.replace('ى', 'ي').replace('ة', 'ه')
    k = re.sub(r'[\s_\-]+', ' ', k)
    return k.strip()


def match_verb(text, verbs):
    """Return (verb, remainder) for the longest verb that ``text`` starts
    with, else (None, text).

    Longest-first matters: "create quote" must win over "create" when
    both are registered, otherwise the more specific command is
    unreachable.
    """
    if not text:
        return None, ''
    stripped = _VERB_PREFIX.sub('', text, count=1)
    low = stripped.lower()
    for verb in sorted(verbs, key=len, reverse=True):
        v = verb.strip().lower()
        if not v:
            continue
        if low.startswith(v):
            tail = stripped[len(v):]
            # Require a boundary so "/create quotes" does not match the
            # verb "create quote" and silently drop the "s".
            if tail[:1] and tail[:1].isalnum():
                continue
            return verb, tail.strip(' ,،:;')
    return None, text


def sweep_pairs(text, alias_map):
    """Extract ``key: value`` pairs from free text.

    ``alias_map`` maps a normalised alias to a canonical field name.
    Returns ``(pairs, leftover)`` — leftover is every chunk that did not
    look like a pair, joined back together, and is what gets handed to
    the model.
    """
    pairs, leftover = {}, []
    if not text:
        return pairs, ''

    # Normalise the map defensively. Callers build alias lists by hand
    # ('أصناف', 'Partner Name') and an un-normalised key silently never
    # matches, which looks like the parser ignoring a field.
    alias_map = {normalise_key(k): v for k, v in (alias_map or {}).items()}

    for chunk in _SPLIT.split(text):
        if not chunk.strip():
            continue
        m = _PAIR.match(chunk)
        if not m:
            leftover.append(chunk.strip())
            continue
        raw_key, value = m.group(1), m.group(2).strip()
        field = alias_map.get(normalise_key(raw_key))
        if field and value:
            # First occurrence wins; a repeated key is more likely a typo
            # than an intent to overwrite.
            pairs.setdefault(field, value)
        else:
            # Unknown key — keep the whole chunk as context rather than
            # dropping it. "note: call before delivery" is meaningful
            # even when no field is called "note".
            leftover.append(chunk.strip())
    return pairs, ' ; '.join(leftover).strip()


def parse(text, verbs, alias_map):
    """Full parse. Returns a dict:

        verb      matched verb, or None
        pairs     {canonical_field: raw string value}
        leftover  unparsed remainder, for the model to interpret
        raw       the original text
    """
    verb, rest = match_verb(text or '', verbs)
    pairs, leftover = sweep_pairs(rest, alias_map) if verb else ({}, (text or '').strip())
    return {'verb': verb, 'pairs': pairs, 'leftover': leftover, 'raw': text or ''}


def looks_like_command(text):
    """True when the user explicitly used the slash form.

    Used to decide whether an unmatched verb deserves "no such command"
    rather than being quietly treated as an ordinary question.
    """
    return bool(text) and text.lstrip().startswith(('/', '\\'))
