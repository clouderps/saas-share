# -*- coding: utf-8 -*-
"""T.2a — generic semantic-search primitive.

One model, two methods, that the chatbot, daily report and any
future agent can call to do "find records similar to a natural-language
query" without the calling module having to know about pgvector,
HNSW, k-NN syntax, or fallback math.

  env['ai.semantic.index'].search(model_name, query, limit=5,
                                  extra_domain=None,
                                  vector_col='ai_embedding',
                                  name_field='display_name',
                                  hint_fields=None,
                                  min_similarity=0.35)

Returns a list[dict] — ``[{id, name, score, hints: {...}}, ...]`` —
or ``to_csv(rows, hint_keys=None)`` to render the result for the
LLM as ``id|name|score|hint1|hint2`` (40 % smaller than JSON).

Where it slots into the token-reduction plan:
  * replaces ``_org_knowledge_block`` once flag ``ab_ai_agent.lazy_rag``
    is on (it just calls ``search('ai.chat.fact', q)``);
  * powers a generic ``semantic_search`` agent tool that any agent
    can use to find leads / partners / docs without us hand-rolling
    a per-model tool;
  * future-proof for `_record_context_block` → ``semantic_record_neighbors``.

Per the SAAS_AI_TOKEN_REDUCTION_SUMMARY plan this is the keystone
tactic — once the index is live we can retire three always-on
context blocks (4–9 k tokens per hot turn) behind feature flags.
"""
from __future__ import annotations

import logging

from odoo import api, models

from ..services import embeddings as _embed

_logger = logging.getLogger(__name__)


class AISemanticIndex(models.AbstractModel):
    _name = 'ai.semantic.index'
    _description = 'Generic semantic search over any model with an embedding column'

    # ── Provisioning ───────────────────────────────────────────────

    @api.model
    def provision(self, model_name, *,
                  vector_col='ai_embedding',
                  dim=768,
                  index_kind='hnsw'):
        """Idempotently set up the embedding column + index for
        ``model_name``. Safe to call from a model's ``init()``.

        Returns True iff pgvector backed the column (caller can use
        the SQL ``::vector`` path); False means the JSON-text fallback
        is in effect (python cosine path).
        """
        Model = self.env.get(model_name)
        if Model is None:
            raise ValueError(f'Unknown model: {model_name}')
        table = Model._table
        return _embed.provision_embedding_column(
            self.env.cr, table, column=vector_col, dim=dim, index_kind=index_kind,
        )

    # ── Embedding writes ───────────────────────────────────────────

    @api.model
    def embed_records(self, records, *,
                      text_fn=None,
                      vector_col='ai_embedding',
                      stamp_field='ai_embedding_at'):
        """Embed each record's text and persist into ``vector_col``.

        ``text_fn`` defaults to ``rec.display_name``. Supply your own
        for richer prompts (e.g. ``lambda r: f"{r.name}\n{r.email_from}\n{r.description or ''}"``).
        Batches in groups of 100 via ``ab_ai_base.services.embeddings``.

        Records that already have an embedding AND ``stamp_field``
        newer than the source text are skipped (caller's responsibility
        to invalidate the stamp on relevant ``write()``s).
        """
        if not records:
            return 0
        text_fn = text_fn or (lambda r: r.display_name or '')
        cr = self.env.cr
        use_pgvector = _embed.has_pgvector(cr)
        table = records._table

        texts = [text_fn(r) for r in records]
        vectors = _embed.embed_many(self.env, texts)
        if not vectors:
            return 0

        from odoo.fields import Datetime as ODT
        now = ODT.now()
        ok = 0
        for rec, vec in zip(records, vectors):
            if not vec:
                continue
            stored = _embed.serialize_vector(vec, use_pgvector)
            try:
                if use_pgvector:
                    cr.execute(
                        f'UPDATE "{table}" SET "{vector_col}" = %s::vector '
                        f'WHERE id = %s',
                        (stored, rec.id),
                    )
                else:
                    cr.execute(
                        f'UPDATE "{table}" SET "{vector_col}" = %s '
                        f'WHERE id = %s',
                        (stored, rec.id),
                    )
                if stamp_field and stamp_field in records._fields:
                    rec.sudo().write({stamp_field: now})
                ok += 1
            except Exception:
                _logger.warning('embed_records: failed to store vector for %s(%s)',
                                records._name, rec.id, exc_info=True)
        return ok

    # ── k-NN search ────────────────────────────────────────────────

    @api.model
    def search(self, model_name, query, *,
               limit=5,
               extra_domain=None,
               vector_col='ai_embedding',
               name_field='display_name',
               hint_fields=None,
               min_similarity=0.35):
        """Semantic k-NN search over ``model_name``.

        Returns: ``list[dict]`` with keys ``id``, ``name``, ``score``
        (cosine similarity ∈ [0,1], 1 = identical), and ``hints``
        (dict of ``hint_fields`` → value).

        When pgvector is unavailable OR the query can't be embedded,
        returns ``[]`` — the caller should degrade gracefully to a
        keyword path. (We don't fall back to ILIKE here on purpose —
        ai.chat.fact has its own hybrid RR-fusion path; generic search
        across e.g. crm.lead doesn't have an obvious keyword channel
        and a silent ILIKE would surprise the caller.)
        """
        if not query or not query.strip():
            return []
        Model = self.env.get(model_name)
        if Model is None:
            _logger.warning('semantic_index.search: unknown model %s', model_name)
            return []
        if vector_col not in Model._fields and not _has_raw_column(
                self.env.cr, Model._table, vector_col):
            _logger.info(
                'semantic_index.search: %s has no %s column — '
                'call provision(%r) first', model_name, vector_col, model_name)
            return []

        # Embed the query — one network call (cached upstream if same text).
        vec = _embed.embed_one(self.env, query)
        if not vec:
            return []

        cr = self.env.cr
        use_pgvector = _embed.has_pgvector(cr)
        table = Model._table

        # Translate extra_domain → SQL using ORM as the query builder so
        # record rules + multi-company filters apply.
        where_sql, where_params = '', []
        if extra_domain:
            try:
                # Odoo 17+: _search returns a Query object; .from_clause /
                # .where_clause give the raw SQL pieces. Older versions
                # return a plain SELECT — we fall back to a naive id-IN
                # in that case.
                q = Model.sudo()._where_calc(extra_domain, active_test=True)
                _, raw_where, raw_params = q.get_sql()
                if raw_where:
                    where_sql = f' AND {raw_where}'
                    where_params = list(raw_params)
            except Exception:
                ids = Model.sudo().search(extra_domain).ids
                if not ids:
                    return []
                where_sql = f' AND "{table}".id = ANY(%s)'
                where_params = [ids]

        # Score = 1 - cosine_distance(vec, ai_embedding). Distance is
        # the <=> operator; HNSW uses cosine_ops index. ORDER BY <=>
        # is the only index-using ordering.
        # We also gate by ``min_similarity`` to drop "least bad" rows
        # (HNSW always returns k rows even when nothing is relevant).
        hints_select = ''
        hint_fields = hint_fields or []
        for f in hint_fields:
            hints_select += f', "{table}"."{f}"'

        if use_pgvector:
            vec_lit = _embed.serialize_vector(vec, True)
            sql = (
                f'SELECT "{table}".id, '
                f'1 - ("{table}"."{vector_col}" <=> %s::vector) AS score'
                f'{hints_select} '
                f'FROM "{table}" '
                f'WHERE "{table}"."{vector_col}" IS NOT NULL'
                f'{where_sql} '
                f'ORDER BY "{table}"."{vector_col}" <=> %s::vector '
                f'LIMIT %s'
            )
            params = [vec_lit, *where_params, vec_lit, int(limit)]
            try:
                cr.execute(sql, params)
                rows = cr.fetchall()
            except Exception:
                _logger.warning('semantic_index.search: SQL failed for %s',
                                model_name, exc_info=True)
                return []
        else:
            # JSON-fallback path — load every embedded row (capped at 500)
            # and rank in python. Acceptable for ai.chat.fact-sized tables;
            # for big tables the caller should ensure pgvector is installed.
            try:
                cr.execute(
                    f'SELECT "{table}".id, "{table}"."{vector_col}"{hints_select} '
                    f'FROM "{table}" '
                    f'WHERE "{table}"."{vector_col}" IS NOT NULL'
                    f'{where_sql} '
                    f'LIMIT 500',
                    where_params,
                )
                raw = cr.fetchall()
            except Exception:
                return []
            scored = []
            for r in raw:
                rid, blob = r[0], r[1]
                stored_vec = _embed.deserialize_vector(blob)
                if not stored_vec:
                    continue
                score = _embed.cosine(vec, stored_vec)
                scored.append((rid, score, *r[2:]))
            scored.sort(key=lambda t: t[1], reverse=True)
            rows = scored[:int(limit)]

        # Resolve names + return.
        ids = [r[0] for r in rows]
        if not ids:
            return []
        recs = Model.sudo().browse(ids)
        by_id = {r.id: r for r in recs.exists()}

        out = []
        for r in rows:
            rid, score = r[0], float(r[1] or 0.0)
            if score < min_similarity:
                continue
            rec = by_id.get(rid)
            if rec is None:
                continue
            name = ''
            if name_field and name_field in rec._fields:
                name = rec[name_field] or ''
            elif name_field == 'display_name':
                name = rec.display_name or ''
            hints = {}
            for i, f in enumerate(hint_fields):
                # raw value from SQL — keep the cheap path; for relational
                # fields the caller should ask for `partner_id` AS a string
                # via a stored display name.
                hints[f] = r[2 + i] if 2 + i < len(r) else None
            out.append({
                'id': rid,
                'name': name,
                'score': round(score, 4),
                'hints': hints,
            })
        return out

    # ── Rendering ──────────────────────────────────────────────────

    @api.model
    def to_csv(self, rows, *, hint_keys=None):
        """Render search rows as pipe-CSV the LLM can read cheaply.

        Header: ``id|name|score|<hint1>|<hint2>``. ~40 % smaller than
        JSON for the same data — token-reduction win that compounds
        with provider prompt cache because the header line cache-hits.
        """
        if not rows:
            return ''
        # Auto-derive hint keys from the first row when not supplied.
        if hint_keys is None:
            hint_keys = list(rows[0].get('hints') or {}).copy()
        header = '|'.join(['id', 'name', 'score', *hint_keys])
        lines = [header]
        for r in rows:
            hints = r.get('hints') or {}
            cells = [
                str(r.get('id', '')),
                _csv_cell(r.get('name', '')),
                f"{float(r.get('score') or 0):.4f}",
            ]
            for k in hint_keys:
                cells.append(_csv_cell(hints.get(k, '')))
            lines.append('|'.join(cells))
        return '\n'.join(lines)


def _csv_cell(value):
    """Coerce + sanitise a value for pipe-CSV output."""
    if value is None or value is False:
        return ''
    s = str(value)
    # Pipe-CSV doesn't have proper quoting; we collapse pipes and newlines
    # so a stray name like "Foo|Bar\nbaz" can't break the parser.
    return s.replace('|', '/').replace('\n', ' ').replace('\r', ' ').strip()


def _has_raw_column(cr, table, column):
    """True iff the table has a column by that name in pg_catalog. Used
    when ``vector_col`` is a SQL-only column (legacy chat_fact pattern)
    that isn't declared as a python field."""
    try:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        return cr.fetchone() is not None
    except Exception:
        return False
