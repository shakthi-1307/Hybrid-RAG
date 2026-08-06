"""Turns stored chunk rows into the DTO the rest of retrieval works with.

Three callers need this mapping — the request path, the retrieval benchmark,
and the generation benchmark — so it lives in one place rather than being
rewritten in each.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.ingestion.metadata import heading_path_from_string
from app.schemas.retrieval import RetrievedChunk
from app.stores import document_repository


def to_retrieved_chunk(row: DocumentChunk) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.id,
        document_id=row.document_id,
        document_title=row.document.title,
        chunk_index=row.chunk_index,
        heading_path=heading_path_from_string(row.heading_path),
        page_start=row.page_start,
        text=row.text,
    )


def hydrate_chunks(
    session: Session, owner_id: UUID, chunk_ids: list[str]
) -> list[RetrievedChunk]:
    """Hydrate in the given order, dropping ids this owner cannot see.

    The ownership filter is applied by the repository query, so this is a
    second independent barrier rather than a convenience.
    """
    rows = document_repository.get_chunks_by_ids(session, owner_id, chunk_ids)
    return [
        to_retrieved_chunk(rows[chunk_id])
        for chunk_id in chunk_ids
        if chunk_id in rows
    ]
