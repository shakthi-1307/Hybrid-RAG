"""Chat resource: sessions, persisted history, and grounded queries.

Every route is owner-scoped; another user's session reads as a 404.

Two query endpoints exist over the same pipeline. ``/query`` returns the whole
answer once and is what the benchmark and any API client uses. ``/query/stream``
sends Server-Sent Events so the UI can render tokens as they arrive. They
share retrieval, generation, and citation code — only the transport differs.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import ChatSession, MessageRole, User
from app.db.session import SessionFactory
from app.errors import AppError, ResourceNotFoundError
from app.graph.pipeline import StreamedAnswer, answer_question, stream_answer
from app.observability.context import get_request_id
from app.observability.timing import current_timer
from app.schemas.chat import (
    AnswerOut,
    MessageOut,
    QueryRequest,
    SessionCreate,
    SessionOut,
)
from app.stores import chat_repository

logger = logging.getLogger(__name__)

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


def _prepare_turn(
    db: Session, chat_session: ChatSession, question: str
) -> list[tuple[str, str]]:
    """Record the user's turn and return the history that preceded it.

    History is read before the new message is stored, so the model sees the
    conversation as it stood when the question was asked rather than a
    transcript that already contains it.
    """
    history = [
        (message.role.value, message.content)
        for message in chat_repository.recent_history(
            db, chat_session, settings.CHAT_HISTORY_TURNS
        )
    ]
    if not history and chat_session.title == DEFAULT_SESSION_TITLE:
        chat_repository.rename_session(db, chat_session, question)

    chat_repository.add_message(
        db, chat_session, role=MessageRole.USER, content=question, citations=[]
    )
    return history


@router.post("/{session_id}/query", response_model=AnswerOut)
def query_session(
    session_id: UUID,
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnswerOut:
    chat_session = _load_session(db, user.id, session_id)
    history = _prepare_turn(db, chat_session, payload.question)

    result = answer_question(db, user.id, payload.question, history)

    message = chat_repository.add_message(
        db,
        chat_session,
        role=MessageRole.ASSISTANT,
        content=result.answer,
        citations=result.citations,
    )
    return AnswerOut(message=MessageOut.model_validate(message), grounded=result.grounded)


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame.

    ``default=str`` because citations carry UUIDs and datetimes; a
    serialisation error here would truncate the stream mid-answer with no way
    to report why.
    """
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/{session_id}/query/stream")
def query_session_stream(
    session_id: UUID,
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream an answer as Server-Sent Events.

    Event sequence:
      ``meta``   once, before generation — the request id and the sources
                 retrieved, so the UI can show them while tokens arrive.
      ``token``  many — one content delta each.
      ``done``   once — the persisted message id, the validated citations, and
                 the stage timings.
      ``error``  instead of ``done`` if generation failed partway.

    SSE rather than WebSockets: the traffic is one-directional and short-lived,
    so a plain HTTP response that proxies, retries, and authenticates like
    every other request is the cheaper choice.
    """
    # Validate ownership and record the user's turn before the response
    # starts. Once the first byte is sent the status code is fixed at 200, so
    # anything that should be a 404 has to happen here.
    chat_session = _load_session(db, user.id, session_id)
    history = _prepare_turn(db, chat_session, payload.question)
    owner_id = user.id
    question = payload.question
    request_id = get_request_id()
    timer = current_timer()

    def event_stream() -> Iterator[str]:
        # A session of its own: the request-scoped one from get_db is closed
        # when the endpoint returns, which for a streaming response is before
        # a single token has been generated.
        with SessionFactory() as stream_db:
            result = StreamedAnswer()
            try:
                tokens = stream_answer(stream_db, owner_id, question, history, result)
                first = next(tokens, None)

                # Retrieval has finished by the time the first token exists,
                # so the sources are known and can be shown immediately.
                yield _sse(
                    "meta",
                    {
                        "request_id": request_id,
                        "grounded": result.grounded,
                        "sources": [
                            {
                                "marker": index,
                                "document_id": str(chunk.document_id),
                                "document_title": chunk.document_title,
                                "section": settings.HEADING_PATH_SEPARATOR.join(
                                    chunk.heading_path
                                )
                                or chunk.document_title,
                                "page": chunk.page_start,
                            }
                            for index, chunk in enumerate(result.chunks, start=1)
                        ],
                    },
                )

                if first is not None:
                    yield _sse("token", {"text": first})
                for piece in tokens:
                    yield _sse("token", {"text": piece})

            except AppError as exc:
                logger.warning(
                    "Streamed query failed: %s",
                    exc.message,
                    extra={"session_id": str(session_id)},
                )
                yield _sse("error", {"detail": exc.message})
                return
            except Exception:
                logger.exception(
                    "Streamed query crashed", extra={"session_id": str(session_id)}
                )
                yield _sse("error", {"detail": "The answer could not be generated."})
                return

            # Persisted only after a complete answer. A stream cut off midway
            # leaves no assistant message, so a reload shows the question
            # unanswered rather than a truncated reply presented as final.
            message = chat_repository.add_message(
                stream_db,
                _load_session(stream_db, owner_id, session_id),
                role=MessageRole.ASSISTANT,
                content=result.text,
                citations=result.citations,
            )
            yield _sse(
                "done",
                {
                    "message_id": str(message.id),
                    "grounded": result.grounded,
                    "citations": [citation.model_dump() for citation in result.citations],
                    "stages": timer.as_dict() if timer else {},
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which holds every
            # token until the answer is complete and defeats the point. This
            # header disables it per-response, so the proxy config and the
            # endpoint cannot drift apart.
            "X-Accel-Buffering": "no",
        },
    )
