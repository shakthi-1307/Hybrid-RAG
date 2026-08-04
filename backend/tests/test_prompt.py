from __future__ import annotations

from uuid import uuid4

from app.generation.prompt import (
    SYSTEM_PROMPT,
    build_context_block,
    build_user_prompt,
    format_source_label,
)
from app.schemas.retrieval import RetrievedChunk


def make_chunk(index: int, text: str = "content") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"doc:{index}",
        document_id=uuid4(),
        document_title="Handbook",
        chunk_index=index,
        heading_path=["Chapter 1"],
        page_start=index + 1,
        text=text,
    )


def test_source_label_includes_document_section_and_page():
    label = format_source_label(make_chunk(0))

    assert "Handbook" in label
    assert "Chapter 1" in label
    assert "p. 1" in label


def test_context_block_numbers_sources_from_one():
    block = build_context_block([make_chunk(0), make_chunk(1)])

    assert block.startswith("[1] ")
    assert "\n\n[2] " in block


def test_user_prompt_contains_history_context_and_question():
    prompt = build_user_prompt(
        "What is the limit?",
        [make_chunk(0)],
        [("user", "hello"), ("assistant", "hi")],
    )

    assert "CONVERSATION SO FAR:" in prompt
    assert "CONTEXT:" in prompt
    assert prompt.rstrip().endswith("What is the limit?")


def test_system_prompt_demands_bracketed_citations():
    assert "[1]" in SYSTEM_PROMPT
