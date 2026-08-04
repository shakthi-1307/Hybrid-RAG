"""Ingestion orchestration: file on disk -> sections -> chunks -> vectors -> rows.

This module wires the ingestion stages together and owns failure handling.
It performs no parsing, chunking, embedding, or SQL of its own.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Document, IngestionStatus
from app.errors import AppError, EmptyDocumentError
from app.ingestion.chunker import chunker
from app.ingestion.embedder import embedder
from app.ingestion.loaders.registry import get_loader
from app.ingestion.metadata import build_chunk_id, build_chunk_metadata
from app.retrieval.index_builder import refresh_bm25_index
from app.schemas.ingestion import Chunk
from app.stores import document_repository
from app.stores.vector_store import vector_store

logger = logging.getLogger(__name__)


def _build_chunks(file_path: Path, filename: str) -> list[Chunk]:
    sections = get_loader(filename).load(file_path)
    if not sections:
        raise EmptyDocumentError(f"No extractable text found in '{filename}'.")

    chunks = chunker.chunk(sections)
    if not chunks:
        raise EmptyDocumentError(f"'{filename}' produced no usable chunks.")
    return chunks


def _persist(session: Session, document: Document, chunks: list[Chunk]) -> None:
    ingested_at = datetime.now(timezone.utc)
    ids = [build_chunk_id(document.id, chunk.chunk_index) for chunk in chunks]
    texts = [chunk.text for chunk in chunks]
    metadatas = [
        build_chunk_metadata(
            document_id=document.id,
            owner_id=document.owner_id,
            document_title=document.title,
            source_filename=document.filename,
            content_type=document.content_type,
            chunk=chunk,
            ingested_at=ingested_at,
        )
        for chunk in chunks
    ]

    vector_store.delete_document(str(document.id))
    vector_store.add(
        ids=ids,
        embeddings=embedder.embed_passages(texts),
        documents=texts,
        metadatas=metadatas,
    )
    document_repository.insert_chunks(session, document, chunks)


def ingest_document(
    session: Session, owner_id: UUID, document_id: UUID, file_path: Path
) -> None:
    document = document_repository.get_document(session, owner_id, document_id)
    if document is None:
        logger.error("Ingestion aborted: document %s no longer exists", document_id)
        return

    document_repository.set_status(session, document, status=IngestionStatus.PROCESSING)
    try:
        chunks = _build_chunks(file_path, document.filename)
        _persist(session, document, chunks)
    except AppError as exc:
        logger.warning("Ingestion rejected %s: %s", document.filename, exc.message)
        document_repository.set_status(
            session, document, status=IngestionStatus.FAILED, error=exc.message
        )
        return
    except Exception as exc:  # noqa: BLE001 - background task must never crash silently
        logger.exception("Ingestion failed for %s", document.filename)
        document_repository.set_status(
            session, document, status=IngestionStatus.FAILED, error=str(exc)
        )
        return

    document_repository.set_status(
        session, document, status=IngestionStatus.READY, chunk_count=len(chunks)
    )
    refresh_bm25_index(session)
    logger.info("Ingested %s into %d chunks", document.filename, len(chunks))
