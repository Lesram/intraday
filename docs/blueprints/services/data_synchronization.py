"""
Module 81: Data Synchronization Service
Real-time data sync, conflict resolution, consistency management, distributed synchronization, change tracking.
"""

import asyncio
import json
import time
import threading
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union, Set, Callable, Type, Tuple
from enum import Enum
from pathlib import Path
import logging
import uuid
import copy

# Configure logging
logger = logging.getLogger(__name__)


class SyncOperation(Enum):
    """Types of synchronization operations."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"


class SyncStatus(Enum):
    """Status of synchronization operations."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class ConflictResolutionStrategy(Enum):
    """Strategies for resolving data conflicts."""
    LAST_WRITE_WINS = "last_write_wins"
    FIRST_WRITE_WINS = "first_write_wins"
    MANUAL = "manual"
    MERGE = "merge"
    CLIENT_WINS = "client_wins"
    SERVER_WINS = "server_wins"


class SyncDirection(Enum):
    """Direction of synchronization."""
    BIDIRECTIONAL = "bidirectional"
    PUSH_ONLY = "push_only"
    PULL_ONLY = "pull_only"


@dataclass
class SyncRecord:
    """Represents a data record for synchronization."""
    id: str
    entity_type: str
    entity_id: str
    data: Dict[str, Any]
    version: int
    timestamp: datetime
    checksum: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
        if not self.checksum:
            self.checksum = self.calculate_checksum()
    
    def calculate_checksum(self) -> str:
        """Calculate checksum for data integrity."""
        data_str = json.dumps(self.data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()


@dataclass
class SyncConflict:
    """Represents a synchronization conflict."""
    id: str
    entity_type: str
    entity_id: str
    local_record: SyncRecord
    remote_record: SyncRecord
    conflict_type: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolution_strategy: Optional[ConflictResolutionStrategy] = None
    resolved_data: Optional[Dict[str, Any]] = None


@dataclass
class SyncEvent:
    """Represents a synchronization event."""
    id: str
    operation: SyncOperation
    entity_type: str
    entity_id: str
    record: Optional[SyncRecord]
    status: SyncStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    retry_count: int = 0
    source: str = "local"
    target: str = "remote"


@dataclass
class SyncSession:
    """Represents a synchronization session."""
    id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: SyncStatus = SyncStatus.PENDING
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL
    entity_types: List[str] = field(default_factory=list)
    total_records: int = 0
    processed_records: int = 0
    conflicts: List[SyncConflict] = field(default_factory=list)
    events: List[SyncEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SyncProvider(ABC):
    """Abstract base class for synchronization providers."""
    
    @abstractmethod
    async def get_records(self, entity_type: str, since: Optional[datetime] = None) -> List[SyncRecord]:
        """Get records from the provider."""
        pass
    
    @abstractmethod
    async def push_record(self, record: SyncRecord) -> bool:
        """Push a record to the provider."""
        pass
    
    @abstractmethod
    async def delete_record(self, entity_type: str, entity_id: str) -> bool:
        """Delete a record from the provider."""
        pass
    
    @abstractmethod
    async def get_record(self, entity_type: str, entity_id: str) -> Optional[SyncRecord]:
        """Get a specific record from the provider."""
        pass


class LocalSyncProvider(SyncProvider):
    """Local synchronization provider using in-memory storage."""
    
    def __init__(self):
        self.records: Dict[str, Dict[str, SyncRecord]] = {}
        self._lock = threading.RLock()
    
    async def get_records(self, entity_type: str, since: Optional[datetime] = None) -> List[SyncRecord]:
        """Get records from local storage."""
        with self._lock:
            if entity_type not in self.records:
                return []
            
            records = list(self.records[entity_type].values())
            if since:
                records = [r for r in records if r.timestamp > since]
            
            return sorted(records, key=lambda x: x.timestamp)
    
    async def push_record(self, record: SyncRecord) -> bool:
        """Push a record to local storage."""
        try:
            with self._lock:
                if record.entity_type not in self.records:
                    self.records[record.entity_type] = {}
                
                self.records[record.entity_type][record.entity_id] = record
                return True
        except Exception as e:
            logger.error(f"Failed to push record: {e}")
            return False
    
    async def delete_record(self, entity_type: str, entity_id: str) -> bool:
        """Delete a record from local storage."""
        try:
            with self._lock:
                if entity_type in self.records and entity_id in self.records[entity_type]:
                    del self.records[entity_type][entity_id]
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to delete record: {e}")
            return False
    
    async def get_record(self, entity_type: str, entity_id: str) -> Optional[SyncRecord]:
        """Get a specific record from local storage."""
        with self._lock:
            if entity_type in self.records and entity_id in self.records[entity_type]:
                return self.records[entity_type][entity_id]
            return None


class ConflictResolver:
    """Handles conflict resolution during synchronization."""
    
    @staticmethod
    async def resolve_conflict(
        conflict: SyncConflict,
        strategy: ConflictResolutionStrategy
    ) -> Optional[SyncRecord]:
        """Resolve a synchronization conflict."""
        try:
            if strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
                if conflict.local_record.timestamp > conflict.remote_record.timestamp:
                    return conflict.local_record
                else:
                    return conflict.remote_record
            
            elif strategy == ConflictResolutionStrategy.FIRST_WRITE_WINS:
                if conflict.local_record.timestamp < conflict.remote_record.timestamp:
                    return conflict.local_record
                else:
                    return conflict.remote_record
            
            elif strategy == ConflictResolutionStrategy.CLIENT_WINS:
                return conflict.local_record
            
            elif strategy == ConflictResolutionStrategy.SERVER_WINS:
                return conflict.remote_record
            
            elif strategy == ConflictResolutionStrategy.MERGE:
                return await ConflictResolver._merge_records(
                    conflict.local_record,
                    conflict.remote_record
                )
            
            elif strategy == ConflictResolutionStrategy.MANUAL:
                # Return None to indicate manual resolution needed
                return None
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to resolve conflict: {e}")
            return None
    
    @staticmethod
    async def _merge_records(local: SyncRecord, remote: SyncRecord) -> SyncRecord:
        """Merge two conflicting records."""
        merged_data = copy.deepcopy(local.data)
        
        # Simple merge strategy: take newer fields
        for key, value in remote.data.items():
            if key not in merged_data:
                merged_data[key] = value
            elif isinstance(value, dict) and isinstance(merged_data[key], dict):
                merged_data[key].update(value)
            else:
                # Take the value from the record with later timestamp
                if remote.timestamp > local.timestamp:
                    merged_data[key] = value
        
        return SyncRecord(
            id=str(uuid.uuid4()),
            entity_type=local.entity_type,
            entity_id=local.entity_id,
            data=merged_data,
            version=max(local.version, remote.version) + 1,
            timestamp=datetime.now(timezone.utc),
            checksum=""
        )


class DataSynchronizationService:
    """Service for managing data synchronization between systems."""
    
    def __init__(self):
        self.providers: Dict[str, SyncProvider] = {}
        self.sessions: Dict[str, SyncSession] = {}
        self.conflicts: Dict[str, SyncConflict] = {}
        self.sync_rules: Dict[str, Dict[str, Any]] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
        self._running_sessions: Set[str] = set()
        
        # Initialize local provider
        self.providers["local"] = LocalSyncProvider()
    
    def register_provider(self, name: str, provider: SyncProvider) -> bool:
        """Register a synchronization provider."""
        try:
            if provider is None:
                logger.error(f"Cannot register None provider: {name}")
                return False
                
            with self._lock:
                self.providers[name] = provider
                logger.info(f"Registered sync provider: {name}")
                return True
        except Exception as e:
            logger.error(f"Failed to register provider {name}: {e}")
            return False
    
    def unregister_provider(self, name: str) -> bool:
        """Unregister a synchronization provider."""
        try:
            with self._lock:
                if name in self.providers and name != "local":
                    del self.providers[name]
                    logger.info(f"Unregistered sync provider: {name}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to unregister provider {name}: {e}")
            return False
    
    def add_sync_rule(
        self,
        entity_type: str,
        direction: SyncDirection = SyncDirection.BIDIRECTIONAL,
        conflict_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.LAST_WRITE_WINS,
        auto_sync: bool = False,
        sync_interval: int = 300,  # 5 minutes
        filters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add a synchronization rule for an entity type."""
        try:
            with self._lock:
                self.sync_rules[entity_type] = {
                    "direction": direction,
                    "conflict_strategy": conflict_strategy,
                    "auto_sync": auto_sync,
                    "sync_interval": sync_interval,
                    "filters": filters or {},
                    "last_sync": None
                }
                logger.info(f"Added sync rule for entity type: {entity_type}")
                return True
        except Exception as e:
            logger.error(f"Failed to add sync rule for {entity_type}: {e}")
            return False
    
    def remove_sync_rule(self, entity_type: str) -> bool:
        """Remove a synchronization rule."""
        try:
            with self._lock:
                if entity_type in self.sync_rules:
                    del self.sync_rules[entity_type]
                    logger.info(f"Removed sync rule for entity type: {entity_type}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to remove sync rule for {entity_type}: {e}")
            return False
    
    async def start_sync_session(
        self,
        entity_types: List[str],
        source_provider: str = "local",
        target_provider: str = "remote",
        direction: SyncDirection = SyncDirection.BIDIRECTIONAL,
        since: Optional[datetime] = None
    ) -> str:
        """Start a synchronization session."""
        session_id = str(uuid.uuid4())
        
        try:
            session = SyncSession(
                id=session_id,
                start_time=datetime.now(timezone.utc),
                direction=direction,
                entity_types=entity_types
            )
            
            with self._lock:
                self.sessions[session_id] = session
                self._running_sessions.add(session_id)
            
            # Start synchronization in background
            asyncio.create_task(self._execute_sync_session(
                session_id, source_provider, target_provider, since
            ))
            
            await self._trigger_event("session_started", {
                "session_id": session_id,
                "entity_types": entity_types
            })
            
            logger.info(f"Started sync session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to start sync session: {e}")
            if session_id in self.sessions:
                self.sessions[session_id].status = SyncStatus.FAILED
            raise
    
    async def _execute_sync_session(
        self,
        session_id: str,
        source_provider: str,
        target_provider: str,
        since: Optional[datetime]
    ):
        """Execute synchronization session."""
        session = None
        try:
            session = self.sessions[session_id]
            session.status = SyncStatus.IN_PROGRESS
            
            source = self.providers.get(source_provider)
            target = self.providers.get(target_provider)
            
            if not source or not target:
                raise ValueError("Invalid provider specified")
            
            for entity_type in session.entity_types:
                await self._sync_entity_type(
                    session, entity_type, source, target, since
                )
            
            session.status = SyncStatus.COMPLETED
            session.end_time = datetime.now(timezone.utc)
            
            await self._trigger_event("session_completed", {
                "session_id": session_id,
                "processed_records": session.processed_records,
                "conflicts": len(session.conflicts)
            })
            
        except Exception as e:
            logger.error(f"Sync session {session_id} failed: {e}")
            if session:
                session.status = SyncStatus.FAILED
                session.end_time = datetime.now(timezone.utc)
            
            await self._trigger_event("session_failed", {
                "session_id": session_id,
                "error": str(e)
            })
        
        finally:
            with self._lock:
                self._running_sessions.discard(session_id)
    
    async def _sync_entity_type(
        self,
        session: SyncSession,
        entity_type: str,
        source: SyncProvider,
        target: SyncProvider,
        since: Optional[datetime]
    ):
        """Synchronize a specific entity type."""
        try:
            # Get records from source
            source_records = await source.get_records(entity_type, since)
            
            for record in source_records:
                await self._sync_record(session, record, target)
                session.processed_records += 1
            
            session.total_records += len(source_records)
            
        except Exception as e:
            logger.error(f"Failed to sync entity type {entity_type}: {e}")
            raise
    
    async def _sync_record(
        self,
        session: SyncSession,
        record: SyncRecord,
        target: SyncProvider
    ):
        """Synchronize a single record."""
        try:
            # Check if record exists in target
            existing_record = await target.get_record(record.entity_type, record.entity_id)
            
            if existing_record:
                # Check for conflicts
                if self._has_conflict(record, existing_record):
                    conflict = SyncConflict(
                        id=str(uuid.uuid4()),
                        entity_type=record.entity_type,
                        entity_id=record.entity_id,
                        local_record=record,
                        remote_record=existing_record,
                        conflict_type="version_conflict"
                    )
                    
                    session.conflicts.append(conflict)
                    self.conflicts[conflict.id] = conflict
                    
                    # Try to resolve automatically
                    strategy = self._get_conflict_strategy(record.entity_type)
                    resolved_record = await ConflictResolver.resolve_conflict(
                        conflict, strategy
                    )
                    
                    if resolved_record:
                        await target.push_record(resolved_record)
                        conflict.resolved = True
                        conflict.resolution_strategy = strategy
                        conflict.resolved_data = resolved_record.data
                    
                    return
            
            # No conflict, push record
            await target.push_record(record)
            
            event = SyncEvent(
                id=str(uuid.uuid4()),
                operation=SyncOperation.UPDATE if existing_record else SyncOperation.CREATE,
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                record=record,
                status=SyncStatus.COMPLETED
            )
            
            session.events.append(event)
            
        except Exception as e:
            logger.error(f"Failed to sync record {record.id}: {e}")
            
            event = SyncEvent(
                id=str(uuid.uuid4()),
                operation=SyncOperation.UPDATE,
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                record=record,
                status=SyncStatus.FAILED,
                error_message=str(e)
            )
            
            session.events.append(event)
    
    def _has_conflict(self, local_record: SyncRecord, remote_record: SyncRecord) -> bool:
        """Check if two records have a conflict."""
        return (
            local_record.version != remote_record.version or
            local_record.checksum != remote_record.checksum
        )
    
    def _get_conflict_strategy(self, entity_type: str) -> ConflictResolutionStrategy:
        """Get conflict resolution strategy for entity type."""
        rule = self.sync_rules.get(entity_type, {})
        return rule.get("conflict_strategy", ConflictResolutionStrategy.LAST_WRITE_WINS)
    
    async def resolve_conflict(
        self,
        conflict_id: str,
        strategy: ConflictResolutionStrategy,
        custom_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Manually resolve a synchronization conflict."""
        try:
            if conflict_id not in self.conflicts:
                return False
            
            conflict = self.conflicts[conflict_id]
            
            if custom_data:
                # Use custom resolution data
                resolved_record = SyncRecord(
                    id=str(uuid.uuid4()),
                    entity_type=conflict.entity_type,
                    entity_id=conflict.entity_id,
                    data=custom_data,
                    version=max(conflict.local_record.version, conflict.remote_record.version) + 1,
                    timestamp=datetime.now(timezone.utc),
                    checksum=""
                )
            else:
                resolved_record = await ConflictResolver.resolve_conflict(conflict, strategy)
            
            if resolved_record:
                # Update in all providers
                for provider in self.providers.values():
                    await provider.push_record(resolved_record)
                
                conflict.resolved = True
                conflict.resolution_strategy = strategy
                conflict.resolved_data = resolved_record.data
                
                await self._trigger_event("conflict_resolved", {
                    "conflict_id": conflict_id,
                    "strategy": strategy.value
                })
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to resolve conflict {conflict_id}: {e}")
            return False
    
    def get_session(self, session_id: str) -> Optional[SyncSession]:
        """Get synchronization session by ID."""
        return self.sessions.get(session_id)
    
    def get_sessions(self, status: Optional[SyncStatus] = None) -> List[SyncSession]:
        """Get all synchronization sessions, optionally filtered by status."""
        sessions = list(self.sessions.values())
        if status:
            sessions = [s for s in sessions if s.status == status]
        return sorted(sessions, key=lambda x: x.start_time, reverse=True)
    
    def get_conflicts(self, resolved: Optional[bool] = None) -> List[SyncConflict]:
        """Get synchronization conflicts, optionally filtered by resolution status."""
        conflicts = list(self.conflicts.values())
        if resolved is not None:
            conflicts = [c for c in conflicts if c.resolved == resolved]
        return sorted(conflicts, key=lambda x: x.timestamp, reverse=True)
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get overall synchronization status."""
        active_sessions = len(self._running_sessions)
        total_sessions = len(self.sessions)
        unresolved_conflicts = len([c for c in self.conflicts.values() if not c.resolved])
        
        return {
            "active_sessions": active_sessions,
            "total_sessions": total_sessions,
            "unresolved_conflicts": unresolved_conflicts,
            "providers": list(self.providers.keys()),
            "sync_rules": list(self.sync_rules.keys())
        }
    
    def register_event_handler(self, event_type: str, handler: Callable) -> bool:
        """Register an event handler."""
        try:
            with self._lock:
                if event_type not in self.event_handlers:
                    self.event_handlers[event_type] = []
                self.event_handlers[event_type].append(handler)
                return True
        except Exception as e:
            logger.error(f"Failed to register event handler: {e}")
            return False
    
    async def _trigger_event(self, event_type: str, data: Dict[str, Any]):
        """Trigger event handlers."""
        try:
            handlers = self.event_handlers.get(event_type, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Event handler failed for {event_type}: {e}")
        except Exception as e:
            logger.error(f"Failed to trigger event {event_type}: {e}")
    
    async def cleanup_old_sessions(self, days: int = 30) -> int:
        """Clean up old synchronization sessions."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            cleaned = 0
            
            with self._lock:
                sessions_to_remove = [
                    session_id for session_id, session in self.sessions.items()
                    if session.end_time and session.end_time < cutoff_date
                    and session_id not in self._running_sessions
                ]
                
                for session_id in sessions_to_remove:
                    del self.sessions[session_id]
                    cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} old sync sessions")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {e}")
            return 0


# Global instance
_sync_service = None


def get_sync_service() -> DataSynchronizationService:
    """Get global synchronization service instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = DataSynchronizationService()
    return _sync_service


# Convenience functions
async def sync_data(
    entity_types: List[str],
    source_provider: str = "local",
    target_provider: str = "remote",
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL
) -> str:
    """Convenience function to start data synchronization."""
    return await get_sync_service().start_sync_session(
        entity_types, source_provider, target_provider, direction
    )


async def resolve_sync_conflict(
    conflict_id: str,
    strategy: ConflictResolutionStrategy
) -> bool:
    """Convenience function to resolve sync conflict."""
    return await get_sync_service().resolve_conflict(conflict_id, strategy)


def get_sync_status() -> Dict[str, Any]:
    """Convenience function to get synchronization status."""
    return get_sync_service().get_sync_status()