from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas.auth import Credentials
from app.security.password import hash_password, verify_password

PASSWORD = "correct-horse-battery"


def test_hash_is_not_the_plaintext():
    assert hash_password(PASSWORD) != PASSWORD


def test_correct_password_verifies():
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_wrong_password_does_not_verify():
    assert not verify_password("wrong-horse-battery", hash_password(PASSWORD))


def test_same_password_hashes_differently_each_time():
    """Distinct salts: identical passwords must not produce identical hashes."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_short_passwords_are_rejected():
    short = "a" * (settings.PASSWORD_MIN_LENGTH - 1)

    with pytest.raises(ValidationError):
        Credentials(email="user@example.com", password=short)


def test_passwords_bcrypt_would_truncate_are_rejected():
    with pytest.raises(ValidationError):
        Credentials(
            email="user@example.com",
            password="a" * (settings.PASSWORD_MAX_BYTES + 1),
        )
