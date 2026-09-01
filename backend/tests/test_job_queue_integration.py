"""The job queue against a real Postgres.

``SKIP LOCKED`` semantics and partial unique indexes only exist in the
database, so these are the tests that actually verify a crash does not strand
a document — the thing the queue was added for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db.models import Document, IngestionJob, IngestionStatus, JobStatus, User
from app.jobs import queue
from tests.conftest import requires_database

pytestmark = requires_database


@pytest.fixture
def pending_document(db_session):
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", password_hash="x")
    document = Document(
        id=uuid.uuid4(),
        owner_id=user.id,
        title="handbook",
        filename="handbook.md",
        content_type="text/markdown",
        byte_size=10,
        checksum=uuid.uuid4().hex,
        status=IngestionStatus.PENDING,
    )
    # Two flushes, not one: without a relationship() between User and Document
    # SQLAlchemy will not reliably order the users INSERT before the documents
    # INSERT, and the foreign key fails.
    db_session.add(user)
    db_session.flush()
    db_session.add(document)
    db_session.flush()
    return document


def enqueue(db_session, document) -> IngestionJob:
    return queue.enqueue(
        db_session,
        document_id=document.id,
        owner_id=document.owner_id,
        file_path=Path("/data/uploads/example.md"),
    )


def test_claiming_moves_the_job_and_the_document_together(db_session, pending_document):
    enqueue(db_session, pending_document)

    job = queue.claim_next(db_session, "worker-1")

    assert job is not None
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 1
    assert job.locked_by == "worker-1"

    db_session.refresh(pending_document)
    assert pending_document.status == IngestionStatus.PROCESSING


def test_a_claimed_job_is_not_handed_to_a_second_worker(db_session, pending_document):
    enqueue(db_session, pending_document)

    assert queue.claim_next(db_session, "worker-1") is not None
    assert queue.claim_next(db_session, "worker-2") is None


def test_an_empty_queue_returns_none_rather_than_blocking(db_session):
    assert queue.claim_next(db_session, "worker-1") is None


def test_only_one_live_job_may_exist_per_document(db_session, pending_document):
    """Double-clicking upload must not create two workers racing on one file."""
    enqueue(db_session, pending_document)

    with pytest.raises(IntegrityError):
        enqueue(db_session, pending_document)
    db_session.rollback()


def test_a_transient_failure_requeues_with_a_future_run_after(
    db_session, pending_document
):
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "worker-1")

    will_retry = queue.mark_failed(db_session, job, "connection reset")

    assert will_retry is True
    assert job.status == JobStatus.QUEUED
    assert job.run_after > datetime.now(UTC)

    # The document must not read as failed while a retry is still coming.
    db_session.refresh(pending_document)
    assert pending_document.status == IngestionStatus.PENDING


def test_a_backed_off_job_is_invisible_until_its_delay_elapses(
    db_session, pending_document
):
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "worker-1")
    queue.mark_failed(db_session, job, "connection reset")

    assert queue.claim_next(db_session, "worker-1") is None


def test_a_permanent_failure_skips_straight_to_dead(db_session, pending_document):
    """An empty PDF fails identically on every attempt. Spending the full
    backoff to confirm that only delays telling the user."""
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "worker-1")

    will_retry = queue.mark_failed(
        db_session, job, "No extractable text found.", permanent=True
    )

    assert will_retry is False
    assert job.status == JobStatus.DEAD
    db_session.refresh(pending_document)
    assert pending_document.status == IngestionStatus.FAILED
    assert pending_document.error == "No extractable text found."


def test_retries_stop_at_max_attempts(db_session, pending_document):
    enqueue(db_session, pending_document)

    for _ in range(settings.JOB_MAX_ATTEMPTS):
        job = db_session.get(
            IngestionJob,
            db_session.query(IngestionJob.id).scalar(),
        )
        job.status = JobStatus.QUEUED
        job.run_after = datetime.now(UTC) - timedelta(seconds=1)
        db_session.commit()

        claimed = queue.claim_next(db_session, "worker-1")
        assert claimed is not None
        queue.mark_failed(db_session, claimed, "still failing")

    assert claimed.status == JobStatus.DEAD
    db_session.refresh(pending_document)
    assert pending_document.status == IngestionStatus.FAILED


def test_the_reaper_requeues_a_job_whose_worker_died(db_session, pending_document):
    """The crash-recovery case.

    Without this the job stays RUNNING forever and its document sits in
    'processing' with nothing working on it and no error to show — exactly the
    stuck state the queue exists to prevent.
    """
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "doomed-worker")

    job.heartbeat_at = datetime.now(UTC) - timedelta(
        seconds=settings.JOB_STALE_AFTER_SECONDS + 60
    )
    db_session.commit()

    requeued = queue.reap_stale_jobs(db_session)

    assert requeued == 1
    db_session.refresh(job)
    assert job.status == JobStatus.QUEUED
    assert job.locked_by is None


def test_the_reaper_leaves_a_healthy_job_alone(db_session, pending_document):
    """A slow document must not be mistaken for a dead worker — requeuing it
    would put two workers on the same file."""
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "busy-worker")
    queue.heartbeat(db_session, job.id)

    assert queue.reap_stale_jobs(db_session) == 0
    db_session.refresh(job)
    assert job.status == JobStatus.RUNNING


def test_success_records_duration_and_clears_the_lock(db_session, pending_document):
    enqueue(db_session, pending_document)
    job = queue.claim_next(db_session, "worker-1")

    queue.mark_succeeded(db_session, job, 1234.5)

    assert job.status == JobStatus.SUCCEEDED
    assert job.duration_ms == pytest.approx(1234.5)
    assert job.locked_by is None
    assert job.last_error is None


def test_queue_depth_reports_every_status(db_session, pending_document):
    enqueue(db_session, pending_document)
    depth = queue.queue_depth(db_session)

    assert depth[JobStatus.QUEUED.value] == 1
    assert depth[JobStatus.DEAD.value] == 0
