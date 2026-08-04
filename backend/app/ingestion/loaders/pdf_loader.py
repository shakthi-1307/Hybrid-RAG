"""PDF loader.

PDFs carry no explicit heading tree, so structure is recovered from two signals
that are combined: the embedded table of contents (when the producer wrote one)
and relative font size / weight of each text line.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.config import settings
from app.ingestion.loaders.base import DocumentLoader
from app.schemas.ingestion import Section

_BOLD_FLAG = 1 << 4


@dataclass(frozen=True)
class _Line:
    page: int
    text: str
    size: float
    bold: bool


class PdfLoader(DocumentLoader):
    def load(self, path: Path) -> list[Section]:
        document = fitz.open(str(path))
        try:
            lines = self._extract_lines(document)
            toc_titles = self._toc_titles(document)
        finally:
            document.close()

        if not lines:
            return []

        body_size = self._body_size(lines)
        level_of_size = self._heading_levels(lines, body_size)
        return self._assemble(lines, toc_titles, body_size, level_of_size)

    # ------------------------------------------------------------- extraction
    def _extract_lines(self, document: fitz.Document) -> list[_Line]:
        lines: list[_Line] = []
        for page_number, page in enumerate(document, start=1):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = "".join(span["text"] for span in spans).strip()
                    if not text:
                        continue
                    lines.append(
                        _Line(
                            page=page_number,
                            text=text,
                            size=max(span["size"] for span in spans),
                            bold=any(span["flags"] & _BOLD_FLAG for span in spans),
                        )
                    )
        return lines

    def _toc_titles(self, document: fitz.Document) -> set[str]:
        return {entry[1].strip() for entry in document.get_toc() if entry[1].strip()}

    # -------------------------------------------------------------- structure
    def _body_size(self, lines: list[_Line]) -> float:
        weighted: Counter[float] = Counter()
        for line in lines:
            weighted[round(line.size, 1)] += len(line.text)
        return weighted.most_common(1)[0][0]

    def _heading_levels(
        self, lines: list[_Line], body_size: float
    ) -> dict[float, int]:
        threshold = body_size * settings.PDF_HEADING_SIZE_RATIO
        candidates = sorted(
            {round(line.size, 1) for line in lines if line.size >= threshold},
            reverse=True,
        )
        return {
            size: index + 1
            for index, size in enumerate(candidates[: settings.MAX_HEADING_DEPTH])
        }

    def _heading_level(
        self,
        line: _Line,
        toc_titles: set[str],
        body_size: float,
        level_of_size: dict[float, int],
    ) -> int | None:
        if len(line.text.split()) > settings.PDF_HEADING_MAX_WORDS:
            return None

        by_size = level_of_size.get(round(line.size, 1))
        if by_size is not None:
            return by_size
        if line.text in toc_titles:
            return settings.MAX_HEADING_DEPTH
        if line.bold and line.size >= body_size and not line.text.endswith("."):
            return settings.MAX_HEADING_DEPTH
        return None

    # --------------------------------------------------------------- assembly
    def _assemble(
        self,
        lines: list[_Line],
        toc_titles: set[str],
        body_size: float,
        level_of_size: dict[float, int],
    ) -> list[Section]:
        sections: list[Section] = []
        stack: list[tuple[int, str]] = []
        buffer: list[str] = []
        first_page = lines[0].page
        last_page = lines[0].page

        def flush() -> None:
            nonlocal buffer
            body = "\n".join(buffer).strip()
            buffer = []
            if body:
                sections.append(
                    Section(
                        order=len(sections),
                        heading_path=[title for _, title in stack],
                        text=body,
                        page_start=first_page,
                        page_end=last_page,
                    )
                )

        for line in lines:
            level = self._heading_level(line, toc_titles, body_size, level_of_size)
            if level is None:
                if not buffer:
                    first_page = line.page
                last_page = line.page
                buffer.append(line.text)
                continue

            flush()
            first_page = line.page
            last_page = line.page
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, line.text))

        flush()
        return sections
