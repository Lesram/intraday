"""Enhanced database models for production idempotency and event tracking

This module extends the database models with:
1. OrderEvent model for trade update deduplication (now in backend.infra.schemas)
2. DailyLedger model for transactional daily caps
3. Enhanced Orders model with account_id and idempotency key
4. Repository methods for atomic guardrail operations
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from backend.infra.schemas import Base, OrderEvent  # noqa: F401 - re-export for backwards compatibility


class DailyLedger(Base):
    """Daily trading ledger for atomic guardrail operations"""
    __tablename__ = "daily_ledger"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(50), nullable=False)
    day_utc = Column(Date, nullable=False)
    orders_count = Column(Integer, server_default='0', nullable=False)
    submitted_notional_usd = Column(Numeric(precision=15, scale=2), server_default='0.00', nullable=False)
    filled_notional_usd = Column(Numeric(precision=15, scale=2), server_default='0.00', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Unique per account per day
    __table_args__ = (
        UniqueConstraint('account_id', 'day_utc', name='uq_daily_ledger_account_day'),
        Index('idx_daily_ledger_account_day', 'account_id', 'day_utc'),
    )


# Add to existing Order model (extend it)
"""
Add these fields to your existing Order model in backend/database/models.py:

class Order(Base):
    # ... existing fields ...

    # Add for idempotency
    account_id = Column(String(50), nullable=True)  # Will be required after migration
    client_idempotency_key = Column(String(100), nullable=True)  # For deduplication

    # Add relationship to events
    events = relationship("OrderEvent", back_populates="order", cascade="all, delete-orphan")

    # Add unique constraint in __table_args__
    __table_args__ = (
        # ... existing constraints ...
        UniqueConstraint('account_id', 'client_idempotency_key',
                        name='uq_orders_account_client_order'),
        Index('idx_orders_broker_order_id', 'broker_order_id'),
        Index('idx_orders_status', 'status'),
        Index('idx_orders_created_at', 'created_at'),
        Index('idx_orders_symbol_created', 'symbol', 'created_at'),
    )
"""
