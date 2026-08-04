"""The lexical index is shared across users; the owner filter is what keeps it safe."""

from __future__ import annotations

from uuid import uuid4

from app.config import settings
from app.retrieval.bm25_search import BM25Index, tokenize

ALICE = uuid4()
BOB = uuid4()
LIMIT = 10

CORPUS = [
    ("alice:0", "quarterly revenue recognition policy", ALICE),
    ("alice:1", "employee onboarding checklist", ALICE),
    ("bob:0", "quarterly revenue recognition policy", BOB),
    ("bob:1", "warehouse safety procedures", BOB),
]


def make_index() -> BM25Index:
    index = BM25Index(k1=settings.BM25_K1, b=settings.BM25_B)
    index.rebuild(CORPUS)
    return index


def test_tokenizer_lowercases_and_drops_punctuation():
    assert tokenize("Revenue, Recognition!") == ["revenue", "recognition"]


def test_search_returns_only_the_querying_users_chunks():
    hits = make_index().search("quarterly revenue recognition", LIMIT, ALICE)

    assert [chunk_id for chunk_id, _ in hits] == ["alice:0"]


def test_an_identical_document_owned_by_someone_else_is_invisible():
    """Bob's copy scores identically to Alice's and must still be excluded."""
    hits = make_index().search("quarterly revenue recognition", LIMIT, BOB)

    assert all(chunk_id.startswith("bob:") for chunk_id, _ in hits)


def test_user_with_no_matching_chunks_gets_nothing():
    assert make_index().search("warehouse safety", LIMIT, ALICE) == []


def test_unknown_owner_sees_an_empty_corpus():
    assert make_index().search("quarterly revenue", LIMIT, uuid4()) == []


def test_size_reports_the_whole_corpus():
    assert make_index().size() == len(CORPUS)


def test_empty_corpus_is_searchable_without_error():
    index = BM25Index(k1=settings.BM25_K1, b=settings.BM25_B)
    index.rebuild([])

    assert index.search("anything", LIMIT, ALICE) == []
