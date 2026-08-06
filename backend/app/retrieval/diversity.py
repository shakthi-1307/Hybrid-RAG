"""Stops one document from occupying every slot in the context window.

Pure relevance ranking answers "which chunks best match this query". For a
comparison — "how does my resume line up against this job description" — that
is the wrong objective: the best six chunks may all come from the longer
document, and the answer is then structurally impossible to give. Capping the
per-document share trades a little relevance for the coverage such questions
require.
"""

from __future__ import annotations

from uuid import UUID

from app.schemas.retrieval import ScoredChunk


def enforce_document_diversity(
    scored: list[ScoredChunk], top_k: int, max_per_document: int
) -> list[ScoredChunk]:
    """Best ``top_k``, with at most ``max_per_document`` from any one document.

    Input must already be ordered best-first. When there are too few distinct
    documents to fill ``top_k``, the remaining slots are backfilled from the
    chunks the cap displaced — a single-document corpus still returns a full
    context window rather than a short one.
    """
    selected: list[tuple[int, ScoredChunk]] = []
    displaced: list[tuple[int, ScoredChunk]] = []
    per_document: dict[UUID, int] = {}

    for position, item in enumerate(scored):
        document_id = item.chunk.document_id
        if per_document.get(document_id, 0) < max_per_document:
            per_document[document_id] = per_document.get(document_id, 0) + 1
            selected.append((position, item))
            if len(selected) == top_k:
                break
        else:
            displaced.append((position, item))

    if len(selected) < top_k:
        selected.extend(displaced[: top_k - len(selected)])
        # Backfill arrives out of order; restore ranking so citation numbers
        # still run best-first.
        selected.sort(key=lambda pair: pair[0])

    return [item for _, item in selected]
