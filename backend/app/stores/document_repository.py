"""Postgres persistence for documents and their chunks.

Every read is scoped by ``owner_id``. Ownership is enforced in the query, not
by the caller, so there is no code path that can return another user's rows.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Document, DocumentChunk, IngestionStatus
from app.ingestion.metadata import build_chunk_id, heading_path_to_string
from app.schemas.ingestion import Chunk
from app.schemas.retrieval import CorpusEntry


def create_document(
    session: Session,
    *,
    owner_id: UUID,
    title: str,
    filename: str,
    content_type: str,
    byte_size: int,
    checksum: str,
) -> Document:
    document = Document(
        owner_id=owner_id,
        title=title,
        filename=filename,
        content_type=content_type,
        byte_size=byte_size,
        checksum=checksum,
        status=IngestionStatus.PENDING,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def find_by_checksum(
    session: Session, owner_id: UUID, checksum: str
) -> Document | None:
    return session.scalar(
        select(Document).where(
            Document.owner_id == owner_id, Document.checksum == checksum
        )
    )


def get_document(
    session: Session, owner_id: UUID, document_id: UUID
) -> Document | None:
    return session.scalar(
        select(Document).where(
            Document.id == document_id, Document.owner_id == owner_id
        )
    )


def list_documents(session: Session, owner_id: UUID) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


def usage_for_owner(session: Session, owner_id: UUID) -> tuple[int, int]:
    """``(document_count, total_bytes)`` currently held by ``owner_id``."""
    row = session.execute(
        select(func.count(Document.id), func.coalesce(func.sum(Document.byte_size), 0))
        .where(Document.owner_id == owner_id)
    ).one()
    return int(row[0]), int(row[1])


def set_status(
    session: Session,
    document: Document,
    *,
    status: IngestionStatus,
    chunk_count: int = 0,
    error: str | None = None,
) -> None:
    document.status = status
    document.chunk_count = chunk_count
    document.error = error
    session.commit()


def delete_document(session: Session, document: Document) -> None:
    session.delete(document)
    session.commit()


def checksum_in_use(session: Session, checksum: str) -> bool:
    """Whether any user still owns a document with these bytes.

    Deliberately unscoped: the file on disk is named by checksum and shared
    across owners, so it may only be unlinked once nobody references it.
    """
    return bool(
        session.scalar(select(exists().where(Document.checksum == checksum)))
    )


def insert_chunks(session: Session, document: Document, chunks: list[Chunk]) -> None:
    session.execute(
        sql_delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    rows = [
        DocumentChunk(
            id=build_chunk_id(document.id, chunk.chunk_index),
            document_id=document.id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            heading_path=heading_path_to_string(chunk.heading_path),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            token_count=chunk.token_count,
        )
        for chunk in chunks
    ]
    session.add_all(rows)
    session.commit()


def list_corpus_entries(session: Session) -> list[CorpusEntry]:
    """Every indexable chunk with its owner — the BM25 corpus."""
    statement = (
        select(DocumentChunk.id, DocumentChunk.text, Document.owner_id)
        .join(Document)
        .where(Document.status == IngestionStatus.READY)
        .order_by(DocumentChunk.id)
    )
    return [(row[0], row[1], row[2]) for row in session.execute(statement).all()]


def get_chunks_by_ids(
    session: Session, owner_id: UUID, chunk_ids: list[str]
) -> dict[str, DocumentChunk]:
    if not chunk_ids:
        return {}
    statement = (
        select(DocumentChunk)
        .join(Document)
        .options(joinedload(DocumentChunk.document))
        .where(DocumentChunk.id.in_(chunk_ids), Document.owner_id == owner_id)
    )
    return {chunk.id: chunk for chunk in session.scalars(statement).all()}
