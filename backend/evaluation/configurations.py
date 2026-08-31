"""The retrieval configurations under test.

Each is composed from the same primitives the request path uses. They are
composed here rather than routed through ``hybrid_retriever`` because three of
the four are ablations that deliberately do not exist as a runtime path — there
is no "lexical only" mode of the service. The fourth mirrors the live pipeline
stage for stage; if you change ``hybrid_retriever``, change ``hybrid_reranked``
with it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.retrieval import lexical_search, vector_search
from app.retrieval.fusion import LEXICAL_SOURCE, VECTOR_SOURCE, reciprocal_rank_fusion
from app.retrieval.hydration import hydrate_chunks
from app.retrieval.reranker import reranker
from evaluation.schema import StageTimings


@dataclass(frozen=True)
class RetrievalOutput:
    chunk_ids: list[str]
    timings: StageTimings


def _vector_candidates(
    session: Session, query: str, owner_id: UUID, limit: int
) -> tuple[list[str], float]:
    start = perf_counter()
    hits = vector_search.search(session, query, limit, owner_id)
    return [chunk_id for chunk_id, _ in hits], (perf_counter() - start) * 1000


def _lexical_candidates(
    session: Session, query: str, owner_id: UUID, limit: int
) -> tuple[list[str], float]:
    start = perf_counter()
    hits = lexical_search.search(session, query, limit, owner_id)
    return [chunk_id for chunk_id, _ in hits], (perf_counter() - start) * 1000


def _fuse(vector_ids: list[str], lexical_ids: list[str]) -> tuple[list[str], float]:
    start = perf_counter()
    fused = reciprocal_rank_fusion(
        ranked_lists={VECTOR_SOURCE: vector_ids, LEXICAL_SOURCE: lexical_ids},
        weights={
            VECTOR_SOURCE: settings.RRF_VECTOR_WEIGHT,
            LEXICAL_SOURCE: settings.RRF_LEXICAL_WEIGHT,
        },
        k=settings.RRF_K,
    )
    return [result.chunk_id for result in fused], (perf_counter() - start) * 1000


def run_vector_only(
    session: Session, query: str, owner_id: UUID, top_k: int
) -> RetrievalOutput:
    chunk_ids, elapsed = _vector_candidates(session, query, owner_id, top_k)
    return RetrievalOutput(chunk_ids[:top_k], StageTimings(vector_ms=elapsed))


def run_lexical_only(
    session: Session, query: str, owner_id: UUID, top_k: int
) -> RetrievalOutput:
    chunk_ids, elapsed = _lexical_candidates(session, query, owner_id, top_k)
    return RetrievalOutput(chunk_ids[:top_k], StageTimings(lexical_ms=elapsed))


def run_hybrid(
    session: Session, query: str, owner_id: UUID, top_k: int
) -> RetrievalOutput:
    vector_ids, vector_ms = _vector_candidates(
        session, query, owner_id, settings.VECTOR_CANDIDATE_COUNT
    )
    lexical_ids, lexical_ms = _lexical_candidates(
        session, query, owner_id, settings.LEXICAL_CANDIDATE_COUNT
    )
    fused_ids, fusion_ms = _fuse(vector_ids, lexical_ids)

    return RetrievalOutput(
        fused_ids[:top_k],
        StageTimings(vector_ms=vector_ms, lexical_ms=lexical_ms, fusion_ms=fusion_ms),
    )


def run_hybrid_reranked(
    session: Session, query: str, owner_id: UUID, top_k: int
) -> RetrievalOutput:
    vector_ids, vector_ms = _vector_candidates(
        session, query, owner_id, settings.VECTOR_CANDIDATE_COUNT
    )
    lexical_ids, lexical_ms = _lexical_candidates(
        session, query, owner_id, settings.LEXICAL_CANDIDATE_COUNT
    )
    fused_ids, fusion_ms = _fuse(vector_ids, lexical_ids)
    # Deliberately no diversity cap here. The gold set asks single-section
    # questions, where capping per-document share can only push the correct
    # chunk out — measuring it against this benchmark would understate it.
    # Diversity is a coverage trade for multi-document questions, and belongs
    # in a benchmark built from those.
    shortlist = fused_ids[: settings.SHORTLIST_CANDIDATE_COUNT]

    # Hydration is timed because the cross-encoder needs chunk text, which the
    # rank-only configurations never have to fetch. Charging it here keeps the
    # latency comparison honest.
    start = perf_counter()
    ordered = hydrate_chunks(session, owner_id, shortlist)
    hydrate_ms = (perf_counter() - start) * 1000

    start = perf_counter()
    scores = reranker.score(query, [chunk.text for chunk in ordered])
    reranked = sorted(
        zip(ordered, scores, strict=False), key=lambda pair: pair[1], reverse=True
    )
    rerank_ms = (perf_counter() - start) * 1000

    return RetrievalOutput(
        [chunk.chunk_id for chunk, _ in reranked[:top_k]],
        StageTimings(
            vector_ms=vector_ms,
            lexical_ms=lexical_ms,
            fusion_ms=fusion_ms,
            hydrate_ms=hydrate_ms,
            rerank_ms=rerank_ms,
        ),
    )


ConfigurationRunner = Callable[[Session, str, UUID, int], RetrievalOutput]

CONFIGURATIONS: list[tuple[str, str, ConfigurationRunner]] = [
    ("lexical_only", "Lexical baseline (Postgres full-text)", run_lexical_only),
    ("vector_only", "Dense baseline (bi-encoder embeddings)", run_vector_only),
    ("hybrid_rrf", "Lexical + dense, Reciprocal Rank Fusion", run_hybrid),
    (
        "hybrid_reranked",
        "Hybrid RRF + cross-encoder reranking",
        run_hybrid_reranked,
    ),
]
