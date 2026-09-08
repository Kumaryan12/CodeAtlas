"""Store immutable repository snapshots, source files, and located symbols."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("branch", sa.String(255)),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.Column("source_bytes", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("skipped", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repositories_created_at", "repositories", ["created_at"])
    op.create_table(
        "repository_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("imports", sa.JSON(), nullable=False),
        sa.Column("warning", sa.Text()),
        sa.Column("symbol_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("repository_id", "path", name="uq_file_repository_path"),
    )
    op.create_table(
        "code_symbols",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "file_id",
            sa.String(36),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("code_symbols.id", ondelete="CASCADE")),
        sa.Column("parameters", sa.JSON(), nullable=False),
    )
    op.create_index("ix_code_symbols_file_id", "code_symbols", ["file_id"])


def downgrade():
    op.drop_table("code_symbols")
    op.drop_table("repository_files")
    op.drop_table("repositories")
