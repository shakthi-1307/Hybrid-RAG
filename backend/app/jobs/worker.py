"""The ingestion worker.

Runs as its own process (``python -m app.worker``). Two reasons it is not a
thread inside the API:

* Embedding a large PDF pins a core for minutes. In the API process that
  competes with request handling, and a document big enough to trigger the
  OOM killer takes the API down with it.
* The models load once here instead of once per API worker, which is most of
  the API container's memory footprint.

Each job gets its own database session. Sharing one across jobs would mean a
failed transaction poisoning the next job's session, turning one bad document
into a stalled worker.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from pathlib import Path
from types import FrameType
from uuid import UUID

from app.config import settings
from app.db.models import IngestionJob
from app.db.session import SessionFactory
from app.ingestion.pipeline import PermanentIngestionError, ingest_document
from app.jobs import queue
from app.observability.context import set_request_id, set_user_id
from app.observability.timing import current_timer, start_timer

logger = logging.getLogger(__name__)


def build_worker_id() -> str:
    """Host and pid. Enough to identify which process holds a job when two are
    running and one has gone quiet."""
    return f"{socket.gethostname()}:{os.getpid()}"


class Heartbeat:
    """Writes a liveness timestamp on an interval while a job runs.

    A daemon thread with its own session: the ingestion work holds the main
    session inside a long transaction, and a heartbeat sharing it would either
    block behind that transaction or commit it early.
    """

    def __init__(self, job_id: UUID, interval: float) -> None:
        self._job_id = job_id
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="heartbeat")

    def __enter__(self) -> Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1.0)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with SessionFactory() as session:
                    queue.heartbeat(session, self._job_id)
            except Exception:
                # A failed heartbeat must not kill the job it is reporting on.
                # Worst case the reaper requeues work that was actually fine,
                # which retries — losing the document would be worse.
                logger.exception("Heartbeat failed", extra={"job_id": str(self._job_id)})


class Worker:
    def __init__(self) -> None:
        self.worker_id = build_worker_id()
        self._shutdown = threading.Event()
        self._last_reap = 0.0

    def request_shutdown(self, signum: int, _: FrameType | None) -> None:
        """Finish the job in hand, then stop.

        Killing mid-document would be safe — the reaper would requeue it — but
        wasteful, since the work would restart from zero.
        """
        logger.info(
            "Signal %s received; finishing current job then shutting down", signum
        )
        self._shutdown.set()

    def run(self) -> None:
        logger.info(
            "Ingestion worker %s started",
            self.worker_id,
            extra={"worker_id": self.worker_id},
        )

        while not self._shutdown.is_set():
            try:
                self._maybe_reap()
                claimed = self._process_one()
            except Exception:
                # The loop is the last line of defence. A crash here stops
                # ingestion entirely, so every escape is caught, logged, and
                # backed off rather than allowed to end the process.
                logger.exception("Worker loop error; backing off")
                self._shutdown.wait(settings.JOB_POLL_INTERVAL_SECONDS)
                continue

            if not claimed:
                # Polling, not listening. At ingestion's timescale a couple of
                # seconds of latency is irrelevant, and LISTEN/NOTIFY would
                # add a persistent connection and a reconnect path to
                # maintain. Worth revisiting only if jobs get small and
                # frequent.
                self._shutdown.wait(settings.JOB_POLL_INTERVAL_SECONDS)

        logger.info("Ingestion worker %s stopped", self.worker_id)

    def _maybe_reap(self) -> None:
        now = time.monotonic()
        if now - self._last_reap < settings.JOB_REAPER_INTERVAL_SECONDS:
            return
        self._last_reap = now

        with SessionFactory() as session:
            requeued = queue.reap_stale_jobs(session)
            purged = queue.purge_old_jobs(session)

        if requeued or purged:
            logger.info(
                "Reaper requeued %d stale job(s), purged %d old job(s)",
                requeued,
                purged,
                extra={"requeued": requeued, "purged": purged},
            )

    def _process_one(self) -> bool:
        with SessionFactory() as session:
            job = queue.claim_next(session, self.worker_id)
            if job is None:
                return False
            self._run_job(session, job)
        return True

    def _run_job(self, session: object, job: IngestionJob) -> None:
        # Carry the upload's request id into the worker so one search across
        # both processes returns the upload and everything it caused.
        set_request_id(job.request_id or f"job-{job.id.hex[:12]}")
        set_user_id(str(job.owner_id))
        timer = start_timer()

        logger.info(
            "Processing document %s (attempt %d/%d)",
            job.document_id,
            job.attempts,
            job.max_attempts,
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "attempts": job.attempts,
            },
        )

        with Heartbeat(job.id, settings.JOB_HEARTBEAT_INTERVAL_SECONDS):
            try:
                chunk_count = ingest_document(
                    session,  # type: ignore[arg-type]
                    job.owner_id,
                    job.document_id,
                    Path(job.file_path),
                )
            except PermanentIngestionError as exc:
                queue.mark_failed(session, job, exc.message, permanent=True)  # type: ignore[arg-type]
                self._log_stages(job, success=False)
                return
            except Exception as exc:
                queue.mark_failed(session, job, f"{type(exc).__name__}: {exc}")  # type: ignore[arg-type]
                logger.exception("Ingestion raised", extra={"job_id": str(job.id)})
                self._log_stages(job, success=False)
                return

            queue.mark_succeeded(session, job, timer.elapsed_ms())  # type: ignore[arg-type]

        logger.info(
            "Document %s ingested into %d chunks",
            job.document_id,
            chunk_count,
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "chunk_count": chunk_count,
            },
        )
        self._log_stages(job, success=True)

    def _log_stages(self, job: IngestionJob, success: bool) -> None:
        timer = current_timer()
        if timer is None:
            return

        logger.info(
            "Ingestion job finished in %.0f ms",
            timer.elapsed_ms(),
            extra={
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "duration_ms": round(timer.elapsed_ms(), 1),
                "succeeded": success,
                "stages": timer.as_dict(),
            },
        )
        if settings.LOG_TIMING_BREAKDOWN:
            logger.info("\n%s", timer.render_breakdown(f"job-{job.id.hex[:12]}"))


def main() -> None:
    from app.observability.logging_config import configure_logging
    from app.startup_checks import verify_configuration

    configure_logging()
    verify_configuration()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    worker = Worker()
    # SIGTERM is what a container runtime sends first; SIGINT is Ctrl-C.
    # Handling both means a compose down and a local interrupt behave the same.
    signal.signal(signal.SIGTERM, worker.request_shutdown)
    signal.signal(signal.SIGINT, worker.request_shutdown)
    worker.run()
