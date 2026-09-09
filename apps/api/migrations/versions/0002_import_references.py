"""Preserve import statements and bounded alias configuration for dependency resolution."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # NULL distinguishes older snapshots from newly analyzed files with no imports/configs.
    op.add_column("repository_files", sa.Column("import_references", sa.JSON(), nullable=True))
    op.add_column("repositories", sa.Column("resolution_configs", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("repository_files", "import_references")
    op.drop_column("repositories", "resolution_configs")
