"""Add partial and GIN indexes for performance optimization

§11.1 FIX: Merged from orphaned alembic/versions/ chain into active migration chain.
Uses IF NOT EXISTS for idempotent DDL (§11.3 FIX).

Revision ID: 20260201_000003
Revises: 20260201_000002
Create Date: 2026-02-01

L-04: Add partial index for active orders
L-05: Add GIN indexes on JSONB columns
"""

from alembic import op
import sqlalchemy as sa


revision = "20260201_000003"
down_revision = "20260201_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # L-04: Partial index for active orders — dramatically speeds up active-order queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_orders_active_status
        ON orders (status, symbol, created_at DESC)
        WHERE status IN ('new', 'pending_new', 'accepted', 'partially_filled', 'pending_cancel');
    """)

    # L-05: GIN indexes on JSON/JSONB columns for efficient JSON queries
    # Use CAST to jsonb for columns that may be json type
    conn = op.get_bind()

    # Helper: try to create GIN index, skip if column doesn't exist or type is incompatible
    for idx_name, table, column in [
        ("ix_orders_attributes_gin", "orders", "attributes"),
        ("ix_order_events_event_data_gin", "order_events", "event_data"),
        ("ix_outbox_events_payload_gin", "outbox_events", "payload"),
    ]:
        try:
            # Check if column exists and get its type
            result = conn.execute(sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :col AND table_schema = 'public'"
            ), {"table": table, "col": column})
            row = result.fetchone()
            if row is None:
                continue  # Column doesn't exist, skip

            data_type = row[0]
            if data_type == "jsonb":
                conn.execute(sa.text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} USING GIN ({column})"
                ))
            elif data_type == "json":
                # Cast json to jsonb for GIN index support
                conn.execute(sa.text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} USING GIN (CAST({column} AS jsonb))"
                ))
        except Exception:
            pass  # Skip indexes that can't be created


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_orders_active_status;")
    op.execute("DROP INDEX IF EXISTS ix_orders_attributes_gin;")
    op.execute("DROP INDEX IF EXISTS ix_order_events_event_data_gin;")
    op.execute("DROP INDEX IF EXISTS ix_outbox_events_payload_gin;")
