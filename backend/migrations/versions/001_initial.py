"""Frozen initial business schema."""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None


def upgrade():
    for name, field in (("model_versions", "metadata_json"), ("tolerances", "config"), ("batches", "metadata_json")):
        op.create_table(
            name,
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(field, sa.JSON(), nullable=False),
        )
    op.create_table(
        "records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("tolerance_id", sa.String(), sa.ForeignKey("tolerances.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created", sa.String(), nullable=False),
    )
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("records.id"), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
    )


def downgrade():
    for table in ("candidates", "records", "batches", "tolerances", "model_versions"):
        op.drop_table(table)
