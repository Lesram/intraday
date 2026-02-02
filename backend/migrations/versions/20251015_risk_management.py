"""add_risk_management_tables

Revision ID: 20251015_risk_management
Revises: d9dc79977b6d
Create Date: 2025-10-15 15:00:00.000000

This migration adds risk management tables for:
1. Real-time risk metrics tracking (daily loss, drawdown, exposure, etc.)
2. Risk violation detection and alerting
3. User-configurable risk limits with thresholds
4. Emergency stop functionality (kill-switch)
5. Comprehensive audit trail for risk events
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251015_risk_management"
down_revision: str | Sequence[str] | None = "d9dc79977b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create risk management tables."""

    # Create risk_metrics table
    op.create_table(
        "risk_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("current_value", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("limit_value", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("percent_used", sa.DECIMAL(5, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_metrics"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_risk_metrics_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('normal', 'warning', 'critical', 'breached')",
            name="chk_risk_metrics_status",
        ),
        sa.CheckConstraint("percent_used >= 0", name="chk_risk_metrics_percent"),
    )

    # Create indexes for risk_metrics
    op.create_index(
        "ix_risk_metrics_user", "risk_metrics", ["user_id"], unique=False
    )
    op.create_index(
        "ix_risk_metrics_name", "risk_metrics", ["metric_name"], unique=False
    )
    op.create_index("ix_risk_metrics_status", "risk_metrics", ["status"], unique=False)
    op.create_index(
        "ix_risk_metrics_updated",
        "risk_metrics",
        ["last_updated"],
        unique=False,
        postgresql_ops={"last_updated": "DESC"},
    )
    op.create_index(
        "ix_risk_metrics_user_name",
        "risk_metrics",
        ["user_id", "metric_name"],
        unique=False,
    )

    # Create risk_violations table
    op.create_table(
        "risk_violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("violation_type", sa.String(20), nullable=False),
        sa.Column("current_value", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("limit_value", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, default=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_violations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_risk_violations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "violation_type IN ('warning', 'breach')",
            name="chk_risk_violations_type",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="chk_risk_violations_severity",
        ),
    )

    # Create indexes for risk_violations
    op.create_index(
        "ix_risk_violations_user", "risk_violations", ["user_id"], unique=False
    )
    op.create_index(
        "ix_risk_violations_resolved", "risk_violations", ["resolved"], unique=False
    )
    op.create_index(
        "ix_risk_violations_created",
        "risk_violations",
        ["created_at"],
        unique=False,
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "ix_risk_violations_severity", "risk_violations", ["severity"], unique=False
    )
    op.create_index(
        "ix_risk_violations_user_resolved",
        "risk_violations",
        ["user_id", "resolved"],
        unique=False,
    )

    # Create risk_limits table
    op.create_table(
        "risk_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("limit_name", sa.String(50), nullable=False),
        sa.Column("limit_value", sa.DECIMAL(15, 2), nullable=False),
        sa.Column(
            "warning_threshold",
            sa.DECIMAL(5, 2),
            nullable=False,
            server_default=sa.text("80.0"),
        ),
        sa.Column(
            "critical_threshold",
            sa.DECIMAL(5, 2),
            nullable=False,
            server_default=sa.text("95.0"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_risk_limits"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_risk_limits_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name="fk_risk_limits_updated_by_users"
        ),
        sa.UniqueConstraint(
            "user_id", "limit_name", name="uq_risk_limits_user_name"
        ),
        sa.CheckConstraint(
            "warning_threshold < critical_threshold",
            name="chk_risk_limits_thresholds",
        ),
    )

    # Create indexes for risk_limits
    op.create_index("ix_risk_limits_user", "risk_limits", ["user_id"], unique=False)
    op.create_index("ix_risk_limits_enabled", "risk_limits", ["enabled"], unique=False)
    op.create_index(
        "ix_risk_limits_user_enabled",
        "risk_limits",
        ["user_id", "enabled"],
        unique=False,
    )

    # Create emergency_stops table
    op.create_table(
        "emergency_stops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("strategies_stopped", sa.Integer(), nullable=False, default=0),
        sa.Column("orders_cancelled", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_emergency_stops"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_emergency_stops_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
            name="fk_emergency_stops_triggered_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name="fk_emergency_stops_resolved_by_users",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'resolved')", name="chk_emergency_stops_status"
        ),
    )

    # Create indexes for emergency_stops
    op.create_index(
        "ix_emergency_stops_user", "emergency_stops", ["user_id"], unique=False
    )
    op.create_index(
        "ix_emergency_stops_status", "emergency_stops", ["status"], unique=False
    )
    op.create_index(
        "ix_emergency_stops_triggered",
        "emergency_stops",
        ["triggered_at"],
        unique=False,
        postgresql_ops={"triggered_at": "DESC"},
    )
    op.create_index(
        "ix_emergency_stops_user_status",
        "emergency_stops",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop risk management tables."""

    # Drop tables in reverse order
    op.drop_table("emergency_stops")
    op.drop_table("risk_limits")
    op.drop_table("risk_violations")
    op.drop_table("risk_metrics")
