"""Explicit execution permission and bounded, versioned test results."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_runs", sa.Column("test_profile", sa.String(30), nullable=True))
    op.create_table(
        "test_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(30), nullable=False),
        sa.Column("workspace_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("image_id", sa.String(100), nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("stdout", sa.Text, nullable=False),
        sa.Column("stderr", sa.Text, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_test_executions_run_id", "test_executions", ["run_id"])


def downgrade():
    op.drop_table("test_executions")
    op.drop_column("agent_runs", "test_profile")
