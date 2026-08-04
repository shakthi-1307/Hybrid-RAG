"""Internal data-transfer objects that flow through the ingestion pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Section(BaseModel):
    """A structurally-identified region of a source document.

    Produced by loaders, consumed by the chunker.
    """

    order: int
    heading_path: list[str] = Field(default_factory=list)
    text: str
    page_start: int | None = None
    page_end: int | None = None


class Chunk(BaseModel):
    """An embeddable unit of text that never crosses a section boundary."""

    chunk_index: int
    text: str
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    token_count: int
