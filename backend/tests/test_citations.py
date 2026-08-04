from __future__ import annotations

from uuid import uuid4

from app.generation.citations import build_citations, extract_citation_markers
from app.schemas.retrieval import RetrievedChunk


def make_chunk(index: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"doc:{index}",
        document_id=uuid4(),
        document_title="Handbook",
        chunk_index=index,
        heading_path=["Chapter 1", "Scope"],
        page_start=index + 1,
        text=f"body text {index}",
    )


def test_markers_are_extracted_in_first_appearance_order_without_duplicates():
    answer = "Claim one [2]. Claim two [1]. Restated [2]."

    assert extract_citation_markers(answer) == [2, 1]


def test_answer_without_markers_yields_no_citations():
    assert extract_citation_markers("No sources referenced here.") == []


def test_citations_resolve_to_the_matching_chunk():
    chunks = [make_chunk(0), make_chunk(1)]

    citations = build_citations([2], chunks)

    assert len(citations) == 1
    assert citations[0].marker == 2
    assert citations[0].chunk_id == "doc:1"
    assert citations[0].section == "Chapter 1 > Scope"
    assert citations[0].page == 2


def test_hallucinated_markers_are_discarded():
    chunks = [make_chunk(0)]

    citations = build_citations([1, 7, 0], chunks)

    assert [citation.marker for citation in citations] == [1]
