"""Reciprocal Rank Fusion.

RRF combines ranked lists without needing their scores to be comparable:

    score(d) = sum over sources of  weight_s / (k + rank_s(d))

That property is what makes it safe to merge cosine similarity with BM25.
"""

from __future__ import annotations

from dataclasses import dataclass

VECTOR_SOURCE = "vector"
BM25_SOURCE = "bm25"


@dataclass(frozen=True)
class FusedResult:
    chunk_id: str
    score: float
    ranks: dict[str, int]


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]],
    weights: dict[str, float],
    k: int,
) -> list[FusedResult]:
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}

    for source, chunk_ids in ranked_lists.items():
        weight = weights[source]
        for position, chunk_id in enumerate(chunk_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + position)
            ranks.setdefault(chunk_id, {})[source] = position

    fused = [
        FusedResult(chunk_id=chunk_id, score=score, ranks=ranks[chunk_id])
        for chunk_id, score in scores.items()
    ]
    fused.sort(key=lambda result: (-result.score, result.chunk_id))
    return fused
