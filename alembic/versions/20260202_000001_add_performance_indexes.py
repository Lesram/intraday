"""Add partial and GIN indexes for performance optimization

Revision ID: 20260202_000001
Revises: 20260129_000001
Create Date: 2026-02-02

L-04: Add partial index for active orders
L-05: Add GIN indexes on JSONB columns
"""

from alembic import op


revision = "20260202_000001"
down_revision = "20260129_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # L-04: Add partial index for active orders
    # This dramatically speeds up queries for active orders which are the most common
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_active_status 
        ON orders (status, symbol, created_at DESC)
        WHERE status IN ('new', 'pending_new', 'accepted', 'partially_filled', 'pending_cancel');
    """)

    # L-05: Add GIN indexes on JSONB columns for efficient JSON queries
    # Orders.attributes - used for strategy_id lookups and other custom attributes
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_attributes_gin 
        ON orders USING GIN (attributes);
    """)

    # OrderEvent.event_data - used for filtering and searching event details
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_order_events_event_data_gin 
        ON order_events USING GIN (event_data);
    """)

    # OutboxEvent.payload - used for payload-based filtering
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_outbox_events_payload_gin 
        ON outbox_events USING GIN (payload);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_active_status;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_orders_attributes_gin;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_order_events_event_data_gin;")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_outbox_events_payload_gin;")
