"""Chat resource: sessions, persisted history, and grounded queries.

Every route is owner-scoped; another user's session reads as a 404.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import ChatSession, MessageRole, User
from app.errors import ResourceNotFoundError
from app.graph.pipeline import answer_question
from app.schemas.chat import (
    AnswerOut,
    MessageOut,
    QueryRequest,
    SessionCreate,
    SessionOut,
)
from app.stores import chat_repository

router = APIRouter(prefix="/chat/sessions", tags=["chat"])

DEFAULT_SESSION_TITLE = "New conversation"


def _load_session(db: Session, owner_id: UUID, session_id: UUID) -> ChatSession:
    chat_session = chat_repository.get_session(db, owner_id, session_id)
    if chat_session is None:
        raise ResourceNotFoundError(f"Chat session {session_id} does not exist.")
    return chat_session


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionOut:
    chat_session = chat_repository.create_session(
        db, user.id, payload.title or DEFAULT_SESSION_TITLE
    )
    return SessionOut.model_validate(chat_session)


@router.get("", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[SessionOut]:
    return [
        SessionOut.model_validate(chat_session)
        for chat_session in chat_repository.list_sessions(db, user.id)
    ]


# response_model=None is required: FastAPI would otherwise infer NoneType from
# the return annotation and reject it as a body on a 204.
@router.delete(
    "/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    chat_repository.delete_session(db, _load_session(db, user.id, session_id))


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    chat_session = _load_session(db, user.id, session_id)
    return [
        MessageOut.model_validate(message)
        for message in chat_repository.list_messages(db, chat_session)
    ]


@router.post("/{session_id}/query", response_model=AnswerOut)
def query_session(
    session_id: UUID,
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnswerOut:
    chat_session = _load_session(db, user.id, session_id)

    history = [
        (message.role.value, message.content)
        for message in chat_repository.recent_history(
            db, chat_session, settings.CHAT_HISTORY_TURNS
        )
    ]
    if not history and chat_session.title == DEFAULT_SESSION_TITLE:
        chat_repository.rename_session(db, chat_session, payload.question)

    chat_repository.add_message(
        db,
        chat_session,
        role=MessageRole.USER,
        content=payload.question,
        citations=[],
    )

    result = answer_question(db, user.id, payload.question, history)

    message = chat_repository.add_message(
        db,
        chat_session,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        citations=result.citations,
    )
    return AnswerOut(
        message=MessageOut.model_validate(message), grounded=result.grounded
    )
