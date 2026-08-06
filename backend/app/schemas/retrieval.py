"""Data-transfer objects for the retrieval stage."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

CorpusEntry = tuple[str, str, UUID]
"""``(chunk_id, text, owner_id)`` — one row of the lexical index corpus."""


class RetrievedChunk(BaseModel):
    """A chunk hydrated from Postgres, ready to be shown to the LLM."""

    chunk_id: str
    document_id: UUID
    document_title: str
    chunk_index: int
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    text: str


class ScoredChunk(BaseModel):
    """A retrieved chunk plus its fusion provenance.

    ``rerank_score`` is None when the cross-encoder is disabled, which is what
    lets the benchmark tell the two pipelines apart in its output.
    """

    chunk: RetrievedChunk
    fused_score: float
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rerank_score: float | None = None
