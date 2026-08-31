"""Dense retrieval: embed the query, ask Postgres for nearest neighbours.

The embedding and the ownership predicate go into the same statement, so the
HNSW index returns this user's best matches rather than the global best
matches with this user's rows filtered out of them afterwards. That
distinction is invisible in a single-tenant demo and is the difference
between working and quietly broken with real users.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.db import pgvector_support
from app.ingestion.embedder import embedder
from app.observability.timing import Stage, stage

# Raw SQL rather than the ORM: the ordering expression is an operator pgvector
# defines (<=> is cosine distance), and the value must bind as a vector, not
# as an array of floats. Expressing that through the query builder obscures
# what actually reaches the planner, which is the one thing worth reading here.
_SEARCH_SQL = text(
    """
    SELECT id, 1 - (embedding <=> :query_embedding) AS similarity
    FROM document_chunks
    WHERE owner_id = :owner_id
    ORDER BY embedding <=> :query_embedding
    LIMIT :limit
    """
).bindparams(bindparam("query_embedding"))


def search(
    session: Session, query: str, limit: int, owner_id: UUID
) -> list[tuple[str, float]]:
    """Return ``(chunk_id, cosine_similarity)`` for ``owner_id``, best-first.

    Similarity rather than distance, so a larger number is a better match and
    the two searches agree on direction before fusion sees them.
    """
    if not query.strip():
        return []

    with stage(Stage.EMBED_QUERY):
        embedding = embedder.embed_query(query)

    with stage(Stage.VECTOR_SEARCH):
        pgvector_support.apply_search_settings(session)
        rows = session.execute(
            _SEARCH_SQL,
            {
                # pgvector's text input format. Passing a Python list here
                # would bind as a Postgres array and fail the operator's type
                # check at execution time.
                "query_embedding": "[" + ",".join(f"{v:.7g}" for v in embedding) + "]",
                "owner_id": str(owner_id),
                "limit": limit,
            },
        ).all()

    return [(row[0], float(row[1])) for row in rows]
