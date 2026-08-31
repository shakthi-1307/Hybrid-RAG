from __future__ import annotations

from uuid import uuid4

import pytest

from app.config import settings
from app.errors import AuthenticationError
from app.security.tokens import create_access_token, decode_access_token


def test_token_round_trips_the_user_id():
    user_id = uuid4()

    assert decode_access_token(create_access_token(user_id)) == user_id


def test_tampered_payload_is_rejected():
    """Flip a character in the payload, not the signature.

    Altering the *last* character of the token looks like the obvious tamper,
    but base64url's final character only encodes leftover bits, so several
    substitutions decode to the same signature bytes and the token stays
    valid — a test that passes or fails depending on the random user id.
    Changing the payload always changes what was signed.
    """
    header, payload, signature = create_access_token(uuid4()).split(".")
    tampered_payload = ("a" if payload[0] != "a" else "b") + payload[1:]

    with pytest.raises(AuthenticationError):
        decode_access_token(f"{header}.{tampered_payload}.{signature}")


def test_tampered_signature_is_rejected():
    header, payload, signature = create_access_token(uuid4()).split(".")
    tampered_signature = ("a" if signature[0] != "a" else "b") + signature[1:]

    with pytest.raises(AuthenticationError):
        decode_access_token(f"{header}.{payload}.{tampered_signature}")


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
