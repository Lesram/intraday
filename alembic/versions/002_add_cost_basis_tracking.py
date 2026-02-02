"""Add cost basis tracking tables

Revision ID: 002_add_cost_basis_tracking
Revises: 001_idempotency_constraints
Create Date: 2025-10-14 12:00:00.000000

This migration adds position lot tracking and realized trade tables for:
1. Accurate cost basis tracking per lot (FIFO/LIFO/SpecID support)
2. True realized P&L calculation
3. Tax-loss harvesting support
4. Wash sale detection capability
5. Historical import compatibility
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_cost_basis_tracking'
down_revision = '001_idempotency_constraints'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create position_lots and realized_trades tables."""
    
    # Create position_lots table
    op.create_table(
        'position_lots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('qty', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('remaining_qty', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('cost_basis', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('open_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id', name='pk_position_lots'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name='fk_position_lots_order_id_orders', ondelete='CASCADE'),
        sa.CheckConstraint('remaining_qty >= 0', name='chk_position_lots_remaining_qty'),
        sa.CheckConstraint('qty > 0', name='chk_position_lots_qty'),
    )
    
    # Create indexes for position_lots
    op.create_index('ix_position_lots_user_symbol', 'position_lots', ['user_id', 'symbol'])
    op.create_index('ix_position_lots_status', 'position_lots', ['status'])
    op.create_index('ix_position_lots_open_date', 'position_lots', ['open_date'])
    op.create_index('ix_position_lots_order_id', 'position_lots', ['order_id'])
    
    # Create realized_trades table
    op.create_table(
        'realized_trades',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('qty', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('open_price', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('close_price', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('realized_pnl', sa.DECIMAL(18, 6), nullable=False),
        sa.Column('realized_pnl_percent', sa.DECIMAL(10, 4), nullable=False),
        sa.Column('open_order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('close_order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('open_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('close_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.PrimaryKeyConstraint('id', name='pk_realized_trades'),
        sa.ForeignKeyConstraint(['open_order_id'], ['orders.id'], name='fk_realized_trades_open_order_id_orders', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['close_order_id'], ['orders.id'], name='fk_realized_trades_close_order_id_orders', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lot_id'], ['position_lots.id'], name='fk_realized_trades_lot_id_position_lots', ondelete='CASCADE'),
        sa.CheckConstraint('qty > 0', name='chk_realized_trades_qty'),
    )
    
    # Create indexes for realized_trades
    op.create_index('ix_realized_trades_user_symbol', 'realized_trades', ['user_id', 'symbol'])
    op.create_index('ix_realized_trades_close_date', 'realized_trades', ['user_id', 'close_date'])
    op.create_index('ix_realized_trades_open_date', 'realized_trades', ['open_date'])
    op.create_index('ix_realized_trades_open_order_id', 'realized_trades', ['open_order_id'])
    op.create_index('ix_realized_trades_close_order_id', 'realized_trades', ['close_order_id'])
    op.create_index('ix_realized_trades_lot_id', 'realized_trades', ['lot_id'])


def downgrade() -> None:
    """Drop position_lots and realized_trades tables."""
    
    # Drop indexes first
    op.drop_index('ix_realized_trades_lot_id', table_name='realized_trades')
    op.drop_index('ix_realized_trades_close_order_id', table_name='realized_trades')
    op.drop_index('ix_realized_trades_open_order_id', table_name='realized_trades')
    op.drop_index('ix_realized_trades_open_date', table_name='realized_trades')
    op.drop_index('ix_realized_trades_close_date', table_name='realized_trades')
    op.drop_index('ix_realized_trades_user_symbol', table_name='realized_trades')
    
    op.drop_index('ix_position_lots_order_id', table_name='position_lots')
    op.drop_index('ix_position_lots_open_date', table_name='position_lots')
    op.drop_index('ix_position_lots_status', table_name='position_lots')
    op.drop_index('ix_position_lots_user_symbol', table_name='position_lots')
    
    # Drop tables
    op.drop_table('realized_trades')
    op.drop_table('position_lots')
