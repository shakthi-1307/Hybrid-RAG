"""Per-request identity, carried without threading it through every signature.

A ``ContextVar`` is the right tool here rather than a global: it is scoped to
the task or thread that set it, so two concurrent requests never see each
other's values. FastAPI copies the context into the threadpool it uses for
``def`` endpoints, which is what lets a synchronous route deep in the call
stack still log the right request id.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

from app.config import settings

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)

# An inbound header is echoed into logs and response headers, so it is treated
# as untrusted input: anything outside this set is discarded and replaced.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def new_request_id() -> str:
    """A short, unambiguous id. 16 hex characters is ~64 bits — plenty to keep
    collisions out of a log search, and short enough to read aloud."""
    return uuid.uuid4().hex[:16]


def sanitize_request_id(candidate: str | None) -> str:
    """Accept an upstream id only if it is safe to echo, else mint a new one."""
    if candidate is None:
        return new_request_id()

    candidate = candidate.strip()
    # Rejected, not truncated. A truncated id still looks like a valid one but
    # no longer matches what the upstream system recorded, so the trace it was
    # sent to join silently fails to join — worse than an obviously new id.
    if (
        not candidate
        or len(candidate) > settings.REQUEST_ID_MAX_LENGTH
        or not _SAFE_REQUEST_ID.match(candidate)
    ):
        return new_request_id()
    return candidate


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_user_id(value: str | None) -> Token[str | None]:
    """Set once authentication resolves.

    Deliberately separate from ``set_request_id``: the request id exists from
    the first byte, the user id only after the cookie has been verified, and
    conflating them would mean logging an unauthenticated request as if it had
    an owner.
    """
    return _user_id.set(value)


def get_user_id() -> str | None:
    return _user_id.get()


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def reset_user_id(token: Token[str | None]) -> None:
    _user_id.reset(token)
