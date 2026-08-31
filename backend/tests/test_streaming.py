"""The streaming answer path.

The contract these pin down: tokens go out immediately, citations are
validated only once the text is complete, and a failure partway does not leave
a half-answer looking finished. All three are easy to break in a way that
looks fine in a demo.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.api.routes.chat import _sse
from app.config import settings
from app.errors import GenerationError
from app.graph import pipeline
from app.schemas.retrieval import RetrievedChunk, ScoredChunk


def make_chunk(marker: int) -> ScoredChunk:
    return ScoredChunk(
        chunk=RetrievedChunk(
            chunk_id=f"doc:{marker}",
            document_id=uuid.uuid4(),
            document_title="Handbook",
            chunk_index=marker,
            heading_path=["Billing", "Refunds"],
            page_start=14,
            text=f"Passage {marker}.",
        ),
        fused_score=1.0 / marker,
    )


@pytest.fixture
def stubbed(monkeypatch):
    """Replace retrieval and the LLM. Neither is what these tests are about,
    and both would need a database and a network call."""

    def fake_retrieve(_state):
        return {"retrieved": [make_chunk(1), make_chunk(2)]}

    monkeypatch.setattr(pipeline, "retrieve_node", fake_retrieve)
    return monkeypatch


# ------------------------------------------------------------------ framing


def test_sse_frame_has_an_event_line_and_a_blank_line_terminator():
    """A frame the client cannot detect the end of is a frame it never
    dispatches, which looks like the stream silently stalling."""
    frame = _sse("token", {"text": "hello"})

    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")


def test_sse_payload_is_valid_json():
    frame = _sse("done", {"message_id": "abc", "citations": []})
    payload = json.loads(frame.split("data: ", 1)[1].strip())

    assert payload["message_id"] == "abc"


def test_sse_serialises_uuids_rather_than_raising():
    """Citations carry UUIDs. A serialisation error mid-stream would truncate
    the answer with no way to report why."""
    frame = _sse("meta", {"document_id": uuid.uuid4()})

    assert json.loads(frame.split("data: ", 1)[1].strip())["document_id"]


def test_sse_escapes_newlines_inside_the_payload():
    """A raw newline in the data would terminate the frame early and split one
    event into two malformed ones."""
    frame = _sse("token", {"text": "line one\nline two"})

    assert frame.count("\n\n") == 1


# --------------------------------------------------------------- streaming


def test_tokens_stream_in_order_and_citations_arrive_only_at_the_end(stubbed):
    stubbed.setattr(
        pipeline.groq_client, "stream", lambda *_: iter(["The ", "answer ", "[1]"])
    )
    result = pipeline.StreamedAnswer()

    emitted = []
    for piece in pipeline.stream_answer(None, uuid.uuid4(), "q", [], result):
        # Citations must not be populated until the generator is exhausted:
        # a marker is only trustworthy once the whole number has arrived.
        assert result.citations == []
        emitted.append(piece)

    assert emitted == ["The ", "answer ", "[1]"]
    assert result.text == "The answer [1]"
    assert [citation.marker for citation in result.citations] == [1]
    assert result.grounded is True


def test_a_marker_outside_the_context_is_dropped(stubbed):
    """Two chunks were retrieved, so [7] cannot be real. The guard has to work
    on the streamed path too, not only the buffered one."""
    stubbed.setattr(pipeline.groq_client, "stream", lambda *_: iter(["See [1] and [7]."]))
    result = pipeline.StreamedAnswer()

    list(pipeline.stream_answer(None, uuid.uuid4(), "q", [], result))

    assert [citation.marker for citation in result.citations] == [1]


def test_no_retrieval_yields_the_fallback_without_calling_the_model(
    monkeypatch,
):
    def empty_retrieve(_state):
        return {"retrieved": []}

    def explode(*_args, **_kwargs):
        raise AssertionError("the model must not be called with no context")

    monkeypatch.setattr(pipeline, "retrieve_node", empty_retrieve)
    monkeypatch.setattr(pipeline.groq_client, "stream", explode)
    result = pipeline.StreamedAnswer()

    emitted = list(pipeline.stream_answer(None, uuid.uuid4(), "q", [], result))

    assert emitted == [settings.NO_CONTEXT_ANSWER]
    assert result.grounded is False
    assert result.citations == []


def test_sources_are_available_before_the_first_token(stubbed):
    """The meta event carries them, so the UI can show sources while the
    answer is still being written."""
    stubbed.setattr(pipeline.groq_client, "stream", lambda *_: iter(["x"]))
    result = pipeline.StreamedAnswer()

    tokens = pipeline.stream_answer(None, uuid.uuid4(), "q", [], result)
    next(tokens)

    assert len(result.chunks) == 2
    assert result.chunks[0].document_title == "Handbook"


def test_a_generation_failure_propagates_rather_than_ending_quietly(stubbed):
    """A stream that just stops looks identical to a complete short answer.
    The error has to reach the caller so it can emit an error event."""

    def failing_stream(*_args):
        yield "partial"
        raise GenerationError("upstream refused")

    stubbed.setattr(pipeline.groq_client, "stream", failing_stream)
    result = pipeline.StreamedAnswer()

    with pytest.raises(GenerationError):
        list(pipeline.stream_answer(None, uuid.uuid4(), "q", [], result))
