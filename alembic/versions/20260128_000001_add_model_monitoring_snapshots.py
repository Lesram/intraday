"""Add model monitoring snapshots

Revision ID: 20260128_000001
Revises: 003_risk_management
Create Date: 2026-01-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260128_000001"
down_revision = "003_risk_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_monitoring_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("drift", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["model_registry.id"], name=op.f("fk_model_monitoring_snapshots_model_id_model_registry"), ondelete="SET NULL"),
    )

    op.create_index(
        "ix_model_monitoring_name_created",
        "model_monitoring_snapshots",
        ["model_name", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_monitoring_model_created",
        "model_monitoring_snapshots",
        ["model_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_monitoring_model_created", table_name="model_monitoring_snapshots")
    op.drop_index("ix_model_monitoring_name_created", table_name="model_monitoring_snapshots")
    op.drop_table("model_monitoring_snapshots")
