"""Public API contract for the health endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LivenessOut(BaseModel):
    status: str
    version: str


class HealthOut(BaseModel):
    status: str
    version: str
    database: bool
    # Vectors and the lexical index are columns on the chunk table now, so one
    # count describes all three. Two separate numbers that could disagree was
    # a property of having two stores.
    indexed_chunks: int
    # Counts by job status. A climbing "queued" with a static "succeeded" is
    # how a stopped worker becomes visible from the API side.
    jobs: dict[str, int] = Field(default_factory=dict)
