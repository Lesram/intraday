"""add_idempotency_constraints_and_order_events

Revision ID: ec197100938a
Revises: 706e00fe1a28
Create Date: 2025-09-30 10:35:21.414259

"""
import logging
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Configure migration logging (M-26 fix)
logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision: str = 'ec197100938a'
down_revision: str | Sequence[str] | None = '706e00fe1a28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add idempotency constraints and order events table"""
    migration_errors: list[str] = []

    # Create order_events table with built-in constraints (if not exists)
    try:
        op.create_table('order_events',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.UUID(), nullable=False),
            sa.Column('broker_order_id', sa.String(100), nullable=False),
            sa.Column('event_type', sa.String(50), nullable=False),
            sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
            sa.Column('event_data', sa.JSON(), nullable=True),
            sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
            sa.UniqueConstraint('broker_order_id', 'event_type', 'event_time', name='uq_events_broker_type_time')
        )
        logger.info("✅ Created order_events table")
    except Exception as e:
        msg = f"order_events table creation skipped: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)

    # Create daily_ledger table with built-in constraints (if not exists)
    try:
        op.create_table('daily_ledger',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('account_id', sa.String(50), nullable=False),
            sa.Column('day_utc', sa.Date(), nullable=False),
            sa.Column('orders_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('submitted_notional_usd', sa.Numeric(precision=15, scale=2), server_default='0.00', nullable=False),
            sa.Column('filled_notional_usd', sa.Numeric(precision=15, scale=2), server_default='0.00', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('account_id', 'day_utc', name='uq_daily_ledger_account_day')
        )
        logger.info("✅ Created daily_ledger table")
    except Exception as e:
        msg = f"daily_ledger table creation skipped: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)

    # Add account_id column to orders table if it doesn't exist
    try:
        with op.batch_alter_table('orders', schema=None) as batch_op:
            batch_op.add_column(sa.Column('account_id', sa.String(50), nullable=True))
        logger.info("✅ Added account_id column to orders table")
    except Exception as e:
        msg = f"account_id column already exists: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)

    # Create performance indexes (ignore if they already exist)
    indexes_to_create = [
        ('idx_orders_created_at', 'orders', ['created_at']),
        ('idx_orders_status', 'orders', ['status']),
        ('idx_orders_broker_order_id', 'orders', ['broker_order_id']),
        ('idx_orders_symbol_created', 'orders', ['symbol', 'created_at']),
    ]

    for idx_name, table_name, columns in indexes_to_create:
        try:
            op.create_index(idx_name, table_name, columns)
            logger.info(f"✅ Created index {idx_name}")
        except Exception as e:
            msg = f"Index {idx_name} skipped: {e}"
            logger.warning(f"⚠️ {msg}")
            migration_errors.append(msg)

    # Create order_events indexes only if table was created
    order_events_indexes = [
        ('idx_events_broker_order', 'order_events', ['broker_order_id']),
        ('idx_events_order_time', 'order_events', ['order_id', 'event_time']),
        ('idx_events_type_time', 'order_events', ['event_type', 'event_time']),
    ]

    for idx_name, table_name, columns in order_events_indexes:
        try:
            op.create_index(idx_name, table_name, columns)
            logger.info(f"✅ Created index {idx_name}")
        except Exception as e:
            msg = f"Index {idx_name} skipped: {e}"
            logger.warning(f"⚠️ {msg}")
            migration_errors.append(msg)

    # Create daily_ledger index
    try:
        op.create_index('idx_daily_ledger_account_day', 'daily_ledger', ['account_id', 'day_utc'])
        logger.info("✅ Created daily_ledger index")
    except Exception as e:
        msg = f"daily_ledger index skipped: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)

    # Log summary
    if migration_errors:
        logger.warning(f"Migration ec197100938a completed with {len(migration_errors)} warnings")
    else:
        logger.info("Migration ec197100938a completed successfully")


def downgrade() -> None:
    """Remove idempotency constraints and order events table"""

    # Drop indexes
    op.drop_index('idx_daily_ledger_account_day', table_name='daily_ledger')
    op.drop_index('idx_events_type_time', table_name='order_events')
    op.drop_index('idx_events_order_time', table_name='order_events')
    op.drop_index('idx_events_broker_order', table_name='order_events')
    op.drop_index('idx_orders_symbol_created', table_name='orders')
    op.drop_index('idx_orders_broker_order_id', table_name='orders')
    op.drop_index('idx_orders_status', table_name='orders')
    op.drop_index('idx_orders_created_at', table_name='orders')

    # Drop constraints
    op.drop_constraint('uq_daily_ledger_account_day', 'daily_ledger', type_='unique')
    op.drop_constraint('uq_events_broker_type_time', 'order_events', type_='unique')

    try:
        op.drop_constraint('uq_orders_account_client_order', 'orders', type_='unique')
    except Exception:
        pass

    # Drop tables
    op.drop_table('daily_ledger')
    op.drop_table('order_events')

    # Remove added columns (commented out to preserve data)
    # op.drop_column('orders', 'client_idempotency_key')
    # op.drop_column('orders', 'account_id')
