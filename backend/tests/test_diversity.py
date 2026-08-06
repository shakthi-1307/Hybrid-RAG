from __future__ import annotations

from uuid import UUID, uuid4

from app.retrieval.diversity import enforce_document_diversity
from app.schemas.retrieval import RetrievedChunk, ScoredChunk

TOP_K = 6
MAX_PER_DOCUMENT = 3

RESUME = uuid4()
JOB_DESCRIPTION = uuid4()


def chunk(document_id: UUID, index: int, score: float) -> ScoredChunk:
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=f"{document_id}:{index}",
            document_id=document_id,
            document_title="doc",
            chunk_index=index,
            heading_path=["Section"],
            text="body",
        ),
        fused_score=score,
    )


def ranked(*documents: UUID) -> list[ScoredChunk]:
    """One chunk per position, descending score, from the documents given."""
    return [
        chunk(document_id, index, 1.0 - index / 100)
        for index, document_id in enumerate(documents)
    ]


def documents_of(selected: list[ScoredChunk]) -> list[UUID]:
    return [item.chunk.document_id for item in selected]


def test_a_dominant_document_cannot_take_every_slot():
    """The exact failure this exists to prevent: the longer document wins all
    six slots and the comparison becomes impossible to answer."""
    scored = ranked(*([JOB_DESCRIPTION] * 8), *([RESUME] * 4))

    selected = enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)

    assert documents_of(selected).count(JOB_DESCRIPTION) == MAX_PER_DOCUMENT
    assert RESUME in documents_of(selected)


def test_selection_stays_within_the_cap_per_document():
    scored = ranked(*([JOB_DESCRIPTION] * 5), *([RESUME] * 5))

    selected = enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)

    assert documents_of(selected).count(RESUME) <= MAX_PER_DOCUMENT
    assert len(selected) == TOP_K


def test_ranking_order_is_preserved():
    scored = ranked(JOB_DESCRIPTION, RESUME, JOB_DESCRIPTION, RESUME)

    selected = enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)

    scores = [item.fused_score for item in selected]
    assert scores == sorted(scores, reverse=True)


def test_single_document_corpus_still_fills_the_context_window():
    """Backfill: with nothing to diversify against, the cap must not shrink
    the context window to three chunks."""
    scored = ranked(*([RESUME] * 10))

    selected = enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)

    assert len(selected) == TOP_K


def test_backfilled_results_are_still_the_highest_scoring_ones():
    scored = ranked(*([RESUME] * 10))

    selected = enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)

    assert [item.chunk.chunk_index for item in selected] == list(range(TOP_K))


def test_fewer_candidates_than_top_k_returns_them_all():
    scored = ranked(RESUME, JOB_DESCRIPTION)

    assert len(enforce_document_diversity(scored, TOP_K, MAX_PER_DOCUMENT)) == 2


def test_empty_input_returns_empty():
    assert enforce_document_diversity([], TOP_K, MAX_PER_DOCUMENT) == []
