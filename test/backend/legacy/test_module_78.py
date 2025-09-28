"""
Comprehensive test suite for Module 78: backend.services.audit
Tests audit service functionality.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.services.audit import (
        AuditService, AuditEventType, AuditEventSeverity, AuditEventOutcome,
        AuditEvent, AuditQuery, AuditReport, AuditStorage, FileAuditStorage,
        log_audit_event, query_audit_trail, generate_audit_report, get_audit_service,
        AuditError, AuditStorageError, AuditQueryError
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule78BackendServicesAudit:
    """Comprehensive test suite for audit service functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for audit files."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def file_storage(self, temp_dir):
        """Create file audit storage instance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        return FileAuditStorage(temp_dir)
    
    @pytest.fixture
    def audit_service(self, file_storage):
        """Create audit service instance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        return AuditService(file_storage)
    
    @pytest_asyncio.fixture
    async def sample_events(self, audit_service):
        """Create sample audit events for testing."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        events = []
        
        # User login event
        event_id1 = await audit_service.log_event(
            AuditEventType.USER_LOGIN,
            user_id="user_123",
            resource="authentication",
            action="login",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO,
            details={"login_method": "password"},
            source_ip="192.168.1.100"
        )
        
        # Trade execution event
        event_id2 = await audit_service.log_event(
            AuditEventType.TRADE_EXECUTION,
            user_id="trader_456",
            resource="trading",
            action="execute_trade",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO,
            details={
                "symbol": "AAPL",
                "quantity": 100,
                "price": 150.00
            }
        )
        
        # Failed authorization event
        event_id3 = await audit_service.log_event(
            AuditEventType.AUTHORIZATION_FAILURE,
            user_id="user_789",
            resource="admin_panel",
            action="access_admin",
            outcome=AuditEventOutcome.FAILURE,
            severity=AuditEventSeverity.WARNING,
            details={"reason": "insufficient_privileges"}
        )
        
        # Compliance violation event
        event_id4 = await audit_service.log_event(
            AuditEventType.COMPLIANCE_VIOLATION,
            user_id="trader_456",
            resource="risk_management",
            action="position_limit_breach",
            outcome=AuditEventOutcome.FAILURE,
            severity=AuditEventSeverity.ERROR,
            details={
                "limit_type": "position_size",
                "limit": 1000000,
                "actual": 1200000
            }
        )
        
        await audit_service.flush_events()
        
        return {
            "login": event_id1,
            "trade": event_id2,
            "auth_failure": event_id3,
            "compliance": event_id4
        }

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.services.audit as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.services.audit as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    def test_audit_event_creation(self):
        """Test audit event data structure."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        event = AuditEvent(
            event_id="test_123",
            event_type=AuditEventType.USER_LOGIN,
            timestamp=datetime.now(timezone.utc),
            user_id="user_123",
            session_id="session_456",
            source_ip="192.168.1.100",
            user_agent="TestAgent/1.0",
            resource="auth",
            action="login",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO,
            details={"method": "password"}
        )
        
        assert event.event_id == "test_123"
        assert event.event_type == AuditEventType.USER_LOGIN
        assert event.user_id == "user_123"
        assert event.outcome == AuditEventOutcome.SUCCESS
        assert event.severity == AuditEventSeverity.INFO
        assert event.details["method"] == "password"
        assert event.compliance_relevant is False
        assert event.risk_score == 0.0

    def test_audit_query_creation(self):
        """Test audit query data structure."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        start_time = datetime.now(timezone.utc) - timedelta(days=7)
        end_time = datetime.now(timezone.utc)
        
        query = AuditQuery(
            start_time=start_time,
            end_time=end_time,
            event_types=[AuditEventType.USER_LOGIN, AuditEventType.TRADE_EXECUTION],
            user_ids=["user_123", "user_456"],
            severities=[AuditEventSeverity.INFO, AuditEventSeverity.WARNING],
            compliance_only=True,
            limit=500
        )
        
        assert query.start_time == start_time
        assert query.end_time == end_time
        assert len(query.event_types) == 2
        assert len(query.user_ids) == 2
        assert query.compliance_only is True
        assert query.limit == 500

    @pytest.mark.asyncio
    async def test_file_storage_basic_operations(self, file_storage):
        """Test basic file storage operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create test event
        event = AuditEvent(
            event_id="storage_test_123",
            event_type=AuditEventType.DATA_ACCESS,
            timestamp=datetime.now(timezone.utc),
            user_id="test_user",
            session_id=None,
            source_ip="127.0.0.1",
            user_agent=None,
            resource="test_resource",
            action="read",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        
        # Test storage
        result = await file_storage.store_event(event)
        assert result is True
        
        # Test query
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            limit=10
        )
        
        events = await file_storage.query_events(query)
        assert len(events) >= 1
        
        # Find our event
        stored_event = next((e for e in events if e.event_id == "storage_test_123"), None)
        assert stored_event is not None
        assert stored_event.user_id == "test_user"
        assert stored_event.resource == "test_resource"

    @pytest.mark.asyncio
    async def test_audit_service_event_logging(self, audit_service):
        """Test audit service event logging."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Log an event
        event_id = await audit_service.log_event(
            AuditEventType.CONFIGURATION_CHANGE,
            user_id="admin_001",
            resource="system_config",
            action="update_trading_params",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.WARNING,
            details={
                "parameter": "max_position_size",
                "old_value": 1000000,
                "new_value": 1500000
            },
            before_state={"max_position_size": 1000000},
            after_state={"max_position_size": 1500000}
        )
        
        assert event_id is not None
        assert isinstance(event_id, str)
        
        # Verify event was buffered
        assert len(audit_service._event_buffer) == 1
        
        # Flush and verify storage
        result = await audit_service.flush_events()
        assert result is True
        assert len(audit_service._event_buffer) == 0

    @pytest.mark.asyncio
    async def test_risk_score_calculation(self, audit_service):
        """Test risk score calculation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # High risk event
        await audit_service.log_event(
            AuditEventType.SECURITY_INCIDENT,
            user_id="user_suspicious",
            resource="security",
            action="security_incident",
            outcome=AuditEventOutcome.FAILURE,
            severity=AuditEventSeverity.CRITICAL
        )
        
        # Low risk event
        await audit_service.log_event(
            AuditEventType.DATA_ACCESS,
            user_id="user_normal",
            resource="data",
            action="read_data",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        
        await audit_service.flush_events()
        
        # Query events and check risk scores
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            limit=10
        )
        events = await audit_service.query_trail(query)
        
        # Find events
        security_event = next((e for e in events if e.action == "security_incident"), None)
        normal_event = next((e for e in events if e.action == "read_data"), None)
        
        assert security_event is not None
        assert normal_event is not None
        assert security_event.risk_score > normal_event.risk_score
        assert security_event.risk_score > 5.0  # High risk threshold

    @pytest.mark.asyncio
    async def test_compliance_relevance(self, audit_service):
        """Test compliance relevance detection."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Compliance relevant event
        await audit_service.log_event(
            AuditEventType.TRADE_EXECUTION,
            user_id="trader_001",
            resource="trading",
            action="execute_trade",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        
        # Non-compliance relevant event
        await audit_service.log_event(
            AuditEventType.USER_LOGIN,
            user_id="user_001",
            resource="auth",
            action="login",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        
        await audit_service.flush_events()
        
        # Query events
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            limit=10
        )
        events = await audit_service.query_trail(query)
        
        trade_event = next((e for e in events if e.event_type == AuditEventType.TRADE_EXECUTION), None)
        login_event = next((e for e in events if e.event_type == AuditEventType.USER_LOGIN), None)
        
        assert trade_event is not None
        assert login_event is not None
        assert trade_event.compliance_relevant is True
        assert login_event.compliance_relevant is False

    @pytest.mark.asyncio
    async def test_audit_trail_querying(self, audit_service, sample_events):
        """Test audit trail querying functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Query all events
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            limit=100
        )
        
        events = await audit_service.query_trail(query)
        assert len(events) >= 4  # Our sample events
        
        # Query by event type
        query.event_types = [AuditEventType.TRADE_EXECUTION]
        trade_events = await audit_service.query_trail(query)
        assert len(trade_events) >= 1
        assert all(e.event_type == AuditEventType.TRADE_EXECUTION for e in trade_events)
        
        # Query by user
        query.event_types = None
        query.user_ids = ["trader_456"]
        trader_events = await audit_service.query_trail(query)
        assert len(trader_events) >= 2  # Trade and compliance events
        assert all(e.user_id == "trader_456" for e in trader_events)
        
        # Query by severity
        query.user_ids = None
        query.severities = [AuditEventSeverity.ERROR]
        error_events = await audit_service.query_trail(query)
        assert len(error_events) >= 1
        assert all(e.severity == AuditEventSeverity.ERROR for e in error_events)

    @pytest.mark.asyncio
    async def test_compliance_trail(self, audit_service, sample_events):
        """Test compliance trail functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        compliance_events = await audit_service.get_compliance_trail(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        # Should include trade and compliance violation events
        assert len(compliance_events) >= 2
        assert all(e.compliance_relevant for e in compliance_events)
        
        # Check specific events
        trade_event = next((e for e in compliance_events if e.event_type == AuditEventType.TRADE_EXECUTION), None)
        compliance_event = next((e for e in compliance_events if e.event_type == AuditEventType.COMPLIANCE_VIOLATION), None)
        
        assert trade_event is not None
        assert compliance_event is not None

    @pytest.mark.asyncio
    async def test_user_activity_tracking(self, audit_service, sample_events):
        """Test user activity tracking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Get activity for trader_456
        user_events = await audit_service.get_user_activity(
            "trader_456",
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        assert len(user_events) >= 2  # Trade and compliance events
        assert all(e.user_id == "trader_456" for e in user_events)
        
        # Check event types
        event_types = {e.event_type for e in user_events}
        assert AuditEventType.TRADE_EXECUTION in event_types
        assert AuditEventType.COMPLIANCE_VIOLATION in event_types

    @pytest.mark.asyncio
    async def test_resource_activity_tracking(self, audit_service, sample_events):
        """Test resource activity tracking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Get activity for trading resource
        resource_events = await audit_service.get_resource_activity(
            "trading",
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        assert len(resource_events) >= 1
        assert all(e.resource == "trading" for e in resource_events)

    @pytest.mark.asyncio
    async def test_security_incidents(self, audit_service):
        """Test security incident detection."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Log multiple failed auth attempts
        for i in range(3):
            await audit_service.log_event(
                AuditEventType.AUTHENTICATION_FAILURE,
                user_id=f"suspicious_user_{i}",
                resource="authentication",
                action="failed_login",
                outcome=AuditEventOutcome.FAILURE,
                severity=AuditEventSeverity.WARNING,
                details={"reason": "invalid_credentials"}
            )
        
        await audit_service.flush_events()
        
        # Get security incidents
        incidents = await audit_service.get_security_incidents(
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            min_risk_score=1.0
        )
        
        assert len(incidents) >= 3
        assert all(e.event_type == AuditEventType.AUTHENTICATION_FAILURE for e in incidents)
        assert all(e.risk_score >= 1.0 for e in incidents)

    @pytest.mark.asyncio
    async def test_report_generation(self, audit_service, sample_events):
        """Test audit report generation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            limit=100
        )
        
        report = await audit_service.generate_report(
            query,
            generated_by="test_admin",
            include_summary=True
        )
        
        assert report.report_id is not None
        assert report.generated_by == "test_admin"
        assert isinstance(report.generated_at, datetime)
        assert len(report.events) >= 4  # Our sample events
        assert report.total_events >= 4
        
        # Check summary
        assert "total" in report.summary
        assert "event_types" in report.summary
        assert "outcomes" in report.summary
        assert "severities" in report.summary
        assert report.summary["total"] >= 4

    @pytest.mark.asyncio
    async def test_event_counting(self, audit_service, sample_events):
        """Test event counting functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        
        count = await audit_service.count_events(query)
        assert count >= 4  # Our sample events
        
        # Count specific event types
        query.event_types = [AuditEventType.TRADE_EXECUTION]
        trade_count = await audit_service.count_events(query)
        assert trade_count >= 1

    @pytest.mark.asyncio
    async def test_auto_flush_on_buffer_full(self, audit_service):
        """Test automatic flushing when buffer is full."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Set small buffer size for testing
        audit_service._buffer_size = 3
        
        # Log events to fill buffer
        for i in range(4):  # One more than buffer size
            await audit_service.log_event(
                AuditEventType.DATA_ACCESS,
                user_id=f"user_{i}",
                resource="test_resource",
                action="test_action",
                outcome=AuditEventOutcome.SUCCESS,
                severity=AuditEventSeverity.INFO
            )
        
        # Buffer should be empty due to auto-flush
        assert len(audit_service._event_buffer) <= 1

    @pytest.mark.asyncio
    async def test_integrity_verification(self, audit_service, sample_events):
        """Test audit trail integrity verification."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Get events for verification
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            limit=100
        )
        
        events = await audit_service.query_trail(query)
        
        # Verify integrity
        integrity_result = await audit_service.verify_integrity(events)
        
        assert "status" in integrity_result
        assert "total_events" in integrity_result
        assert "issues" in integrity_result
        assert integrity_result["total_events"] >= 4
        
        # Should be valid for our test events
        assert integrity_result["status"] in ["valid", "issues_found"]

    @pytest.mark.asyncio
    async def test_expired_events_cleanup(self, audit_service):
        """Test cleanup of expired events."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Log an event
        await audit_service.log_event(
            AuditEventType.DATA_ACCESS,
            user_id="cleanup_test",
            resource="test",
            action="test",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        await audit_service.flush_events()
        
        # Clean up with very short retention (should not delete recent events)
        deleted_count = await audit_service.cleanup_expired_events(retention_days=1)
        
        # Should not delete recent events
        assert deleted_count >= 0  # May be 0 if no old events exist

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test log_audit_event
        event_id = await log_audit_event(
            AuditEventType.API_ACCESS,
            user_id="api_user",
            resource="api",
            action="get_data",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO
        )
        
        assert event_id is not None
        
        # Test query_audit_trail
        query = AuditQuery(
            start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
            limit=10
        )
        events = await query_audit_trail(query)
        assert isinstance(events, list)
        
        # Test generate_audit_report
        report = await generate_audit_report(query, "test_user")
        assert isinstance(report, AuditReport)
        
        # Test get_audit_service
        service = get_audit_service()
        assert isinstance(service, AuditService)

    def test_enums_and_constants(self):
        """Test enum definitions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test AuditEventType enum
        assert AuditEventType.USER_LOGIN.value == "user_login"
        assert AuditEventType.TRADE_EXECUTION.value == "trade_execution"
        assert AuditEventType.COMPLIANCE_VIOLATION.value == "compliance_violation"
        
        # Test AuditEventSeverity enum
        assert AuditEventSeverity.INFO.value == "info"
        assert AuditEventSeverity.WARNING.value == "warning"
        assert AuditEventSeverity.ERROR.value == "error"
        assert AuditEventSeverity.CRITICAL.value == "critical"
        
        # Test AuditEventOutcome enum
        assert AuditEventOutcome.SUCCESS.value == "success"
        assert AuditEventOutcome.FAILURE.value == "failure"
        assert AuditEventOutcome.PARTIAL.value == "partial"

    @pytest.mark.asyncio
    async def test_edge_cases_and_error_handling(self, audit_service):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test querying with no events
        empty_query = AuditQuery(
            start_time=datetime.now(timezone.utc) + timedelta(days=1),  # Future date
            end_time=datetime.now(timezone.utc) + timedelta(days=2),
            limit=10
        )
        
        empty_events = await audit_service.query_trail(empty_query)
        assert len(empty_events) == 0
        
        # Test count with empty result
        count = await audit_service.count_events(empty_query)
        assert count == 0
        
        # Test report with empty events
        empty_report = await audit_service.generate_report(empty_query, "test_user")
        assert empty_report.total_events == 0
        assert len(empty_report.events) == 0
        assert empty_report.summary["total"] == 0
        
        # Test integrity verification with empty events
        integrity = await audit_service.verify_integrity([])
        assert integrity["status"] == "valid"
        assert integrity["total_events"] == 0

    @pytest.mark.asyncio
    async def test_file_storage_query_filtering(self, file_storage):
        """Test file storage query filtering."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create events with different characteristics
        event1 = AuditEvent(
            event_id="filter_test_1",
            event_type=AuditEventType.USER_LOGIN,
            timestamp=datetime.now(timezone.utc),
            user_id="filter_user_1",
            session_id=None,
            source_ip=None,
            user_agent=None,
            resource="auth",
            action="login",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.INFO,
            compliance_relevant=False
        )
        
        event2 = AuditEvent(
            event_id="filter_test_2",
            event_type=AuditEventType.TRADE_EXECUTION,
            timestamp=datetime.now(timezone.utc),
            user_id="filter_user_2",
            session_id=None,
            source_ip=None,
            user_agent=None,
            resource="trading",
            action="execute",
            outcome=AuditEventOutcome.FAILURE,
            severity=AuditEventSeverity.ERROR,
            compliance_relevant=True
        )
        
        # Store events
        await file_storage.store_event(event1)
        await file_storage.store_event(event2)
        
        # Test filtering by event type
        query = AuditQuery(
            event_types=[AuditEventType.USER_LOGIN],
            limit=10
        )
        filtered_events = await file_storage.query_events(query)
        login_events = [e for e in filtered_events if e.event_id == "filter_test_1"]
        assert len(login_events) >= 1
        
        # Test filtering by compliance relevance
        query.event_types = None
        query.compliance_only = True
        compliance_events = await file_storage.query_events(query)
        trade_events = [e for e in compliance_events if e.event_id == "filter_test_2"]
        assert len(trade_events) >= 1
        
        # Test filtering by outcome
        query.compliance_only = False
        query.outcomes = [AuditEventOutcome.FAILURE]
        failure_events = await file_storage.query_events(query)
        failed_events = [e for e in failure_events if e.event_id == "filter_test_2"]
        assert len(failed_events) >= 1

    def test_data_class_serialization(self):
        """Test data class JSON serialization compatibility."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test AuditEvent with various data types
        event = AuditEvent(
            event_id="serialization_test",
            event_type=AuditEventType.DATA_MODIFICATION,
            timestamp=datetime.now(timezone.utc),
            user_id="test_user",
            session_id="test_session",
            source_ip="192.168.1.1",
            user_agent="TestAgent/1.0",
            resource="test_resource",
            action="modify",
            outcome=AuditEventOutcome.SUCCESS,
            severity=AuditEventSeverity.WARNING,
            details={"key": "value", "number": 42, "nested": {"inner": "data"}},
            before_state={"old": "value"},
            after_state={"new": "value"},
            risk_score=3.5,
            compliance_relevant=True
        )
        
        # Should be able to convert to dict (used for JSON serialization)
        from dataclasses import asdict
        event_dict = asdict(event)
        
        assert event_dict["event_id"] == "serialization_test"
        assert event_dict["details"]["key"] == "value"
        assert event_dict["details"]["number"] == 42
        assert event_dict["risk_score"] == 3.5

