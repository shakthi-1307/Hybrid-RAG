"""The ingestion job queue, backed by a Postgres table.

Why a table and not a broker: the jobs are already about rows in this
database, and a broker would add a second system that can disagree with it —
a job saying "ready" for a document that was deleted, or a document stuck in
``processing`` with nothing queued. Claiming with ``SELECT ... FOR UPDATE SKIP
LOCKED`` gives exactly-one-worker semantics without that split brain, and the
claim is transactional, so a worker that dies mid-job releases its lock rather
than taking the job down with it.

What this does not give you: throughput past a few hundred jobs a second, and
fan-out to other consumers. Neither is a constraint here — ingestion is
minutes of CPU per document, so the queue is never the bottleneck. If it ever
becomes one, the swap is to a broker and this module is the seam.

Three mechanisms keep a crash from stranding work:

1. **The claim is a transaction.** A worker killed between claiming and
   finishing never committed anything, so the row stays as it was.
2. **Heartbeats.** A running job writes a timestamp on an interval. The reaper
   requeues jobs whose heartbeat went stale, which covers the case where the
   process was killed with the transaction already committed.
3. **Bounded attempts.** Retries back off exponentially and stop at
   ``JOB_MAX_ATTEMPTS``, so a document that fails every time ends up DEAD with
   its error recorded instead of cycling forever.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Document, IngestionJob, IngestionStatus, JobStatus
from app.observability.context import get_request_id

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def backoff_delay_seconds(attempts: int) -> int:
    """Exponential backoff, capped.

    Attempt 1 waits the base delay, attempt 2 twice that, and so on. The cap
    matters because an unbounded doubling would eventually schedule a retry
    days out, which reads to a user as the document silently never finishing.
    """
    if attempts < 1:
        return settings.JOB_BACKOFF_BASE_SECONDS
    delay = settings.JOB_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
    return int(min(delay, settings.JOB_BACKOFF_MAX_SECONDS))


def enqueue(
    session: Session,
    *,
    document_id: UUID,
    owner_id: UUID,
    file_path: Path,
) -> IngestionJob:
    """Queue a document for ingestion.

    A partial unique index allows only one live job per document, so a double
    submission raises rather than creating two workers racing over the same
    rows. The caller treats that as success — the work is already scheduled.
    """
    job = IngestionJob(
        document_id=document_id,
        owner_id=owner_id,
        file_path=str(file_path),
        status=JobStatus.QUEUED,
        attempts=0,
        max_attempts=settings.JOB_MAX_ATTEMPTS,
        run_after=_now(),
        request_id=get_request_id(),
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    logger.info(
        "Queued ingestion job for document %s",
        document_id,
        extra={"job_id": str(job.id), "document_id": str(document_id)},
    )
    return job


def claim_next(session: Session, worker_id: str) -> IngestionJob | None:
    """Atomically take the oldest due job, or return None.

    ``FOR UPDATE SKIP LOCKED`` inside the subquery is what makes this safe to
    run from several workers at once: each skips rows another has locked
    instead of blocking on them, so N workers pick up N different jobs with no
    coordination between them.

    Due-ness is tested against ``clock_timestamp()`` rather than ``now()``.
    ``now()`` is transaction start time, frozen for the life of the
    transaction, so a job that became due while the transaction was open would
    stay invisible until the next one — and a long-running transaction would
    hold the whole queue back. ``clock_timestamp()`` reads the real clock.
    """
    claim = text(
        """
        UPDATE ingestion_jobs
        SET status = 'running',
            attempts = attempts + 1,
            locked_by = :worker_id,
            heartbeat_at = now(),
            updated_at = now()
        WHERE id = (
            SELECT id
            FROM ingestion_jobs
            WHERE status = 'queued'
              AND run_after <= clock_timestamp()
            ORDER BY run_after, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id
        """
    )
    job_id = session.execute(claim, {"worker_id": worker_id}).scalar()
    if job_id is None:
        session.commit()
        return None

    job = session.get(IngestionJob, job_id)
    if job is not None:
        _set_document_status(session, job, IngestionStatus.PROCESSING)
    session.commit()
    if job is not None:
        session.refresh(job)
    return job


def heartbeat(session: Session, job_id: UUID) -> None:
    """Signal that the job is still being worked on.

    Deliberately narrow: it touches one column, so it cannot interfere with
    whatever the ingestion transaction is doing.
    """
    session.execute(
        update(IngestionJob).where(IngestionJob.id == job_id).values(heartbeat_at=_now())
    )
    session.commit()


def mark_succeeded(session: Session, job: IngestionJob, duration_ms: float) -> None:
    job.status = JobStatus.SUCCEEDED
    job.last_error = None
    job.duration_ms = duration_ms
    job.locked_by = None
    job.heartbeat_at = None
    job.updated_at = _now()
    session.commit()


def mark_failed(
    session: Session,
    job: IngestionJob,
    error: str,
    *,
    permanent: bool = False,
) -> bool:
    """Record a failure. Returns True if the job will be retried.

    A permanent error skips straight to DEAD: an empty PDF fails the same way
    on attempt three as on attempt one, and spending fifteen minutes of
    backoff to confirm that only delays telling the user.
    """
    # Errors go to the user, so they are truncated: a driver traceback can run
    # to kilobytes, and the column is not a log.
    error = error.strip()[:2000]
    exhausted = job.attempts >= job.max_attempts
    will_retry = not permanent and not exhausted

    job.last_error = error
    job.locked_by = None
    job.heartbeat_at = None
    job.updated_at = _now()

    if will_retry:
        delay = backoff_delay_seconds(job.attempts)
        job.status = JobStatus.QUEUED
        job.run_after = _now() + timedelta(seconds=delay)
        # The document goes back to PENDING, not FAILED: it is still going to
        # be processed, and showing "failed" for something that will succeed
        # in thirty seconds is a lie the UI would have to walk back.
        _set_document_status(session, job, IngestionStatus.PENDING, error=error)
        logger.warning(
            "Ingestion attempt %d/%d failed, retrying in %ds: %s",
            job.attempts,
            job.max_attempts,
            delay,
            error,
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "attempts": job.attempts,
                "retry_in_seconds": delay,
            },
        )
    else:
        job.status = JobStatus.DEAD
        _set_document_status(session, job, IngestionStatus.FAILED, error=error)
        logger.error(
            "Ingestion permanently failed after %d attempt(s): %s",
            job.attempts,
            error,
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "attempts": job.attempts,
                "permanent": permanent,
            },
        )

    session.commit()
    return will_retry


def _set_document_status(
    session: Session,
    job: IngestionJob,
    status: IngestionStatus,
    error: str | None = None,
) -> None:
    """Keep the document's user-visible status in step with its job.

    Uses a targeted UPDATE rather than loading the ORM object, so it cannot
    accidentally flush unrelated pending changes on the session.
    """
    session.execute(
        update(Document)
        .where(Document.id == job.document_id)
        .values(status=status, error=error)
    )


def reap_stale_jobs(session: Session) -> int:
    """Requeue jobs whose worker stopped reporting. Returns how many.

    This is the mechanism that answers "the machine died mid-ingest". Without
    it, a job that was RUNNING when the process was killed stays RUNNING
    forever, and its document sits in ``processing`` with nothing working on
    it and no error to show.

    The staleness window has to exceed the slowest realistic document, or a
    long ingestion gets requeued while it is still succeeding, and two workers
    end up on the same document.
    """
    cutoff = _now() - timedelta(seconds=settings.JOB_STALE_AFTER_SECONDS)

    stale = list(
        session.scalars(
            select(IngestionJob).where(
                IngestionJob.status == JobStatus.RUNNING,
                IngestionJob.heartbeat_at < cutoff,
            )
        ).all()
    )

    for job in stale:
        logger.warning(
            "Requeuing job abandoned by worker %s",
            job.locked_by,
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "attempts": job.attempts,
                "last_heartbeat": job.heartbeat_at,
            },
        )
        mark_failed(
            session,
            job,
            f"Worker {job.locked_by or 'unknown'} stopped responding; requeued.",
        )

    return len(stale)


def purge_old_jobs(session: Session) -> int:
    """Delete terminal jobs past the retention window."""
    cutoff = _now() - timedelta(hours=settings.JOB_RETENTION_HOURS)
    result = session.execute(
        text(
            """
            DELETE FROM ingestion_jobs
            WHERE status IN ('succeeded', 'dead')
              AND updated_at < :cutoff
            """
        ),
        {"cutoff": cutoff},
    )
    session.commit()
    return int(result.rowcount or 0)


def queue_depth(session: Session) -> dict[str, int]:
    """Counts by status, for the health endpoint.

    A growing ``queued`` with a flat ``succeeded`` is the signal that the
    worker has stopped, which is otherwise invisible from the API side.
    """
    rows = session.execute(
        text("SELECT status, count(*) FROM ingestion_jobs GROUP BY status")
    ).all()
    counts = {status.value: 0 for status in JobStatus}
    for status, count in rows:
        counts[str(status)] = int(count)
    return counts
