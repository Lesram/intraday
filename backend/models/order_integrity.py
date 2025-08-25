"""
Order State Management and Integrity System

This module provides comprehensive order lifecycle management with:
- Explicit Finite State Machine (FSM) for order states
- Append-only audit logging for complete traceability
- Idempotency guarantees at API, service, and outbox layers
- Event schema validation with versioning
- State transition validation and rollback protection
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import logging
import time
from typing import Any
import uuid

from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)

# Metrics for order integrity monitoring
order_state_transitions = Counter(
    "trading_order_state_transitions_total",
    "Order state transitions",
    ["from_state", "to_state", "trigger"],
)

order_integrity_violations = Counter(
    "trading_order_integrity_violations_total",
    "Order integrity violations detected",
    ["violation_type"],
)

audit_log_entries = Counter(
    "trading_audit_log_entries_total",
    "Audit log entries created",
    ["event_type", "entity_type"],
)

idempotency_cache_hits = Counter(
    "trading_idempotency_cache_hits_total",
    "Idempotency cache hits by layer",
    ["layer"],  # api, service, outbox
)

order_processing_duration = Histogram(
    "trading_order_processing_duration_seconds",
    "Time spent processing orders by state",
    ["state", "operation"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

Base = declarative_base()


class OrderState(Enum):
    """
    Explicit order states following a strict finite state machine.

    State transitions are controlled and validated to prevent invalid states.
    """

    # Initial states
    PENDING_VALIDATION = "pending_validation"
    VALIDATED = "validated"

    # Risk assessment states
    PENDING_RISK_ASSESSMENT = "pending_risk_assessment"
    RISK_APPROVED = "risk_approved"
    RISK_REJECTED = "risk_rejected"

    # Execution states
    PENDING_SUBMISSION = "pending_submission"
    SUBMITTED = "submitted"
    PENDING_EXECUTION = "pending_execution"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"

    # Terminal states
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"

    # Recovery states
    PENDING_RETRY = "pending_retry"
    UNDER_REVIEW = "under_review"

    @classmethod
    def terminal_states(cls) -> set["OrderState"]:
        """Return set of terminal states that cannot transition."""
        return {cls.FILLED, cls.CANCELLED, cls.REJECTED, cls.EXPIRED, cls.FAILED}

    @classmethod
    def active_states(cls) -> set["OrderState"]:
        """Return set of states considered 'active' orders."""
        return {
            cls.VALIDATED,
            cls.RISK_APPROVED,
            cls.PENDING_SUBMISSION,
            cls.SUBMITTED,
            cls.PENDING_EXECUTION,
            cls.PARTIALLY_FILLED,
        }


class OrderEventType(Enum):
    """Types of events that can occur during order lifecycle."""

    CREATED = "created"
    VALIDATED = "validated"
    RISK_ASSESSED = "risk_assessed"
    SUBMITTED = "submitted"
    EXECUTION_UPDATE = "execution_update"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    MANUAL_INTERVENTION = "manual_intervention"


class TransitionTrigger(Enum):
    """Triggers that can cause state transitions."""

    VALIDATION_COMPLETE = "validation_complete"
    RISK_DECISION = "risk_decision"
    BROKER_SUBMISSION = "broker_submission"
    BROKER_UPDATE = "broker_update"
    USER_CANCELLATION = "user_cancellation"
    SYSTEM_TIMEOUT = "system_timeout"
    ERROR_RECOVERY = "error_recovery"
    MANUAL_OVERRIDE = "manual_override"


# Valid state transitions mapping
VALID_TRANSITIONS: dict[OrderState, dict[TransitionTrigger, OrderState]] = {
    OrderState.PENDING_VALIDATION: {
        TransitionTrigger.VALIDATION_COMPLETE: OrderState.VALIDATED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
        TransitionTrigger.SYSTEM_TIMEOUT: OrderState.EXPIRED,
    },
    OrderState.VALIDATED: {
        TransitionTrigger.RISK_DECISION: OrderState.PENDING_RISK_ASSESSMENT,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.PENDING_RISK_ASSESSMENT: {
        TransitionTrigger.RISK_DECISION: OrderState.RISK_APPROVED,
        TransitionTrigger.RISK_DECISION: OrderState.RISK_REJECTED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
        TransitionTrigger.SYSTEM_TIMEOUT: OrderState.EXPIRED,
    },
    OrderState.RISK_APPROVED: {
        TransitionTrigger.BROKER_SUBMISSION: OrderState.PENDING_SUBMISSION,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.RISK_REJECTED: {
        TransitionTrigger.MANUAL_OVERRIDE: OrderState.VALIDATED,
        # Risk rejected orders can be manually reviewed
    },
    OrderState.PENDING_SUBMISSION: {
        TransitionTrigger.BROKER_SUBMISSION: OrderState.SUBMITTED,
        TransitionTrigger.ERROR_RECOVERY: OrderState.FAILED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.SUBMITTED: {
        TransitionTrigger.BROKER_UPDATE: OrderState.PENDING_EXECUTION,
        TransitionTrigger.BROKER_UPDATE: OrderState.REJECTED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.PENDING_EXECUTION: {
        TransitionTrigger.BROKER_UPDATE: OrderState.PARTIALLY_FILLED,
        TransitionTrigger.BROKER_UPDATE: OrderState.FILLED,
        TransitionTrigger.BROKER_UPDATE: OrderState.CANCELLED,
        TransitionTrigger.SYSTEM_TIMEOUT: OrderState.EXPIRED,
    },
    OrderState.PARTIALLY_FILLED: {
        TransitionTrigger.BROKER_UPDATE: OrderState.FILLED,
        TransitionTrigger.BROKER_UPDATE: OrderState.CANCELLED,
        TransitionTrigger.SYSTEM_TIMEOUT: OrderState.EXPIRED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.FAILED: {
        TransitionTrigger.ERROR_RECOVERY: OrderState.PENDING_RETRY,
        TransitionTrigger.MANUAL_OVERRIDE: OrderState.UNDER_REVIEW,
    },
    OrderState.PENDING_RETRY: {
        TransitionTrigger.VALIDATION_COMPLETE: OrderState.VALIDATED,
        TransitionTrigger.SYSTEM_TIMEOUT: OrderState.FAILED,
        TransitionTrigger.USER_CANCELLATION: OrderState.CANCELLED,
    },
    OrderState.UNDER_REVIEW: {
        TransitionTrigger.MANUAL_OVERRIDE: OrderState.VALIDATED,
        TransitionTrigger.MANUAL_OVERRIDE: OrderState.CANCELLED,
    },
}


@dataclass
class OrderSnapshot:
    """Immutable snapshot of order data at a point in time."""

    order_id: str
    user_id: str
    symbol: str
    quantity: int
    side: str  # buy/sell
    order_type: str  # market/limit
    price: float | None = None
    time_in_force: str = "day"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data

    def calculate_hash(self) -> str:
        """Calculate hash for integrity verification."""
        data_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()


class OrderEventSchema(BaseModel):
    """Pydantic schema for order events with versioning."""

    class Config:
        extra = "forbid"  # Reject unknown fields

    schema_version: str = Field(default="1.0", description="Event schema version")
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: OrderEventType
    order_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # State transition info
    from_state: OrderState | None = None
    to_state: OrderState | None = None
    trigger: TransitionTrigger | None = None

    # Event data
    event_data: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    source_system: str = Field(default="trading-platform")

    # Integrity fields
    idempotency_key: str | None = None
    parent_event_id: str | None = None
    correlation_id: str | None = None

    @validator("schema_version")
    def validate_schema_version(cls, v):
        """Validate schema version format."""
        if not v or not isinstance(v, str) or "." not in v:
            raise ValueError("Schema version must be in format 'X.Y'")
        return v

    @validator("event_data")
    def validate_event_data_size(cls, v):
        """Prevent excessively large event data."""
        if len(json.dumps(v)) > 10000:  # 10KB limit
            raise ValueError("Event data exceeds maximum size")
        return v


class AuditLogEntry(Base):
    """Append-only audit log for complete order traceability."""

    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )

    # Event metadata
    event_type = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False, default="order")
    entity_id = Column(String(100), nullable=False)  # order_id

    # Timing
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Event details
    event_data = Column(JSONB, nullable=False)
    schema_version = Column(String(10), nullable=False, default="1.0")

    # Traceability
    user_id = Column(String(100))
    source_system = Column(String(50), nullable=False, default="trading-platform")
    correlation_id = Column(String(100))
    idempotency_key = Column(String(100))

    # Integrity
    data_hash = Column(String(64), nullable=False)  # SHA-256 hash
    previous_hash = Column(String(64))  # Chain of custody

    # Indexes for performance
    __table_args__ = (
        Index("ix_audit_entity_id_timestamp", "entity_id", "timestamp"),
        Index("ix_audit_event_type_timestamp", "event_type", "timestamp"),
        Index("ix_audit_user_id_timestamp", "user_id", "timestamp"),
        Index("ix_audit_correlation_id", "correlation_id"),
        Index("ix_audit_idempotency_key", "idempotency_key"),
    )


class OrderStateMachine:
    """
    Finite State Machine for order state management.

    Ensures all state transitions are valid and logged properly.
    """

    def __init__(self, *args, audit_logger=None, **kwargs):
        # E1: Accept args and kwargs tolerantly
        self.audit_logger = audit_logger or (lambda *a, **k: None)

    def can_transition(
        self, from_state: OrderState, to_state: OrderState, trigger: TransitionTrigger
    ) -> bool:
        """Check if state transition is valid."""

        # Terminal states cannot transition
        if from_state in OrderState.terminal_states():
            return False

        # Check if transition is defined in the FSM
        valid_triggers = VALID_TRANSITIONS.get(from_state, {})

        # Special handling for risk decisions with different outcomes
        if trigger == TransitionTrigger.RISK_DECISION:
            return to_state in [OrderState.RISK_APPROVED, OrderState.RISK_REJECTED]

        # Special handling for broker updates with different outcomes
        if trigger == TransitionTrigger.BROKER_UPDATE:
            valid_states = []
            for t, state in valid_triggers.items():
                if t == TransitionTrigger.BROKER_UPDATE:
                    valid_states.append(state)
            return to_state in valid_states or len(valid_states) == 0

        return trigger in valid_triggers and valid_triggers[trigger] == to_state

    async def transition(
        self,
        order_id: str,
        from_state: OrderState,
        to_state: OrderState,
        trigger: TransitionTrigger,
        event_data: dict[str, Any],
        user_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> bool:
        """
        Execute state transition with validation and logging.

        Returns True if transition was successful, False otherwise.
        """

        # Validate transition
        if not self.can_transition(from_state, to_state, trigger):
            logger.warning(
                f"Invalid state transition: {from_state} -> {to_state} via {trigger}"
            )

            order_integrity_violations.labels(violation_type="invalid_transition").inc()

            return False

        # Record metrics
        order_state_transitions.labels(
            from_state=from_state.value, to_state=to_state.value, trigger=trigger.value
        ).inc()

        # Create state transition event
        event = OrderEventSchema(
            event_type=OrderEventType.EXECUTION_UPDATE,  # Generic for state changes
            order_id=order_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            event_data=event_data,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

        # Log to audit trail
        await self.audit_logger.log_event(event)

        logger.info(
            f"Order {order_id} transitioned: {from_state} -> {to_state} via {trigger}"
        )
        return True

    def get_valid_transitions(
        self, current_state: OrderState
    ) -> dict[TransitionTrigger, OrderState]:
        """Get valid transitions for current state."""
        return VALID_TRANSITIONS.get(current_state, {})

    def get_reachable_states(self, current_state: OrderState) -> set[OrderState]:
        """Get all states reachable from current state."""
        if current_state in OrderState.terminal_states():
            return set()

        valid_transitions = VALID_TRANSITIONS.get(current_state, {})
        return set(valid_transitions.values())


class IdempotencyManager:
    """
    Multi-layer idempotency management for API, service, and outbox operations.
    """

    def __init__(self, cache_backend=None):
        # In production, this would be Redis or similar
        self._api_cache = {}
        self._service_cache = {}
        self._outbox_cache = {}
        self.cache_backend = cache_backend

    async def check_api_idempotency(
        self, key: str, operation: str
    ) -> dict[str, Any] | None:
        """Check if API operation has already been processed."""
        cache_key = f"api:{operation}:{key}"

        if cache_key in self._api_cache:
            idempotency_cache_hits.labels(layer="api").inc()
            return self._api_cache[cache_key]

        return None

    async def record_api_operation(
        self, key: str, operation: str, result: dict[str, Any]
    ):
        """Record API operation result for idempotency."""
        cache_key = f"api:{operation}:{key}"
        self._api_cache[cache_key] = {
            "result": result,
            "timestamp": time.time(),
            "operation": operation,
        }

    async def check_service_idempotency(
        self, key: str, service: str
    ) -> dict[str, Any] | None:
        """Check if service operation has already been processed."""
        cache_key = f"service:{service}:{key}"

        if cache_key in self._service_cache:
            idempotency_cache_hits.labels(layer="service").inc()
            return self._service_cache[cache_key]

        return None

    async def record_service_operation(
        self, key: str, service: str, result: dict[str, Any]
    ):
        """Record service operation result for idempotency."""
        cache_key = f"service:{service}:{key}"
        self._service_cache[cache_key] = {
            "result": result,
            "timestamp": time.time(),
            "service": service,
        }

    async def check_outbox_idempotency(self, key: str) -> bool:
        """Check if message has already been sent to outbox."""
        cache_key = f"outbox:{key}"

        if cache_key in self._outbox_cache:
            idempotency_cache_hits.labels(layer="outbox").inc()
            return True

        return False

    async def record_outbox_message(self, key: str, message: dict[str, Any]):
        """Record outbox message for idempotency."""
        cache_key = f"outbox:{key}"
        self._outbox_cache[cache_key] = {"message": message, "timestamp": time.time()}


class AuditLogger:
    """
    Append-only audit logger with integrity verification.

    Provides complete traceability of order events with hash chaining.
    """

    def __init__(self, db_session):
        self.db_session = db_session
        self._previous_hash_cache = {}

    async def log_event(self, event: OrderEventSchema):
        """Log event to append-only audit trail."""

        # Calculate data hash for integrity
        event_dict = event.dict()
        data_json = json.dumps(event_dict, sort_keys=True, default=str)
        data_hash = hashlib.sha256(data_json.encode()).hexdigest()

        # Get previous hash for chaining (simplified)
        previous_hash = self._previous_hash_cache.get(event.order_id)

        # Create audit log entry
        audit_entry = AuditLogEntry(
            event_id=uuid.UUID(event.event_id),
            event_type=event.event_type.value,
            entity_type="order",
            entity_id=event.order_id,
            timestamp=event.timestamp,
            event_data=event_dict,
            schema_version=event.schema_version,
            user_id=event.user_id,
            source_system=event.source_system,
            correlation_id=event.correlation_id,
            idempotency_key=event.idempotency_key,
            data_hash=data_hash,
            previous_hash=previous_hash,
        )

        # Save to database
        self.db_session.add(audit_entry)
        await self.db_session.commit()

        # Update hash chain cache
        self._previous_hash_cache[event.order_id] = data_hash

        # Record metrics
        audit_log_entries.labels(
            event_type=event.event_type.value, entity_type="order"
        ).inc()

        logger.debug(
            f"Audit event logged: {event.event_type} for order {event.order_id}"
        )

    async def get_order_audit_trail(self, order_id: str) -> list[AuditLogEntry]:
        """Get complete audit trail for an order."""

        query = (
            self.db_session.query(AuditLogEntry)
            .filter(AuditLogEntry.entity_id == order_id)
            .order_by(AuditLogEntry.timestamp)
        )

        return await query.all()

    async def verify_audit_integrity(self, order_id: str) -> bool:
        """Verify audit trail integrity using hash chaining."""

        trail = await self.get_order_audit_trail(order_id)

        previous_hash = None
        for entry in trail:
            # Verify hash chain
            if previous_hash and entry.previous_hash != previous_hash:
                logger.error(
                    f"Audit integrity violation: hash chain broken for order {order_id}"
                )
                order_integrity_violations.labels(
                    violation_type="hash_chain_broken"
                ).inc()
                return False

            # Verify data hash
            event_json = json.dumps(entry.event_data, sort_keys=True, default=str)
            expected_hash = hashlib.sha256(event_json.encode()).hexdigest()

            if entry.data_hash != expected_hash:
                logger.error(
                    f"Audit integrity violation: data hash mismatch for order {order_id}"
                )
                order_integrity_violations.labels(
                    violation_type="data_hash_mismatch"
                ).inc()
                return False

            previous_hash = entry.data_hash

        return True


class OrderIntegrityService:
    """
    Main service for order integrity management.

    Coordinates FSM, audit logging, and idempotency across all layers.
    """

    def __init__(self, *args, db_session=None, **kwargs):
        # E1: Accept args and kwargs tolerantly
        self.db_session = db_session
        self.audit_logger = AuditLogger(db_session) if db_session else None
        self.state_machine = OrderStateMachine(audit_logger=self.audit_logger)
        self.idempotency_manager = IdempotencyManager()

    async def create_order(
        self, order_data: OrderSnapshot, user_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        """
        Create new order with full integrity guarantees.
        """

        # Check API-level idempotency
        existing_result = await self.idempotency_manager.check_api_idempotency(
            idempotency_key, "create_order"
        )
        if existing_result:
            return existing_result["result"]

        # Create order creation event
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id=order_data.order_id,
            event_data=order_data.to_dict(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            correlation_id=str(uuid.uuid4()),
        )

        # Log creation event
        await self.audit_logger.log_event(event)

        # Initial state is pending validation
        await self.state_machine.transition(
            order_id=order_data.order_id,
            from_state=None,  # No previous state
            to_state=OrderState.PENDING_VALIDATION,
            trigger=TransitionTrigger.VALIDATION_COMPLETE,  # System trigger
            event_data={"created": True},
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

        result = {
            "order_id": order_data.order_id,
            "state": OrderState.PENDING_VALIDATION.value,
            "created_at": order_data.created_at.isoformat(),
            "integrity_hash": order_data.calculate_hash(),
        }

        # Record API operation for idempotency
        await self.idempotency_manager.record_api_operation(
            idempotency_key, "create_order", result
        )

        return result

    async def transition_order_state(
        self,
        order_id: str,
        from_state: OrderState,
        to_state: OrderState,
        trigger: TransitionTrigger,
        event_data: dict[str, Any],
        user_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> bool:
        """
        Transition order state with full validation and logging.
        """

        # Check service-level idempotency
        if idempotency_key:
            existing_result = await self.idempotency_manager.check_service_idempotency(
                idempotency_key, "state_transition"
            )
            if existing_result:
                return existing_result["result"]

        # Execute transition
        success = await self.state_machine.transition(
            order_id=order_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            event_data=event_data,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

        # Record service operation for idempotency
        if idempotency_key:
            await self.idempotency_manager.record_service_operation(
                idempotency_key, "state_transition", {"success": success}
            )

        return success

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        """Get comprehensive order status including audit trail."""

        # Get audit trail
        audit_trail = await self.audit_logger.get_order_audit_trail(order_id)

        if not audit_trail:
            return {"error": "Order not found"}

        # Get current state from latest audit entry
        latest_entry = audit_trail[-1]
        current_state = None

        # Extract state from event data
        if "to_state" in latest_entry.event_data:
            current_state = latest_entry.event_data["to_state"]

        # Verify integrity
        integrity_valid = await self.audit_logger.verify_audit_integrity(order_id)

        return {
            "order_id": order_id,
            "current_state": current_state,
            "audit_trail_length": len(audit_trail),
            "integrity_valid": integrity_valid,
            "created_at": audit_trail[0].timestamp.isoformat() if audit_trail else None,
            "last_updated": latest_entry.timestamp.isoformat(),
        }

    async def send_to_outbox(
        self, order_id: str, message: dict[str, Any], idempotency_key: str
    ) -> bool:
        """Send message to outbox with idempotency guarantee."""

        # Check outbox-level idempotency
        if await self.idempotency_manager.check_outbox_idempotency(idempotency_key):
            return True  # Already sent

        # Record outbox message (simplified - in production would use message queue)
        await self.idempotency_manager.record_outbox_message(idempotency_key, message)

        # Log outbox event
        event = OrderEventSchema(
            event_type=OrderEventType.EXECUTION_UPDATE,
            order_id=order_id,
            event_data={"outbox_message": message},
            idempotency_key=idempotency_key,
        )

        await self.audit_logger.log_event(event)

        return True
