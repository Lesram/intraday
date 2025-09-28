"""
Module 78: Audit Service
Comprehensive audit logging and trail management for compliance and security.
"""

import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
import hashlib
import uuid
import logging
from pathlib import Path
import gzip
import os

# Configure logging
logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATION = "user_creation"
    USER_MODIFICATION = "user_modification"
    USER_DELETION = "user_deletion"
    
    TRADE_EXECUTION = "trade_execution"
    TRADE_MODIFICATION = "trade_modification"
    TRADE_CANCELLATION = "trade_cancellation"
    
    POSITION_CHANGE = "position_change"
    PORTFOLIO_UPDATE = "portfolio_update"
    
    RISK_LIMIT_BREACH = "risk_limit_breach"
    RISK_OVERRIDE = "risk_override"
    
    CONFIGURATION_CHANGE = "configuration_change"
    SYSTEM_START = "system_start"
    SYSTEM_SHUTDOWN = "system_shutdown"
    
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    
    COMPLIANCE_VIOLATION = "compliance_violation"
    COMPLIANCE_REMEDIATION = "compliance_remediation"
    
    AUTHORIZATION_FAILURE = "authorization_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    
    API_ACCESS = "api_access"
    ADMIN_ACTION = "admin_action"
    
    ERROR_OCCURRED = "error_occurred"
    SECURITY_INCIDENT = "security_incident"


class AuditEventSeverity(Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEventOutcome(Enum):
    """Outcomes of audit events."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    user_id: Optional[str]
    session_id: Optional[str]
    source_ip: Optional[str]
    user_agent: Optional[str]
    resource: str
    action: str
    outcome: AuditEventOutcome
    severity: AuditEventSeverity
    details: Dict[str, Any] = field(default_factory=dict)
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    risk_score: float = 0.0
    compliance_relevant: bool = False
    retention_period_days: int = 2555  # 7 years default
    
    def __post_init__(self):
        """Post-initialization processing."""
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)
        if not self.timestamp.tzinfo:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)


@dataclass
class AuditQuery:
    """Audit trail query parameters."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_types: Optional[List[AuditEventType]] = None
    user_ids: Optional[List[str]] = None
    resources: Optional[List[str]] = None
    severities: Optional[List[AuditEventSeverity]] = None
    outcomes: Optional[List[AuditEventOutcome]] = None
    compliance_only: bool = False
    limit: int = 1000
    offset: int = 0
    include_details: bool = True


@dataclass
class AuditReport:
    """Audit report data structure."""
    report_id: str
    query: AuditQuery
    events: List[AuditEvent]
    total_events: int
    summary: Dict[str, Any]
    generated_at: datetime
    generated_by: str


class AuditStorage(ABC):
    """Abstract base class for audit storage backends."""
    
    @abstractmethod
    async def store_event(self, event: AuditEvent) -> bool:
        """Store an audit event."""
        pass
    
    @abstractmethod
    async def query_events(self, query: AuditQuery) -> List[AuditEvent]:
        """Query audit events."""
        pass
    
    @abstractmethod
    async def count_events(self, query: AuditQuery) -> int:
        """Count events matching query."""
        pass
    
    @abstractmethod
    async def delete_expired_events(self, before_date: datetime) -> int:
        """Delete expired events."""
        pass


class FileAuditStorage(AuditStorage):
    """File-based audit storage implementation."""
    
    def __init__(self, storage_path: str = "logs/audit"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._events_cache: List[AuditEvent] = []
        self._cache_limit = 10000
    
    def _get_file_path(self, date: datetime) -> Path:
        """Get file path for a specific date."""
        return self.storage_path / f"audit_{date.strftime('%Y_%m_%d')}.json"
    
    async def store_event(self, event: AuditEvent) -> bool:
        """Store an audit event to file."""
        try:
            file_path = self._get_file_path(event.timestamp)
            
            # Convert event to dict with enum serialization
            event_dict = asdict(event)
            
            # Convert enums to their values for JSON serialization
            event_dict['event_type'] = event.event_type.value
            event_dict['outcome'] = event.outcome.value
            event_dict['severity'] = event.severity.value
            event_dict['timestamp'] = event.timestamp.isoformat()
            
            # Append to file
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event_dict) + '\n')
            
            # Add to cache
            self._events_cache.append(event)
            if len(self._events_cache) > self._cache_limit:
                self._events_cache = self._events_cache[-self._cache_limit:]
            
            return True
        except Exception as e:
            logger.error(f"Failed to store audit event: {e}")
            return False
    
    async def query_events(self, query: AuditQuery) -> List[AuditEvent]:
        """Query audit events from files."""
        events = []
        
        # Determine date range
        start_date = query.start_time or datetime.now(timezone.utc) - timedelta(days=30)
        end_date = query.end_time or datetime.now(timezone.utc)
        
        current_date = start_date.date()
        while current_date <= end_date.date():
            file_path = self._get_file_path(datetime.combine(current_date, datetime.min.time()))
            
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                event_dict = json.loads(line.strip())
                                
                                # Convert enum values back to enums
                                if 'event_type' in event_dict:
                                    event_dict['event_type'] = AuditEventType(event_dict['event_type'])
                                if 'outcome' in event_dict:
                                    event_dict['outcome'] = AuditEventOutcome(event_dict['outcome'])
                                if 'severity' in event_dict:
                                    event_dict['severity'] = AuditEventSeverity(event_dict['severity'])
                                
                                event = AuditEvent(**event_dict)
                                
                                if self._matches_query(event, query):
                                    events.append(event)
                except Exception as e:
                    logger.error(f"Error reading audit file {file_path}: {e}")
            
            current_date += timedelta(days=1)
        
        # Sort by timestamp and apply limit/offset
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[query.offset:query.offset + query.limit]
    
    def _matches_query(self, event: AuditEvent, query: AuditQuery) -> bool:
        """Check if event matches query criteria."""
        if query.start_time and event.timestamp < query.start_time:
            return False
        if query.end_time and event.timestamp > query.end_time:
            return False
        if query.event_types and event.event_type not in query.event_types:
            return False
        if query.user_ids and event.user_id not in query.user_ids:
            return False
        if query.resources and event.resource not in query.resources:
            return False
        if query.severities and event.severity not in query.severities:
            return False
        if query.outcomes and event.outcome not in query.outcomes:
            return False
        if query.compliance_only and not event.compliance_relevant:
            return False
        
        return True
    
    async def count_events(self, query: AuditQuery) -> int:
        """Count events matching query."""
        events = await self.query_events(query)
        return len(events)
    
    async def delete_expired_events(self, before_date: datetime) -> int:
        """Delete expired events."""
        deleted_count = 0
        
        # Find files older than before_date
        for file_path in self.storage_path.glob("audit_*.json"):
            try:
                # Extract date from filename
                date_str = file_path.stem.replace("audit_", "")
                file_date = datetime.strptime(date_str, "%Y_%m_%d")
                
                if file_date.date() < before_date.date():
                    # Count events in file before deletion
                    if file_path.exists():
                        with open(file_path, 'r', encoding='utf-8') as f:
                            deleted_count += sum(1 for line in f if line.strip())
                    
                    # Delete file
                    file_path.unlink()
                    
            except Exception as e:
                logger.error(f"Error processing audit file {file_path}: {e}")
        
        return deleted_count


class AuditService:
    """Comprehensive audit service for logging and trail management."""
    
    def __init__(self, storage: Optional[AuditStorage] = None):
        self.storage = storage or FileAuditStorage()
        self._event_buffer: List[AuditEvent] = []
        self._buffer_size = 100
        self._flush_interval = 30  # seconds
        self._last_flush = datetime.now(timezone.utc)
        self._risk_rules: Dict[str, float] = self._load_risk_rules()
        self._compliance_rules: Set[AuditEventType] = self._load_compliance_rules()
    
    def _load_risk_rules(self) -> Dict[str, float]:
        """Load risk scoring rules."""
        return {
            "failed_login": 2.0,
            "admin_action": 3.0,
            "risk_override": 4.0,
            "security_incident": 8.0,
            "compliance_violation": 6.0,
            "unauthorized_access": 7.0,
            "data_deletion": 5.0,
            "configuration_change": 3.0
        }
    
    def _load_compliance_rules(self) -> Set[AuditEventType]:
        """Load compliance-relevant event types."""
        return {
            AuditEventType.TRADE_EXECUTION,
            AuditEventType.TRADE_MODIFICATION,
            AuditEventType.TRADE_CANCELLATION,
            AuditEventType.POSITION_CHANGE,
            AuditEventType.RISK_LIMIT_BREACH,
            AuditEventType.RISK_OVERRIDE,
            AuditEventType.COMPLIANCE_VIOLATION,
            AuditEventType.COMPLIANCE_REMEDIATION,
            AuditEventType.DATA_DELETION,
            AuditEventType.DATA_EXPORT,
            AuditEventType.ADMIN_ACTION
        }
    
    def _calculate_risk_score(self, event: AuditEvent) -> float:
        """Calculate risk score for an event."""
        base_score = 0.0
        
        # Event type based scoring
        for rule, score in self._risk_rules.items():
            if rule in event.action.lower() or rule in event.event_type.value:
                base_score += score
        
        # Outcome based scoring
        if event.outcome == AuditEventOutcome.FAILURE:
            base_score += 2.0
        elif event.outcome == AuditEventOutcome.PARTIAL:
            base_score += 1.0
        
        # Severity based scoring
        severity_multiplier = {
            AuditEventSeverity.INFO: 1.0,
            AuditEventSeverity.WARNING: 1.5,
            AuditEventSeverity.ERROR: 2.0,
            AuditEventSeverity.CRITICAL: 3.0
        }
        
        base_score *= severity_multiplier.get(event.severity, 1.0)
        
        # Time-based scoring (higher for off-hours)
        hour = event.timestamp.hour
        if hour < 6 or hour > 22:  # Off-hours
            base_score *= 1.2
        
        return min(base_score, 10.0)  # Cap at 10
    
    def _is_compliance_relevant(self, event: AuditEvent) -> bool:
        """Determine if event is compliance relevant."""
        return event.event_type in self._compliance_rules
    
    async def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str],
        resource: str,
        action: str,
        outcome: AuditEventOutcome,
        severity: AuditEventSeverity = AuditEventSeverity.INFO,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log an audit event."""
        
        event_id = str(uuid.uuid4())
        
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            resource=resource,
            action=action,
            outcome=outcome,
            severity=severity,
            details=details or {},
            before_state=before_state,
            after_state=after_state
        )
        
        # Calculate risk score and compliance relevance
        event.risk_score = self._calculate_risk_score(event)
        event.compliance_relevant = self._is_compliance_relevant(event)
        
        # Add to buffer
        self._event_buffer.append(event)
        
        # Auto-flush if buffer is full
        if len(self._event_buffer) >= self._buffer_size:
            await self.flush_events()
        
        # Auto-flush if interval exceeded
        elif (datetime.now(timezone.utc) - self._last_flush).seconds >= self._flush_interval:
            await self.flush_events()
        
        return event_id
    
    async def flush_events(self) -> bool:
        """Flush buffered events to storage."""
        if not self._event_buffer:
            return True
        
        try:
            for event in self._event_buffer:
                await self.storage.store_event(event)
            
            self._event_buffer.clear()
            self._last_flush = datetime.now(timezone.utc)
            return True
            
        except Exception as e:
            logger.error(f"Failed to flush audit events: {e}")
            return False
    
    async def query_trail(self, query: AuditQuery) -> List[AuditEvent]:
        """Query the audit trail."""
        # Ensure any buffered events are flushed
        await self.flush_events()
        
        return await self.storage.query_events(query)
    
    async def count_events(self, query: AuditQuery) -> int:
        """Count events matching query."""
        return await self.storage.count_events(query)
    
    async def generate_report(
        self,
        query: AuditQuery,
        generated_by: str,
        include_summary: bool = True
    ) -> AuditReport:
        """Generate an audit report."""
        
        events = await self.query_trail(query)
        total_events = await self.count_events(query)
        
        summary = {}
        if include_summary:
            summary = self._generate_summary(events)
        
        return AuditReport(
            report_id=str(uuid.uuid4()),
            query=query,
            events=events,
            total_events=total_events,
            summary=summary,
            generated_at=datetime.now(timezone.utc),
            generated_by=generated_by
        )
    
    def _generate_summary(self, events: List[AuditEvent]) -> Dict[str, Any]:
        """Generate summary statistics for events."""
        if not events:
            return {"total": 0}
        
        # Count by event type
        event_types = {}
        for event in events:
            event_types[event.event_type.value] = event_types.get(event.event_type.value, 0) + 1
        
        # Count by outcome
        outcomes = {}
        for event in events:
            outcomes[event.outcome.value] = outcomes.get(event.outcome.value, 0) + 1
        
        # Count by severity
        severities = {}
        for event in events:
            severities[event.severity.value] = severities.get(event.severity.value, 0) + 1
        
        # Count by user
        users = {}
        for event in events:
            if event.user_id:
                users[event.user_id] = users.get(event.user_id, 0) + 1
        
        # Risk metrics
        risk_scores = [event.risk_score for event in events]
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
        high_risk_events = len([e for e in events if e.risk_score > 5.0])
        
        # Compliance metrics
        compliance_events = len([e for e in events if e.compliance_relevant])
        
        return {
            "total": len(events),
            "event_types": event_types,
            "outcomes": outcomes,
            "severities": severities,
            "top_users": dict(sorted(users.items(), key=lambda x: x[1], reverse=True)[:10]),
            "average_risk_score": round(avg_risk, 2),
            "high_risk_events": high_risk_events,
            "compliance_events": compliance_events,
            "time_range": {
                "start": min(events, key=lambda e: e.timestamp).timestamp.isoformat(),
                "end": max(events, key=lambda e: e.timestamp).timestamp.isoformat()
            }
        }
    
    async def get_user_activity(
        self,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get audit trail for a specific user."""
        
        query = AuditQuery(
            start_time=start_time or datetime.now(timezone.utc) - timedelta(days=30),
            end_time=end_time or datetime.now(timezone.utc),
            user_ids=[user_id],
            limit=limit
        )
        
        return await self.query_trail(query)
    
    async def get_resource_activity(
        self,
        resource: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get audit trail for a specific resource."""
        
        query = AuditQuery(
            start_time=start_time or datetime.now(timezone.utc) - timedelta(days=30),
            end_time=end_time or datetime.now(timezone.utc),
            resources=[resource],
            limit=limit
        )
        
        return await self.query_trail(query)
    
    async def get_compliance_trail(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[AuditEvent]:
        """Get compliance-relevant audit trail."""
        
        query = AuditQuery(
            start_time=start_time or datetime.now(timezone.utc) - timedelta(days=90),
            end_time=end_time or datetime.now(timezone.utc),
            compliance_only=True,
            limit=limit
        )
        
        return await self.query_trail(query)
    
    async def get_security_incidents(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        min_risk_score: float = 5.0,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Get high-risk security incidents."""
        
        query = AuditQuery(
            start_time=start_time or datetime.now(timezone.utc) - timedelta(days=7),
            end_time=end_time or datetime.now(timezone.utc),
            event_types=[
                AuditEventType.AUTHORIZATION_FAILURE,
                AuditEventType.AUTHENTICATION_FAILURE,
                AuditEventType.SECURITY_INCIDENT
            ],
            limit=limit
        )
        
        events = await self.query_trail(query)
        return [e for e in events if e.risk_score >= min_risk_score]
    
    async def cleanup_expired_events(self, retention_days: int = 2555) -> int:
        """Clean up expired audit events."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        return await self.storage.delete_expired_events(cutoff_date)
    
    async def verify_integrity(self, events: List[AuditEvent]) -> Dict[str, Any]:
        """Verify audit trail integrity."""
        
        if not events:
            return {"status": "valid", "issues": [], "total_events": 0}
        
        issues = []
        
        # Check chronological order
        for i in range(1, len(events)):
            if events[i-1].timestamp > events[i].timestamp:
                issues.append(f"Chronological order violation at index {i}")
        
        # Check for duplicate event IDs
        event_ids = [e.event_id for e in events]
        if len(event_ids) != len(set(event_ids)):
            issues.append("Duplicate event IDs found")
        
        # Check for gaps in timeline (>1 hour without events)
        if len(events) > 1:
            for i in range(1, len(events)):
                time_gap = (events[i-1].timestamp - events[i].timestamp).total_seconds()
                if time_gap > 3600:  # 1 hour
                    issues.append(f"Large time gap detected: {time_gap/3600:.1f} hours")
        
        return {
            "status": "valid" if not issues else "issues_found",
            "total_events": len(events),
            "issues": issues,
            "time_span": {
                "start": events[-1].timestamp.isoformat() if events else None,
                "end": events[0].timestamp.isoformat() if events else None
            }
        }


# Global audit service instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


# Convenience functions
async def log_audit_event(
    event_type: AuditEventType,
    user_id: Optional[str],
    resource: str,
    action: str,
    outcome: AuditEventOutcome,
    **kwargs
) -> str:
    """Convenience function to log an audit event."""
    service = get_audit_service()
    return await service.log_event(event_type, user_id, resource, action, outcome, **kwargs)


async def query_audit_trail(query: AuditQuery) -> List[AuditEvent]:
    """Convenience function to query audit trail."""
    service = get_audit_service()
    return await service.query_trail(query)


async def generate_audit_report(query: AuditQuery, generated_by: str) -> AuditReport:
    """Convenience function to generate audit report."""
    service = get_audit_service()
    return await service.generate_report(query, generated_by)


# Exception classes
class AuditError(Exception):
    """Base audit service exception."""
    pass


class AuditStorageError(AuditError):
    """Audit storage exception."""
    pass


class AuditQueryError(AuditError):
    """Audit query exception."""
    pass