"""
Audits repository - tracks system audit logs and compliance.
Implements async CRUD operations with proper error handling.
"""
from datetime import datetime
import logging
from typing import Any
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import AuditLog

logger = logging.getLogger(__name__)


class AuditNotFoundError(Exception):
    """Raised when an audit log is not found."""
    pass


class AuditsRepo:
    """Repository for audit log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None
    ) -> AuditLog:
        """
        Create a new audit log entry.
        
        Args:
            action: Action performed ('CREATE', 'UPDATE', 'DELETE', 'LOGIN', etc.)
            entity_type: Type of entity ('order', 'position', 'user', 'config', etc.)
            entity_id: ID of the entity (as string for flexibility)
            user_id: Optional user ID who performed the action
            ip_address: Optional IP address of the request
            user_agent: Optional user agent string
            details: Optional additional details
            
        Returns:
            AuditLog: Newly created audit log
        """
        new_audit_log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {}
        )

        try:
            self.session.add(new_audit_log)
            await self.session.flush()  # Get the ID without committing

            logger.info(
                "Audit log created",
                extra={
                    "audit_id": str(new_audit_log.id),
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "user_id": user_id
                }
            )

            return new_audit_log

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(
                "Failed to create audit log",
                extra={
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "error": str(e)
                }
            )
            raise

    async def log_order_action(
        self,
        *,
        action: str,
        order_id: uuid.UUID,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None
    ) -> AuditLog:
        """
        Log an order-related action.
        
        Args:
            action: Action performed
            order_id: Order ID
            user_id: Optional user ID
            details: Optional additional details
            ip_address: Optional IP address
            
        Returns:
            AuditLog: Created audit log
        """
        return await self.create_audit_log(
            action=action,
            entity_type='order',
            entity_id=str(order_id),
            user_id=user_id,
            ip_address=ip_address,
            details=details
        )

    async def log_position_action(
        self,
        *,
        action: str,
        position_id: uuid.UUID,
        user_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None
    ) -> AuditLog:
        """
        Log a position-related action.
        
        Args:
            action: Action performed
            position_id: Position ID
            user_id: Optional user ID
            details: Optional additional details
            ip_address: Optional IP address
            
        Returns:
            AuditLog: Created audit log
        """
        return await self.create_audit_log(
            action=action,
            entity_type='position',
            entity_id=str(position_id),
            user_id=user_id,
            ip_address=ip_address,
            details=details
        )

    async def log_user_action(
        self,
        *,
        action: str,
        target_user_id: str,
        acting_user_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None
    ) -> AuditLog:
        """
        Log a user-related action.
        
        Args:
            action: Action performed
            target_user_id: User ID being acted upon
            acting_user_id: User ID performing the action
            details: Optional additional details
            ip_address: Optional IP address
            user_agent: Optional user agent
            
        Returns:
            AuditLog: Created audit log
        """
        return await self.create_audit_log(
            action=action,
            entity_type='user',
            entity_id=target_user_id,
            user_id=acting_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details
        )

    async def log_system_action(
        self,
        *,
        action: str,
        component: str,
        details: dict[str, Any] | None = None
    ) -> AuditLog:
        """
        Log a system-level action.
        
        Args:
            action: Action performed
            component: System component name
            details: Optional additional details
            
        Returns:
            AuditLog: Created audit log
        """
        return await self.create_audit_log(
            action=action,
            entity_type='system',
            entity_id=component,
            details=details
        )

    async def get_by_id(self, audit_id: uuid.UUID) -> AuditLog | None:
        """
        Get audit log by ID.
        
        Args:
            audit_id: Audit log ID
            
        Returns:
            AuditLog if found, None otherwise
        """
        stmt = select(AuditLog).where(AuditLog.id == audit_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_logs_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> list[AuditLog]:
        """
        Get audit logs for a specific entity.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity ID
            limit: Maximum number of logs to return
            
        Returns:
            List of audit logs
        """
        stmt = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.entity_type == entity_type,
                    AuditLog.entity_id == entity_id
                )
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_logs_by_user(
        self,
        user_id: str,
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[AuditLog]:
        """
        Get audit logs for a specific user.
        
        Args:
            user_id: User ID
            limit: Maximum number of logs to return
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of audit logs
        """
        conditions = [AuditLog.user_id == user_id]

        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)

        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        stmt = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_logs_by_action(
        self,
        action: str,
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[AuditLog]:
        """
        Get audit logs by action type.
        
        Args:
            action: Action type
            limit: Maximum number of logs to return
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of audit logs
        """
        conditions = [AuditLog.action == action]

        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)

        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        stmt = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_logs(
        self,
        limit: int = 100,
        entity_type: str | None = None
    ) -> list[AuditLog]:
        """
        Get recent audit logs.
        
        Args:
            limit: Maximum number of logs to return
            entity_type: Optional entity type filter
            
        Returns:
            List of recent audit logs
        """
        stmt = select(AuditLog)

        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)

        stmt = (
            stmt.order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_security_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100
    ) -> list[AuditLog]:
        """
        Get security-related audit events.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of logs to return
            
        Returns:
            List of security-related audit logs
        """
        security_actions = ['LOGIN', 'LOGOUT', 'LOGIN_FAILED', 'PASSWORD_CHANGE',
                           'PERMISSION_DENIED', 'API_KEY_CREATED', 'API_KEY_REVOKED']

        conditions = [AuditLog.action.in_(security_actions)]

        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)

        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        stmt = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_audit_summary(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> dict[str, Any]:
        """
        Get audit log summary statistics.
        
        Args:
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            Dictionary with audit summary
        """
        conditions = []

        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)

        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        if conditions:
            stmt = select(AuditLog).where(and_(*conditions))
        else:
            stmt = select(AuditLog)

        result = await self.session.execute(stmt)
        logs = list(result.scalars().all())

        if not logs:
            return {
                "total_logs": 0,
                "date_range": {
                    "start": start_time,
                    "end": end_time
                },
                "action_counts": {},
                "entity_type_counts": {},
                "user_counts": {},
                "unique_ips": 0
            }

        # Count by action
        action_counts = {}
        for log in logs:
            action_counts[log.action] = action_counts.get(log.action, 0) + 1

        # Count by entity type
        entity_type_counts = {}
        for log in logs:
            entity_type_counts[log.entity_type] = entity_type_counts.get(log.entity_type, 0) + 1

        # Count by user
        user_counts = {}
        for log in logs:
            if log.user_id:
                user_counts[log.user_id] = user_counts.get(log.user_id, 0) + 1

        # Count unique IPs
        unique_ips = len(set(log.ip_address for log in logs if log.ip_address))

        # Get time range from actual data
        timestamps = [log.timestamp for log in logs]
        actual_start = min(timestamps) if timestamps else None
        actual_end = max(timestamps) if timestamps else None

        return {
            "total_logs": len(logs),
            "date_range": {
                "requested_start": start_time,
                "requested_end": end_time,
                "actual_start": actual_start,
                "actual_end": actual_end
            },
            "action_counts": action_counts,
            "entity_type_counts": entity_type_counts,
            "user_counts": user_counts,
            "unique_ips": unique_ips,
            "top_actions": sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_users": sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        }

    async def search_logs(
        self,
        *,
        search_term: str,
        search_fields: list[str] | None = None,
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None
    ) -> list[AuditLog]:
        """
        Search audit logs by text.
        
        Args:
            search_term: Text to search for
            search_fields: Optional list of fields to search in
            limit: Maximum number of results
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            List of matching audit logs
        """
        conditions = []

        # Time filters
        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)

        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        # Default fields to search if not specified
        if not search_fields:
            search_fields = ['action', 'entity_type', 'entity_id', 'user_id']

        # Build search conditions (case-insensitive)
        search_conditions = []
        search_lower = search_term.lower()

        for field in search_fields:
            if field == 'action':
                search_conditions.append(func.lower(AuditLog.action).contains(search_lower))
            elif field == 'entity_type':
                search_conditions.append(func.lower(AuditLog.entity_type).contains(search_lower))
            elif field == 'entity_id':
                search_conditions.append(func.lower(AuditLog.entity_id).contains(search_lower))
            elif field == 'user_id':
                search_conditions.append(func.lower(AuditLog.user_id).contains(search_lower))
            elif field == 'ip_address':
                search_conditions.append(func.lower(AuditLog.ip_address).contains(search_lower))

        if search_conditions:
            conditions.append(or_(*search_conditions))

        if conditions:
            stmt = (
                select(AuditLog)
                .where(and_(*conditions))
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
            )
        else:
            # If no conditions, return recent logs
            stmt = (
                select(AuditLog)
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
            )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cleanup_old_logs(
        self,
        older_than_days: int = 90
    ) -> int:
        """
        Count old audit logs that could be archived/cleaned up.
        
        Args:
            older_than_days: Consider logs older than this many days
            
        Returns:
            Number of old logs found
        """
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

        # For safety, we'll just count for now rather than actually delete
        # In production, you might want to move to archive table first
        stmt = (
            select(func.count(AuditLog.id))
            .where(AuditLog.timestamp < cutoff_date)
        )

        result = await self.session.execute(stmt)
        old_log_count = result.scalar_one() or 0

        logger.info(
            "Old audit logs cleanup check",
            extra={
                "cutoff_date": cutoff_date,
                "old_logs_found": old_log_count,
                "older_than_days": older_than_days
            }
        )

        return old_log_count
