"""
SQLAlchemy 2.0 models for the trading platform.
All models use async patterns and include proper indexes for performance.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid

import sqlalchemy as sa
from sqlalchemy import (
    DECIMAL,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def get_json_type():
    """Get the appropriate JSON type for the current database dialect."""
    # This will be JSONB for PostgreSQL, JSON for others (SQLite, etc.)
    return sa.JSON().with_variant(JSONB, "postgresql")


# Base class with async support
class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    # Naming convention for constraints
    __abstract__ = True

    metadata = sa.MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class User(Base):
    """
    User model for authentication and authorization.
    This model represents the existing users table in the database.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=True, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    roles: Mapped[list[str]] = mapped_column(sa.ARRAY(String), nullable=False, default=[])
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(Base):
    """Order model - tracks all order lifecycle states."""

    __tablename__ = "orders"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # User ownership - for multi-user support and IDOR prevention
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="admin", index=True
    )

    # Idempotency key - ensures no duplicate orders
    client_idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    # Order details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # 'buy' or 'sell'
    qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    order_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'market', 'limit', etc.
    tif: Mapped[str] = mapped_column(String(10), nullable=False)  # 'gtc', 'ioc', 'fok'

    # Fill tracking
    filled_qty: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 6), nullable=False, default=0, server_default=sa.text("0.0")
    )

    # Price fields
    limit_price: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted", index=True
    )

    # Timestamps
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Broker integration
    broker_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Flexible attributes for order-specific data
    attributes: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Relationships
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="order", cascade="all, delete-orphan"
    )
    events: Mapped[list["OrderEvent"]] = relationship(
        "OrderEvent", back_populates="order", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_orders_symbol_status", "symbol", "status"),
        Index("ix_orders_submitted_at", "submitted_at"),
    )


class Execution(Base):
    """Execution model - tracks individual fills."""

    __tablename__ = "executions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key to order
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Execution details
    fill_qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    fill_price: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    venue: Mapped[str] = mapped_column(String(50), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="executions")

    # Indexes
    __table_args__ = (
        Index("ix_executions_ts", "ts"),
        Index("ix_executions_order_ts", "order_id", "ts"),
    )


class OrderEvent(Base):
    """Trade update events for deduplication and audit trail."""

    __tablename__ = "order_events"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Foreign key to order
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event details
    broker_order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # trade_update, fill, cancel, etc.
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_data: Mapped[dict[str, Any] | None] = mapped_column(get_json_type(), nullable=True)

    # Timestamps
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="events")

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint('broker_order_id', 'event_type', 'event_time',
                        name='uq_events_broker_type_time'),
        Index('idx_events_broker_order', 'broker_order_id'),
        Index('idx_events_order_time', 'order_id', 'event_time'),
        Index('idx_events_type_time', 'event_type', 'event_time'),
    )


class Position(Base):
    """Position model - tracks current positions by symbol."""

    __tablename__ = "positions"

    # Symbol as primary key (one position per symbol)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Position details
    qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False, default=0)
    avg_price: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 6), nullable=False, default=0
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 6), nullable=False, default=0
    )

    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


class Signal(Base):
    """Signal model - tracks trading signals from strategies."""

    __tablename__ = "signals"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Core signal identification
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Signal characteristics
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # 'buy', 'sell', 'hold'
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # 'long', 'short', 'neutral'
    strength: Mapped[Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)  # 0.0000 to 1.0000
    confidence: Mapped[Decimal] = mapped_column(DECIMAL(5, 4), nullable=False)  # 0.0000 to 1.0000

    # Optional price targets
    target_price: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)

    # Expiry for signal validity
    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Additional metadata
    attributes: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Legacy fields for backward compatibility
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(get_json_type(), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_signals_symbol_ts", "symbol", "ts"),
        Index("ix_signals_strategy_ts", "strategy", "ts"),
        Index("ix_signals_symbol_model", "symbol", "model_name"),
        Index("ix_signals_signal_type_direction", "signal_type", "direction"),
        Index("ix_signals_confidence_strength", "confidence", "strength"),
        Index("ix_signals_expiry", "expiry"),
        Index("ix_signals_created_at", "created_at"),
    )


class ModelRegistry(Base):
    """Model registry - tracks ML models and their metadata."""

    __tablename__ = "model_registry"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Model identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)

    # Model metadata
    metrics: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Model status
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Indexes and constraints
    __table_args__ = (
        Index("ix_model_registry_name_version", "name", "version"),
        Index("ix_model_registry_active", "active"),
        UniqueConstraint("name", "version", name="uq_model_registry_name_version"),
    )


class ModelMonitoringSnapshot(Base):
    """Monitoring snapshots for models (rolling evaluation + drift)."""

    __tablename__ = "model_monitoring_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metrics: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )
    drift: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_model_monitoring_name_created", "model_name", "created_at"),
        Index("ix_model_monitoring_model_created", "model_id", "created_at"),
    )


class ModelLifecycleEvent(Base):
    """Lifecycle events (monitoring, retrain decisions, promotion reviews)."""

    __tablename__ = "model_lifecycle_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_registry.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    payload: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_model_lifecycle_name_created", "model_name", "created_at"),
        Index("ix_model_lifecycle_type_created", "event_type", "created_at"),
        Index("ix_model_lifecycle_model_created", "model_id", "created_at"),
    )


class AuditLog(Base):
    """Audit log model - tracks all system actions for compliance."""

    __tablename__ = "audit_logs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Audit details
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    actor: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # user, system, etc.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # order, position, etc.
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Flexible payload for audit data
    payload: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Hash chain for tamper detection (B9 will use this)
    hash_chain: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_audit_logs_ts", "ts"),
        Index("ix_audit_logs_actor_ts", "actor", "ts"),
        Index("ix_audit_logs_entity_ts", "entity", "ts"),
        Index("ix_audit_logs_action_ts", "action", "ts"),
    )


class OutboxEvent(Base):
    """Outbox event model for exactly-once side-effects."""

    __tablename__ = "outbox_events"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Topic for routing to handlers
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Event payload with all necessary data
    payload: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Processing status
    status: Mapped[str] = mapped_column(
        Enum("pending", "sent", "failed", name="outbox_status"),
        nullable=False,
        default="pending",
        index=True,
    )

    # Retry tracking
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    # Backoff scheduling
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        # For polling pending events
        Index("ix_outbox_status_next_attempt", "status", "next_attempt_at"),
        # For topic-based filtering
        Index("ix_outbox_topic_status", "topic", "status"),
        # For cleanup and monitoring
        Index("ix_outbox_created_at", "created_at"),
    )


class Strategy(Base):
    """Strategy model - tracks trading strategy configurations and performance."""

    __tablename__ = "strategies"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Strategy identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status management
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="inactive", server_default="inactive", index=True
    )

    # Configuration - stored as JSONB for flexibility
    symbols: Mapped[list[str]] = mapped_column(
        get_json_type(), nullable=False, default=list, server_default=sa.text("'[]'")
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Performance tracking
    total_pnl: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 6), nullable=False, default=0, server_default=sa.text("0.0")
    )
    total_trades: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    winning_trades: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    losing_trades: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )
    win_rate: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 4), nullable=False, default=0, server_default=sa.text("0.0")
    )

    # Risk limits
    max_position_size: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)
    max_daily_loss: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 6), nullable=True)
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(5, 4), nullable=True)

    # Execution tracking
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_signal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default=sa.text("0")
    )

    # Model integration (optional)
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=True, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    model: Mapped["ModelRegistry | None"] = relationship(
        "ModelRegistry", foreign_keys=[model_id], lazy="selectin"
    )

    # Indexes
    __table_args__ = (
        Index("ix_strategies_status_type", "status", "strategy_type"),
        Index("ix_strategies_updated_at", "updated_at"),
    )


class Backtest(Base):
    """Backtest model - stores historical strategy backtesting results."""

    __tablename__ = "backtests"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )

    # Foreign keys
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NOTE: user_id is UUID in production database (no FK constraint to users table)
    # This allows external user IDs or future migration flexibility
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Backtest parameters
    start_date: Mapped[datetime] = mapped_column(sa.Date(), nullable=False)
    end_date: Mapped[datetime] = mapped_column(sa.Date(), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(get_json_type(), nullable=True)

    # Results summary
    final_equity: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2), nullable=True)
    total_return: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    annualized_return: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    win_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    total_trades: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    winning_trades: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)
    losing_trades: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)

    # Detailed results (JSON)
    equity_curve: Mapped[list[dict[str, Any]] | None] = mapped_column(get_json_type(), nullable=True)
    trade_log: Mapped[list[dict[str, Any]] | None] = mapped_column(get_json_type(), nullable=True)
    monthly_returns: Mapped[list[dict[str, Any]] | None] = mapped_column(get_json_type(), nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(get_json_type(), nullable=True)

    # Execution info
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    progress: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0, server_default=sa.text("0"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    strategy: Mapped["Strategy"] = relationship(
        "Strategy", foreign_keys=[strategy_id], lazy="selectin"
    )

    # Indexes and constraints
    __table_args__ = (
        Index("idx_backtests_strategy", "strategy_id"),
        Index("idx_backtests_user", "user_id"),
        Index("idx_backtests_status", "status"),
        Index("idx_backtests_created", "created_at"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="chk_backtests_status",
        ),
        sa.CheckConstraint("end_date >= start_date", name="chk_backtests_dates"),
        sa.CheckConstraint("initial_capital >= 1000", name="chk_backtests_capital"),
    )


class PositionLot(Base):
    """
    Position Lot model - tracks individual position lots for accurate cost basis.
    Enables FIFO/LIFO/SpecID lot matching and proper realized P&L calculation.
    """

    __tablename__ = "position_lots"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # User and symbol
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Lot details
    qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 6), nullable=False
    )  # Price per share

    # Order reference
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    open_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True
    )  # 'open', 'closed'

    # Relationships
    order: Mapped[Order] = relationship("Order")

    # Indexes
    __table_args__ = (
        Index("ix_position_lots_user_symbol", "user_id", "symbol"),
        Index("ix_position_lots_status", "status"),
        Index("ix_position_lots_open_date", "open_date"),
        sa.CheckConstraint("remaining_qty >= 0", name="chk_position_lots_remaining_qty"),
        sa.CheckConstraint("qty > 0", name="chk_position_lots_qty"),
    )


class RealizedTrade(Base):
    """
    Realized Trade model - tracks completed (closed) trades with accurate P&L.
    Created when a position lot is fully or partially closed.
    """

    __tablename__ = "realized_trades"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # User and symbol
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Trade details
    qty: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    open_price: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)

    # Realized P&L
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), nullable=False)
    realized_pnl_percent: Mapped[Decimal] = mapped_column(DECIMAL(10, 4), nullable=False)

    # Order references
    open_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    close_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Lot reference
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("position_lots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    open_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    close_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Additional metadata (commissions, fees, etc.)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict, server_default=sa.text("'{}'")
    )

    # Relationships
    open_order: Mapped[Order] = relationship("Order", foreign_keys=[open_order_id])
    close_order: Mapped[Order] = relationship("Order", foreign_keys=[close_order_id])
    lot: Mapped[PositionLot] = relationship("PositionLot")

    # Indexes
    __table_args__ = (
        Index("ix_realized_trades_user_symbol", "user_id", "symbol"),
        Index("ix_realized_trades_close_date", "user_id", "close_date"),
        Index("ix_realized_trades_open_date", "open_date"),
        sa.CheckConstraint("qty > 0", name="chk_realized_trades_qty"),
    )


# ===========================
# RISK MANAGEMENT TABLES
# ===========================


class RiskMetric(Base):
    """
    Real-time risk metrics tracking.
    Stores current values and status of each risk metric.
    """

    __tablename__ = "risk_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    current_value: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    limit_value: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    percent_used: Mapped[Decimal] = mapped_column(DECIMAL(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # normal, warning, critical, breached
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Constraints and indexes
    __table_args__ = (
        Index("ix_risk_metrics_user_name", "user_id", "metric_name"),
        Index("ix_risk_metrics_status", "status"),
        sa.CheckConstraint(
            "status IN ('normal', 'warning', 'critical', 'breached')",
            name="chk_risk_metrics_status",
        ),
        sa.CheckConstraint("percent_used >= 0", name="chk_risk_metrics_percent"),
    )


class RiskViolation(Base):
    """
    Risk limit violation records.
    Stores historical violations with severity and resolution status.
    """

    __tablename__ = "risk_violations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    violation_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # warning, breach
    current_value: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    limit_value: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # low, medium, high, critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        index=True,
    )

    # Constraints and indexes
    __table_args__ = (
        Index("ix_risk_violations_user_resolved", "user_id", "resolved"),
        Index("ix_risk_violations_severity", "severity"),
        sa.CheckConstraint(
            "violation_type IN ('warning', 'breach')", name="chk_risk_violations_type"
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="chk_risk_violations_severity",
        ),
    )


class RiskLimit(Base):
    """
    User risk limit configurations.
    Defines limits and thresholds for each risk metric.
    """

    __tablename__ = "risk_limits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    limit_name: Mapped[str] = mapped_column(String(50), nullable=False)
    limit_value: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    warning_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("80.0")
    )
    critical_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("95.0")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("user_id", "limit_name", name="uq_risk_limits_user_name"),
        Index("ix_risk_limits_user_enabled", "user_id", "enabled"),
        sa.CheckConstraint(
            "warning_threshold < critical_threshold", name="chk_risk_limits_thresholds"
        ),
    )


class EmergencyStop(Base):
    """
    Emergency stop records.
    Tracks when emergency stops are triggered and resolved.
    """

    __tablename__ = "emergency_stops"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    strategies_stopped: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    orders_cancelled: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # active, resolved
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Constraints and indexes
    __table_args__ = (
        Index("ix_emergency_stops_user_status", "user_id", "status"),
        sa.CheckConstraint(
            "status IN ('active', 'resolved')", name="chk_emergency_stops_status"
        ),
    )


class PortfolioHistory(Base):
    """
    Portfolio history snapshots for tracking equity over time.
    
    Phase: Portfolio Analytics
    PREREQUISITE: Background job to record snapshots (e.g., Celery beat or APScheduler)
    
    This table stores periodic snapshots of portfolio state for:
    - Equity curve visualization
    - Historical performance analysis
    - Drawdown calculations
    """

    __tablename__ = "portfolio_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    total_equity: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 2), nullable=False, comment="Total portfolio value including positions"
    )
    cash: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 2), nullable=False, comment="Available cash balance"
    )
    positions_value: Mapped[Decimal] = mapped_column(
        DECIMAL(18, 2), nullable=False, default=0, comment="Total value of open positions"
    )
    daily_pnl: Mapped[Decimal | None] = mapped_column(
        DECIMAL(18, 2), nullable=True, comment="Profit/loss for the day"
    )
    daily_pnl_percent: Mapped[Decimal | None] = mapped_column(
        DECIMAL(8, 4), nullable=True, comment="Daily P&L as percentage"
    )
    total_pnl: Mapped[Decimal | None] = mapped_column(
        DECIMAL(18, 2), nullable=True, comment="Cumulative profit/loss"
    )
    total_pnl_percent: Mapped[Decimal | None] = mapped_column(
        DECIMAL(8, 4), nullable=True, comment="Cumulative P&L as percentage"
    )
    position_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of open positions"
    )
    snapshot_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled",
        comment="Type: scheduled, manual, trade, rebalance"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Constraints and indexes for efficient querying
    __table_args__ = (
        Index("ix_portfolio_history_user_timestamp", "user_id", "timestamp"),
        Index("ix_portfolio_history_timestamp", "timestamp"),
        sa.CheckConstraint(
            "snapshot_type IN ('scheduled', 'manual', 'trade', 'rebalance')",
            name="chk_portfolio_history_snapshot_type"
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "userId": self.user_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "totalEquity": float(self.total_equity),
            "cash": float(self.cash),
            "positionsValue": float(self.positions_value),
            "dailyPnL": float(self.daily_pnl) if self.daily_pnl else None,
            "dailyPnLPercent": float(self.daily_pnl_percent) if self.daily_pnl_percent else None,
            "totalPnL": float(self.total_pnl) if self.total_pnl else None,
            "totalPnLPercent": float(self.total_pnl_percent) if self.total_pnl_percent else None,
            "positionCount": self.position_count,
            "snapshotType": self.snapshot_type,
        }


class Watchlist(Base):
    """
    Watchlist model - tracks user's symbol watchlists.
    Phase 7 - Market Data & Charting
    """

    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    symbols: Mapped[list["WatchlistSymbol"]] = relationship(
        "WatchlistSymbol",
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistSymbol.order",
    )

    # Constraints and indexes
    __table_args__ = (
        Index("ix_watchlists_user_id", "user_id"),
        UniqueConstraint("user_id", "name", name="uq_watchlists_user_name"),
    )

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "is_default": self.is_default,
            "symbols": [
                {
                    "id": s.id,
                    "symbol": s.symbol,
                    "order": s.order,
                }
                for s in self.symbols
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WatchlistSymbol(Base):
    """
    Watchlist symbol model - individual symbols in a watchlist.
    Phase 7 - Market Data & Charting
    """

    __tablename__ = "watchlist_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # Relationships
    watchlist: Mapped["Watchlist"] = relationship("Watchlist", back_populates="symbols")

    # Constraints and indexes
    __table_args__ = (
        Index("ix_watchlist_symbols_watchlist_id", "watchlist_id"),
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbols_watchlist_symbol"),
        Index("ix_watchlist_symbols_symbol", "symbol"),
    )


class ChartTemplate(Base):
    """
    Chart template model - saves chart configurations (layout, indicators, styles).
    Phase 7 - Market Data & Charting
    """

    __tablename__ = "chart_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    layout: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict
    )
    indicators: Mapped[list[dict[str, Any]]] = mapped_column(
        get_json_type(), nullable=False, default=list
    )
    drawings: Mapped[list[dict[str, Any]]] = mapped_column(
        get_json_type(), nullable=False, default=list
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        get_json_type(), nullable=False, default=dict
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        onupdate=sa.text("CURRENT_TIMESTAMP"),
    )

    # Constraints and indexes
    __table_args__ = (
        Index("ix_chart_templates_user_id", "user_id"),
        UniqueConstraint("user_id", "name", name="uq_chart_templates_user_name"),
    )

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "layout": self.layout,
            "indicators": self.indicators,
            "drawings": self.drawings,
            "settings": self.settings,
            "is_default": self.is_default,
            "is_preset": self.is_preset,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
