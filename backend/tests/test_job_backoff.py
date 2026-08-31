"""Retry backoff arithmetic.

Small surface, but it decides how long a user waits before a transient
failure resolves itself, and an unbounded doubling is the kind of bug that
only shows up on the attempt nobody tested.
"""

from __future__ import annotations

from app.config import settings
from app.jobs.queue import backoff_delay_seconds


def test_first_retry_waits_the_base_delay():
    assert backoff_delay_seconds(1) == settings.JOB_BACKOFF_BASE_SECONDS


def test_delay_doubles_with_each_attempt():
    assert backoff_delay_seconds(2) == settings.JOB_BACKOFF_BASE_SECONDS * 2
    assert backoff_delay_seconds(3) == settings.JOB_BACKOFF_BASE_SECONDS * 4


def test_delay_is_capped():
    """Without a cap the doubling eventually schedules a retry days out, which
    a user cannot distinguish from the document never finishing."""
    assert backoff_delay_seconds(50) == settings.JOB_BACKOFF_MAX_SECONDS


def test_zero_attempts_is_treated_as_the_first():
    """Defensive: a job claimed but not yet incremented should not produce a
    negative exponent and a sub-second retry storm."""
    assert backoff_delay_seconds(0) == settings.JOB_BACKOFF_BASE_SECONDS


def test_stale_window_exceeds_heartbeat_interval():
    """A guard on configuration, not code.

    If the staleness window is not comfortably larger than the heartbeat
    interval, the reaper requeues jobs that are still running normally and two
    workers end up processing the same document.
    """
    assert settings.JOB_STALE_AFTER_SECONDS > (
        settings.JOB_HEARTBEAT_INTERVAL_SECONDS * 3
    )
