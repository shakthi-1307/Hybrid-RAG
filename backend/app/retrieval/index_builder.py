"""Keeps the in-memory BM25 index in sync with Postgres.

Called at application startup and after any mutation of the chunk corpus.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.retrieval.bm25_search import bm25_index
from app.stores import document_repository

logger = logging.getLogger(__name__)


def refresh_bm25_index(session: Session) -> None:
    entries = document_repository.list_corpus_entries(session)
    bm25_index.rebuild(entries)
    logger.info("BM25 index rebuilt with %d chunks", len(entries))
