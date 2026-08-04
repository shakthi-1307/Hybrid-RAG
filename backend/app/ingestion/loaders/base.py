"""The loader contract: turn a file on disk into ordered, heading-aware sections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas.ingestion import Section


class DocumentLoader(ABC):
    @abstractmethod
    def load(self, path: Path) -> list[Section]:
        """Return sections in document order. May return an empty list."""
