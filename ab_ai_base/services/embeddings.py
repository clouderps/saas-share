# -*- coding: utf-8 -*-
"""T.2a — canonical embedding helper.

Promoted from saas-client/ab_ai_chatbot/services/embeddings.py so that
non-tenant code (DBCLOUD gateway, daily report, any model with a
``Vector`` field) can embed text without depending back into the
chatbot module.

What it does:
  * batches inputs to the 100-per-call provider API limit
  * detects whether the cluster has pgvector installed
  * serialises / deserialises vectors for both pgvector and the
    JSON-text fallback path
  * exposes a python-side cosine for the fallback path
  * idempotently provisions a vector(768)/text embedding column +
    HNSW/IVFFlat index on any table (replaces the inline ALTER TABLE
    dance every consumer model used to copy)

Callers import via either path — both resolve to this module:
  * ``from odoo.addons.ab_ai_base.services import embeddings``  (preferred)
  * ``from ..services import embeddings`` inside ab_ai_chatbot (shim re-export)
"""
from __future__ import annotations

import json
import logging
import math
from functools import lru_cache

_logger = logging.getLogger(__name__)


EMBED_DIM = 768  # text-embedding-004 native — Matryoshka-truncated for non-Google


# ─── Embedding ─────────────────────────────────────────────────────

def embed_one(env, text: str) -> list[float] | None:
    """Embed a single text. Returns the vector or None on failure."""
    if not text or not text.strip():
        return None
    vectors = embed_many(env, [text.strip()])
    return vectors[0] if vectors else None


def embed_many(env, texts: list[str]) -> list[list[float]]:
    """Embed a batch. Auto-splits into 100-per-call chunks. Returns
    a list of vectors (same length as ``texts``). On failure of any
    chunk the corresponding slot is ``[]`` so caller indexing stays
    aligned."""
    if not texts:
        return []
    out: list[list[float]] = []

    # Path A: gateway-routed (tenant containers). The ai.client.config
    # central path handles auth + per-tenant budget.
    Cfg = env.get('ai.client.config')
    gateway = None
    if Cfg is not None:
        try:
            gateway = Cfg.get_config()
        except Exception:
            gateway = None

    # Path B: direct provider (DBCLOUD, dev). ai.provider.service
    # implements call_embedding() against the active provider config.
    direct = None
    if gateway is None:
        direct = env.get('ai.provider.service')

    chunk = 100
    for i in range(0, len(texts), chunk):
        batch = [t or '' for t in texts[i:i + chunk]]
        try:
            if gateway is not None:
                vectors, _usage = gateway.call_embedding(batch)
            elif direct is not None:
                vectors, _usage = direct.sudo().call_embedding(batch)
            else:
                vectors = [[] for _ in batch]
        except Exception:
            _logger.warning('embed_many: chunk %d failed', i // chunk, exc_info=True)
            vectors = [[] for _ in batch]
        while len(vectors) < len(batch):
            vectors.append([])
        out.extend(vectors[:len(batch)])
    return out


# ─── pgvector capability detection ─────────────────────────────────

@lru_cache(maxsize=1)
def has_pgvector(cr) -> bool:
    """True when the running cluster has the pgvector extension."""
    try:
        cr.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        return cr.fetchone() is not None
    except Exception:
        return False


def serialize_vector(vec: list[float], use_pgvector: bool) -> str | None:
    """Format a vector for storage."""
    if not vec:
        return None
    if use_pgvector:
        return '[' + ','.join(f'{x:.7g}' for x in vec) + ']'
    return json.dumps([float(x) for x in vec])


def deserialize_vector(s) -> list[float] | None:
    """Parse a stored vector — handles both pgvector and JSON text."""
    if not s:
        return None
    if isinstance(s, (list, tuple)):
        return list(s)
    s = s.strip() if hasattr(s, 'strip') else s
    if not s:
        return None
    try:
        return list(json.loads(s))
    except (ValueError, TypeError):
        pass
    try:
        if s.startswith('[') and s.endswith(']'):
            return [float(x) for x in s[1:-1].split(',') if x.strip()]
    except (ValueError, TypeError):
        pass
    return None


# ─── Cosine (python fallback path) ─────────────────────────────────

def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na * nb)
    return dot / denom if denom else 0.0


# ─── pgvector column + index provisioning (T.2a) ───────────────────

def provision_embedding_column(cr, table, *,
                               column='ai_embedding',
                               dim=EMBED_DIM,
                               index_kind='hnsw',
                               index_name=None) -> bool:
    """Idempotently provision a vector(dim) / text embedding column +
    HNSW (or IVFFlat) cosine index on ``table``.

    Replaces the inline ALTER TABLE dance every consumer copy-pasted.
    Returns True iff pgvector was used (so the caller knows whether
    to insert ``[a,b,c]`` literals or JSON text).

    Args:
        cr: odoo cursor.
        table: SQL table name, e.g. 'crm_lead'.
        column: column name (default 'ai_embedding').
        dim: vector dimension (default 768).
        index_kind: 'hnsw' (default, scales to millions) or 'ivfflat'
                    (fine for <100k rows, older pgvector clusters).
        index_name: explicit index name; default '<table>_<column>_idx'.

    Behavior:
      * If pgvector unavailable → column type is ``text`` (JSON fallback).
      * If column already exists → does nothing.
      * If index can't be created (no pgvector, ext not loaded, conflicting
        type) → logs and continues — the column still works for the
        Python cosine path.
    """
    has_vec = has_pgvector(cr)
    if not has_vec:
        # Try to enable on the fly (same logic the chat_fact init uses).
        try:
            cr.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            if cr.fetchone():
                try:
                    with cr.savepoint(flush=False):
                        cr.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    has_vec = True
                except Exception:
                    _logger.info(
                        'pgvector available but CREATE EXTENSION failed — '
                        '%s.%s will use JSON-text fallback', table, column)
        except Exception:
            pass

    # Column.
    has_col = False
    try:
        with cr.savepoint(flush=False):
            cr.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
            """, (table, column))
            has_col = cr.fetchone() is not None
    except Exception:
        has_col = False

    if not has_col:
        col_type = f'vector({int(dim)})' if has_vec else 'text'
        try:
            with cr.savepoint(flush=False):
                cr.execute(
                    f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type}'
                )
            _logger.info('Provisioned %s.%s (%s)', table, column, col_type)
        except Exception:
            _logger.warning('Failed to add %s.%s column', table, column, exc_info=True)
            return has_vec

    # Index — only meaningful when pgvector is live.
    if has_vec:
        idx = index_name or f'{table}_{column}_idx'
        # HNSW is the default — production-grade, no list-count tuning.
        # IVFFlat needs WITH (lists = N) — N ≈ sqrt(rows). Caller can
        # override via index_kind='ivfflat' when row count is bounded.
        if index_kind == 'ivfflat':
            ddl = (f'CREATE INDEX IF NOT EXISTS "{idx}" '
                   f'ON "{table}" USING ivfflat ("{column}" vector_cosine_ops) '
                   f'WITH (lists = 50)')
        else:
            ddl = (f'CREATE INDEX IF NOT EXISTS "{idx}" '
                   f'ON "{table}" USING hnsw ("{column}" vector_cosine_ops)')
        try:
            with cr.savepoint(flush=False):
                cr.execute(ddl)
        except Exception:
            _logger.info('Could not create %s on %s.%s (likely older pgvector)',
                         index_kind, table, column, exc_info=True)
    return has_vec
