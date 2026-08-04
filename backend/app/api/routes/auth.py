"""Registration, sign-in, sign-out, and the current-user probe.

The session token is delivered as an httpOnly cookie so that JavaScript — and
therefore any XSS payload — cannot read it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import User
from app.errors import AuthenticationError, EmailAlreadyRegisteredError
from app.schemas.auth import Credentials, UserOut
from app.security.password import hash_password, verify_password
from app.security.tokens import create_access_token
from app.stores import user_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=create_access_token(user.id),
        max_age=settings.JWT_EXPIRY_MINUTES * 60,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    if user_repository.find_by_email(db, payload.email) is not None:
        raise EmailAlreadyRegisteredError("That email is already registered.")

    user = user_repository.create_user(
        db, email=payload.email, password_hash=hash_password(payload.password)
    )
    _issue_session_cookie(response, user)
    logger.info("Registered user %s", user.id)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(
    payload: Credentials, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    user = user_repository.find_by_email(db, payload.email)
    # One message for both failure modes: revealing which half was wrong turns
    # the login form into an account-enumeration oracle.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Incorrect email or password.")

    _issue_session_cookie(response, user)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


@router.get("/me", response_model=UserOut)
def read_current_user(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
