"""The state object passed between LangGraph nodes."""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.chat import Citation
from app.schemas.retrieval import ScoredChunk


class RAGState(TypedDict, total=False):
    # Inputs
    db: Session
    owner_id: UUID
    question: str
    history: list[tuple[str, str]]
    # Produced by the retrieve node
    retrieved: list[ScoredChunk]
    # Produced by the generate / fallback nodes
    answer: str
    grounded: bool
    # Produced by the cite node
    citations: list[Citation]
