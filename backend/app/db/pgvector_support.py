"""Capability detection for the pgvector extension.

Two search-time settings materially change filtered vector search, and one of
them only exists in pgvector 0.8 and later. Issuing ``SET LOCAL`` for a GUC
the server does not know is not a warning — it aborts the transaction. So the
version is checked once per process and the result cached, rather than
guessing or wrapping every query in a try/except that would swallow real
errors alongside the expected one.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

_ITERATIVE_SCAN_MIN_VERSION = (0, 8)
_supports_iterative_scan: bool | None = None


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in raw.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def detect(session: Session) -> bool:
    """Whether this server supports ``hnsw.iterative_scan``. Cached per process."""
    global _supports_iterative_scan
    if _supports_iterative_scan is not None:
        return _supports_iterative_scan

    raw = session.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    )
    if raw is None:
        raise RuntimeError(
            "The 'vector' extension is not installed in this database. Run the "
            "Alembic migrations, and make sure the Postgres image includes "
            "pgvector (see docker-compose.yml)."
        )

    _supports_iterative_scan = _parse_version(raw) >= _ITERATIVE_SCAN_MIN_VERSION
    if not _supports_iterative_scan:
        logger.warning(
            "pgvector %s predates iterative index scans. Filtered vector search "
            "may return fewer than VECTOR_CANDIDATE_COUNT rows for a user whose "
            "chunks are a small share of the corpus, which costs recall without "
            "raising an error. Upgrade to pgvector 0.8 or later.",
            raw,
            extra={"pgvector_version": raw},
        )
    return _supports_iterative_scan


def apply_search_settings(session: Session) -> None:
    """Configure HNSW search behaviour for the current transaction.

    ``SET LOCAL`` scopes these to the transaction, so they cannot leak onto
    the next request that borrows the same pooled connection.
    """
    session.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}"))

    if detect(session):
        session.execute(
            text(f"SET LOCAL hnsw.iterative_scan = '{settings.HNSW_ITERATIVE_SCAN}'")
        )
        session.execute(
            text(
                "SET LOCAL hnsw.max_scan_tuples = "
                f"{int(settings.HNSW_MAX_SCAN_TUPLES)}"
            )
        )


def reset_cache() -> None:
    """Test hook. Production never needs this — the version cannot change
    under a running process."""
    global _supports_iterative_scan
    _supports_iterative_scan = None
