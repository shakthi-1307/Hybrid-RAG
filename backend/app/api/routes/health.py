"""Liveness and readiness reporting.

Split into two endpoints because an orchestrator asks two different questions.
``/health/live`` asks "is this process wedged, should I restart it?" and must
not depend on anything external — a database outage restarting every API
container turns a recoverable incident into an outage of its own.
``/health/ready`` asks "should traffic go here?" and does check dependencies.

``/health`` is kept as the detailed human- and dashboard-facing view.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.jobs import queue
from app.schemas.health import HealthOut, LivenessOut
from app.stores import document_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LivenessOut)
def liveness() -> LivenessOut:
    """Process is running and can serve a response. No dependencies touched."""
    return LivenessOut(status="ok", version=settings.APP_VERSION)


@router.get("/health", response_model=HealthOut)
def health(response: Response, db: Session = Depends(get_db)) -> HealthOut:
    """Dependency detail.

    Every probe is individually guarded. A health endpoint that raises tells
    you only that something is wrong, which is precisely the information you
    already had — the point is to report *which* component failed.
    """
    database_ok = True
    chunk_count = 0
    jobs: dict[str, int] = {}

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        database_ok = False

    if database_ok:
        try:
            chunk_count = document_repository.count_chunks(db)
        except Exception:
            logger.exception("Chunk count failed")
            database_ok = False

        try:
            jobs = queue.queue_depth(db)
        except Exception:
            # The queue table being unreadable while plain queries work is
            # worth reporting, but it does not make the service unable to
            # answer questions about documents already ingested.
            logger.exception("Queue depth check failed")

    if not database_ok:
        # Without this the orchestrator sees a 200 and keeps routing traffic
        # to an instance that cannot answer anything.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthOut(
        status="ok" if database_ok else "degraded",
        version=settings.APP_VERSION,
        database=database_ok,
        indexed_chunks=chunk_count,
        jobs=jobs,
    )


@router.get("/health/ready", response_model=HealthOut)
def readiness(response: Response, db: Session = Depends(get_db)) -> HealthOut:
    return health(response, db)
