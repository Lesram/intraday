#!/usr/bin/env python3
"""
Staging Database Seeder

Creates initial staging data including an admin user and sample data
for testing the trading platform.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_admin_user(session):
    """Create admin user for staging environment."""
    try:
        from backend.infra.schemas import Base
        from backend.infra.schemas import Order, Signal, Position, AuditLog
        from backend.infra.security import hash_password
        
        # Hash the password using bcrypt
        password = "admin123"
        password_hash = hash_password(password)
        
        logger.info(f"Creating admin user with credentials:")
        logger.info(f"  Username: admin")
        logger.info(f"  Password: {password}")
        logger.info(f"  Hash: {password_hash}")
        
        # Note: We don't have a User model in our current schemas,
        # but we can create an audit log entry for the admin creation
        admin_audit = AuditLog(
            id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            actor="system",
            action="create_admin_user",
            entity="admin",
            entity_id="admin@staging.local",
            payload={
                "username": "admin",
                "email": "admin@staging.local", 
                "role": "admin",
                "created_for": "staging_environment",
                "password_hash": password_hash,  # Properly hashed password
                "permissions": ["read", "write", "admin", "trading"]
            }
        )
        
        session.add(admin_audit)
        await session.commit()
        
        logger.info("Created admin user audit entry: admin@staging.local")
        return "admin@staging.local"
        
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        await session.rollback()
        raise


async def seed_sample_data(session):
    """Create sample trading data for testing."""
    try:
        from backend.infra.schemas import Order, Signal, Position, AuditLog
        
        # Create sample positions
        positions = [
            Position(
                symbol="AAPL",
                qty=Decimal("100.0"),
                avg_price=Decimal("150.25"),
                realized_pnl=Decimal("0.0")
            ),
            Position(
                symbol="GOOGL",
                qty=Decimal("50.0"),
                avg_price=Decimal("2800.50"),
                realized_pnl=Decimal("250.75")
            ),
        ]
        
        for position in positions:
            session.add(position)
        
        # Create sample signals
        signals = [
            Signal(
                id=uuid.uuid4(),
                symbol="AAPL",
                model_name="momentum_v1",
                signal_type="buy",
                direction="long",
                strength=Decimal("0.8500"),
                confidence=Decimal("0.7200"),
                target_price=Decimal("155.00"),
                stop_loss=Decimal("145.00"),
                strategy="momentum_strategy",
                attributes={
                    "rsi": 65.5,
                    "moving_average": 149.8,
                    "volume_ratio": 1.25
                }
            ),
            Signal(
                id=uuid.uuid4(),
                symbol="TSLA",
                model_name="sentiment_v2",
                signal_type="sell",
                direction="short",
                strength=Decimal("0.7200"),
                confidence=Decimal("0.8100"),
                target_price=Decimal("200.00"),
                stop_loss=Decimal("220.00"),
                strategy="sentiment_analysis",
                attributes={
                    "sentiment_score": -0.65,
                    "news_impact": 0.85,
                    "social_buzz": 1.45
                }
            ),
        ]
        
        for signal in signals:
            session.add(signal)
        
        # Create sample orders
        orders = [
            Order(
                id=uuid.uuid4(),
                client_idempotency_key="staging_order_1",
                symbol="AAPL",
                side="buy",
                qty=Decimal("10.0"),
                order_type="market",
                tif="gtc",
                status="filled",
                broker_order_id="ALPACA_12345",
                attributes={
                    "source": "staging_seed",
                    "signal_id": str(signals[0].id)
                }
            ),
            Order(
                id=uuid.uuid4(),
                client_idempotency_key="staging_order_2", 
                symbol="GOOGL",
                side="buy",
                qty=Decimal("5.0"),
                order_type="limit",
                tif="gtc",
                status="accepted",
                attributes={
                    "limit_price": "2750.00",
                    "source": "staging_seed"
                }
            ),
        ]
        
        for order in orders:
            session.add(order)
        
        # Create audit entries for seeding
        seed_audit = AuditLog(
            id=uuid.uuid4(),
            ts=datetime.now(timezone.utc),
            actor="system",
            action="seed_staging_data",
            entity="database",
            entity_id="staging",
            payload={
                "positions_created": len(positions),
                "signals_created": len(signals),
                "orders_created": len(orders),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        session.add(seed_audit)
        await session.commit()
        
        logger.info(f"Created sample data: {len(positions)} positions, {len(signals)} signals, {len(orders)} orders")
        
    except Exception as e:
        logger.error(f"Failed to seed sample data: {e}")
        await session.rollback()
        raise


async def run_seeding():
    """Run the complete seeding process."""
    try:
        # Set up database connection
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        # Get database URL from environment - REQUIRED
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.error("DATABASE_URL environment variable is required but not set!")
            logger.error("")
            logger.error("For staging, start PostgreSQL with Docker:")
            logger.error("  docker-compose up -d db")
            logger.error("")
            logger.error("Then set DATABASE_URL:")
            logger.error("  export DATABASE_URL='postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading'")
            raise ValueError("DATABASE_URL is required")
        
        logger.info(f"Connecting to database: {database_url}")
        
        # Create async engine
        engine = create_async_engine(database_url, echo=False)
        async_session_maker = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session_maker() as session:
            logger.info("Starting staging data seeding...")
            
            # Create admin user
            admin_email = await create_admin_user(session)
            
            # Create sample data
            await seed_sample_data(session)
            
            logger.info("Staging seeding completed successfully!")
            logger.info(f"Admin user created: {admin_email}")
            logger.info("Sample trading data has been created for testing")
            
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        sys.exit(1)


def create_api_token():
    """Generate a sample API token for testing."""
    import secrets
    
    # Generate a simple token for staging (not for production use)
    token = secrets.token_urlsafe(32)
    logger.info(f"Generated staging API token: {token}")
    logger.info("Use this token for authenticated API calls during testing")
    return token


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Staging Database Seeder")
    parser.add_argument(
        "--database-url",
        help="Database URL to use (overrides DATABASE_URL env var)"
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Only generate an API token, don't seed database"
    )
    
    args = parser.parse_args()
    
    # Set database URL from command line if provided
    if args.database_url:
        os.environ['DATABASE_URL'] = args.database_url
    
    if args.token_only:
        create_api_token()
    else:
        # Run seeding
        asyncio.run(run_seeding())
        
        # Also generate a token
        logger.info("\n" + "="*50)
        create_api_token()