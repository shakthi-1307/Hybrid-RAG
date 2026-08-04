"""Groq chat-completion client. The only module that talks to the LLM API."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.errors import GenerationError

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
        max_retries: int,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if not self._api_key:
            raise GenerationError(
                "GROQ_API_KEY is not configured; the service cannot generate answers."
            )
        if self._client is None:
            from groq import Groq

            self._client = Groq(
                api_key=self._api_key,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._ensure_client().chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except GenerationError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a 502 to the caller
            logger.exception("Groq completion failed")
            raise GenerationError(f"Language model request failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise GenerationError("Language model returned an empty response.")
        return content.strip()


groq_client = GroqClient(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
    temperature=settings.GROQ_TEMPERATURE,
    max_tokens=settings.GROQ_MAX_TOKENS,
    timeout=settings.GROQ_TIMEOUT_SECONDS,
    max_retries=settings.GROQ_MAX_RETRIES,
)
