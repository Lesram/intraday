"""add_backtests_table

Revision ID: 76f317122560
Revises: 20251007_214733
Create Date: 2025-10-12 16:10:40.381128

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '76f317122560'
down_revision: str | Sequence[str] | None = '20251007_214733'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create backtests table
    # H-16 NOTE: user_id is UUID and intentionally does NOT have FK to users table
    # because users table uses Integer id. This is a design decision to allow
    # backtests to work with various auth systems (JWT claims use string user_id).
    # If referential integrity with users table is needed, create a new migration
    # to add a uuid_id column to users table or convert users.id to UUID.
    op.create_table(
        'backtests',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('strategy_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),  # No FK - see note above

        # Backtest parameters
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('initial_capital', sa.Numeric(15, 2), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=True),

        # Results summary
        sa.Column('final_equity', sa.Numeric(15, 2), nullable=True),
        sa.Column('total_return', sa.Numeric(10, 4), nullable=True),
        sa.Column('annualized_return', sa.Numeric(10, 4), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(10, 4), nullable=True),
        sa.Column('max_drawdown', sa.Numeric(10, 4), nullable=True),
        sa.Column('win_rate', sa.Numeric(10, 4), nullable=True),
        sa.Column('profit_factor', sa.Numeric(10, 4), nullable=True),
        sa.Column('total_trades', sa.Integer(), nullable=True),
        sa.Column('winning_trades', sa.Integer(), nullable=True),
        sa.Column('losing_trades', sa.Integer(), nullable=True),

        # Detailed results (JSON)
        sa.Column('equity_curve', sa.JSON(), nullable=True),
        sa.Column('trade_log', sa.JSON(), nullable=True),
        sa.Column('monthly_returns', sa.JSON(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),

        # Execution info
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id'], ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name='chk_backtests_status'),
        sa.CheckConstraint('end_date >= start_date', name='chk_backtests_dates'),
        sa.CheckConstraint('initial_capital >= 1000', name='chk_backtests_capital')
    )

    # Create indexes
    op.create_index('idx_backtests_strategy', 'backtests', ['strategy_id'])
    op.create_index('idx_backtests_user', 'backtests', ['user_id'])
    op.create_index('idx_backtests_status', 'backtests', ['status'])
    op.create_index('idx_backtests_created', 'backtests', ['created_at'], postgresql_ops={'created_at': 'DESC'})


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_backtests_created', table_name='backtests')
    op.drop_index('idx_backtests_status', table_name='backtests')
    op.drop_index('idx_backtests_user', table_name='backtests')
    op.drop_index('idx_backtests_strategy', table_name='backtests')

    # Drop table
    op.drop_table('backtests')
