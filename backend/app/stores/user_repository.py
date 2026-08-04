"""Postgres persistence for user accounts."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


def create_user(session: Session, *, email: str, password_hash: str) -> User:
    user = User(email=email.lower(), password_hash=password_hash)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def find_by_email(session: Session, email: str) -> User | None:
    # Emails are stored lowercased on write, so lowercasing the lookup here
    # keeps the comparison a plain indexed equality.
    return session.scalar(select(User).where(User.email == email.lower()))


def get_user(session: Session, user_id: UUID) -> User | None:
    return session.get(User, user_id)
