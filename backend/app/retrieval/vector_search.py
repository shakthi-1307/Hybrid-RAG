"""Dense retrieval: embed the query, ask Chroma for nearest neighbours."""

from __future__ import annotations

from uuid import UUID

from app.ingestion.embedder import embedder
from app.ingestion.metadata import OWNER_METADATA_KEY
from app.stores.vector_store import vector_store


def search(query: str, limit: int, owner_id: UUID) -> list[tuple[str, float]]:
    """Return ``(chunk_id, cosine_similarity)`` for ``owner_id``, best-first."""
    if not query.strip():
        return []
    return vector_store.query(
        embedding=embedder.embed_query(query),
        n_results=limit,
        where={OWNER_METADATA_KEY: str(owner_id)},
    )
