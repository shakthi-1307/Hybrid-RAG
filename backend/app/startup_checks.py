"""Fail-closed configuration checks, run once from the application lifespan.

A *missing* ``JWT_SECRET_KEY`` is caught earlier and harder — the field has no
default, so ``Settings()`` raises before this module ever runs. What is left
for here is a secret that exists but is too weak to resist offline brute force
against an HS256 signature, plus warnings for merely risky settings.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db.url import describe_database_target

logger = logging.getLogger(__name__)


class InsecureConfigurationError(RuntimeError):
    """Raised at startup rather than serving traffic in a forgeable state."""


def verify_configuration() -> None:
    logger.info("Database target: %s", describe_database_target())

    if len(settings.JWT_SECRET_KEY) < settings.JWT_SECRET_MIN_LENGTH:
        raise InsecureConfigurationError(
            f"JWT_SECRET_KEY must be at least {settings.JWT_SECRET_MIN_LENGTH} "
            "characters. A short secret can be recovered offline from a single "
            "captured token, which allows forging a session for any account. "
            "Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    if not settings.AUTH_COOKIE_SECURE:
        logger.warning(
            "AUTH_COOKIE_SECURE is false: session cookies will be sent over "
            "plain HTTP. Set it to true once TLS terminates in front of the API."
        )

    if not settings.GROQ_API_KEY:
        logger.warning(
            "GROQ_API_KEY is not set: ingestion will work but every query will "
            "fail at the generation step."
        )
