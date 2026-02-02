"""add_order_price_and_fill_fields

Revision ID: 83ec4ee73d7d
Revises: ec197100938a
Create Date: 2025-10-07 14:58:33.429381

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '83ec4ee73d7d'
down_revision: str | Sequence[str] | None = 'ec197100938a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add price and fill quantity fields to orders table."""
    # Add filled_qty column
    op.add_column('orders',
        sa.Column('filled_qty', sa.DECIMAL(precision=18, scale=6),
                  nullable=False, server_default='0.0')
    )

    # Add avg_fill_price column
    op.add_column('orders',
        sa.Column('avg_fill_price', sa.DECIMAL(precision=18, scale=6),
                  nullable=True)
    )

    # Add limit_price column
    op.add_column('orders',
        sa.Column('limit_price', sa.DECIMAL(precision=18, scale=6),
                  nullable=True)
    )

    # Add stop_price column
    op.add_column('orders',
        sa.Column('stop_price', sa.DECIMAL(precision=18, scale=6),
                  nullable=True)
    )


def downgrade() -> None:
    """Remove price and fill quantity fields from orders table."""
    op.drop_column('orders', 'stop_price')
    op.drop_column('orders', 'limit_price')
    op.drop_column('orders', 'avg_fill_price')
    op.drop_column('orders', 'filled_qty')
