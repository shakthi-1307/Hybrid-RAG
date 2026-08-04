"""Public API contracts for the document resource."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import IngestionStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    filename: str
    content_type: str
    byte_size: int
    status: IngestionStatus
    chunk_count: int
    error: str | None
    created_at: datetime
