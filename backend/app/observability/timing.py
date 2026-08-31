"""Per-request latency attribution.

The question this answers is "the request took 2.8 seconds — where did it go?"
Answering it needs the breakdown collected at the point the work happens and
reported once at the end, not scattered across a dozen log lines that have to
be correlated by hand afterwards.

Usage is a context manager at each stage boundary::

    with stage(Stage.VECTOR_SEARCH):
        hits = ...

Stages nest safely but are recorded flat, and repeated entries into the same
stage accumulate — five embedding calls report as one ``embed`` total with a
count of five, which is what you want when reading a latency report.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter

logger = logging.getLogger(__name__)


class Stage:
    """Stage names, in the order they appear in a request.

    Declared as constants rather than free strings so a typo is an
    AttributeError at import time instead of a silently missing row in the
    latency report.
    """

    DATABASE = "database"
    EMBED_QUERY = "embed_query"
    VECTOR_SEARCH = "vector_search"
    LEXICAL_SEARCH = "lexical_search"
    FUSION = "fusion"
    HYDRATE = "hydrate"
    RERANK = "rerank"
    LLM = "llm"
    LOAD = "load"
    CHUNK = "chunk"
    EMBED_PASSAGES = "embed_passages"
    PERSIST = "persist"

    ORDER = (
        DATABASE,
        EMBED_QUERY,
        VECTOR_SEARCH,
        LEXICAL_SEARCH,
        FUSION,
        HYDRATE,
        RERANK,
        LLM,
        LOAD,
        CHUNK,
        EMBED_PASSAGES,
        PERSIST,
    )

    LABELS = {
        DATABASE: "Database",
        EMBED_QUERY: "Embed query",
        VECTOR_SEARCH: "Vector search",
        LEXICAL_SEARCH: "Lexical search",
        FUSION: "Fusion",
        HYDRATE: "Hydrate",
        RERANK: "Reranking",
        LLM: "LLM",
        LOAD: "Load",
        CHUNK: "Chunk",
        EMBED_PASSAGES: "Embed passages",
        PERSIST: "Persist",
    }


@dataclass
class StageTimer:
    """Accumulates elapsed milliseconds per stage for one request."""

    totals: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=perf_counter)

    def record(self, name: str, elapsed_ms: float) -> None:
        self.totals[name] = self.totals.get(name, 0.0) + elapsed_ms
        self.counts[name] = self.counts.get(name, 0) + 1

    def elapsed_ms(self) -> float:
        return (perf_counter() - self.started_at) * 1000.0

    def as_dict(self) -> dict[str, float]:
        """Recorded stages in declaration order, rounded for readability."""
        ordered = {
            name: round(self.totals[name], 1)
            for name in Stage.ORDER
            if name in self.totals
        }
        # Anything recorded under a name not in ORDER still gets reported —
        # losing a measurement because it was not pre-registered would be a
        # worse failure than an out-of-order row.
        for name, value in self.totals.items():
            ordered.setdefault(name, round(value, 1))
        return ordered

    def render_breakdown(self, request_id: str | None) -> str:
        """The human-readable block, aligned so the numbers form a column.

        Only rendered when LOG_TIMING_BREAKDOWN is on. The same numbers always
        reach the structured record via ``as_dict``.
        """
        rows = self.as_dict()
        if not rows:
            return f"Request: {request_id or '-'}\n  (no instrumented stages)"

        label_width = max(len(Stage.LABELS.get(name, name)) for name in rows)
        value_width = max(len(f"{value:.0f}") for value in rows.values())

        lines = [f"Request: {request_id or '-'}"]
        for name, value in rows.items():
            label = Stage.LABELS.get(name, name)
            lines.append(f"  {label:<{label_width}}  {value:>{value_width}.0f} ms")

        measured = sum(rows.values())
        total = self.elapsed_ms()
        lines.append(f"  {'Total':<{label_width}}  {total:>{value_width}.0f} ms")
        # Time the instrumented stages do not account for: serialisation,
        # framework overhead, waiting on the connection pool. A large gap here
        # is itself a finding, so it is shown rather than hidden.
        lines.append(
            f"  {'Unattributed':<{label_width}}  "
            f"{max(total - measured, 0.0):>{value_width}.0f} ms"
        )
        return "\n".join(lines)


_timer: ContextVar[StageTimer | None] = ContextVar("stage_timer", default=None)


def start_timer() -> StageTimer:
    timer = StageTimer()
    _timer.set(timer)
    return timer


def current_timer() -> StageTimer | None:
    return _timer.get()


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Time a block and attribute it to ``name``.

    Outside a request — in tests, the worker, or the benchmark harness — there
    is no timer in context and this degrades to a plain no-op rather than
    forcing every caller to check first.
    """
    timer = _timer.get()
    if timer is None:
        yield
        return

    start = perf_counter()
    try:
        yield
    finally:
        timer.record(name, (perf_counter() - start) * 1000.0)
