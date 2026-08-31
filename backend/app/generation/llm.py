"""Groq chat-completion client. The only module that talks to the LLM API."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from app.config import settings
from app.errors import GenerationError
from app.observability.timing import Stage, stage

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

    def _messages(self, system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        with stage(Stage.LLM):
            try:
                response = self._ensure_client().chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=self._messages(system_prompt, user_prompt),
                )
            except GenerationError:
                raise
            except Exception as exc:  # noqa: BLE001 - surfaced as a 502 to the caller
                logger.exception("Groq completion failed")
                raise GenerationError(f"Language model request failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise GenerationError("Language model returned an empty response.")

        self._log_usage(response)
        return content.strip()

    def stream(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        """Yield content deltas as they arrive.

        Errors are raised from inside the generator, which means they surface
        on the first ``next()`` rather than at call time. The caller has
        usually already opened an HTTP response by then and cannot change the
        status code, so the streaming route reports them as an SSE error event
        instead — see ``app.api.routes.chat``.
        """
        with stage(Stage.LLM):
            try:
                completion = self._ensure_client().chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=self._messages(system_prompt, user_prompt),
                    stream=True,
                )
                emitted = False
                for chunk in completion:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    piece = getattr(delta, "content", None)
                    if piece:
                        emitted = True
                        yield piece
            except GenerationError:
                raise
            except Exception as exc:  # noqa: BLE001 - reported as an SSE error event
                logger.exception("Groq stream failed")
                raise GenerationError(f"Language model request failed: {exc}") from exc

        if not emitted:
            raise GenerationError("Language model returned an empty response.")

    def _log_usage(self, response: Any) -> None:
        """Record token counts so cost is attributable per request and per user.

        Not fatal if the field is absent: a usage block missing from a
        provider response is not a reason to fail a request that otherwise
        succeeded.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        logger.info(
            "Groq completion used %s tokens",
            getattr(usage, "total_tokens", "?"),
            extra={
                "llm_model": self._model,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        )


groq_client = GroqClient(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
    temperature=settings.GROQ_TEMPERATURE,
    max_tokens=settings.GROQ_MAX_TOKENS,
    timeout=settings.GROQ_TIMEOUT_SECONDS,
    max_retries=settings.GROQ_MAX_RETRIES,
)
