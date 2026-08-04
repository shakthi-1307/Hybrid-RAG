"""Hybrid retrieval orchestration.

Runs dense and lexical retrieval independently, fuses their rankings with RRF,
then hydrates the winners from Postgres. Scoring lives in the search modules;
fusion maths lives in ``fusion``; this file only coordinates.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.metadata import heading_path_from_string
from app.retrieval import vector_search
from app.retrieval.bm25_search import bm25_index
from app.retrieval.fusion import BM25_SOURCE, VECTOR_SOURCE, reciprocal_rank_fusion
from app.schemas.retrieval import RetrievedChunk, ScoredChunk
from app.stores import document_repository


def retrieve(
    session: Session, query: str, top_k: int, owner_id: UUID
) -> list[ScoredChunk]:
    vector_hits = vector_search.search(
        query, settings.VECTOR_CANDIDATE_COUNT, owner_id
    )
    bm25_hits = bm25_index.search(query, settings.BM25_CANDIDATE_COUNT, owner_id)

    fused = reciprocal_rank_fusion(
        ranked_lists={
            VECTOR_SOURCE: [chunk_id for chunk_id, _ in vector_hits],
            BM25_SOURCE: [chunk_id for chunk_id, _ in bm25_hits],
        },
        weights={
            VECTOR_SOURCE: settings.RRF_VECTOR_WEIGHT,
            BM25_SOURCE: settings.RRF_BM25_WEIGHT,
        },
        k=settings.RRF_K,
    )[:top_k]

    # Both searches already filtered by owner; hydration filters again so a
    # future change to either search cannot turn into a cross-user leak.
    rows = document_repository.get_chunks_by_ids(
        session, owner_id, [result.chunk_id for result in fused]
    )

    scored: list[ScoredChunk] = []
    for result in fused:
        row = rows.get(result.chunk_id)
        if row is None:
            continue
        scored.append(
            ScoredChunk(
                chunk=RetrievedChunk(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    document_title=row.document.title,
                    chunk_index=row.chunk_index,
                    heading_path=heading_path_from_string(row.heading_path),
                    page_start=row.page_start,
                    text=row.text,
                ),
                fused_score=result.score,
                vector_rank=result.ranks.get(VECTOR_SOURCE),
                bm25_rank=result.ranks.get(BM25_SOURCE),
            )
        )
    return scored
