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


def find_by_checksum(session: Session, owner_id: UUID, checksum: str) -> Document | None:
    return session.scalar(
        select(Document).where(
            Document.owner_id == owner_id, Document.checksum == checksum
        )
    )


def get_document(session: Session, owner_id: UUID, document_id: UUID) -> Document | None:
    return session.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
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
        select(
            func.count(Document.id), func.coalesce(func.sum(Document.byte_size), 0)
        ).where(Document.owner_id == owner_id)
    ).one()
    return int(row[0]), int(row[1])


def set_status(
    session: Session,
    document: Document,
    *,
    status: IngestionStatus,
    chunk_count: int | None = None,
    error: str | None = None,
    commit: bool = True,
) -> None:
    """Update status, leaving unmentioned fields alone.

    ``chunk_count`` defaults to None rather than 0 so that moving a document
    to PROCESSING for a retry does not wipe the count from the run before it —
    which would report "0 chunks" in the UI for a document that still has
    plenty, until the retry finished.

    ``commit=False`` lets a caller fold this into a larger transaction. The
    ingestion pipeline uses it to write chunks and flip to READY atomically,
    so a crash between the two is not possible.
    """
    document.status = status
    document.error = error
    if chunk_count is not None:
        document.chunk_count = chunk_count
    if commit:
        session.commit()


def delete_document(session: Session, document: Document) -> None:
    session.delete(document)
    session.commit()


def checksum_in_use(session: Session, checksum: str) -> bool:
    """Whether any user still owns a document with these bytes.

    Deliberately unscoped: the file on disk is named by checksum and shared
    across owners, so it may only be unlinked once nobody references it.
    """
    return bool(session.scalar(select(exists().where(Document.checksum == checksum))))


def delete_chunks(session: Session, document_id: UUID, *, commit: bool = True) -> None:
    """Drop every chunk for a document.

    Called at the start of a re-ingest so a failed attempt cannot leave half
    the old chunks alongside none of the new ones.
    """
    session.execute(
        sql_delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    if commit:
        session.commit()


def insert_chunks(
    session: Session,
    document: Document,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    *,
    commit: bool = True,
) -> None:
    """Write chunks and their embeddings in one statement.

    The vector is a column on the same row as the text it belongs to, so there
    is no ordering between "store the vector" and "store the chunk" that could
    be interrupted — the two either both exist or neither does. The lexical
    index needs no write at all: ``search_vector`` is a generated column, so
    Postgres derives it from the text as the row lands.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Got {len(chunks)} chunks and {len(embeddings)} embeddings; "
            "they must correspond one to one."
        )

    session.add_all(
        [
            DocumentChunk(
                id=build_chunk_id(document.id, chunk.chunk_index),
                document_id=document.id,
                owner_id=document.owner_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                heading_path=heading_path_to_string(chunk.heading_path),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                token_count=chunk.token_count,
                embedding=embedding,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=False)
        ]
    )
    if commit:
        session.commit()


def count_chunks(session: Session) -> int:
    return int(session.scalar(select(func.count(DocumentChunk.id))) or 0)


def get_chunks_by_ids(
    session: Session, owner_id: UUID, chunk_ids: list[str]
) -> dict[str, DocumentChunk]:
    if not chunk_ids:
        return {}
    # Filtering on the chunk's own owner_id rather than the document's keeps
    # this a single-table lookup on an indexed column; the join is only for
    # the document title the DTO carries.
    statement = (
        select(DocumentChunk)
        .join(Document)
        .options(joinedload(DocumentChunk.document))
        .where(DocumentChunk.id.in_(chunk_ids), DocumentChunk.owner_id == owner_id)
    )
    return {chunk.id: chunk for chunk in session.scalars(statement).all()}
