"""station configs: per-station remote config overrides

The template for all stations lives in ``settings`` (``stations.config_template``).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "station_configs",
        sa.Column("station_id", sa.String(length=64), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            name=op.f("fk_station_configs_station_id_stations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("station_id", name=op.f("pk_station_configs")),
    )


def downgrade() -> None:
    op.drop_table("station_configs")
