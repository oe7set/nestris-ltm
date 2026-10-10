"""schema history: which app version migrated the database

Lets an older NestrisLTM name the version that left a newer schema behind.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("revision", sa.String(length=32), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=False),
        sa.Column(
            "migrated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schema_history")),
    )


def downgrade() -> None:
    op.drop_table("schema_history")
