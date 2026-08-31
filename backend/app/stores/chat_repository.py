"""Postgres persistence for chat sessions and their message history.

Every read is scoped by ``owner_id``, so a session belonging to another user is
indistinguishable from one that does not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ChatMessage, ChatSession, MessageRole
from app.schemas.chat import Citation


def create_session(session: Session, owner_id: UUID, title: str) -> ChatSession:
    chat_session = ChatSession(
        owner_id=owner_id, title=title[: settings.SESSION_TITLE_MAX_CHARS]
    )
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)
    return chat_session


def get_session(session: Session, owner_id: UUID, session_id: UUID) -> ChatSession | None:
    return session.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.owner_id == owner_id
        )
    )


def list_sessions(session: Session, owner_id: UUID) -> list[ChatSession]:
    return list(
        session.scalars(
            select(ChatSession)
            .where(ChatSession.owner_id == owner_id)
            .order_by(ChatSession.updated_at.desc())
        ).all()
    )


def rename_session(session: Session, chat_session: ChatSession, title: str) -> None:
    chat_session.title = title[: settings.SESSION_TITLE_MAX_CHARS]
    session.commit()


def delete_session(session: Session, chat_session: ChatSession) -> None:
    session.delete(chat_session)
    session.commit()


def list_messages(session: Session, chat_session: ChatSession) -> list[ChatMessage]:
    return list(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at.asc())
        ).all()
    )


def recent_history(
    session: Session, chat_session: ChatSession, turns: int
) -> list[ChatMessage]:
    """The most recent messages, returned oldest-first for prompt assembly."""
    statement = (
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(turns * 2)
    )
    return list(reversed(session.scalars(statement).all()))


def add_message(
    session: Session,
    chat_session: ChatSession,
    *,
    role: MessageRole,
    content: str,
    citations: list[Citation],
) -> ChatMessage:
    message = ChatMessage(
        session_id=chat_session.id,
        role=role,
        content=content,
        citations=[citation.model_dump(mode="json") for citation in citations],
    )
    session.add(message)
    chat_session.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(message)
    return message
