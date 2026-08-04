"""Maps a file extension to the loader that understands it.

This is the only place that knows which formats the system accepts.
"""

from __future__ import annotations

from pathlib import Path

from app.errors import UnsupportedFormatError
from app.ingestion.loaders.base import DocumentLoader
from app.ingestion.loaders.markdown_loader import MarkdownLoader
from app.ingestion.loaders.pdf_loader import PdfLoader

_markdown_loader = MarkdownLoader()

_LOADERS: dict[str, DocumentLoader] = {
    ".pdf": PdfLoader(),
    ".md": _markdown_loader,
    ".markdown": _markdown_loader,
}

SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(sorted(_LOADERS))


def get_loader(filename: str) -> DocumentLoader:
    extension = Path(filename).suffix.lower()
    loader = _LOADERS.get(extension)
    if loader is None:
        raise UnsupportedFormatError(
            f"'{extension or filename}' is not supported. "
            f"Accepted formats: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    return loader
