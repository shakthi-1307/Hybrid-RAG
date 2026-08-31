from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.config import settings
from app.ingestion.metadata import (
    OWNER_METADATA_KEY,
    build_chunk_id,
    build_chunk_metadata,
    heading_path_from_string,
    heading_path_to_string,
)
from app.schemas.ingestion import Chunk

PATH = ["Chapter 1", "Scope", "Limits"]


def test_heading_path_round_trips():
    assert heading_path_from_string(heading_path_to_string(PATH)) == PATH


def test_empty_heading_path_round_trips():
    assert heading_path_from_string(heading_path_to_string([])) == []


def test_chunk_id_is_document_scoped():
    document_id = uuid4()

    assert build_chunk_id(document_id, 7) == f"{document_id}:7"


def test_metadata_is_flat_and_carries_the_schema_version():
    document_id = uuid4()
    chunk = Chunk(
        chunk_index=3,
        text="body",
        heading_path=PATH,
        page_start=11,
        page_end=12,
        token_count=42,
    )

    owner_id = uuid4()

    metadata = build_chunk_metadata(
        document_id=document_id,
        owner_id=owner_id,
        document_title="Handbook",
        source_filename="handbook.pdf",
        content_type="application/pdf",
        chunk=chunk,
        ingested_at=datetime.now(UTC),
    )

    assert all(isinstance(v, str | int | float | bool) for v in metadata.values())
    assert metadata["schema_version"] == settings.METADATA_SCHEMA_VERSION
    assert metadata["section"] == "Limits"
    assert metadata["page_start"] == 11


def test_metadata_carries_the_owner_retrieval_filters_on():
    owner_id = uuid4()
    chunk = Chunk(chunk_index=0, text="body", heading_path=[], token_count=1)

    metadata = build_chunk_metadata(
        document_id=uuid4(),
        owner_id=owner_id,
        document_title="Notes",
        source_filename="notes.md",
        content_type="text/markdown",
        chunk=chunk,
        ingested_at=datetime.now(UTC),
    )

    assert metadata[OWNER_METADATA_KEY] == str(owner_id)


def test_absent_page_numbers_are_omitted_rather_than_null():
    chunk = Chunk(chunk_index=0, text="body", heading_path=[], token_count=1)

    metadata = build_chunk_metadata(
        document_id=uuid4(),
        owner_id=uuid4(),
        document_title="Notes",
        source_filename="notes.md",
        content_type="text/markdown",
        chunk=chunk,
        ingested_at=datetime.now(UTC),
    )

    assert "page_start" not in metadata
    assert metadata["section"] == "Notes"
