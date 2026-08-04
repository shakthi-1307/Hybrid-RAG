"""In-process sliding-window rate limiting for unauthenticated endpoints.

Scope and limits: this is per-process state. Behind several API instances the
effective limit is multiplied by the instance count, which still bounds abuse
but is not exact. Moving to a shared store (Redis) is the upgrade path; the
call sites do not change.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request

from app.config import settings
from app.errors import RateLimitedError


def _now() -> float:
    """Indirection so tests can advance the clock without sleeping."""
    return time.monotonic()


def client_identifier(request: Request) -> str:
    """Best-effort caller identity for limiting.

    Reads ``X-Forwarded-For`` from the right by the number of proxies we
    actually run, so a caller cannot lift their own limit by sending a header.
    """
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        chain = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    def __init__(
        self, max_attempts: int, window_seconds: int, max_tracked_keys: int
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._max_tracked_keys = max_tracked_keys
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        """Record an attempt, or raise if ``key`` is over its allowance."""
        now = _now()
        with self._lock:
            self._evict_stale(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self._window:
                hits.popleft()

            if len(hits) >= self._max_attempts:
                raise RateLimitedError(
                    "Too many attempts. Try again shortly.",
                    retry_after_seconds=int(self._window - (now - hits[0])) + 1,
                )
            hits.append(now)

    def reset(self, key: str) -> None:
        """Clear a key's history — called on success so a legitimate user is
        not locked out by their own earlier typos."""
        with self._lock:
            self._hits.pop(key, None)

    def _evict_stale(self, now: float) -> None:
        if len(self._hits) <= self._max_tracked_keys:
            return
        expired = [
            key
            for key, hits in self._hits.items()
            if not hits or now - hits[-1] > self._window
        ]
        for key in expired:
            del self._hits[key]


login_limiter = SlidingWindowLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    max_tracked_keys=settings.RATE_LIMIT_MAX_TRACKED_KEYS,
)

register_limiter = SlidingWindowLimiter(
    max_attempts=settings.REGISTER_RATE_LIMIT_ATTEMPTS,
    window_seconds=settings.REGISTER_RATE_LIMIT_WINDOW_SECONDS,
    max_tracked_keys=settings.RATE_LIMIT_MAX_TRACKED_KEYS,
)
