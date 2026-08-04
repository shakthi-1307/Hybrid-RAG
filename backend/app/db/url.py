"""Resolves the database URL from configuration.

Kept separate from ``config`` because assembling and describing a URL is logic,
not declaration, and separate from ``session`` because Alembic needs the same
answer without importing an engine.
"""

from __future__ import annotations

from sqlalchemy import URL
from sqlalchemy.engine import make_url

from app.config import settings


def build_database_url() -> str:
    """A complete DATABASE_URL wins; otherwise assemble one from the parts.

    ``URL.create`` escapes each component, so a password containing ``@``,
    ``:``, ``/`` or ``%`` cannot corrupt the host section — which is what
    string-formatted URLs get wrong, usually surfacing as a confusing
    "Name or service not known".
    """
    if settings.DATABASE_URL:
        return settings.DATABASE_URL

    return URL.create(
        drivername=settings.DATABASE_DRIVER,
        username=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
    ).render_as_string(hide_password=False)


def describe_database_target() -> str:
    """Where we are about to connect, with the password removed.

    Connection failures are far more often a malformed URL than a network
    fault, and this is the one line that tells them apart.
    """
    url = make_url(build_database_url())
    return f"{url.username}@{url.host}:{url.port}/{url.database}"
