from __future__ import annotations

from uuid import uuid4

import pytest

from app.config import settings
from app.errors import AuthenticationError
from app.security.tokens import create_access_token, decode_access_token


def test_token_round_trips_the_user_id():
    user_id = uuid4()

    assert decode_access_token(create_access_token(user_id)) == user_id


def test_tampered_token_is_rejected():
    token = create_access_token(uuid4())
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    with pytest.raises(AuthenticationError):
        decode_access_token(tampered)


def test_token_signed_with_another_secret_is_rejected(monkeypatch):
    token = create_access_token(uuid4())
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "a-different-secret")

    with pytest.raises(AuthenticationError):
        decode_access_token(token)


def test_expired_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "JWT_EXPIRY_MINUTES", -1)
    token = create_access_token(uuid4())

    with pytest.raises(AuthenticationError):
        decode_access_token(token)


def test_garbage_is_rejected_rather_than_raising_something_unexpected():
    with pytest.raises(AuthenticationError):
        decode_access_token("not-a-jwt")
