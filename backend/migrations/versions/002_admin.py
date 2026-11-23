"""Add administrator, server sessions and operation audit."""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"


def upgrade():
    op.create_table(
        "admin",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="only_admin"),
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("csrf", sa.String(), nullable=False),
        sa.Column("created", sa.BigInteger(), nullable=False),
        sa.Column("last_seen", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("remote", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("login_sessions")
    op.drop_table("admin")
