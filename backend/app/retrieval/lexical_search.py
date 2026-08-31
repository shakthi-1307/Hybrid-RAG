"""Lexical retrieval over Postgres full-text search.

This replaces an in-process BM25 index, and the trade is worth stating plainly
because it is the most debatable decision in the retrieval stack.

What was lost: ``ts_rank_cd`` is not BM25. It has no term-frequency
saturation, and its length normalisation is a coarser knob than BM25's ``b``.
On absolute scores the two disagree.

What was gained: the index lives in the database, so it is correct with more
than one API process, updates per row instead of rebuilding the whole corpus
on every upload, survives a restart, and is written in the same transaction as
the chunk it indexes. The previous design was none of those things — with two
workers, only the one that handled an upload could see the new document, and
nothing anywhere reported that.

Why the trade is defensible: fusion consumes *ranks*, never scores. As long as
the same relevant chunks land near the top, RRF cannot tell which scorer
produced the ordering. Whether that holds for a given corpus is exactly what
``backend/evaluation`` measures — run it before and after and compare nDCG
against the confidence interval rather than taking this paragraph on trust.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.observability.timing import Stage, stage

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# websearch_to_tsquery treats these as operators. A user asking "cats and dogs"
# means both words, not a boolean expression, so they are dropped before the
# terms are re-joined with an explicit OR.
_OPERATOR_WORDS = frozenset({"or", "and", "not"})

_SEARCH_SQL = text(
    """
    SELECT id,
           ts_rank_cd(search_vector, query, :normalization) AS score
    FROM document_chunks,
         websearch_to_tsquery(:config, :query_text) AS query
    WHERE owner_id = :owner_id
      AND search_vector @@ query
    ORDER BY score DESC, id
    LIMIT :limit
    """
)


def tokenize(text_value: str) -> list[str]:
    """Lowercase alphanumeric runs. Mirrors the old index's tokenizer so the
    owner-scoping tests carry over unchanged."""
    return _TOKEN_RE.findall(text_value.lower())


def build_query_expression(query: str) -> str:
    """Turn a natural-language question into a websearch_to_tsquery string.

    ``websearch_to_tsquery`` ANDs bare terms, which is wrong for retrieval: a
    nine-word question would match only chunks containing all nine, and long
    questions would return nothing at all. BM25 scored any overlap, so the
    terms are joined with an explicit OR to keep that recall behaviour, and
    ranking decides the order.

    The parser is used rather than hand-built tsquery syntax because it never
    raises on malformed input — no amount of punctuation a user types can turn
    into a syntax error, which ``to_tsquery`` would.
    """
    terms = [term for term in tokenize(query) if term not in _OPERATOR_WORDS]
    if not terms:
        return ""
    # Deduplicate while preserving order: a repeated word adds nothing to an
    # OR and only makes the parsed query bigger.
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return " or ".join(seen[: settings.MAX_QUERY_TERMS])


def search(
    session: Session, query: str, limit: int, owner_id: UUID
) -> list[tuple[str, float]]:
    """Return ``(chunk_id, rank_score)`` for ``owner_id``, best-first.

    The owner predicate is part of the statement, so it is applied before the
    LIMIT rather than to its output — a user's results are never the leftovers
    of someone else's.
    """
    expression = build_query_expression(query)
    if not expression:
        return []

    with stage(Stage.LEXICAL_SEARCH):
        rows = session.execute(
            _SEARCH_SQL,
            {
                "config": settings.TEXT_SEARCH_CONFIG,
                "query_text": expression,
                "owner_id": str(owner_id),
                "normalization": settings.TEXT_RANK_NORMALIZATION,
                "limit": limit,
            },
        ).all()

    return [(row[0], float(row[1])) for row in rows]


def count_indexed_chunks(session: Session) -> int:
    """Size of the lexical corpus, for the health endpoint.

    Every chunk row has a generated ``search_vector``, so this is simply the
    chunk count — but it is queried through this module so the health check
    does not have to know that.
    """
    return int(session.scalar(text("SELECT count(*) FROM document_chunks")) or 0)
