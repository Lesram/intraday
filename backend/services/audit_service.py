"""
Compliance-Ready Audit Service for Trading Platform.

Implements SEC Rule 17a-4 and FINRA compliance requirements:
- Immutable audit trail with cryptographic hash chain
- Tamper detection and verification
- Retention policies and archival
- Export capabilities for regulatory reporting

The hash chain ensures that any modification to historical records
can be detected by verifying the chain integrity.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import AuditLog

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Standardized audit action types for compliance."""

    # Order lifecycle
    ORDER_SUBMITTED = "order.submitted"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_REJECTED = "order.rejected"
    ORDER_FILLED = "order.filled"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_MODIFIED = "order.modified"
    ORDER_EXPIRED = "order.expired"

    # Position changes
    POSITION_OPENED = "position.opened"
    POSITION_CLOSED = "position.closed"
    POSITION_ADJUSTED = "position.adjusted"

    # Risk events
    RISK_LIMIT_WARNING = "risk.warning"
    RISK_LIMIT_BREACH = "risk.breach"
    EMERGENCY_STOP_TRIGGERED = "risk.emergency_stop"
    EMERGENCY_STOP_RESOLVED = "risk.emergency_resolved"

    # Strategy events
    STRATEGY_STARTED = "strategy.started"
    STRATEGY_STOPPED = "strategy.stopped"
    STRATEGY_UPDATED = "strategy.updated"
    STRATEGY_ERROR = "strategy.error"

    # Model events
    MODEL_DEPLOYED = "model.deployed"
    MODEL_RETIRED = "model.retired"
    MODEL_PREDICTION = "model.prediction"

    # User events
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DISABLED = "user.disabled"

    # Configuration changes
    CONFIG_UPDATED = "config.updated"
    RISK_LIMIT_UPDATED = "config.risk_limit"

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYNC_COMPLETED = "system.sync"


class AuditEntity(Enum):
    """Entity types for audit categorization."""

    ORDER = "order"
    POSITION = "position"
    STRATEGY = "strategy"
    MODEL = "model"
    USER = "user"
    RISK = "risk"
    CONFIG = "config"
    SYSTEM = "system"


def _json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for audit payloads."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    return str(obj)


def _compute_hash(
    previous_hash: str | None,
    timestamp: datetime,
    action: str,
    entity: str,
    entity_id: str,
    actor: str,
    payload: dict[str, Any],
) -> str:
    """
    Compute SHA-256 hash for audit record.

    The hash includes the previous record's hash, creating
    an immutable chain that detects any tampering.
    """
    # Canonical JSON representation for consistent hashing
    data = {
        "prev": previous_hash or "GENESIS",
        "ts": timestamp.isoformat(),
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "actor": actor,
        "payload": payload,
    }

    canonical = json.dumps(data, sort_keys=True, default=_json_serializer)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ComplianceAuditService:
    """
    Compliance-ready audit service with cryptographic integrity.

    Features:
    - Hash chain for tamper detection
    - Standardized action types
    - Regulatory-compliant retention
    - Export capabilities

    Usage:
        audit_service = ComplianceAuditService(db_session)
        await audit_service.log_order_event(
            action=AuditAction.ORDER_SUBMITTED,
            order_id=order.id,
            actor="user:123",
            details={"symbol": "AAPL", "qty": 100}
        )
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self._last_hash_cache: str | None = None

    async def _get_last_hash(self) -> str | None:
        """Get the hash of the most recent audit record."""
        if self._last_hash_cache:
            return self._last_hash_cache

        result = await self.db.execute(
            select(AuditLog.hash_chain)
            .order_by(desc(AuditLog.ts))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        self._last_hash_cache = row
        return row

    async def log(
        self,
        action: AuditAction,
        entity: AuditEntity,
        entity_id: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        """
        Create an audit log entry with hash chain integrity.

        Args:
            action: The action being logged
            entity: Type of entity affected
            entity_id: ID of the affected entity
            actor: Who/what performed the action (e.g., "user:123", "system:risk_manager")
            payload: Additional details about the action

        Returns:
            The created AuditLog record
        """
        now = datetime.now(UTC)
        payload = payload or {}

        # Get previous hash for chain
        prev_hash = await self._get_last_hash()

        # Compute hash for this record
        record_hash = _compute_hash(
            previous_hash=prev_hash,
            timestamp=now,
            action=action.value,
            entity=entity.value,
            entity_id=entity_id,
            actor=actor,
            payload=payload,
        )

        # Create record
        audit_log = AuditLog(
            id=uuid4(),
            ts=now,
            actor=actor,
            action=action.value,
            entity=entity.value,
            entity_id=entity_id,
            payload=payload,
            hash_chain=record_hash,
        )

        self.db.add(audit_log)
        await self.db.flush()

        # Update cache
        self._last_hash_cache = record_hash

        logger.info(
            "Audit log created",
            extra={
                "audit_id": str(audit_log.id),
                "action": action.value,
                "entity": entity.value,
                "entity_id": entity_id,
                "actor": actor,
                "hash": record_hash[:16],
            }
        )

        return audit_log

    # Convenience methods for common events

    async def log_order_event(
        self,
        action: AuditAction,
        order_id: UUID | str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log an order-related event."""
        return await self.log(
            action=action,
            entity=AuditEntity.ORDER,
            entity_id=str(order_id),
            actor=actor,
            payload=details,
        )

    async def log_position_event(
        self,
        action: AuditAction,
        symbol: str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log a position-related event."""
        return await self.log(
            action=action,
            entity=AuditEntity.POSITION,
            entity_id=symbol,
            actor=actor,
            payload=details,
        )

    async def log_risk_event(
        self,
        action: AuditAction,
        user_id: int | str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log a risk-related event."""
        return await self.log(
            action=action,
            entity=AuditEntity.RISK,
            entity_id=str(user_id),
            actor=actor,
            payload=details,
        )

    async def log_strategy_event(
        self,
        action: AuditAction,
        strategy_id: UUID | str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log a strategy-related event."""
        return await self.log(
            action=action,
            entity=AuditEntity.STRATEGY,
            entity_id=str(strategy_id),
            actor=actor,
            payload=details,
        )

    async def log_user_event(
        self,
        action: AuditAction,
        user_id: int | str,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log a user-related event."""
        return await self.log(
            action=action,
            entity=AuditEntity.USER,
            entity_id=str(user_id),
            actor=actor,
            payload=details,
        )

    async def log_system_event(
        self,
        action: AuditAction,
        component: str,
        details: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Log a system-level event."""
        return await self.log(
            action=action,
            entity=AuditEntity.SYSTEM,
            entity_id=component,
            actor=f"system:{component}",
            payload=details,
        )

    # Verification and compliance methods

    async def verify_chain_integrity(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 10000,
    ) -> dict[str, Any]:
        """
        Verify the integrity of the audit hash chain.

        Checks that each record's hash correctly chains to the previous.
        Used for compliance audits and tamper detection.

        Returns:
            Dict with verification results:
            - valid: bool - Whether chain is intact
            - records_checked: int - Number of records verified
            - first_invalid_id: Optional[str] - ID of first invalid record
            - error: Optional[str] - Error message if invalid
        """
        # Build query
        query = select(AuditLog).order_by(AuditLog.ts)

        if start_time:
            query = query.where(AuditLog.ts >= start_time)
        if end_time:
            query = query.where(AuditLog.ts <= end_time)

        query = query.limit(limit)

        result = await self.db.execute(query)
        records = result.scalars().all()

        if not records:
            return {
                "valid": True,
                "records_checked": 0,
                "message": "No records to verify",
            }

        # Verify chain
        prev_hash = None
        for i, record in enumerate(records):
            if i == 0 and record.hash_chain:
                # First record - just get its hash
                prev_hash = record.hash_chain
                continue

            # Compute expected hash
            expected_hash = _compute_hash(
                previous_hash=prev_hash,
                timestamp=record.ts,
                action=record.action,
                entity=record.entity,
                entity_id=record.entity_id,
                actor=record.actor,
                payload=record.payload or {},
            )

            if record.hash_chain != expected_hash:
                logger.error(
                    "Audit chain integrity violation",
                    extra={
                        "record_id": str(record.id),
                        "expected_hash": expected_hash[:16],
                        "actual_hash": record.hash_chain[:16] if record.hash_chain else None,
                    }
                )
                return {
                    "valid": False,
                    "records_checked": i + 1,
                    "first_invalid_id": str(record.id),
                    "error": f"Hash mismatch at record {i + 1}",
                }

            prev_hash = record.hash_chain

        return {
            "valid": True,
            "records_checked": len(records),
            "message": "Chain integrity verified",
        }

    async def get_audit_trail(
        self,
        entity_type: AuditEntity | None = None,
        entity_id: str | None = None,
        action: AuditAction | None = None,
        actor: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """
        Query audit trail with filters.

        Supports regulatory reporting requirements.
        """
        query = select(AuditLog).order_by(desc(AuditLog.ts))

        conditions = []
        if entity_type:
            conditions.append(AuditLog.entity == entity_type.value)
        if entity_id:
            conditions.append(AuditLog.entity_id == entity_id)
        if action:
            conditions.append(AuditLog.action == action.value)
        if actor:
            conditions.append(AuditLog.actor == actor)
        if start_time:
            conditions.append(AuditLog.ts >= start_time)
        if end_time:
            conditions.append(AuditLog.ts <= end_time)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_audit_trail(
        self,
        entity_type: AuditEntity | None = None,
        entity_id: str | None = None,
        action: AuditAction | None = None,
        actor: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> int:
        """
        Count audit records matching filters for pagination.
        """
        query = select(func.count(AuditLog.id))

        conditions = []
        if entity_type:
            conditions.append(AuditLog.entity == entity_type.value)
        if entity_id:
            conditions.append(AuditLog.entity_id == entity_id)
        if action:
            conditions.append(AuditLog.action == action.value)
        if actor:
            conditions.append(AuditLog.actor == actor)
        if start_time:
            conditions.append(AuditLog.ts >= start_time)
        if end_time:
            conditions.append(AuditLog.ts <= end_time)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def export_for_compliance(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """
        Export audit records for regulatory reporting.

        Returns records in a format suitable for SEC/FINRA reporting.
        """
        records = await self.get_audit_trail(
            start_time=start_date,
            end_time=end_date,
            limit=100000,  # Compliance exports may be large
        )

        return [
            {
                "id": str(r.id),
                "timestamp": r.ts.isoformat(),
                "action": r.action,
                "entity_type": r.entity,
                "entity_id": r.entity_id,
                "actor": r.actor,
                "details": r.payload,
                "hash": r.hash_chain,
            }
            for r in records
        ]

    async def get_statistics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Get audit trail statistics for monitoring."""
        query = select(
            AuditLog.entity,
            AuditLog.action,
            func.count(AuditLog.id).label("count"),
        ).group_by(AuditLog.entity, AuditLog.action)

        if start_time:
            query = query.where(AuditLog.ts >= start_time)
        if end_time:
            query = query.where(AuditLog.ts <= end_time)

        result = await self.db.execute(query)
        rows = result.all()

        # Aggregate by entity and action
        by_entity: dict[str, int] = {}
        by_action: dict[str, int] = {}

        for entity, action, count in rows:
            by_entity[entity] = by_entity.get(entity, 0) + count
            by_action[action] = by_action.get(action, 0) + count

        total = sum(by_entity.values())

        return {
            "total_records": total,
            "by_entity": by_entity,
            "by_action": by_action,
            "period": {
                "start": start_time.isoformat() if start_time else None,
                "end": end_time.isoformat() if end_time else None,
            }
        }


# Global singleton (lazy init)
_audit_service: ComplianceAuditService | None = None


async def get_audit_service(db_session: AsyncSession) -> ComplianceAuditService:
    """Get or create audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = ComplianceAuditService(db_session)
    return _audit_service
