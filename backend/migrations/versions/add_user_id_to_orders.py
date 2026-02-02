"""Add user_id column to orders table for multi-user support

Revision ID: add_user_id_orders
Revises: phase7_watchlists_templates
Create Date: 2026-01-30

Design Decision (M-24): user_id is String(255) intentionally to store JWT username claims
rather than referencing User.id (Integer FK). This allows order tracking for API users
that authenticate via JWT but may not have database User records. The tradeoff is no FK
constraint, but this enables better separation between auth (JWT-based) and storage layers.
"""
import logging
from alembic import op
import sqlalchemy as sa

# Configure migration logging (M-26 fix)
logger = logging.getLogger("alembic.runtime.migration")


# revision identifiers, used by Alembic.
revision = 'add_user_id_orders'
down_revision = 'phase7_watchlists_templates'  # Linear chain now
branch_labels = None
depends_on = None


def upgrade():
    """Add user_id column to orders table."""
    migration_errors: list[str] = []
    
    # Add user_id column with default 'admin' for existing records
    try:
        op.add_column(
            'orders',
            sa.Column('user_id', sa.String(255), nullable=False, server_default='admin')
        )
        logger.info("✅ Added user_id column to orders table")
    except Exception as e:
        # Column might already exist - log but don't fail
        msg = f"user_id column already exists or error: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)
    
    # Create index for efficient user-based queries
    try:
        op.create_index(
            'idx_orders_user_id',
            'orders',
            ['user_id']
        )
        logger.info("✅ Created index on user_id")
    except Exception as e:
        msg = f"Index creation skipped: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)
    
    # Create composite index for user + status queries
    try:
        op.create_index(
            'idx_orders_user_status',
            'orders',
            ['user_id', 'status']
        )
        logger.info("✅ Created composite index on user_id, status")
    except Exception as e:
        msg = f"Composite index creation skipped: {e}"
        logger.warning(f"⚠️ {msg}")
        migration_errors.append(msg)
    
    # Log summary
    if migration_errors:
        logger.warning(f"Migration completed with {len(migration_errors)} warnings: {migration_errors}")
    else:
        logger.info("Migration add_user_id_orders completed successfully")


def downgrade():
    """Remove user_id column from orders table."""
    for operation, args in [
        (op.drop_index, ('idx_orders_user_status', {'table_name': 'orders'})),
        (op.drop_index, ('idx_orders_user_id', {'table_name': 'orders'})),
        (op.drop_column, ('orders', 'user_id')),
    ]:
        try:
            if isinstance(args, tuple) and len(args) == 2 and isinstance(args[1], dict):
                operation(args[0], **args[1])
            else:
                operation(*args)
        except Exception as e:
            logger.warning(f"Downgrade step skipped: {e}")
