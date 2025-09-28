"""
SQLAlchemy 2.0 models for the trading platform.
All models use async patterns and include proper indexes for performance.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    DECIMAL,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
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


class Order(Base):
    """Order model - tracks all order lifecycle states."""

    __tablename__ = "orders"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
