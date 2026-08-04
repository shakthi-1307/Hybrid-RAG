"""Public API contracts for chat sessions, messages, and grounded answers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import MessageRole


class Citation(BaseModel):
    """One numbered source backing a sentence in the answer."""

    marker: int
    document_id: UUID
    document_title: str
    section: str
    page: int | None = None
    chunk_id: str
    snippet: str


class SessionCreate(BaseModel):
    title: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: MessageRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class AnswerOut(BaseModel):
    """The assistant turn returned synchronously after a query."""

    message: MessageOut
    grounded: bool
