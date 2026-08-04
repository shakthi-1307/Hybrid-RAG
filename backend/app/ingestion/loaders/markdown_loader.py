"""Markdown loader. Uses the ATX heading hierarchy as the document structure."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings
from app.ingestion.loaders.base import DocumentLoader
from app.schemas.ingestion import Section

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _path_from_stack(stack: list[tuple[int, str]]) -> list[str]:
    return [title for _, title in stack][: settings.MAX_HEADING_DEPTH]


class MarkdownLoader(DocumentLoader):
    def load(self, path: Path) -> list[Section]:
        raw = path.read_text(encoding="utf-8", errors="replace")

        sections: list[Section] = []
        stack: list[tuple[int, str]] = []
        buffer: list[str] = []
        in_fence = False

        def flush() -> None:
            body = "\n".join(buffer).strip()
            buffer.clear()
            if body:
                sections.append(
                    Section(
                        order=len(sections),
                        heading_path=_path_from_stack(stack),
                        text=body,
                    )
                )

        for line in raw.splitlines():
            if _FENCE_RE.match(line):
                in_fence = not in_fence
                buffer.append(line)
                continue

            match = None if in_fence else _HEADING_RE.match(line)
            if match is None:
                buffer.append(line)
                continue

            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2).strip()))

        flush()
        return sections
