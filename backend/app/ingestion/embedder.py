"""Embedding model wrapper.

BGE models are asymmetric: passages are embedded bare, queries are embedded
with an instruction prefix. Getting that wrong silently costs recall, so both
paths live here and nowhere else.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(
        self,
        model_name: str,
        dimension: int,
        device: str,
        batch_size: int,
        normalize: bool,
        query_prefix: str,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._device = device
        self._batch_size = batch_size
        self._normalize = normalize
        self._query_prefix = query_prefix
        self._model: Any | None = None

    def _ensure_loaded(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self._model_name)
            model = SentenceTransformer(self._model_name, device=self._device)

            actual = model.get_sentence_embedding_dimension()
            if actual != self._dimension:
                raise ValueError(
                    f"{self._model_name} produces {actual}-dimensional vectors but "
                    f"EMBEDDING_DIMENSION is {self._dimension}. Changing the model "
                    "requires re-ingesting every document."
                )
            self._model = model
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self._ensure_loaded().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._ensure_loaded().encode(
            f"{self._query_prefix}{text}",
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return vector.tolist()


embedder = Embedder(
    model_name=settings.EMBEDDING_MODEL_NAME,
    dimension=settings.EMBEDDING_DIMENSION,
    device=settings.EMBEDDING_DEVICE,
    batch_size=settings.EMBEDDING_BATCH_SIZE,
    normalize=settings.EMBEDDING_NORMALIZE,
    query_prefix=settings.EMBEDDING_QUERY_PREFIX,
)
