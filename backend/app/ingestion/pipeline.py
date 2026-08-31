"""Ingestion orchestration: file on disk -> sections -> chunks -> rows.

This module wires the ingestion stages together and owns failure handling. It
performs no parsing, chunking, embedding, or SQL of its own.

The whole persistence step is one transaction. Chunks, their embeddings, and
the document's READY status commit together or not at all, which removes the
class of bug where a crash leaves vectors that no row points at — previously
handled by dropping orphans at query time, and now simply not possible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Document, IngestionStatus
from app.errors import AppError, EmptyDocumentError
from app.ingestion.chunker import chunker
from app.ingestion.embedder import embedder
from app.ingestion.loaders.registry import get_loader
from app.observability.timing import Stage, stage
from app.schemas.ingestion import Chunk
from app.stores import document_repository

logger = logging.getLogger(__name__)


class PermanentIngestionError(Exception):
    """A failure that retrying cannot fix.

    An unreadable PDF or an empty document will fail identically on every
    attempt, so the queue marks it dead immediately instead of burning three
    attempts and a quarter of an hour of backoff to reach the same answer.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _build_chunks(file_path: Path, filename: str) -> list[Chunk]:
    if not file_path.exists():
        # Retrying will not conjure the file back. Distinguished from a
        # transient read error so it fails fast with an accurate reason.
        raise PermanentIngestionError(
            f"The stored file for '{filename}' is missing from disk."
        )

    with stage(Stage.LOAD):
        sections = get_loader(filename).load(file_path)
    if not sections:
        raise EmptyDocumentError(f"No extractable text found in '{filename}'.")

    with stage(Stage.CHUNK):
        chunks = chunker.chunk(sections)
    if not chunks:
        raise EmptyDocumentError(f"'{filename}' produced no usable chunks.")
    return chunks


def _persist(session: Session, document: Document, chunks: list[Chunk]) -> None:
    with stage(Stage.EMBED_PASSAGES):
        embeddings = embedder.embed_passages([chunk.text for chunk in chunks])

    with stage(Stage.PERSIST):
        # No commit until the end: the delete, the insert, and the status flip
        # are one atomic unit.
        document_repository.delete_chunks(session, document.id, commit=False)
        document_repository.insert_chunks(
            session, document, chunks, embeddings, commit=False
        )
        document_repository.set_status(
            session,
            document,
            status=IngestionStatus.READY,
            chunk_count=len(chunks),
            error=None,
            commit=False,
        )
        session.commit()


def ingest_document(
    session: Session, owner_id: UUID, document_id: UUID, file_path: Path
) -> int:
    """Ingest one document, returning the chunk count.

    Raises on failure rather than swallowing it. The caller is the job queue,
    which needs to know whether to retry — a function that always returns
    cleanly cannot tell it that.
    """
    document = document_repository.get_document(session, owner_id, document_id)
    if document is None:
        # The user deleted the document between upload and processing. Nothing
        # to do, and nothing worth retrying.
        raise PermanentIngestionError(f"Document {document_id} no longer exists.")

    document_repository.set_status(
        session, document, status=IngestionStatus.PROCESSING, error=None
    )

    try:
        chunks = _build_chunks(file_path, document.filename)
        _persist(session, document, chunks)
    except AppError as exc:
        # A domain error is a verdict on the file itself, not on the attempt.
        session.rollback()
        raise PermanentIngestionError(exc.message) from exc
    except Exception:
        session.rollback()
        raise

    logger.info(
        "Ingested %s into %d chunks",
        document.filename,
        len(chunks),
        extra={
            "document_id": str(document.id),
            "chunk_count": len(chunks),
            "document_filename": document.filename,
        },
    )
    return len(chunks)
