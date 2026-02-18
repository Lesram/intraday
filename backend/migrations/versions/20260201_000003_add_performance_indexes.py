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


revision = "20260201_000003"
down_revision = "20260201_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # L-04: Partial index for active orders — dramatically speeds up active-order queries
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_active_status
        ON orders (status, symbol, created_at DESC)
        WHERE status IN ('new', 'pending_new', 'accepted', 'partially_filled', 'pending_cancel');
    """)

    # L-05: GIN indexes on JSONB columns for efficient JSON queries
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_attributes_gin
        ON orders USING GIN (attributes);
    """)

    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_order_events_event_data_gin
        ON order_events USING GIN (event_data);
    """)

    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_outbox_events_payload_gin
        ON outbox_events USING GIN (payload);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_active_status;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_attributes_gin;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_order_events_event_data_gin;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_outbox_events_payload_gin;")
