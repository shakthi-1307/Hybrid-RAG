"""Request-scoped context, timing, and the one log line per request.

This is the only place that decides what a completed request looks like in the
logs. Routes never log their own completion, so the format cannot drift
endpoint by endpoint.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.observability.context import (
    reset_request_id,
    reset_user_id,
    sanitize_request_id,
    set_request_id,
    set_user_id,
)
from app.observability.timing import current_timer, start_timer

logger = logging.getLogger("app.request")

# Health checks run every few seconds forever. Logging them at INFO buries
# everything else, and their failures are already reported by the status code
# the orchestrator sees.
_QUIET_PATHS = frozenset(
    {"/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"}
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = sanitize_request_id(request.headers.get(settings.REQUEST_ID_HEADER))
        request_token = set_request_id(request_id)
        user_token = set_user_id(None)
        timer = start_timer()

        # Exposed on request.state so a route or dependency can read the id
        # without importing the contextvar module.
        request.state.request_id = request_id

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[settings.REQUEST_ID_HEADER] = request_id
            return response
        finally:
            self._log_completion(request, status_code, timer.elapsed_ms(), request_id)
            reset_user_id(user_token)
            reset_request_id(request_token)

    def _log_completion(
        self, request: Request, status_code: int, duration_ms: float, request_id: str
    ) -> None:
        if request.url.path in _QUIET_PATHS and status_code < 400:
            return

        timer = current_timer()
        stages = timer.as_dict() if timer else {}

        if status_code >= 500:
            level = logging.ERROR
        elif duration_ms >= settings.SLOW_REQUEST_MS:
            level = logging.WARNING
        else:
            level = logging.INFO

        logger.log(
            level,
            "%s %s -> %s in %.0f ms",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": status_code,
                "duration_ms": round(duration_ms, 1),
                "stages": stages,
            },
        )

        if settings.LOG_TIMING_BREAKDOWN and timer is not None and stages:
            # Emitted as its own record so the structured line above stays one
            # parseable object per line.
            logger.log(level, "\n%s", timer.render_breakdown(request_id))
