"""Hybrid retrieval orchestration.

Runs dense and lexical retrieval, fuses their rankings with RRF, hydrates the
shortlist, and optionally reorders it with a cross-encoder. Scoring lives in
the search modules; fusion maths lives in ``fusion``; reranking lives in
``reranker``. This file only coordinates, and times each stage so a slow query
can be attributed rather than guessed at.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.observability.timing import Stage, stage
from app.retrieval import lexical_search, vector_search
from app.retrieval.diversity import enforce_document_diversity
from app.retrieval.fusion import (
    LEXICAL_SOURCE,
    VECTOR_SOURCE,
    FusedResult,
    reciprocal_rank_fusion,
)
from app.retrieval.hydration import hydrate_chunks
from app.retrieval.reranker import reranker
from app.schemas.retrieval import ScoredChunk


def _fuse(session: Session, query: str, owner_id: UUID) -> list[FusedResult]:
    vector_hits = vector_search.search(
        session, query, settings.VECTOR_CANDIDATE_COUNT, owner_id
    )
    lexical_hits = lexical_search.search(
        session, query, settings.LEXICAL_CANDIDATE_COUNT, owner_id
    )

    with stage(Stage.FUSION):
        return reciprocal_rank_fusion(
            ranked_lists={
                VECTOR_SOURCE: [chunk_id for chunk_id, _ in vector_hits],
                LEXICAL_SOURCE: [chunk_id for chunk_id, _ in lexical_hits],
            },
            weights={
                VECTOR_SOURCE: settings.RRF_VECTOR_WEIGHT,
                LEXICAL_SOURCE: settings.RRF_LEXICAL_WEIGHT,
            },
            k=settings.RRF_K,
        )


def _hydrate(
    session: Session, owner_id: UUID, fused: list[FusedResult]
) -> list[ScoredChunk]:
    # Both searches already filtered by owner; hydration filters again so a
    # future change to either search cannot turn into a cross-user leak.
    with stage(Stage.HYDRATE):
        chunks = {
            chunk.chunk_id: chunk
            for chunk in hydrate_chunks(
                session, owner_id, [result.chunk_id for result in fused]
            )
        }

    scored: list[ScoredChunk] = []
    for result in fused:
        chunk = chunks.get(result.chunk_id)
        if chunk is None:
            continue
        scored.append(
            ScoredChunk(
                chunk=chunk,
                fused_score=result.score,
                vector_rank=result.ranks.get(VECTOR_SOURCE),
                lexical_rank=result.ranks.get(LEXICAL_SOURCE),
            )
        )
    return scored


def _rerank(query: str, scored: list[ScoredChunk]) -> list[ScoredChunk]:
    with stage(Stage.RERANK):
        scores = reranker.score(query, [item.chunk.text for item in scored])
    for item, score in zip(scored, scores, strict=False):
        item.rerank_score = score
    # Ties break on the fused score, so the ordering stays deterministic.
    scored.sort(key=lambda item: (-item.rerank_score, -item.fused_score))
    return scored


def retrieve(
    session: Session, query: str, top_k: int, owner_id: UUID
) -> list[ScoredChunk]:
    fused = _fuse(session, query, owner_id)

    # Fusion only has to get the right chunks into a shortlist. Ordering is
    # settled afterwards by the cross-encoder, and the final selection by the
    # diversity cap — neither of which can promote a chunk that fusion never
    # shortlisted, so the shortlist stays much wider than top_k.
    scored = _hydrate(session, owner_id, fused[: settings.SHORTLIST_CANDIDATE_COUNT])

    if settings.RERANKER_ENABLED:
        scored = _rerank(query, scored)

    return enforce_document_diversity(scored, top_k, settings.MAX_CHUNKS_PER_DOCUMENT)
