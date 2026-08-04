"""Document resource: upload, list, delete. Every route is owner-scoped."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.db.models import User
from app.db.session import SessionFactory
from app.errors import DocumentTooLargeError, ResourceNotFoundError
from app.ingestion.loaders.registry import get_loader
from app.ingestion.pipeline import ingest_document
from app.retrieval.index_builder import refresh_bm25_index
from app.schemas.document import DocumentOut
from app.stores import document_repository
from app.stores.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _store_upload(upload: UploadFile) -> tuple[Path, int, str]:
    """Stream the upload to disk, enforcing the size cap as it goes."""
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Never trust the client-supplied name as a path component.
    safe_name = Path(upload.filename).name
    staged_path = settings.UPLOAD_DIR / f"staging-{uuid4()}-{safe_name}"
    digest = hashlib.sha256()
    byte_size = 0

    with staged_path.open("wb") as handle:
        while block := upload.file.read(settings.UPLOAD_STREAM_CHUNK_BYTES):
            byte_size += len(block)
            if byte_size > settings.MAX_UPLOAD_BYTES:
                handle.close()
                staged_path.unlink(missing_ok=True)
                raise DocumentTooLargeError(
                    f"File exceeds the {settings.MAX_UPLOAD_BYTES} byte limit."
                )
            digest.update(block)
            handle.write(block)

    checksum = digest.hexdigest()
    final_path = settings.UPLOAD_DIR / f"{checksum}{Path(safe_name).suffix.lower()}"
    staged_path.replace(final_path)
    return final_path, byte_size, checksum


def _run_ingestion(owner_id: UUID, document_id: UUID, file_path: Path) -> None:
    """Background entry point: owns its own database session."""
    with SessionFactory() as session:
        ingest_document(session, owner_id, document_id, file_path)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    get_loader(file.filename)  # rejects unsupported formats before touching disk

    file_path, byte_size, checksum = _store_upload(file)

    existing = document_repository.find_by_checksum(db, user.id, checksum)
    if existing is not None:
        logger.info("Upload %s already ingested as %s", file.filename, existing.id)
        return DocumentOut.model_validate(existing)

    document = document_repository.create_document(
        db,
        owner_id=user.id,
        title=Path(file.filename).stem,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        byte_size=byte_size,
        checksum=checksum,
    )
    background_tasks.add_task(_run_ingestion, user.id, document.id, file_path)
    return DocumentOut.model_validate(document)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[DocumentOut]:
    return [
        DocumentOut.model_validate(document)
        for document in document_repository.list_documents(db, user.id)
    ]


# response_model=None is required: FastAPI would otherwise infer NoneType from
# the return annotation and reject it as a body on a 204.
@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
def delete_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    document = document_repository.get_document(db, user.id, document_id)
    if document is None:
        raise ResourceNotFoundError(f"Document {document_id} does not exist.")

    vector_store.delete_document(str(document.id))

    # Read these before the delete: the instance is detached afterwards.
    checksum = document.checksum
    stored_file = (
        settings.UPLOAD_DIR / f"{checksum}{Path(document.filename).suffix.lower()}"
    )

    document_repository.delete_document(db, document)

    # Two users uploading identical bytes share one file on disk, so it is only
    # safe to unlink once no document anywhere still references that checksum.
    if not document_repository.checksum_in_use(db, checksum):
        stored_file.unlink(missing_ok=True)

    refresh_bm25_index(db)
