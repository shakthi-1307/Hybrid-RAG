"""Structure-based chunking.

A chunk never crosses a section boundary, so every chunk inherits exactly one
heading path. Within a section, sentences are packed greedily up to
``CHUNK_TARGET_TOKENS`` with a ``CHUNK_OVERLAP_TOKENS`` tail carried forward.
"""

from __future__ import annotations

import re

from app.config import settings
from app.ingestion.tokenizer import TokenCounter, token_counter
from app.schemas.ingestion import Chunk, Section

_UNIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


class StructuralChunker:
    def __init__(
        self,
        target_tokens: int,
        overlap_tokens: int,
        min_tokens: int,
        counter: TokenCounter,
    ) -> None:
        self._target = target_tokens
        self._overlap = overlap_tokens
        self._min = min_tokens
        self._counter = counter

    def chunk(self, sections: list[Section]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in sections:
            for body in self._split(section.text):
                chunks.append(
                    Chunk(
                        chunk_index=len(chunks),
                        text=body,
                        heading_path=section.heading_path,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        token_count=self._counter.count(body),
                    )
                )
        return chunks

    # ---------------------------------------------------------------- packing
    def _split(self, text: str) -> list[str]:
        units: list[str] = []
        for raw in _UNIT_RE.split(text):
            unit = raw.strip()
            if not unit:
                continue
            if self._counter.count(unit) > self._target:
                units.extend(self._hard_split(unit))
            else:
                units.append(unit)
        return self._pack(units)

    def _pack(self, units: list[str]) -> list[str]:
        windows: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = self._counter.count(unit)
            if current and current_tokens + unit_tokens > self._target:
                windows.append(" ".join(current))
                current = self._overlap_tail(current)
                current_tokens = sum(self._counter.count(u) for u in current)
            current.append(unit)
            current_tokens += unit_tokens

        if current:
            windows.append(" ".join(current))

        if len(windows) > 1 and self._counter.count(windows[-1]) < self._min:
            tail = windows.pop()
            windows[-1] = f"{windows[-1]} {tail}"
        return windows

    def _overlap_tail(self, units: list[str]) -> list[str]:
        tail: list[str] = []
        budget = self._overlap
        for unit in reversed(units):
            cost = self._counter.count(unit)
            if cost > budget:
                break
            tail.insert(0, unit)
            budget -= cost
        return tail

    def _hard_split(self, unit: str) -> list[str]:
        pieces: list[str] = []
        words: list[str] = []
        tokens = 0
        for word in unit.split():
            cost = self._counter.count(word)
            if words and tokens + cost > self._target:
                pieces.append(" ".join(words))
                words = []
                tokens = 0
            words.append(word)
            tokens += cost
        if words:
            pieces.append(" ".join(words))
        return pieces


chunker = StructuralChunker(
    target_tokens=settings.CHUNK_TARGET_TOKENS,
    overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
    min_tokens=settings.CHUNK_MIN_TOKENS,
    counter=token_counter,
)
