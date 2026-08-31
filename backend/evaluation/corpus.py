"""Corpus reads the benchmark needs that the request path has no use for."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, IngestionStatus
from app.ingestion.metadata import heading_path_to_string


def sample_chunks(
    session: Session, owner_id: UUID, limit: int, min_chars: int
) -> list[tuple[DocumentChunk, str]]:
    """Random ready chunks with their document title, for question drafting.

    Randomised so a second drafting run explores different parts of the corpus
    instead of re-proposing the opening pages.
    """
    statement = (
        select(DocumentChunk, Document.title)
        .join(Document)
        .where(
            Document.owner_id == owner_id,
            Document.status == IngestionStatus.READY,
            func.length(DocumentChunk.text) >= min_chars,
        )
        .order_by(func.random())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in session.execute(statement).all()]


def sections_for_chunk_ids(
    session: Session, owner_id: UUID, chunk_ids: list[str]
) -> dict[str, str]:
    """Heading path per chunk id, used to score a retrieved ranking.

    Falls back to the document title so a chunk from an unstructured document
    still has something to match against rather than an empty string.
    """
    if not chunk_ids:
        return {}

    statement = (
        select(DocumentChunk.id, DocumentChunk.heading_path, Document.title)
        .join(Document)
        .where(DocumentChunk.id.in_(chunk_ids), Document.owner_id == owner_id)
    )
    return {row[0]: (row[1] or row[2]) for row in session.execute(statement).all()}


def section_of(chunk: DocumentChunk, document_title: str) -> str:
    return chunk.heading_path or heading_path_to_string([document_title])
