"""Public API contract for the health endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str
    version: str
    database: bool
    vector_count: int
    bm25_documents: int
