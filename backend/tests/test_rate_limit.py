from __future__ import annotations

import pytest

from app.errors import RateLimitedError
from app.security import rate_limit
from app.security.rate_limit import SlidingWindowLimiter

MAX_ATTEMPTS = 3
WINDOW = 60
TRACKED_KEYS = 100
KEY = "203.0.113.7|user@example.com"


@pytest.fixture
def clock(monkeypatch):
    """A controllable stand-in for the limiter's monotonic clock."""
    current = {"t": 1000.0}
    monkeypatch.setattr(rate_limit, "_now", lambda: current["t"])
    return current


@pytest.fixture
def limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(
        max_attempts=MAX_ATTEMPTS,
        window_seconds=WINDOW,
        max_tracked_keys=TRACKED_KEYS,
    )


def test_attempts_up_to_the_limit_are_allowed(clock, limiter):
    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)


def test_the_next_attempt_is_refused(clock, limiter):
    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)

    with pytest.raises(RateLimitedError):
        limiter.check(KEY)


def test_refusal_reports_how_long_to_wait(clock, limiter):
    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)

    with pytest.raises(RateLimitedError) as caught:
        limiter.check(KEY)

    assert int(caught.value.headers["Retry-After"]) <= WINDOW + 1


def test_keys_are_limited_independently(clock, limiter):
    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)

    limiter.check("198.51.100.4|other@example.com")


def test_the_window_slides(clock, limiter):
    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)

    clock["t"] += WINDOW + 1

    limiter.check(KEY)


def test_reset_clears_a_key_so_success_forgives_earlier_typos(clock, limiter):
    for _ in range(MAX_ATTEMPTS - 1):
        limiter.check(KEY)

    limiter.reset(KEY)

    for _ in range(MAX_ATTEMPTS):
        limiter.check(KEY)


def test_stale_keys_are_evicted_so_memory_stays_bounded(clock):
    limiter = SlidingWindowLimiter(
        max_attempts=MAX_ATTEMPTS, window_seconds=WINDOW, max_tracked_keys=2
    )
    for index in range(5):
        limiter.check(f"key-{index}")

    clock["t"] += WINDOW + 1
    limiter.check("trigger-eviction")

    # Reaching into private state on purpose: unbounded growth here is a
    # memory leak, and there is no public surface that would reveal it.
    assert len(limiter._hits) == 1
