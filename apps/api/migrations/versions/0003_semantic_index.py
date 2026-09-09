"""Persist replaceable, snapshot-scoped semantic indexes."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "semantic_indexes",
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fingerprint", sa.String(200), nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False),
        sa.Column("skipped_long_lines", sa.Integer, nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "embedding_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("semantic_indexes.repository_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            sa.String(36),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("symbol", sa.Text, nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("vector", sa.JSON, nullable=False),
    )
    op.create_index("ix_embedding_chunks_repository_id", "embedding_chunks", ["repository_id"])


def downgrade():
    op.drop_table("embedding_chunks")
    op.drop_table("semantic_indexes")
