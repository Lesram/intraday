"""Add model lifecycle events

Revision ID: 20260129_000001
Revises: 20260128_000001
Create Date: 2026-01-29

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260129_000001"
down_revision = "20260128_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["model_registry.id"],
            name=op.f("fk_model_lifecycle_events_model_id_model_registry"),
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_model_lifecycle_name_created",
        "model_lifecycle_events",
        ["model_name", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_lifecycle_type_created",
        "model_lifecycle_events",
        ["event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_lifecycle_model_created",
        "model_lifecycle_events",
        ["model_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_lifecycle_model_created", table_name="model_lifecycle_events")
    op.drop_index("ix_model_lifecycle_type_created", table_name="model_lifecycle_events")
    op.drop_index("ix_model_lifecycle_name_created", table_name="model_lifecycle_events")
    op.drop_table("model_lifecycle_events")
