"""V11 prep / Wave-61 (XX-3 closure): create portfolio_history table.

V10 XX track found `portfolio_history` declared in
backend/infra/schemas.py (1135-1204) but no migration creates it —
identical to the V7 BB / wave-25 `drawings` bug class.  An existing
`scripts/runtime/write_runtime_snapshot.py` and the FE
`PortfolioStore` rely on this table; without the migration the live
DB has no place to write.

Schema mirrors backend/infra/schemas.py::PortfolioHistory verbatim:
  - PK id, FK user_id (CASCADE), timestamp index
  - DECIMAL columns for equity / cash / positions_value / pnl
  - String snapshot_type with CHECK
  - Composite index (user_id, timestamp) for per-user equity curve

Revision ID: 20260503_000003
Revises: 20260503_000002
Create Date: 2026-05-03
"""
import sqlalchemy as sa
from alembic import op


revision = "20260503_000003"
down_revision = "20260503_000002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "total_equity",
            sa.DECIMAL(18, 2),
            nullable=False,
            comment="Total portfolio value including positions",
        ),
        sa.Column(
            "cash",
            sa.DECIMAL(18, 2),
            nullable=False,
            comment="Available cash balance",
        ),
        sa.Column(
            "positions_value",
            sa.DECIMAL(18, 2),
            nullable=False,
            server_default="0",
            comment="Total value of open positions",
        ),
        sa.Column("daily_pnl", sa.DECIMAL(18, 2), nullable=True),
        sa.Column("daily_pnl_percent", sa.DECIMAL(8, 4), nullable=True),
        sa.Column("total_pnl", sa.DECIMAL(18, 2), nullable=True),
        sa.Column("total_pnl_percent", sa.DECIMAL(8, 4), nullable=True),
        sa.Column(
            "position_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "snapshot_type",
            sa.String(20),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "snapshot_type IN ('scheduled', 'manual', 'trade', 'rebalance')",
            name="chk_portfolio_history_snapshot_type",
        ),
    )
    op.create_index(
        "ix_portfolio_history_user_timestamp",
        "portfolio_history",
        ["user_id", "timestamp"],
    )
    op.create_index(
        "ix_portfolio_history_timestamp",
        "portfolio_history",
        ["timestamp"],
    )
    op.create_index(
        "ix_portfolio_history_user_id",
        "portfolio_history",
        ["user_id"],
    )


def downgrade():
    op.drop_index("ix_portfolio_history_user_id", table_name="portfolio_history")
    op.drop_index("ix_portfolio_history_timestamp", table_name="portfolio_history")
    op.drop_index("ix_portfolio_history_user_timestamp", table_name="portfolio_history")
    op.drop_table("portfolio_history")
