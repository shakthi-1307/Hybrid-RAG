"""Request identity and latency attribution.

The request id is echoed into response headers and log lines, so an inbound
one is untrusted input — these tests exist mostly to pin that down.
"""

from __future__ import annotations

import json
import logging

from app.observability.context import (
    sanitize_request_id,
    set_request_id,
    set_user_id,
)
from app.observability.logging_config import ContextFilter, JsonFormatter
from app.observability.timing import Stage, StageTimer, stage, start_timer


def test_absent_header_gets_a_generated_id():
    assert len(sanitize_request_id(None)) == 16


def test_a_clean_upstream_id_is_preserved():
    """Propagating the caller's id is what makes a trace span services."""
    assert sanitize_request_id("edge-7f3a91") == "edge-7f3a91"


def test_an_id_with_control_characters_is_replaced():
    """A newline in a request id would let a caller forge extra log lines."""
    generated = sanitize_request_id("abc\ndef")

    assert generated != "abc\ndef"
    assert len(generated) == 16


def test_an_overlong_id_is_replaced_rather_than_echoed():
    assert len(sanitize_request_id("x" * 500)) == 16


def test_an_empty_header_gets_a_generated_id():
    assert len(sanitize_request_id("   ")) == 16


def test_stage_timings_accumulate_across_repeated_entries():
    timer = StageTimer()
    timer.record(Stage.DATABASE, 10.0)
    timer.record(Stage.DATABASE, 5.0)

    assert timer.as_dict()[Stage.DATABASE] == 15.0
    assert timer.counts[Stage.DATABASE] == 2


def test_stage_context_manager_records_without_an_active_timer():
    """Outside a request there is no timer. Timing has to degrade to a no-op,
    not raise — the same code runs in the worker and the benchmark."""
    with stage(Stage.LLM):
        pass  # No timer in context; must not raise.


def test_stage_context_manager_records_with_an_active_timer():
    timer = start_timer()
    with stage(Stage.RERANK):
        pass

    assert Stage.RERANK in timer.as_dict()


def test_breakdown_lists_stages_in_pipeline_order():
    timer = StageTimer()
    timer.record(Stage.LLM, 2500.0)
    timer.record(Stage.DATABASE, 30.0)
    timer.record(Stage.VECTOR_SEARCH, 80.0)

    rendered = timer.render_breakdown("abc123")

    assert rendered.startswith("Request: abc123")
    assert rendered.index("Database") < rendered.index("Vector search")
    assert rendered.index("Vector search") < rendered.index("LLM")


def test_json_log_record_carries_request_and_user_id():
    set_request_id("req-1")
    set_user_id("user-9")

    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="retrieved %d chunks",
        args=(6,),
        exc_info=None,
    )
    ContextFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "req-1"
    assert payload["user_id"] == "user-9"
    assert payload["message"] == "retrieved 6 chunks"


def test_extra_fields_reach_the_structured_record():
    """Stage timings ride on ``extra``; if those were dropped the latency
    breakdown would never leave the process."""
    set_request_id("req-2")

    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="done",
        args=(),
        exc_info=None,
    )
    record.stages = {"database": 30.0, "llm": 2500.0}
    ContextFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["stages"]["llm"] == 2500.0
