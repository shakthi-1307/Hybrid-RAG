"""Move vectors and the lexical index into Postgres; add the ingestion queue.

DESTRUCTIVE. Read before running.

Embeddings previously lived in ChromaDB and the lexical index was rebuilt in
process memory at startup. Neither can be migrated into Postgres: Chroma's
vectors are keyed by chunk id but are not reachable from a SQL migration, and
the in-memory index never had a durable form at all.

So this migration deletes every chunk row and resets every document to
PENDING, then queues one ingestion job per document. The worker re-embeds
everything from the original file, which is still on disk under UPLOAD_DIR.
No uploaded file is touched and no user, document, or chat history is lost —
but every document is re-processed, which costs roughly the same wall time as
the original upload did.

After this runs, the ``/data/chroma`` directory is dead weight and can be
deleted by hand. It is deliberately left alone here: a migration that removes
the only copy of data it cannot restore is a migration you cannot back out of.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Read from the application settings so the two cannot drift: an index built
# for 384 dimensions and a model producing 768 fails at insert time with an
# error that does not mention either number.
from app.config import settings  # noqa: E402

EMBEDDING_DIMENSION = settings.EMBEDDING_DIMENSION


def upgrade() -> None:
    # pgvector ships the type, the operators, and the HNSW access method.
    # IF NOT EXISTS so a re-run on a partially migrated database is not an
    # error. Requires the extension files to be present in the image — the
    # stock postgres image does not have them (see docker-compose.yml).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------------------------------------------------------------- chunks
    # Chunks are rebuilt from scratch, so the new NOT NULL columns can be
    # added without a backfill strategy. Clearing first also means the HNSW
    # index is created on an empty table, which is far faster than building it
    # over existing rows and then discarding them.
    op.execute("DELETE FROM document_chunks")
    op.execute("UPDATE documents SET status = 'PENDING', chunk_count = 0, error = NULL")

    op.add_column(
        "document_chunks",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_document_chunks_owner_id",
        "document_chunks",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_document_chunks_owner_id", "document_chunks", ["owner_id"])

    op.execute(
        f"ALTER TABLE document_chunks "
        f"ADD COLUMN embedding vector({EMBEDDING_DIMENSION}) NOT NULL"
    )

    # A generated column cannot fall out of sync with the text it indexes.
    # The regconfig is written as a literal cast because to_tsvector is only
    # IMMUTABLE — and therefore only legal in a generated column — when the
    # configuration is fixed rather than taken from a session setting.
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'english'::regconfig,
                coalesce(heading_path, '') || ' ' || coalesce(text, '')
            )
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_search_vector "
        "ON document_chunks USING gin (search_vector)"
    )
    op.execute(
        f"CREATE INDEX ix_document_chunks_embedding "
        f"ON document_chunks USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = {settings.HNSW_M}, "
        f"ef_construction = {settings.HNSW_EF_CONSTRUCTION})"
    )

    # ------------------------------------------------------------------ jobs
    # create_type=False is load-bearing. A SQLAlchemy ENUM emits its own
    # CREATE TYPE from a before_create hook on the table, and that hook does
    # not inherit the checkfirst above — so without this the type is created
    # twice in one transaction and the migration dies on DuplicateObject.
    # The type is created explicitly here instead, where checkfirst makes a
    # re-run safe.
    postgresql.ENUM("queued", "running", "succeeded", "dead", name="job_status").create(
        op.get_bind(), checkfirst=True
    )

    job_status = postgresql.ENUM(
        "queued",
        "running",
        "succeeded",
        "dead",
        name="job_status",
        create_type=False,
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            job_status,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Partial unique: one *live* job per document. A plain unique constraint
    # would also count finished jobs, so re-uploading a document after a
    # failure would be rejected by its own history.
    op.execute(
        "CREATE UNIQUE INDEX uq_ingestion_jobs_active_document "
        "ON ingestion_jobs (document_id) "
        "WHERE status IN ('queued', 'running')"
    )
    # Matches the claim query's access path exactly: only queued rows are ever
    # scanned, and they come back already ordered.
    op.execute(
        "CREATE INDEX ix_ingestion_jobs_claim ON ingestion_jobs (run_after) "
        "WHERE status = 'queued'"
    )
    op.execute(
        "CREATE INDEX ix_ingestion_jobs_heartbeat ON ingestion_jobs (heartbeat_at) "
        "WHERE status = 'running'"
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])

    _queue_reingestion()


def _queue_reingestion() -> None:
    """Queue every existing document so the worker rebuilds its chunks.

    The stored file is named by checksum plus the original extension — the
    same convention the upload route uses. Documents whose file is missing are
    skipped rather than queued: a job that can only fail is worse than no job,
    because it consumes attempts and reports an error the user cannot act on.
    """
    connection = op.get_bind()
    documents = connection.execute(
        sa.text("SELECT id, owner_id, filename, checksum FROM documents")
    ).all()

    queued = 0
    skipped = 0
    for document_id, owner_id, filename, checksum in documents:
        suffix = Path(filename).suffix.lower()
        file_path = settings.UPLOAD_DIR / f"{checksum}{suffix}"
        if not file_path.exists():
            skipped += 1
            continue

        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_jobs
                    (id, document_id, owner_id, file_path, status, attempts,
                     max_attempts, run_after, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :document_id, :owner_id, :file_path,
                     'queued', 0, :max_attempts, now(), now(), now())
                """
            ),
            {
                "document_id": document_id,
                "owner_id": owner_id,
                "file_path": str(file_path),
                "max_attempts": settings.JOB_MAX_ATTEMPTS,
            },
        )
        queued += 1

    print(f"alembic 0003: queued {queued} document(s) for re-ingestion")
    if skipped:
        print(
            f"alembic 0003: skipped {skipped} document(s) whose stored file is "
            "missing — they will stay in 'pending' and should be re-uploaded"
        )


def downgrade() -> None:
    """Reverses the schema. It cannot reverse the data loss.

    Going back leaves every chunk row deleted and every document PENDING, with
    no vectors anywhere — Chroma's directory may still exist, but nothing
    reads it after this revision. Recovery is to re-upgrade and let the worker
    re-ingest.
    """
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.execute("DROP INDEX IF EXISTS ix_ingestion_jobs_heartbeat")
    op.execute("DROP INDEX IF EXISTS ix_ingestion_jobs_claim")
    op.execute("DROP INDEX IF EXISTS uq_ingestion_jobs_active_document")
    op.drop_table("ingestion_jobs")
    op.execute("DROP TYPE IF EXISTS job_status")

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search_vector")
    op.drop_column("document_chunks", "search_vector")
    op.drop_column("document_chunks", "embedding")
    op.drop_index("ix_document_chunks_owner_id", table_name="document_chunks")
    op.drop_constraint(
        "fk_document_chunks_owner_id", "document_chunks", type_="foreignkey"
    )
    op.drop_column("document_chunks", "owner_id")
