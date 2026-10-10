"""admin roles: admin or helper

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(length=16), server_default=sa.text("'admin'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_admin_users_role"), "admin_users", "role IN ('admin', 'helper')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_admin_users_role"), "admin_users", type_="check")
    op.drop_column("admin_users", "role")
