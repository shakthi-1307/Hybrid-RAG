"""Grounded prompt assembly.

The context block is numbered; the system prompt requires the model to cite
those numbers. Everything downstream (citation extraction, the UI) depends on
that numbering being generated here and nowhere else.
"""

from __future__ import annotations

from app.config import settings
from app.schemas.retrieval import RetrievedChunk

SYSTEM_PROMPT = (
    "You are a retrieval-grounded assistant. Answer using ONLY the numbered "
    "sources provided in the CONTEXT block.\n"
    "Rules:\n"
    "1. Cite every factual claim with the bracketed number of the source it "
    "came from, e.g. [1] or [2][3]. Place the citation at the end of the "
    "sentence it supports.\n"
    "2. If the context does not contain the answer, say so plainly instead of "
    "guessing. Do not use outside knowledge.\n"
    "3. Never invent a source number that is not in the CONTEXT block.\n"
    "4. Be concise and specific. Quote exact terminology from the sources."
)


def format_source_label(chunk: RetrievedChunk) -> str:
    parts = [chunk.document_title]
    if chunk.heading_path:
        parts.append(settings.HEADING_PATH_SEPARATOR.join(chunk.heading_path))
    if chunk.page_start is not None:
        parts.append(f"p. {chunk.page_start}")
    return " | ".join(parts)


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    used_chars = 0

    for marker, chunk in enumerate(chunks, start=1):
        snippet = chunk.text[: settings.MAX_SNIPPET_CHARS]
        block = f"[{marker}] {format_source_label(chunk)}\n{snippet}"
        if used_chars + len(block) > settings.MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        used_chars += len(block)

    return "\n\n".join(blocks)


def build_user_prompt(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[tuple[str, str]],
) -> str:
    parts: list[str] = []
    if history:
        transcript = "\n".join(f"{role}: {content}" for role, content in history)
        parts.append(f"CONVERSATION SO FAR:\n{transcript}")
    parts.append(f"CONTEXT:\n{build_context_block(chunks)}")
    parts.append(f"QUESTION:\n{question}")
    return "\n\n".join(parts)
