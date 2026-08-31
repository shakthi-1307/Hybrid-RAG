"""The chunk metadata schema.

The heading hierarchy is stored as a single delimited string rather than an
array. That began as a constraint of the vector store, which only accepted
flat scalar metadata; it is kept because the citation format, the full-text
index, and the benchmark's section matching all want one comparable string,
and a column that has to be joined back together at every read is worse than
one that was never split.

This module owns the encoding in both directions and is the only place that
knows the metadata field names.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.config import settings
from app.schemas.ingestion import Chunk

MetadataValue = str | int | float | bool

OWNER_METADATA_KEY = "owner_id"
"""The field retrieval filters on. Named here so the writer and the reader
cannot drift apart."""


def heading_path_to_string(heading_path: list[str]) -> str:
    return settings.HEADING_PATH_SEPARATOR.join(heading_path)


def heading_path_from_string(value: str) -> list[str]:
    if not value:
        return []
    return [
        part.strip()
        for part in value.split(settings.HEADING_PATH_SEPARATOR)
        if part.strip()
    ]


def build_chunk_id(document_id: UUID, chunk_index: int) -> str:
    return f"{document_id}:{chunk_index}"


def build_chunk_metadata(
    *,
    document_id: UUID,
    owner_id: UUID,
    document_title: str,
    source_filename: str,
    content_type: str,
    chunk: Chunk,
    ingested_at: datetime,
) -> dict[str, MetadataValue]:
    heading_path = heading_path_to_string(chunk.heading_path)
    metadata: dict[str, MetadataValue] = {
        "schema_version": settings.METADATA_SCHEMA_VERSION,
        "document_id": str(document_id),
        OWNER_METADATA_KEY: str(owner_id),
        "document_title": document_title,
        "source_filename": source_filename,
        "content_type": content_type,
        "chunk_index": chunk.chunk_index,
        "heading_path": heading_path,
        "section": chunk.heading_path[-1] if chunk.heading_path else document_title,
        "token_count": chunk.token_count,
        "ingested_at": ingested_at.isoformat(),
    }
    if chunk.page_start is not None:
        metadata["page_start"] = chunk.page_start
    if chunk.page_end is not None:
        metadata["page_end"] = chunk.page_end
    return metadata
