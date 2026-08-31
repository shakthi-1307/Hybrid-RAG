"""user accounts and per-user ownership of documents and chats

Pre-auth rows have no owner and cannot be attributed to one, so they are
removed. (At this revision vectors lived in a separate store; revision 0003
moves them into Postgres. On a fresh install both run in order.) Wipe
the ``rag-data`` volume alongside this upgrade if it already holds vectors.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # Cascades to document_chunks and chat_messages.
    op.execute("DELETE FROM documents")
    op.execute("DELETE FROM chat_sessions")

    op.add_column(
        "documents",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_documents_owner_id",
        "documents",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.drop_constraint("uq_documents_checksum", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_documents_owner_checksum", "documents", ["owner_id", "checksum"]
    )

    op.add_column(
        "chat_sessions",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        "fk_chat_sessions_owner_id",
        "chat_sessions",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chat_sessions_owner_id", "chat_sessions", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_owner_id", table_name="chat_sessions")
    op.drop_constraint("fk_chat_sessions_owner_id", "chat_sessions", type_="foreignkey")
    op.drop_column("chat_sessions", "owner_id")

    op.drop_constraint("uq_documents_owner_checksum", "documents", type_="unique")
    op.create_unique_constraint("uq_documents_checksum", "documents", ["checksum"])
    op.drop_index("ix_documents_owner_id", table_name="documents")
    op.drop_constraint("fk_documents_owner_id", "documents", type_="foreignkey")
    op.drop_column("documents", "owner_id")

    op.drop_table("users")
