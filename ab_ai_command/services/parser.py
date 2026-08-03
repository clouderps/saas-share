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
#: U+061B is the Arabic semicolon — it is what an Arabic keyboard layout
#: actually emits, so a user typing the command in Arabic never produces
#: the ASCII ";" and the whole line used to collapse into one pair.
_SPLIT = re.compile('[;؛\n]+')

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


#: Prepositions people put before a value: "for abdalmola", "to Acme",
#: "لـ عبدالمولى". They carry no meaning for us and would otherwise end
#: up inside the name we search for.
_LEAD_PREP = re.compile(r'^\s*(?:for|to|from|of|لـ|ل|الى|إلى|من)\s+',
                        re.I | re.U)


def strip_leading_preposition(value):
    """'for abdalmola' → 'abdalmola'. Applied to values, never keys."""
    return _LEAD_PREP.sub('', (value or '').strip(), count=1).strip()


def split_on_aliases(text, alias_map, max_alias_words=3):
    """Split unpunctuated text at the alias words inside it.

    "for abdalmola items services price 90" has no separator, so the
    whole tail used to land in the first field. Walking the words and
    starting a new pair whenever one matches an alias recovers what the
    user meant without asking them to add semicolons they never think
    about.

    Longest alias wins at each position, so "partner name" binds as one
    key rather than "partner" leaving "name" in the value. Returns
    ``(pairs, leading)`` — leading is anything before the first alias.
    """
    words = (text or '').split()
    if not words:
        return {}, ''

    marks = []                      # (word index, field, alias length)
    i = 0
    while i < len(words):
        for take in range(min(max_alias_words, len(words) - i), 0, -1):
            field = alias_map.get(normalise_key(' '.join(words[i:i + take])))
            if field:
                marks.append((i, field, take))
                i += take
                break
        else:
            i += 1

    if not marks:
        return {}, ' '.join(words)

    leading = ' '.join(words[:marks[0][0]])
    pairs = {}
    for n, (start, field, take) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(words)
        value = strip_leading_preposition(' '.join(words[start + take:end]))
        if value:
            pairs.setdefault(field, value)
    return pairs, leading


def _match_bare_alias(chunk, alias_map):
    """``partner abdalmola`` → ('partner_id', 'abdalmola').

    Matches the LONGEST alias that prefixes the chunk, so "partner name
    abdalmola" binds the whole two-word alias rather than leaving "name"
    glued to the value.
    """
    words = (chunk or '').strip().split()
    if len(words) < 2:
        return None, None
    # Try the longest prefix first — aliases are at most a few words.
    for take in range(min(4, len(words) - 1), 0, -1):
        field = alias_map.get(normalise_key(' '.join(words[:take])))
        if field:
            return field, strip_leading_preposition(' '.join(words[take:]))
    return None, None


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
            # No colon. People type "partner abdalmola" as often as
            # "partner: abdalmola", and a whole sentence may carry
            # several fields with no punctuation at all.
            found, leading = split_on_aliases(chunk, alias_map)
            if found:
                for field, value in found.items():
                    pairs.setdefault(field, value)
                if leading:
                    leftover.append(leading)
            else:
                leftover.append(chunk.strip())
            continue
        raw_key, value = m.group(1), strip_leading_preposition(m.group(2))
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
