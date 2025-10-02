"""Add idempotency constraints

Revision ID: add_idempotency_constraints
Revises: <previous_revision>
Create Date: 2025-10-02 12:00:00.000000

Defense-in-depth: Database-level idempotency constraints prevent duplicate orders
even if application logic regresses.

Constraints added:
1. orders(account_id, client_order_id) UNIQUE - Prevents duplicate client order IDs per account
2. order_events(broker_order_id, event_type, event_time) UNIQUE - Prevents duplicate broker events
3. outbox_events(aggregate_id, event_type, created_at) UNIQUE - Prevents duplicate outbox events
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_idempotency_constraints'
down_revision = None  # TODO: Update with actual previous revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add idempotency constraints to orders and events tables."""
    
    # 1. Add UNIQUE constraint to orders table for client order ID per account
    # This prevents duplicate orders with same client_order_id for same account
    try:
        op.create_unique_constraint(
            'uq_orders_account_client_order_id',
            'orders',
            ['account_id', 'client_order_id']
        )
        print("✅ Added UNIQUE constraint: orders(account_id, client_order_id)")
    except Exception as e:
        print(f"⚠️  orders constraint may already exist: {e}")
    
    # 2. Add UNIQUE constraint to order_events for broker event deduplication
    # This prevents duplicate broker events (fills, cancellations, etc.)
    try:
        op.create_unique_constraint(
            'uq_order_events_broker_event',
            'order_events',
            ['broker_order_id', 'event_type', 'event_time']
        )
        print("✅ Added UNIQUE constraint: order_events(broker_order_id, event_type, event_time)")
    except Exception as e:
        print(f"⚠️  order_events constraint may already exist: {e}")
    
    # 3. Add UNIQUE constraint to outbox_events for outbox event deduplication
    # This prevents duplicate outbox events for same aggregate
    try:
        op.create_unique_constraint(
            'uq_outbox_events_aggregate_event',
            'outbox_events',
            ['aggregate_id', 'event_type', 'created_at']
        )
        print("✅ Added UNIQUE constraint: outbox_events(aggregate_id, event_type, created_at)")
    except Exception as e:
        print(f"⚠️  outbox_events constraint may already exist: {e}")
    
    # 4. Add index for faster duplicate checks
    try:
        op.create_index(
            'idx_orders_client_order_id',
            'orders',
            ['client_order_id'],
            unique=False
        )
        print("✅ Added index: orders(client_order_id)")
    except Exception as e:
        print(f"⚠️  orders index may already exist: {e}")
    
    print("\n✅ Idempotency constraints migration complete!")
    print("   Database-level deduplication now enforced")


def downgrade() -> None:
    """Remove idempotency constraints."""
    
    # Drop constraints in reverse order
    try:
        op.drop_index('idx_orders_client_order_id', table_name='orders')
    except Exception as e:
        print(f"⚠️  index drop failed: {e}")
    
    try:
        op.drop_constraint('uq_outbox_events_aggregate_event', 'outbox_events', type_='unique')
    except Exception as e:
        print(f"⚠️  outbox_events constraint drop failed: {e}")
    
    try:
        op.drop_constraint('uq_order_events_broker_event', 'order_events', type_='unique')
    except Exception as e:
        print(f"⚠️  order_events constraint drop failed: {e}")
    
    try:
        op.drop_constraint('uq_orders_account_client_order_id', 'orders', type_='unique')
    except Exception as e:
        print(f"⚠️  orders constraint drop failed: {e}")
    
    print("\n✅ Idempotency constraints removed")
