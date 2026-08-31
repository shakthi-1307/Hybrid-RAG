"""End-to-end retrieval against a real Postgres.

The properties under test are all properties of SQL — an index filter applied
before the limit, a generated column that populates itself, a cascade that
removes vectors along with a document. None of them can be checked with a
fake, and all of them fail silently: wrong results, not exceptions.

The tenant-isolation cases are the ones that matter most. A leak here is a
security bug, and it would look exactly like working software.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import Document, DocumentChunk, IngestionStatus, User
from app.retrieval import lexical_search, vector_search
from tests.conftest import requires_database

pytestmark = requires_database

DIMENSION = 384


def unit_vector(index: int) -> list[float]:
    """A one-hot vector.

    Cosine distance between two distinct one-hot vectors is exactly 1 and
    between identical ones exactly 0, so ranking is decided by construction
    rather than by whatever a real embedding model happens to produce. That
    keeps the test about the query, not about the model.
    """
    vector = [0.0] * DIMENSION
    vector[index % DIMENSION] = 1.0
    return vector


@pytest.fixture
def two_tenants(db_session):
    """Alice and Bob, each with a document whose text is word-for-word identical.

    Identical text is the point: any correct result must be explained by
    ownership, because relevance cannot tell the two apart.
    """
    alice = User(id=uuid.uuid4(), email="alice@example.test", password_hash="x")
    bob = User(id=uuid.uuid4(), email="bob@example.test", password_hash="x")
    db_session.add_all([alice, bob])

    documents = {}
    for owner, name in ((alice, "alice"), (bob, "bob")):
        document = Document(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title=f"{name} handbook",
            filename=f"{name}.md",
            content_type="text/markdown",
            byte_size=100,
            checksum=f"{name}-checksum",
            status=IngestionStatus.READY,
            chunk_count=2,
        )
        documents[name] = document
        db_session.add(document)
        db_session.add_all(
            [
                DocumentChunk(
                    id=f"{name}:0",
                    document_id=document.id,
                    owner_id=owner.id,
                    chunk_index=0,
                    text="quarterly revenue recognition policy for error E-4471",
                    heading_path="Finance > Revenue",
                    token_count=8,
                    embedding=unit_vector(0),
                ),
                DocumentChunk(
                    id=f"{name}:1",
                    document_id=document.id,
                    owner_id=owner.id,
                    chunk_index=1,
                    text="warehouse safety procedures and equipment checks",
                    heading_path="Operations > Safety",
                    token_count=7,
                    embedding=unit_vector(1),
                ),
            ]
        )

    db_session.flush()
    return {"alice": alice, "bob": bob, "documents": documents}


# --------------------------------------------------------------- lexical


def test_lexical_search_returns_only_the_querying_users_chunks(db_session, two_tenants):
    hits = lexical_search.search(
        db_session, "quarterly revenue recognition", 10, two_tenants["alice"].id
    )

    assert [chunk_id for chunk_id, _ in hits] == ["alice:0"]


def test_an_identical_document_owned_by_someone_else_is_invisible(
    db_session, two_tenants
):
    """Bob's chunk is textually identical to Alice's, so it ranks identically.
    Only the owner predicate separates them."""
    hits = lexical_search.search(
        db_session, "quarterly revenue recognition", 10, two_tenants["bob"].id
    )

    assert all(chunk_id.startswith("bob:") for chunk_id, _ in hits)


def test_search_vector_is_generated_without_the_application_writing_it(
    db_session, two_tenants
):
    """Nothing in the insert set search_vector. If the generated column were
    wrong, lexical search would return nothing and look like a bad query."""
    hits = lexical_search.search(
        db_session, "warehouse safety", 10, two_tenants["alice"].id
    )

    assert [chunk_id for chunk_id, _ in hits] == ["alice:1"]


def test_heading_path_is_searchable(db_session, two_tenants):
    """A question naming a section should find it even when the section name
    never appears in the prose — "Operations" is only in the heading."""
    hits = lexical_search.search(db_session, "operations", 10, two_tenants["alice"].id)

    assert [chunk_id for chunk_id, _ in hits] == ["alice:1"]


def test_partial_term_overlap_still_matches(db_session, two_tenants):
    """The OR-joining behaviour, verified against a real tsquery parser rather
    than only against the expression builder."""
    hits = lexical_search.search(
        db_session,
        "what is the revenue policy for unrelated nonexistent topics",
        10,
        two_tenants["alice"].id,
    )

    assert [chunk_id for chunk_id, _ in hits] == ["alice:0"]


def test_unknown_owner_sees_nothing(db_session, two_tenants):
    assert lexical_search.search(db_session, "revenue", 10, uuid.uuid4()) == []


def test_punctuation_only_query_does_not_reach_the_database(db_session, two_tenants):
    assert lexical_search.search(db_session, "???", 10, two_tenants["alice"].id) == []


# ---------------------------------------------------------------- vector


def test_vector_search_is_scoped_to_the_owner(db_session, two_tenants, monkeypatch):
    """The filter has to be inside the query, not applied to its output.

    Alice and Bob hold vectors at identical positions, so an unscoped
    nearest-neighbour search would rank Bob's chunk exactly as highly as
    Alice's and the limit would decide arbitrarily which she sees.
    """
    monkeypatch.setattr(vector_search.embedder, "embed_query", lambda _: unit_vector(0))

    hits = vector_search.search(db_session, "revenue policy", 10, two_tenants["alice"].id)

    assert hits
    assert all(chunk_id.startswith("alice:") for chunk_id, _ in hits)


def test_vector_search_returns_similarity_not_distance(
    db_session, two_tenants, monkeypatch
):
    """Fusion assumes larger is better. Returning raw distance would invert
    the ranking of one source and silently halve retrieval quality."""
    monkeypatch.setattr(vector_search.embedder, "embed_query", lambda _: unit_vector(0))

    hits = vector_search.search(db_session, "revenue policy", 10, two_tenants["alice"].id)
    scores = [score for _, score in hits]

    assert hits[0][0] == "alice:0"
    assert scores[0] == pytest.approx(1.0, abs=1e-6)
    assert scores == sorted(scores, reverse=True)


def test_empty_query_skips_the_search_entirely(db_session, two_tenants):
    assert vector_search.search(db_session, "   ", 10, two_tenants["alice"].id) == []


# --------------------------------------------------------------- cascade


def test_deleting_a_document_removes_its_vectors(db_session, two_tenants):
    """The payoff for one store: no second system to clean up, and no window
    where a deleted document's vectors are still retrievable."""
    document = two_tenants["documents"]["alice"]
    db_session.delete(document)
    db_session.flush()

    remaining = lexical_search.search(
        db_session, "quarterly revenue", 10, two_tenants["alice"].id
    )

    assert remaining == []
    assert (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .count()
        == 0
    )
