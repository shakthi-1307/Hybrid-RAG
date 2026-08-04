"""Liveness and readiness reporting."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.retrieval.bm25_search import bm25_index
from app.schemas.health import HealthOut
from app.stores.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 - health must report, not raise
        logger.exception("Database health check failed")
        database_ok = False

    return HealthOut(
        status="ok" if database_ok else "degraded",
        version=settings.APP_VERSION,
        database=database_ok,
        vector_count=vector_store.count(),
        bm25_documents=bm25_index.size(),
    )
