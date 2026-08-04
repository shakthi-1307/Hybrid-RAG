"""Test bootstrap: make ``app`` importable and provide shared fakes.

Every fixture defined here is consumed by at least one test module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
