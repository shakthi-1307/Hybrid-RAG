"""Token counting backed by the embedding model's own tokenizer.

Chunk sizes are meaningless unless they are measured with the same tokenizer
the embedding model uses, so the chunker borrows it from here.
"""

from __future__ import annotations

from typing import Any

from app.config import settings


class TokenCounter:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._tokenizer: Any | None = None

    def _ensure_loaded(self) -> Any:
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        return self._tokenizer

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._ensure_loaded().encode(text, add_special_tokens=False))


token_counter = TokenCounter(settings.EMBEDDING_MODEL_NAME)
