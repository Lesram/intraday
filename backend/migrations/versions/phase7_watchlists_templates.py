"""
Phase 7 - Add watchlists and chart templates tables

Revision ID: phase7_watchlists_templates
Create Date: 2025-10-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers
revision = 'phase7_watchlists_templates'
down_revision = '20251015_risk_management'  # Fixed: depends on risk_management after initial chain
branch_labels = None
depends_on = None


def upgrade():
    """
    Create watchlists, watchlist_symbols, and chart_templates tables.
    Phase 7 - Market Data & Charting
    """

    # Create watchlists table
    op.create_table(
        'watchlists',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'name', name='uq_watchlists_user_name')
    )

    # Create indexes for watchlists
    op.create_index('ix_watchlists_user_id', 'watchlists', ['user_id'])

    # Create watchlist_symbols table
    op.create_table(
        'watchlist_symbols',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('watchlist_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'added_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['watchlist_id'], ['watchlists.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('watchlist_id', 'symbol', name='uq_watchlist_symbols_watchlist_symbol')
    )

    # Create indexes for watchlist_symbols
    op.create_index('ix_watchlist_symbols_watchlist_id', 'watchlist_symbols', ['watchlist_id'])
    op.create_index('ix_watchlist_symbols_symbol', 'watchlist_symbols', ['symbol'])

    # Create chart_templates table
    op.create_table(
        'chart_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('layout', JSONB if op.get_bind().dialect.name == 'postgresql' else sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('indicators', JSONB if op.get_bind().dialect.name == 'postgresql' else sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('drawings', JSONB if op.get_bind().dialect.name == 'postgresql' else sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('settings', JSONB if op.get_bind().dialect.name == 'postgresql' else sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_preset', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'name', name='uq_chart_templates_user_name')
    )

    # Create indexes for chart_templates
    op.create_index('ix_chart_templates_user_id', 'chart_templates', ['user_id'])

    print("✅ Phase 7 tables created: watchlists, watchlist_symbols, chart_templates")


def downgrade():
    """
    Drop watchlists and chart templates tables.
    """

    # Drop chart_templates
    op.drop_index('ix_chart_templates_user_id', table_name='chart_templates')
    op.drop_table('chart_templates')

    # Drop watchlist_symbols
    op.drop_index('ix_watchlist_symbols_symbol', table_name='watchlist_symbols')
    op.drop_index('ix_watchlist_symbols_watchlist_id', table_name='watchlist_symbols')
    op.drop_table('watchlist_symbols')

    # Drop watchlists
    op.drop_index('ix_watchlists_user_id', table_name='watchlists')
    op.drop_table('watchlists')

    print("✅ Phase 7 tables dropped")
