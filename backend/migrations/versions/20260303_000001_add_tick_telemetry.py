"""Add tick_telemetry table for persisted decision telemetry

Stores per-tick snapshots every ~1 minute for post-session analysis.
7-day retention with daily cleanup. ~1.2 MB/day at 390 rows/day.

Revision ID: 20260303_000001
Revises: 20260201_000003
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260303_000001"
down_revision = "20260201_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tick_telemetry",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tick_number", sa.Integer, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("regime", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("equity", sa.DECIMAL(14, 2), nullable=False, server_default="0"),
        sa.Column("drawdown_pct", sa.DECIMAL(6, 4), nullable=False, server_default="0"),
        sa.Column("open_positions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("entries_blocked_reason", sa.String(64), nullable=False, server_default=""),
        sa.Column("orders_submitted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gate_rejections", JSONB, nullable=False, server_default="{}"),
        sa.Column("top_candidates", JSONB, nullable=False, server_default="[]"),
        sa.Column("exit_decisions", JSONB, nullable=False, server_default="[]"),
    )
    op.create_index("ix_tick_telemetry_timestamp", "tick_telemetry", ["timestamp"])
    op.create_index("ix_tick_telemetry_tick_number", "tick_telemetry", ["tick_number"])


def downgrade() -> None:
    op.drop_index("ix_tick_telemetry_tick_number", table_name="tick_telemetry")
    op.drop_index("ix_tick_telemetry_timestamp", table_name="tick_telemetry")
    op.drop_table("tick_telemetry")
