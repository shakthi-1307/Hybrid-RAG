from __future__ import annotations

import pytest

from app.config import settings
from app.startup_checks import InsecureConfigurationError, verify_configuration

STRONG_SECRET = "x" * 64


def test_boot_is_refused_for_a_secret_short_enough_to_brute_force(monkeypatch):
    monkeypatch.setattr(
        settings, "JWT_SECRET_KEY", "y" * (settings.JWT_SECRET_MIN_LENGTH - 1)
    )

    with pytest.raises(InsecureConfigurationError):
        verify_configuration()


def test_boot_is_refused_for_an_empty_secret(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "")

    with pytest.raises(InsecureConfigurationError):
        verify_configuration()


def test_a_generated_secret_passes(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", STRONG_SECRET)

    verify_configuration()


def test_insecure_cookies_warn_but_do_not_block(monkeypatch, caplog):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", False)

    with caplog.at_level("WARNING"):
        verify_configuration()

    assert "AUTH_COOKIE_SECURE" in caplog.text


def test_missing_groq_key_warns_but_does_not_block(monkeypatch, caplog):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")

    with caplog.at_level("WARNING"):
        verify_configuration()

    assert "GROQ_API_KEY" in caplog.text
