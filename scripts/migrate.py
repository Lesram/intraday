#!/usr/bin/env python3
"""
Database Migration Script

Runs Alembic migrations to upgrade database to the latest schema.
Supports environment variable configuration for database URL.
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_migrations():
    """Run Alembic migrations to upgrade to head."""
    try:
        # Import after path setup
        from alembic import command
        from alembic.config import Config
        
        # Set up Alembic configuration
        alembic_cfg_path = project_root / "alembic.ini"
        alembic_cfg = Config(str(alembic_cfg_path))
        
        # Override database URL from environment if provided
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            alembic_cfg.set_main_option('sqlalchemy.url', database_url)
            logger.info(f"Using database URL from environment: {database_url}")
        else:
            # Use default SQLite database for development
            default_url = "sqlite:///./staging.db"
            alembic_cfg.set_main_option('sqlalchemy.url', default_url)
            logger.info(f"Using default database URL: {default_url}")
        
        # Run migration
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


def check_migration_status():
    """Check current migration status."""
    try:
        from alembic import command
        from alembic.config import Config
        
        alembic_cfg_path = project_root / "alembic.ini"
        alembic_cfg = Config(str(alembic_cfg_path))
        
        database_url = os.getenv('DATABASE_URL', "sqlite:///./staging.db")
        alembic_cfg.set_main_option('sqlalchemy.url', database_url)
        
        logger.info("Current migration status:")
        command.current(alembic_cfg)
        
    except Exception as e:
        logger.warning(f"Could not check migration status: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Tool")
    parser.add_argument(
        "--check", 
        action="store_true", 
        help="Check current migration status"
    )
    parser.add_argument(
        "--database-url",
        help="Database URL to use (overrides DATABASE_URL env var)"
    )
    
    args = parser.parse_args()
    
    # Set database URL from command line if provided
    if args.database_url:
        os.environ['DATABASE_URL'] = args.database_url
    
    if args.check:
        check_migration_status()
    else:
        run_migrations()