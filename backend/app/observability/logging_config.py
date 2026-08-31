"""Process-wide logging configuration. Called once at startup.

Two renderers over one set of fields. ``json`` emits a single object per line
for anything that ships logs to a collector; ``console`` emits the same fields
formatted for a human reading a terminal. Choosing between them must never
change *which* fields exist, only how they are drawn — otherwise a bug is
visible in development and invisible in production.

Every record carries ``request_id`` and ``user_id``, injected by a filter
rather than passed by callers. A logging call in a module three layers deep
should not have to know it is inside a request to be traceable.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

from app.config import settings
from app.observability.context import get_request_id, get_user_id

# Attributes the stdlib puts on every LogRecord. Anything *not* in this set was
# attached by a caller via ``extra=`` and is worth emitting as a structured
# field, which is how a log line gets useful data without string formatting.
_STANDARD_ATTRIBUTES = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
        "request_id",
        "user_id",
    }
)


class ContextFilter(logging.Filter):
    """Copies the current request id and user id onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.user_id = get_user_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRIBUTES and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str so a UUID, Path, or datetime in an ``extra`` cannot take
        # the whole log line down. Losing type fidelity in a log beats losing
        # the log.
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable, with the request id in front of the message."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = getattr(record, "request_id", None)
        return f"[{request_id}] {base}" if request_id else base


def configure_logging() -> None:
    if settings.LOG_RENDERER == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = ConsoleFormatter(settings.LOG_CONSOLE_FORMAT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)

    # uvicorn installs its own handlers at import. Left alone, every access log
    # line would be emitted twice — once in its format, once in ours — and
    # neither copy would carry a request id.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # uvicorn.access duplicates what RequestContextMiddleware already logs,
    # minus the request id and the stage breakdown. Silence it rather than
    # print each request twice.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
