# -*- coding: utf-8 -*-
"""Phase H §3.9 — inline citation rendering.

Native pattern: model emits `[SOURCE:42]` markers in the response;
post-processor replaces each with a numeric superscript and appends
a numbered list of source titles + links.

Adapted for our stack:
  * accepts any source identifier (attachment id, fact id, URL)
  * filters out inaccessible-by-ACL sources per user
  * returns plain markdown — the existing AiMarkdown renderer handles
    sanitisation
"""
from __future__ import annotations

import re

_SRC_RE = re.compile(r'\[SOURCE:([^\]]+)\]')


def apply_numeric_citations(text, source_lookup):
    """Replace [SOURCE:X] markers with numeric superscripts.

    Args:
        text: model response containing optional [SOURCE:X] markers
        source_lookup: dict {raw_key: {'name': str, 'url': str}} —
            keys present here are rendered; missing keys are stripped.

    Returns:
        (rewritten_text, ordered_sources) where ordered_sources is a
        list of dicts in citation order (numbered 1..N).
    """
    if not text:
        return text, []

    seen: dict = {}
    ordered = []

    def _replace(match):
        key = match.group(1).strip()
        meta = source_lookup.get(key)
        if not meta:
            return ''
        if key not in seen:
            seen[key] = len(seen) + 1
            ordered.append({'n': seen[key], 'key': key, **meta})
        return f'<sup>[{seen[key]}]</sup>'

    rewritten = _SRC_RE.sub(_replace, text)

    if ordered:
        appendix = '\n\n---\n**Sources:**\n'
        for src in ordered:
            url = src.get('url') or ''
            label = src.get('name') or src['key']
            line = (f'<sup>[{src["n"]}]</sup> [{label}]({url})'
                    if url else f'<sup>[{src["n"]}]</sup> {label}')
            appendix += line + '\n'
        rewritten += appendix

    return rewritten, ordered
