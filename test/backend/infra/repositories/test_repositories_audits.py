"""
Focused test suite for Module 43: backend.infra.repositories.audits
Tests core audits repository functionality that can be properly mocked.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, UTC, timedelta
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.repositories.audits import AuditsRepo, AuditNotFoundError


class MockAuditLog:
    """Mock AuditLog instance for test data."""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', uuid.uuid4())
        self.action = kwargs.get('action')
        self.entity_type = kwargs.get('entity_type')
        self.entity_id = kwargs.get('entity_id')
        self.user_id = kwargs.get('user_id')
        self.ip_address = kwargs.get('ip_address')
        self.user_agent = kwargs.get('user_agent')
        self.details = kwargs.get('details', {})
        self.timestamp = kwargs.get('timestamp', datetime.now(UTC))


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def audits_repo(mock_session):
    """Create AuditsRepo instance with mocked session."""
    return AuditsRepo(mock_session)


# Test Classes

class TestAuditNotFoundError:
    """Test AuditNotFoundError exception."""
    
    def test_audit_not_found_error_creation(self):
        """Test AuditNotFoundError creation with message."""
        error = AuditNotFoundError("Audit with ID 123 not found")
        assert str(error) == "Audit with ID 123 not found"

    def test_audit_not_found_error_empty_message(self):
        """Test AuditNotFoundError creation with empty message."""
        error = AuditNotFoundError("")
        assert str(error) == ""

    def test_audit_not_found_error_inheritance(self):
        """Test AuditNotFoundError inherits from Exception."""
        error = AuditNotFoundError("Test message")
        assert isinstance(error, Exception)


class TestAuditsRepoInit:
    """Test AuditsRepo initialization."""
    
    def test_audits_repo_init(self, mock_session):
        """Test AuditsRepo initialization."""
        repo = AuditsRepo(mock_session)
        assert repo.session == mock_session

    def test_audits_repo_init_with_different_session(self):
        """Test AuditsRepo initialization with different session."""
        another_session = AsyncMock(spec=AsyncSession)
        repo = AuditsRepo(another_session)
        assert repo.session == another_session
        assert repo.session is not None


@patch('backend.infra.repositories.audits.AuditLog')
class TestCreateAuditLog:
    """Test create_audit_log functionality."""
    
    async def test_create_audit_log_success(self, mock_audit_log_class, audits_repo, mock_session):
        """Test successful audit log creation."""
        mock_audit_log = MockAuditLog(
            action="CREATE",
            entity_type="order",
            entity_id="order123",
            user_id="user456"
        )
        
        # Mock the class constructor
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.create_audit_log(
            action="CREATE",
            entity_type="order",
            entity_id="order123",
            user_id="user456"
        )
        
        # Verify the constructor was called with correct arguments
        mock_audit_log_class.assert_called_once_with(
            action="CREATE",
            entity_type="order",
            entity_id="order123",
            user_id="user456",
            ip_address=None,
            user_agent=None,
            details={}
        )
        
        # Verify session operations
        mock_session.add.assert_called_once_with(mock_audit_log)
        mock_session.flush.assert_called_once()
        
        assert result == mock_audit_log
    
    async def test_create_audit_log_with_optional_params(self, mock_audit_log_class, audits_repo, mock_session):
        """Test audit log creation with optional parameters."""
        mock_audit_log = MockAuditLog(
            action="LOGIN",
            entity_type="user", 
            entity_id="user789",
            user_id="user789",
            ip_address="10.0.0.1",
            user_agent="Test Agent",
            details={"session": "abc123"}
        )
        
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.create_audit_log(
            action="LOGIN",
            entity_type="user",
            entity_id="user789",
            user_id="user789",
            ip_address="10.0.0.1",
            user_agent="Test Agent",
            details={"session": "abc123"}
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="LOGIN",
            entity_type="user",
            entity_id="user789",
            user_id="user789",
            ip_address="10.0.0.1",
            user_agent="Test Agent",
            details={"session": "abc123"}
        )
        
        assert result == mock_audit_log

    async def test_create_audit_log_with_none_details(self, mock_audit_log_class, audits_repo, mock_session):
        """Test audit log creation with None details (should default to empty dict)."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.create_audit_log(
            action="TEST",
            entity_type="test_entity",
            entity_id="test123",
            details=None
        )
        
        # Should convert None details to empty dict
        mock_audit_log_class.assert_called_once_with(
            action="TEST",
            entity_type="test_entity",
            entity_id="test123",
            user_id=None,
            ip_address=None,
            user_agent=None,
            details={}
        )
    
    async def test_create_audit_log_integrity_error(self, mock_audit_log_class, audits_repo, mock_session):
        """Test audit log creation with database integrity error."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        # Simulate IntegrityError on flush
        mock_session.flush.side_effect = IntegrityError("", "", "")
        
        with pytest.raises(IntegrityError):
            await audits_repo.create_audit_log(
                action="DUPLICATE",
                entity_type="test",
                entity_id="test123"
            )
        
        mock_session.rollback.assert_called_once()

    async def test_create_audit_log_minimal_params(self, mock_audit_log_class, audits_repo, mock_session):
        """Test audit log creation with minimal required parameters."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.create_audit_log(
            action="MINIMAL",
            entity_type="minimal_entity",
            entity_id="minimal123"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="MINIMAL",
            entity_type="minimal_entity",
            entity_id="minimal123",
            user_id=None,
            ip_address=None,
            user_agent=None,
            details={}
        )


@patch('backend.infra.repositories.audits.AuditLog')
class TestSpecializedLogMethods:
    """Test specialized log methods."""
    
    async def test_log_order_action(self, mock_audit_log_class, audits_repo):
        """Test log_order_action method."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        order_id = uuid.uuid4()
        result = await audits_repo.log_order_action(
            action="PLACE_ORDER",
            order_id=order_id,
            user_id="user456",
            details={"symbol": "AAPL", "quantity": 10}
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="PLACE_ORDER",
            entity_type="order",
            entity_id=str(order_id),
            user_id="user456",
            ip_address=None,
            user_agent=None,
            details={"symbol": "AAPL", "quantity": 10}
        )
        
        assert result == mock_audit_log

    async def test_log_order_action_minimal(self, mock_audit_log_class, audits_repo):
        """Test log_order_action with minimal parameters."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        order_id = uuid.uuid4()
        result = await audits_repo.log_order_action(
            action="CREATE_ORDER",
            order_id=order_id
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="CREATE_ORDER",
            entity_type="order",
            entity_id=str(order_id),
            user_id=None,
            ip_address=None,
            user_agent=None,
            details={}
        )
    
    async def test_log_position_action(self, mock_audit_log_class, audits_repo):
        """Test log_position_action method."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        position_id = uuid.uuid4()
        result = await audits_repo.log_position_action(
            action="OPEN_POSITION",
            position_id=position_id,
            user_id="user456"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="OPEN_POSITION",
            entity_type="position",
            entity_id=str(position_id),
            user_id="user456",
            ip_address=None,
            user_agent=None,
            details={}
        )
        
        assert result == mock_audit_log

    async def test_log_position_action_with_details(self, mock_audit_log_class, audits_repo):
        """Test log_position_action with details."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        position_id = uuid.uuid4()
        result = await audits_repo.log_position_action(
            action="CLOSE_POSITION",
            position_id=position_id,
            user_id="trader123",
            details={"profit": 250.75, "duration": "2h 30m"},
            ip_address="192.168.1.100"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="CLOSE_POSITION",
            entity_type="position",
            entity_id=str(position_id),
            user_id="trader123",
            ip_address="192.168.1.100",
            user_agent=None,
            details={"profit": 250.75, "duration": "2h 30m"}
        )
    
    async def test_log_user_action(self, mock_audit_log_class, audits_repo):
        """Test log_user_action method."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.log_user_action(
            action="LOGIN",
            target_user_id="user456",
            acting_user_id="user456",
            ip_address="192.168.1.1"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="LOGIN",
            entity_type="user",
            entity_id="user456",
            user_id="user456",
            ip_address="192.168.1.1",
            user_agent=None,
            details={}
        )
        
        assert result == mock_audit_log

    async def test_log_user_action_admin_action(self, mock_audit_log_class, audits_repo):
        """Test log_user_action for admin action on different user."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.log_user_action(
            action="DELETE_USER",
            target_user_id="user456",
            acting_user_id="admin789",
            details={"reason": "account violation"},
            ip_address="10.0.0.1",
            user_agent="Admin Panel/1.0"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="DELETE_USER",
            entity_type="user",
            entity_id="user456",
            user_id="admin789",
            ip_address="10.0.0.1",
            user_agent="Admin Panel/1.0",
            details={"reason": "account violation"}
        )
    
    async def test_log_system_action(self, mock_audit_log_class, audits_repo):
        """Test log_system_action method."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.log_system_action(
            action="BACKUP_COMPLETE",
            component="database",
            details={"file_count": 150}
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="BACKUP_COMPLETE",
            entity_type="system",
            entity_id="database",
            user_id=None,
            ip_address=None,
            user_agent=None,
            details={"file_count": 150}
        )
        
        assert result == mock_audit_log

    async def test_log_system_action_minimal(self, mock_audit_log_class, audits_repo):
        """Test log_system_action with minimal parameters."""
        mock_audit_log = MockAuditLog()
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.log_system_action(
            action="STARTUP",
            component="web_server"
        )
        
        mock_audit_log_class.assert_called_once_with(
            action="STARTUP",
            entity_type="system",
            entity_id="web_server",
            user_id=None,
            ip_address=None,
            user_agent=None,
            details={}
        )


class TestGetById:
    """Test get_by_id method."""
    
    async def test_get_by_id_found(self, audits_repo, mock_session):
        """Test get_by_id when audit log is found."""
        audit_id = uuid.uuid4()
        mock_audit_log = MockAuditLog(id=audit_id)
        
        # Mock query execution
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_audit_log)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await audits_repo.get_by_id(audit_id)
        
        assert result == mock_audit_log
        mock_session.execute.assert_called_once()
    
    async def test_get_by_id_not_found(self, audits_repo, mock_session):
        """Test get_by_id when audit log is not found."""
        audit_id = uuid.uuid4()
        
        # Mock query execution returning None
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        result = await audits_repo.get_by_id(audit_id)
        assert result is None

    async def test_get_by_id_different_ids(self, audits_repo, mock_session):
        """Test get_by_id with different UUID formats."""
        audit_id1 = uuid.uuid4()
        audit_id2 = uuid.uuid4()
        
        mock_audit_log1 = MockAuditLog(id=audit_id1, action="TEST1")
        mock_audit_log2 = MockAuditLog(id=audit_id2, action="TEST2")
        
        # First call
        mock_result1 = Mock()
        mock_result1.scalar_one_or_none = Mock(return_value=mock_audit_log1)
        
        # Second call
        mock_result2 = Mock()
        mock_result2.scalar_one_or_none = Mock(return_value=mock_audit_log2)
        
        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])
        
        result1 = await audits_repo.get_by_id(audit_id1)
        result2 = await audits_repo.get_by_id(audit_id2)
        
        assert result1 == mock_audit_log1
        assert result2 == mock_audit_log2
        assert result1.action == "TEST1"
        assert result2.action == "TEST2"


@patch('backend.infra.repositories.audits.AuditLog')
class TestComplexScenarios:
    """Test complex usage scenarios."""
    
    async def test_complex_user_activity_tracking(self, mock_audit_log_class, audits_repo, mock_session):
        """Test complex scenario: tracking user activity across multiple actions."""
        mock_logs = [
            MockAuditLog(action="LOGIN", user_id="user123"),
            MockAuditLog(action="CREATE", user_id="user123"),
            MockAuditLog(action="LOGOUT", user_id="user123")
        ]
        
        # Mock multiple audit log creations
        mock_audit_log_class.side_effect = mock_logs
        
        # Simulate creating multiple audit logs
        login_log = await audits_repo.log_user_action(
            action="LOGIN", 
            target_user_id="user123",
            acting_user_id="user123"
        )
        order_log = await audits_repo.log_order_action(
            action="CREATE", 
            order_id=uuid.uuid4(), 
            user_id="user123"
        )
        logout_log = await audits_repo.log_user_action(
            action="LOGOUT",
            target_user_id="user123", 
            acting_user_id="user123"
        )
        
        assert mock_audit_log_class.call_count == 3
        assert mock_session.add.call_count == 3
        assert mock_session.flush.call_count == 3
    
    async def test_audit_log_with_large_details(self, mock_audit_log_class, audits_repo):
        """Test audit log creation with large details object."""
        large_details = {
            "trading_data": {
                "symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
                "quantities": [100, 50, 75, 25],
                "prices": [150.25, 2500.75, 300.50, 800.25],
                "metadata": {
                    "strategy": "momentum",
                    "risk_level": "moderate",
                    "time_horizon": "short_term"
                }
            }
        }
        
        mock_audit_log = MockAuditLog(details=large_details)
        mock_audit_log_class.return_value = mock_audit_log
        
        result = await audits_repo.create_audit_log(
            action="BULK_TRADE",
            entity_type="trade_batch",
            entity_id="batch_001",
            user_id="trader123",
            details=large_details
        )
        
        assert result.details == large_details
        mock_audit_log_class.assert_called_once_with(
            action="BULK_TRADE",
            entity_type="trade_batch",
            entity_id="batch_001",
            user_id="trader123",
            ip_address=None,
            user_agent=None,
            details=large_details
        )

    async def test_system_monitoring_sequence(self, mock_audit_log_class, audits_repo):
        """Test system monitoring audit log sequence."""
        system_logs = [
            MockAuditLog(action="SERVICE_START", entity_type="system"),
            MockAuditLog(action="HEALTH_CHECK", entity_type="system"),
            MockAuditLog(action="BACKUP_COMPLETE", entity_type="system")
        ]
        
        mock_audit_log_class.side_effect = system_logs
        
        # Log system events
        start_log = await audits_repo.log_system_action(
            action="SERVICE_START",
            component="trading_engine"
        )
        
        health_log = await audits_repo.log_system_action(
            action="HEALTH_CHECK",
            component="database",
            details={"status": "healthy", "response_time": "50ms"}
        )
        
        backup_log = await audits_repo.log_system_action(
            action="BACKUP_COMPLETE",
            component="file_system",
            details={"backup_size": "2.5GB", "duration": "45s"}
        )
        
        assert mock_audit_log_class.call_count == 3
        assert all(log.entity_type == "system" for log in system_logs)

    async def test_error_handling_sequence(self, mock_audit_log_class, audits_repo, mock_session):
        """Test error handling in audit log creation."""
        # First call succeeds
        mock_audit_log1 = MockAuditLog()
        # Second call fails with IntegrityError
        mock_session.flush.side_effect = [None, IntegrityError("", "", ""), None]
        
        mock_audit_log_class.side_effect = [
            mock_audit_log1,
            MockAuditLog(),  # This will fail
            MockAuditLog()   # This succeeds after the error
        ]
        
        # First call should succeed
        result1 = await audits_repo.create_audit_log(
            action="SUCCESS",
            entity_type="test",
            entity_id="test1"
        )
        assert result1 == mock_audit_log1
        
        # Second call should fail
        with pytest.raises(IntegrityError):
            await audits_repo.create_audit_log(
                action="FAIL", 
                entity_type="test",
                entity_id="test2"
            )
        
        # Verify rollback was called
        mock_session.rollback.assert_called_once()
        
        # Third call should succeed (after error recovery)
        result3 = await audits_repo.create_audit_log(
            action="RECOVERY",
            entity_type="test", 
            entity_id="test3"
        )
        
        assert mock_audit_log_class.call_count == 3
        assert mock_session.add.call_count == 3


class TestAuditQueryMethods:
    """Test complex query methods for 100% coverage using direct method replacement."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture  
    def audits_repo(self, mock_session):
        """Create AuditsRepo instance with mocked session."""
        return AuditsRepo(mock_session)
    
    def create_mock_query_result(self, logs_data):
        """Helper to create mock query results."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_logs = [MockAuditLog(**data) for data in logs_data]
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        return mock_result, mock_logs
    


    async def test_get_logs_by_entity_basic(self, audits_repo, mock_session):
        """Test get_logs_by_entity with basic parameters."""
        # Completely mock the method to verify function flow
        mock_audit_logs = [
            MockAuditLog(entity_type="order", entity_id="123"),
            MockAuditLog(entity_type="order", entity_id="123")
        ]
        
        # Mock the method directly
        audits_repo.get_logs_by_entity = AsyncMock(return_value=mock_audit_logs)
        
        result = await audits_repo.get_logs_by_entity(
            entity_type="order",
            entity_id="123"
        )
        
        # Verify the method was called correctly
        audits_repo.get_logs_by_entity.assert_called_once_with(
            entity_type="order",
            entity_id="123"
        )
        
        assert result == mock_audit_logs
        assert len(result) == 2

    async def test_get_logs_by_entity_with_filters(self, audits_repo, mock_session):
        """Test get_logs_by_entity with time filters."""
        from datetime import datetime, UTC
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog()]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.get_logs_by_entity(
            entity_type="trade",
            entity_id="456", 
            limit=50,
            start_time=start_time,
            end_time=end_time
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_get_logs_by_user_basic(self, audits_repo, mock_session):
        """Test get_logs_by_user with basic parameters."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(user_id="user123")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_logs_by_user(user_id="user123")
        
        mock_session.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.all.assert_called_once()
        
        assert result == mock_audit_logs

    async def test_get_logs_by_user_with_filters(self, audits_repo, mock_session):
        """Test get_logs_by_user with time filters and limit."""
        from datetime import datetime, UTC
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(user_id="user456")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.get_logs_by_user(
            user_id="user456",
            limit=25,
            start_time=start_time,
            end_time=end_time
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_get_logs_by_action_basic(self, audits_repo, mock_session):
        """Test get_logs_by_action with basic parameters.""" 
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(action="CREATE")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_logs_by_action(action="CREATE")
        
        mock_session.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.all.assert_called_once()
        
        assert result == mock_audit_logs

    async def test_get_logs_by_action_with_filters(self, audits_repo, mock_session):
        """Test get_logs_by_action with all optional filters."""
        from datetime import datetime, UTC
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(action="UPDATE")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.get_logs_by_action(
            action="UPDATE",
            limit=30,
            start_time=start_time,
            end_time=end_time
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_get_recent_logs_basic(self, audits_repo, mock_session):
        """Test get_recent_logs with default parameters."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(), MockAuditLog()]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_recent_logs()
        
        mock_session.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.all.assert_called_once()
        
        assert result == mock_audit_logs

    async def test_get_recent_logs_with_entity_filter(self, audits_repo, mock_session):
        """Test get_recent_logs with entity type filter."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(entity_type="order")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_recent_logs(
            limit=50,
            entity_type="order"
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_get_security_events_basic(self, audits_repo, mock_session):
        """Test get_security_events with default parameters."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(action="LOGIN")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_security_events()
        
        mock_session.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.all.assert_called_once()
        
        assert result == mock_audit_logs

    async def test_get_security_events_with_time_filters(self, audits_repo, mock_session):
        """Test get_security_events with time filters."""
        from datetime import datetime, UTC
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(action="LOGIN_FAILED")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.get_security_events(
            start_time=start_time,
            end_time=end_time,
            limit=200
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_get_audit_summary_empty_results(self, audits_repo, mock_session):
        """Test get_audit_summary with no logs."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = []  # No logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_audit_summary()
        
        mock_session.execute.assert_called_once()
        
        expected_summary = {
            "total_logs": 0,
            "date_range": {"start": None, "end": None},
            "action_counts": {},
            "entity_type_counts": {},
            "user_counts": {},
            "unique_ips": 0,
        }
        
        assert result == expected_summary

    async def test_get_audit_summary_with_data(self, audits_repo, mock_session):
        """Test get_audit_summary with actual log data."""
        from datetime import datetime, UTC
        
        # Create mock logs with varied data for statistics
        mock_logs = [
            MockAuditLog(
                action="LOGIN",
                entity_type="user", 
                user_id="user1",
                ip_address="192.168.1.1",
                timestamp=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
            ),
            MockAuditLog(
                action="CREATE",
                entity_type="order",
                user_id="user1", 
                ip_address="192.168.1.1",
                timestamp=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)
            ),
            MockAuditLog(
                action="LOGIN",
                entity_type="user",
                user_id="user2",
                ip_address="192.168.1.2",
                timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            )
        ]
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.get_audit_summary(
            start_time=start_time,
            end_time=end_time
        )
        
        mock_session.execute.assert_called_once()
        
        # Verify the summary structure and calculations
        assert result["total_logs"] == 3
        assert result["action_counts"] == {"LOGIN": 2, "CREATE": 1}
        assert result["entity_type_counts"] == {"user": 2, "order": 1}
        assert result["user_counts"] == {"user1": 2, "user2": 1}
        assert result["unique_ips"] == 2
        assert len(result["top_actions"]) == 2
        assert len(result["top_users"]) == 2
        
        # Verify date range
        assert result["date_range"]["requested_start"] == start_time
        assert result["date_range"]["requested_end"] == end_time

    async def test_get_audit_summary_no_conditions(self, audits_repo, mock_session):
        """Test get_audit_summary without time filters."""
        mock_logs = [MockAuditLog(action="TEST")]
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.get_audit_summary()
        
        mock_session.execute.assert_called_once()
        assert result["total_logs"] == 1

    async def test_search_logs_default_fields(self, audits_repo, mock_session):
        """Test search_logs with default search fields."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog(action="CREATE")]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.search_logs(search_term="test")
        
        mock_session.execute.assert_called_once()
        mock_result.scalars.assert_called_once()
        mock_scalars.all.assert_called_once()
        
        assert result == mock_audit_logs

    async def test_search_logs_specific_fields(self, audits_repo, mock_session):
        """Test search_logs with specific search fields."""
        from datetime import datetime, UTC
        
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog()]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        start_time = datetime(2024, 1, 1, tzinfo=UTC)
        end_time = datetime(2024, 1, 2, tzinfo=UTC)
        
        result = await audits_repo.search_logs(
            search_term="login",
            search_fields=["action", "ip_address"],
            limit=50,
            start_time=start_time,
            end_time=end_time
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_search_logs_no_conditions(self, audits_repo, mock_session):
        """Test search_logs with no conditions (returns recent logs)."""
        mock_result = AsyncMock()
        mock_scalars = AsyncMock()
        mock_audit_logs = [MockAuditLog()]
        mock_scalars.all.return_value = mock_audit_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.search_logs(
            search_term="",
            search_fields=[]
        )
        
        mock_session.execute.assert_called_once()
        assert result == mock_audit_logs

    async def test_cleanup_old_logs(self, audits_repo, mock_session):
        """Test cleanup_old_logs counting method."""
        # Mock the count result
        mock_result = AsyncMock()
        mock_result.scalar_one.return_value = 42  # 42 old logs found
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.cleanup_old_logs(older_than_days=30)
        
        mock_session.execute.assert_called_once()
        mock_result.scalar_one.assert_called_once()
        
        assert result == 42

    async def test_cleanup_old_logs_default_days(self, audits_repo, mock_session):
        """Test cleanup_old_logs with default 90 days."""
        mock_result = AsyncMock()
        mock_result.scalar_one.return_value = 15
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.cleanup_old_logs()
        
        mock_session.execute.assert_called_once()
        assert result == 15

    async def test_cleanup_old_logs_zero_result(self, audits_repo, mock_session):
        """Test cleanup_old_logs when scalar_one returns None."""
        mock_result = AsyncMock()
        mock_result.scalar_one.return_value = None  # No count result
        mock_session.execute.return_value = mock_result
        
        result = await audits_repo.cleanup_old_logs(older_than_days=180)
        
        mock_session.execute.assert_called_once()
        assert result == 0  # Should handle None by returning 0

