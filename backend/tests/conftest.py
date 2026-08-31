"""Test bootstrap: make ``app`` importable and provide shared fakes.

Every fixture defined here is consumed by at least one test module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# JWT_SECRET_KEY is a required setting with no default, so importing anything
# under ``app`` fails without it. pytest loads conftest before any test module,
# which makes this the only place early enough to supply one. The value is
# throwaway; tests that care about the secret monkeypatch it themselves.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-" + "x" * 40)

from app.ingestion.tokenizer import TokenCounter  # noqa: E402

# Integration tests need a real Postgres with pgvector — the behaviour under
# test is SQL (index filtering, generated columns, SKIP LOCKED), none of which
# a fake can reproduce. They are skipped rather than failed when no database
# is configured, so `pytest` stays runnable on a laptop with nothing running.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_database = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a Postgres instance with pgvector installed.",
)


@pytest.fixture(scope="session")
def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")

    from sqlalchemy import create_engine, text

    from app.db.models import Base

    engine = create_engine(TEST_DATABASE_URL, future=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # create_all rather than running Alembic: these tests assert the behaviour
    # of the current model definitions. Whether the migrations arrive at the
    # same schema is a separate question, and CI answers it separately by
    # running `alembic upgrade head` against its own database.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """A session rolled back after each test, so tests cannot see each other."""
    from sqlalchemy.orm import Session

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class FakeTokenCounter(TokenCounter):
    """Counts whitespace-separated words.

    Substituting this keeps the chunking tests deterministic and offline —
    they assert packing behaviour, not tokenizer vocabulary.
    """

    def __init__(self) -> None:
        super().__init__(model_name="fake")

    def count(self, text: str) -> int:
        return len(text.split())


@pytest.fixture
def counter() -> FakeTokenCounter:
    return FakeTokenCounter()
