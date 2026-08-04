"""In-memory BM25 lexical index over chunk text.

Owns tokenisation, scoring, and owner filtering. It does not know where the
corpus comes from — ``app.retrieval.index_builder`` is responsible for feeding
it.

One index holds every user's chunks and filters at query time. That keeps IDF
statistics stable and avoids rebuilding per user; the filter is applied before
truncation, so a user can never see another user's chunk regardless of score.
"""

from __future__ import annotations

import re
import threading
from typing import Any
from uuid import UUID

from app.config import settings
from app.schemas.retrieval import CorpusEntry

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, k1: float, b: float) -> None:
        self._k1 = k1
        self._b = b
        self._lock = threading.RLock()
        self._index: Any | None = None
        self._chunk_ids: list[str] = []
        self._owner_ids: list[UUID] = []

    def rebuild(self, entries: list[CorpusEntry]) -> None:
        from rank_bm25 import BM25Okapi

        corpus = [tokenize(text) for _, text, _ in entries]
        with self._lock:
            self._chunk_ids = [chunk_id for chunk_id, _, _ in entries]
            self._owner_ids = [owner_id for _, _, owner_id in entries]
            self._index = BM25Okapi(corpus, k1=self._k1, b=self._b) if corpus else None

    def search(
        self, query: str, limit: int, owner_id: UUID
    ) -> list[tuple[str, float]]:
        """Return ``(chunk_id, bm25_score)`` for ``owner_id``, best-first."""
        tokens = tokenize(query)
        with self._lock:
            if self._index is None or not tokens:
                return []
            scores = self._index.get_scores(tokens)
            chunk_ids = self._chunk_ids
            owner_ids = self._owner_ids

        owned = [
            (chunk_ids[position], float(score))
            for position, score in enumerate(scores)
            if owner_ids[position] == owner_id and score > 0.0
        ]
        owned.sort(key=lambda pair: pair[1], reverse=True)
        return owned[:limit]

    def size(self) -> int:
        with self._lock:
            return len(self._chunk_ids)


bm25_index = BM25Index(k1=settings.BM25_K1, b=settings.BM25_B)
