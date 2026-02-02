"""add strategies table

Revision ID: 20251007_214733
Revises: 83ec4ee73d7d
Create Date: 2025-10-07 21:47:33.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20251007_214733'
down_revision: str | None = '83ec4ee73d7d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add strategies table."""
    op.create_table('strategies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('strategy_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='inactive'),
        sa.Column('symbols', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('total_pnl', sa.DECIMAL(precision=18, scale=6), nullable=False, server_default='0.0'),
        sa.Column('total_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('losing_trades', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.DECIMAL(precision=5, scale=4), nullable=False, server_default='0.0'),
        sa.Column('max_position_size', sa.DECIMAL(precision=18, scale=6), nullable=True),
        sa.Column('max_daily_loss', sa.DECIMAL(precision=18, scale=6), nullable=True),
        sa.Column('max_drawdown_pct', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('last_executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_signal_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['model_id'], ['model_registry.id'], name=op.f('fk_strategies_model_id_model_registry')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_strategies')),
        sa.UniqueConstraint('name', name=op.f('uq_strategies_name'))
    )
    op.create_index('ix_strategies_model_id', 'strategies', ['model_id'], unique=False)
    op.create_index('ix_strategies_name', 'strategies', ['name'], unique=True)
    op.create_index('ix_strategies_status', 'strategies', ['status'], unique=False)
    op.create_index('ix_strategies_status_type', 'strategies', ['status', 'strategy_type'], unique=False)
    op.create_index('ix_strategies_strategy_type', 'strategies', ['strategy_type'], unique=False)
    op.create_index('ix_strategies_updated_at', 'strategies', ['updated_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema - remove strategies table."""
    op.drop_index('ix_strategies_updated_at', table_name='strategies')
    op.drop_index('ix_strategies_strategy_type', table_name='strategies')
    op.drop_index('ix_strategies_status_type', table_name='strategies')
    op.drop_index('ix_strategies_status', table_name='strategies')
    op.drop_index('ix_strategies_name', table_name='strategies')
    op.drop_index('ix_strategies_model_id', table_name='strategies')
    op.drop_table('strategies')
