"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import User
from app.db.session import SessionFactory
from app.errors import AuthenticationError
from app.observability.context import set_user_id
from app.security.tokens import decode_access_token
from app.stores import user_repository


def get_db() -> Iterator[Session]:
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not token:
        raise AuthenticationError("Not signed in.")

    user = user_repository.get_user(db, decode_access_token(token))
    if user is None:
        # Valid signature, but the account was deleted since the token was issued.
        raise AuthenticationError("Session is invalid or has expired.")

    # From here on every log record in this request carries the user id, which
    # is what turns "something failed" into "this account hit an error" without
    # any route having to remember to include it.
    set_user_id(str(user.id))
    return user
