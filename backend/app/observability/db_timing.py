"""Attributes time spent inside the database to the request that caused it.

Hooking SQLAlchemy's cursor events measures what actually happened rather than
what the code looks like it does. An N+1 query pattern shows up here as a
large ``database`` total with a high query count, which reading the source
would not have revealed.

Registered once against the engine at import of ``app.db.session``.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.observability.timing import Stage, current_timer

_START_KEY = "_stage_timer_start"


def install(engine: Engine) -> None:
    # SQLAlchemy invokes these positionally against a fixed signature, so
    # every parameter has to be present even though most are unused here.
    # Underscore-prefixed to say that deliberately rather than suppress it.
    @event.listens_for(engine, "before_cursor_execute")
    def _before(
        conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        _context: Any,
        _many: bool,
    ) -> None:
        # Stashed on the connection's info dict rather than a module global:
        # a pool serves many concurrent connections, and a global would have
        # them overwriting each other's start times.
        conn.info.setdefault(_START_KEY, []).append(perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(
        conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        _context: Any,
        _many: bool,
    ) -> None:
        stack = conn.info.get(_START_KEY)
        if not stack:
            return
        elapsed_ms = (perf_counter() - stack.pop()) * 1000.0

        timer = current_timer()
        if timer is not None:
            timer.record(Stage.DATABASE, elapsed_ms)
