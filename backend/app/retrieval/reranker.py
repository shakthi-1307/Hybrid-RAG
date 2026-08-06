"""Cross-encoder reranking of the fused candidate shortlist.

The bi-encoder in ``app.ingestion.embedder`` embeds the query and each passage
independently, so it never compares them directly — it compares two summaries.
A cross-encoder feeds ``(query, passage)`` through one model together and
outputs a relevance score, which orders a shortlist far more accurately.

The cost is one forward pass per candidate instead of one vector lookup, so it
is only ever applied to a shortlist, never to the corpus.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(self, model_name: str, batch_size: int) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._model: Any | None = None

    def _ensure_loaded(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance score per passage, in the order given.

        Takes raw text rather than a DTO so both the request path and the
        benchmark can call it without either owning the other's types.
        """
        if not passages:
            return []
        pairs = [(query, passage) for passage in passages]
        scores = self._ensure_loaded().predict(
            pairs, batch_size=self._batch_size, show_progress_bar=False
        )
        return [float(score) for score in scores]


reranker = CrossEncoderReranker(
    model_name=settings.RERANKER_MODEL_NAME,
    batch_size=settings.RERANKER_BATCH_SIZE,
)
