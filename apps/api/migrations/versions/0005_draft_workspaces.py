"""Per-run copy-on-write source workspaces; existing runs remain read-only."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_runs", sa.Column("mode", sa.String(20), nullable=False, server_default="investigate")
    )
    op.add_column("agent_runs", sa.Column("changes", sa.JSON, nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("agent_runs", "changes")
    op.drop_column("agent_runs", "mode")
