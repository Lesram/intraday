"""
Tests for Module 81: Data Synchronization Service
Tests for real-time data sync, conflict resolution, consistency management, distributed synchronization, change tracking.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
import uuid

from backend.services.data_synchronization import (
    DataSynchronizationService,
    SyncRecord,
    SyncConflict,
    SyncEvent,
    SyncSession,
    SyncProvider,
    LocalSyncProvider,
    ConflictResolver,
    SyncOperation,
    SyncStatus,
    ConflictResolutionStrategy,
    SyncDirection,
    get_sync_service,
    sync_data,
    resolve_sync_conflict,
    get_sync_status
)


@pytest.fixture
def sync_service():
    """Create data synchronization service for testing."""
    return DataSynchronizationService()


@pytest.fixture
def sample_sync_record():
    """Create sample sync record for testing."""
    return SyncRecord(
        id="test-record-1",
        entity_type="user",
        entity_id="user-123",
        data={"name": "Test User", "email": "test@example.com"},
        version=1,
        timestamp=datetime.now(timezone.utc),
        checksum=""
    )


@pytest.fixture
def mock_sync_provider():
    """Create mock sync provider for testing."""
    provider = Mock(spec=SyncProvider)
    provider.get_records = AsyncMock(return_value=[])
    provider.push_record = AsyncMock(return_value=True)
    provider.delete_record = AsyncMock(return_value=True)
    provider.get_record = AsyncMock(return_value=None)
    return provider


class TestSyncRecord:
    """Test SyncRecord class."""
    
    def test_sync_record_creation(self, sample_sync_record):
        """Test sync record creation."""
        assert sample_sync_record.id == "test-record-1"
        assert sample_sync_record.entity_type == "user"
        assert sample_sync_record.entity_id == "user-123"
        assert sample_sync_record.data["name"] == "Test User"
        assert sample_sync_record.version == 1
        assert sample_sync_record.checksum != ""
    
    def test_checksum_calculation(self, sample_sync_record):
        """Test checksum calculation."""
        # Create another record with same data
        record2 = SyncRecord(
            id="test-record-2",
            entity_type="user",
            entity_id="user-123",
            data={"name": "Test User", "email": "test@example.com"},
            version=1,
            timestamp=sample_sync_record.timestamp,
            checksum=""
        )
        
        # Same data should produce same checksum
        assert sample_sync_record.checksum == record2.checksum
    
    def test_timestamp_conversion(self):
        """Test timestamp string conversion."""
        timestamp_str = "2023-01-01T12:00:00Z"
        record = SyncRecord(
            id="test",
            entity_type="test",
            entity_id="test",
            data={},
            version=1,
            timestamp=timestamp_str,
            checksum=""
        )
        
        assert isinstance(record.timestamp, datetime)


class TestLocalSyncProvider:
    """Test LocalSyncProvider class."""
    
    def test_local_provider_initialization(self):
        """Test local provider initialization."""
        provider = LocalSyncProvider()
        assert provider.records == {}
    
    @pytest.mark.asyncio
    async def test_push_and_get_record(self, sample_sync_record):
        """Test pushing and getting records."""
        provider = LocalSyncProvider()
        
        # Push record
        result = await provider.push_record(sample_sync_record)
        assert result is True
        
        # Get record
        retrieved = await provider.get_record(
            sample_sync_record.entity_type,
            sample_sync_record.entity_id
        )
        assert retrieved is not None
        assert retrieved.id == sample_sync_record.id
    
    @pytest.mark.asyncio
    async def test_get_records_with_filter(self, sample_sync_record):
        """Test getting records with time filter."""
        provider = LocalSyncProvider()
        
        # Push record
        await provider.push_record(sample_sync_record)
        
        # Get all records
        all_records = await provider.get_records(sample_sync_record.entity_type)
        assert len(all_records) == 1
        
        # Get records since future date (should be empty)
        future_date = datetime.now(timezone.utc) + timedelta(hours=1)
        recent_records = await provider.get_records(
            sample_sync_record.entity_type,
            since=future_date
        )
        assert len(recent_records) == 0
    
    @pytest.mark.asyncio
    async def test_delete_record(self, sample_sync_record):
        """Test deleting records."""
        provider = LocalSyncProvider()
        
        # Push record
        await provider.push_record(sample_sync_record)
        
        # Delete record
        result = await provider.delete_record(
            sample_sync_record.entity_type,
            sample_sync_record.entity_id
        )
        assert result is True
        
        # Verify record is gone
        retrieved = await provider.get_record(
            sample_sync_record.entity_type,
            sample_sync_record.entity_id
        )
        assert retrieved is None


class TestConflictResolver:
    """Test ConflictResolver class."""
    
    def create_conflict(self):
        """Create test conflict."""
        local_record = SyncRecord(
            id="local-1",
            entity_type="user",
            entity_id="user-123",
            data={"name": "Local User", "email": "local@example.com"},
            version=1,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
            checksum=""
        )
        
        remote_record = SyncRecord(
            id="remote-1",
            entity_type="user",
            entity_id="user-123",
            data={"name": "Remote User", "email": "remote@example.com"},
            version=2,
            timestamp=datetime.now(timezone.utc),
            checksum=""
        )
        
        return SyncConflict(
            id="conflict-1",
            entity_type="user",
            entity_id="user-123",
            local_record=local_record,
            remote_record=remote_record,
            conflict_type="version_conflict"
        )
    
    @pytest.mark.asyncio
    async def test_last_write_wins_strategy(self):
        """Test last write wins conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.LAST_WRITE_WINS
        )
        
        assert resolved is not None
        assert resolved.data["name"] == "Remote User"  # Remote is newer
    
    @pytest.mark.asyncio
    async def test_first_write_wins_strategy(self):
        """Test first write wins conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.FIRST_WRITE_WINS
        )
        
        assert resolved is not None
        assert resolved.data["name"] == "Local User"  # Local is older
    
    @pytest.mark.asyncio
    async def test_client_wins_strategy(self):
        """Test client wins conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.CLIENT_WINS
        )
        
        assert resolved is not None
        assert resolved.data["name"] == "Local User"  # Local is client
    
    @pytest.mark.asyncio
    async def test_server_wins_strategy(self):
        """Test server wins conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.SERVER_WINS
        )
        
        assert resolved is not None
        assert resolved.data["name"] == "Remote User"  # Remote is server
    
    @pytest.mark.asyncio
    async def test_merge_strategy(self):
        """Test merge conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.MERGE
        )
        
        assert resolved is not None
        assert resolved.version > max(conflict.local_record.version, conflict.remote_record.version)
    
    @pytest.mark.asyncio
    async def test_manual_strategy(self):
        """Test manual conflict resolution."""
        conflict = self.create_conflict()
        
        resolved = await ConflictResolver.resolve_conflict(
            conflict,
            ConflictResolutionStrategy.MANUAL
        )
        
        assert resolved is None  # Manual resolution returns None


class TestDataSynchronizationService:
    """Test DataSynchronizationService class."""
    
    def test_service_initialization(self, sync_service):
        """Test service initialization."""
        assert sync_service.providers is not None
        assert "local" in sync_service.providers
        assert sync_service.sessions == {}
        assert sync_service.conflicts == {}
        assert sync_service.sync_rules == {}
    
    def test_provider_registration(self, sync_service, mock_sync_provider):
        """Test provider registration and unregistration."""
        # Register provider
        result = sync_service.register_provider("test", mock_sync_provider)
        assert result is True
        assert "test" in sync_service.providers
        
        # Unregister provider
        result = sync_service.unregister_provider("test")
        assert result is True
        assert "test" not in sync_service.providers
        
        # Cannot unregister local provider
        result = sync_service.unregister_provider("local")
        assert result is False
    
    def test_sync_rule_management(self, sync_service):
        """Test adding and removing sync rules."""
        # Add sync rule
        result = sync_service.add_sync_rule(
            "user",
            direction=SyncDirection.BIDIRECTIONAL,
            conflict_strategy=ConflictResolutionStrategy.LAST_WRITE_WINS
        )
        assert result is True
        assert "user" in sync_service.sync_rules
        
        # Remove sync rule
        result = sync_service.remove_sync_rule("user")
        assert result is True
        assert "user" not in sync_service.sync_rules
    
    @pytest.mark.asyncio
    async def test_start_sync_session(self, sync_service, mock_sync_provider):
        """Test starting synchronization session."""
        # Register mock provider
        sync_service.register_provider("remote", mock_sync_provider)
        
        # Start sync session
        session_id = await sync_service.start_sync_session(
            entity_types=["user"],
            source_provider="local",
            target_provider="remote"
        )
        
        assert session_id is not None
        assert session_id in sync_service.sessions
        assert session_id in sync_service._running_sessions
        
        # Wait a bit for async execution
        await asyncio.sleep(0.1)
    
    def test_get_session(self, sync_service):
        """Test getting session information."""
        # Non-existent session
        session = sync_service.get_session("non-existent")
        assert session is None
        
        # Create a session manually for testing
        session = SyncSession(
            id="test-session",
            start_time=datetime.now(timezone.utc),
            entity_types=["user"]
        )
        sync_service.sessions["test-session"] = session
        
        # Get existing session
        retrieved = sync_service.get_session("test-session")
        assert retrieved is not None
        assert retrieved.id == "test-session"
    
    def test_get_sessions_with_filter(self, sync_service):
        """Test getting sessions with status filter."""
        # Create test sessions
        session1 = SyncSession(
            id="session-1",
            start_time=datetime.now(timezone.utc),
            entity_types=["user"],
            status=SyncStatus.COMPLETED
        )
        session2 = SyncSession(
            id="session-2",
            start_time=datetime.now(timezone.utc),
            entity_types=["order"],
            status=SyncStatus.FAILED
        )
        
        sync_service.sessions["session-1"] = session1
        sync_service.sessions["session-2"] = session2
        
        # Get all sessions
        all_sessions = sync_service.get_sessions()
        assert len(all_sessions) == 2
        
        # Get completed sessions only
        completed_sessions = sync_service.get_sessions(SyncStatus.COMPLETED)
        assert len(completed_sessions) == 1
        assert completed_sessions[0].id == "session-1"
    
    def test_get_conflicts(self, sync_service):
        """Test getting conflicts with filter."""
        # Create test conflicts
        conflict1 = SyncConflict(
            id="conflict-1",
            entity_type="user",
            entity_id="user-1",
            local_record=Mock(),
            remote_record=Mock(),
            conflict_type="version",
            resolved=True
        )
        conflict2 = SyncConflict(
            id="conflict-2",
            entity_type="user",
            entity_id="user-2",
            local_record=Mock(),
            remote_record=Mock(),
            conflict_type="version",
            resolved=False
        )
        
        sync_service.conflicts["conflict-1"] = conflict1
        sync_service.conflicts["conflict-2"] = conflict2
        
        # Get all conflicts
        all_conflicts = sync_service.get_conflicts()
        assert len(all_conflicts) == 2
        
        # Get unresolved conflicts only
        unresolved = sync_service.get_conflicts(resolved=False)
        assert len(unresolved) == 1
        assert unresolved[0].id == "conflict-2"
    
    def test_get_sync_status(self, sync_service):
        """Test getting synchronization status."""
        status = sync_service.get_sync_status()
        
        assert "active_sessions" in status
        assert "total_sessions" in status
        assert "unresolved_conflicts" in status
        assert "providers" in status
        assert "sync_rules" in status
        
        assert isinstance(status["active_sessions"], int)
        assert isinstance(status["total_sessions"], int)
        assert isinstance(status["unresolved_conflicts"], int)
        assert isinstance(status["providers"], list)
        assert isinstance(status["sync_rules"], list)
    
    @pytest.mark.asyncio
    async def test_event_handler_registration(self, sync_service):
        """Test event handler registration and triggering."""
        events_received = []
        
        def event_handler(data):
            events_received.append(data)
        
        # Register event handler
        result = sync_service.register_event_handler("test_event", event_handler)
        assert result is True
        
        # Trigger event
        await sync_service._trigger_event("test_event", {"test": "data"})
        
        assert len(events_received) == 1
        assert events_received[0]["test"] == "data"
    
    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, sync_service):
        """Test cleaning up old sessions."""
        # Create old session
        old_session = SyncSession(
            id="old-session",
            start_time=datetime.now(timezone.utc) - timedelta(days=35),
            end_time=datetime.now(timezone.utc) - timedelta(days=35),
            entity_types=["user"],
            status=SyncStatus.COMPLETED
        )
        
        # Create recent session
        recent_session = SyncSession(
            id="recent-session",
            start_time=datetime.now(timezone.utc) - timedelta(days=5),
            end_time=datetime.now(timezone.utc) - timedelta(days=5),
            entity_types=["user"],
            status=SyncStatus.COMPLETED
        )
        
        sync_service.sessions["old-session"] = old_session
        sync_service.sessions["recent-session"] = recent_session
        
        # Cleanup old sessions
        cleaned = await sync_service.cleanup_old_sessions(days=30)
        
        assert cleaned == 1
        assert "old-session" not in sync_service.sessions
        assert "recent-session" in sync_service.sessions


class TestSyncUtilities:
    """Test sync utility functions."""
    
    def test_get_sync_service_singleton(self):
        """Test getting global sync service."""
        service1 = get_sync_service()
        service2 = get_sync_service()
        
        assert service1 is service2  # Should be same instance
    
    def test_get_sync_status_convenience(self):
        """Test get sync status convenience function."""
        status = get_sync_status()
        
        assert isinstance(status, dict)
        assert "active_sessions" in status
    
    @pytest.mark.asyncio
    async def test_sync_data_convenience(self):
        """Test sync data convenience function."""
        with patch('backend.services.data_synchronization.get_sync_service') as mock_service:
            mock_instance = Mock()
            mock_instance.start_sync_session = AsyncMock(return_value="session-123")
            mock_service.return_value = mock_instance
            
            session_id = await sync_data(["user"])
            
            assert session_id == "session-123"
            mock_instance.start_sync_session.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resolve_sync_conflict_convenience(self):
        """Test resolve sync conflict convenience function."""
        with patch('backend.services.data_synchronization.get_sync_service') as mock_service:
            mock_instance = Mock()
            mock_instance.resolve_conflict = AsyncMock(return_value=True)
            mock_service.return_value = mock_instance
            
            result = await resolve_sync_conflict(
                "conflict-123",
                ConflictResolutionStrategy.LAST_WRITE_WINS
            )
            
            assert result is True
            mock_instance.resolve_conflict.assert_called_once()


class TestSyncEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_sync_with_invalid_provider(self, sync_service):
        """Test synchronization with invalid provider."""
        # Create a session first
        session = SyncSession(
            id="test-session",
            start_time=datetime.now(timezone.utc),
            entity_types=["user"]
        )
        sync_service.sessions["test-session"] = session
        
        # This should fail but not raise an exception since it's async
        await sync_service._execute_sync_session(
            "test-session",
            "invalid_source",
            "invalid_target",
            None
        )
        
        # Check that session was marked as failed
        assert session.status == SyncStatus.FAILED
    
    def test_provider_registration_error_handling(self, sync_service):
        """Test provider registration error handling."""
        # Test with None provider
        result = sync_service.register_provider("test", None)
        assert result is False
    
    def test_conflict_resolution_with_invalid_conflict(self, sync_service):
        """Test conflict resolution with invalid conflict ID."""
        result = asyncio.run(sync_service.resolve_conflict(
            "invalid-conflict",
            ConflictResolutionStrategy.LAST_WRITE_WINS
        ))
        assert result is False
    
    @pytest.mark.asyncio
    async def test_concurrent_sync_operations(self, sync_service, sample_sync_record):
        """Test concurrent synchronization operations."""
        provider = LocalSyncProvider()
        
        # Start multiple concurrent operations
        tasks = []
        for i in range(10):
            record = SyncRecord(
                id=f"record-{i}",
                entity_type="user",
                entity_id=f"user-{i}",
                data={"name": f"User {i}"},
                version=1,
                timestamp=datetime.now(timezone.utc),
                checksum=""
            )
            tasks.append(provider.push_record(record))
        
        results = await asyncio.gather(*tasks)
        assert all(results)  # All operations should succeed
        
        # Verify all records were stored
        all_records = await provider.get_records("user")
        assert len(all_records) == 10


class TestModule81BackendModule81:
    """Test module 81 integration and availability."""
    
    def test_module_availability(self):
        """Test that all required classes and functions are available."""
        # Test main classes
        assert DataSynchronizationService is not None
        assert SyncRecord is not None
        assert SyncConflict is not None
        assert LocalSyncProvider is not None
        assert ConflictResolver is not None
        
        # Test enums
        assert SyncOperation is not None
        assert SyncStatus is not None
        assert ConflictResolutionStrategy is not None
        assert SyncDirection is not None
        
        # Test utility functions
        assert get_sync_service is not None
        assert sync_data is not None
        assert resolve_sync_conflict is not None
        assert get_sync_status is not None
    
    def test_module_functionality(self):
        """Test basic module functionality."""
        service = DataSynchronizationService()
        assert service is not None
        
        # Test basic operations
        assert hasattr(service, 'register_provider')
        assert hasattr(service, 'start_sync_session')
        assert hasattr(service, 'resolve_conflict')
        assert hasattr(service, 'get_sync_status')
    
    def test_module_integration(self):
        """Test module integration with other components."""
        # Test that service can be instantiated and used
        service = get_sync_service()
        status = service.get_sync_status()
        
        assert isinstance(status, dict)
        assert "providers" in status
        assert "local" in status["providers"]
    
    @pytest.mark.asyncio
    async def test_full_sync_workflow(self):
        """Test complete synchronization workflow."""
        service = DataSynchronizationService()
        
        # Create test data
        record = SyncRecord(
            id="test-workflow",
            entity_type="test",
            entity_id="test-1",
            data={"test": "data"},
            version=1,
            timestamp=datetime.now(timezone.utc),
            checksum=""
        )
        
        # Add to local provider
        local_provider = service.providers["local"]
        await local_provider.push_record(record)
        
        # Verify record exists
        retrieved = await local_provider.get_record("test", "test-1")
        assert retrieved is not None
        assert retrieved.id == record.id
        
        # Test sync status
        status = service.get_sync_status()
        assert status["providers"] == ["local"]
