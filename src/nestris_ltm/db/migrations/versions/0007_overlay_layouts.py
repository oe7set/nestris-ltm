"""overlay layouts (layout builder); NES style for every scene

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "overlay_layouts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "description", sa.String(length=500), server_default=sa.text("''"), nullable=False
        ),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_overlay_layouts")),
    )
    # "custom:" + uuid does not fit 32 characters.
    op.alter_column("scenes", "layout", type_=sa.String(length=64), existing_nullable=False)

    # The NES style becomes the standard: every existing scene switches to it.
    op.execute(
        """
        INSERT INTO audit_log (actor, action, entity, entity_id, before, after)
        SELECT 'migration', 'update', 'scene', id::text,
               jsonb_build_object('style', COALESCE(settings->>'style', 'modern')),
               jsonb_build_object('style', 'nes')
        FROM scenes WHERE COALESCE(settings->>'style', '') <> 'nes'
        """
    )
    op.execute(
        "UPDATE scenes SET settings = "
        "jsonb_set(COALESCE(settings, '{}'::jsonb), '{style}', '\"nes\"')"
    )


def downgrade() -> None:
    op.execute("UPDATE scenes SET layout = '1v1' WHERE layout LIKE 'custom:%'")
    op.alter_column("scenes", "layout", type_=sa.String(length=32), existing_nullable=False)
    op.drop_table("overlay_layouts")
    # The style stays as it is (NES); switch it back per scene in the studio.
