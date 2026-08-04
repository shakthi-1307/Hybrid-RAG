"""Turns the ``[n]`` markers the model emitted into resolved source records.

Markers that point outside the context block are dropped rather than trusted,
which is what stops a hallucinated citation from reaching the UI.
"""

from __future__ import annotations

import re

from app.config import settings
from app.schemas.chat import Citation
from app.schemas.retrieval import RetrievedChunk

_MARKER_RE = re.compile(r"\[(\d{1,2})\]")


def extract_citation_markers(answer: str) -> list[int]:
    """Marker numbers in first-appearance order, deduplicated."""
    seen: list[int] = []
    for match in _MARKER_RE.finditer(answer):
        marker = int(match.group(1))
        if marker not in seen:
            seen.append(marker)
    return seen


def build_citations(
    markers: list[int], chunks: list[RetrievedChunk]
) -> list[Citation]:
    citations: list[Citation] = []
    for marker in markers:
        if not 1 <= marker <= len(chunks):
            continue
        chunk = chunks[marker - 1]
        citations.append(
            Citation(
                marker=marker,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                section=settings.HEADING_PATH_SEPARATOR.join(chunk.heading_path)
                or chunk.document_title,
                page=chunk.page_start,
                chunk_id=chunk.chunk_id,
                snippet=chunk.text[: settings.MAX_SNIPPET_CHARS],
            )
        )
    return citations
