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
