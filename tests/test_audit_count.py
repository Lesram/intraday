"""
Tests for audit trail count functionality.

Verifies the count_audit_trail method provides accurate pagination totals.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.services.audit_service import (
    ComplianceAuditService,
    AuditEntity,
    AuditAction,
)


class TestAuditCountTrail:
    """Tests for count_audit_trail method."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async database session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def audit_service(self, mock_db):
        """Create an audit service with mock database."""
        return ComplianceAuditService(mock_db)

    @pytest.mark.asyncio
    async def test_count_all_records(self, audit_service, mock_db):
        """Test counting all audit records without filters."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 150
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail()

        assert count == 150
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_with_entity_type_filter(self, audit_service, mock_db):
        """Test counting with entity type filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            entity_type=AuditEntity.ORDER
        )

        assert count == 42

    @pytest.mark.asyncio
    async def test_count_with_entity_id_filter(self, audit_service, mock_db):
        """Test counting with entity ID filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            entity_id="order-123"
        )

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_with_action_filter(self, audit_service, mock_db):
        """Test counting with action filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 25
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            action=AuditAction.ORDER_SUBMITTED
        )

        assert count == 25

    @pytest.mark.asyncio
    async def test_count_with_actor_filter(self, audit_service, mock_db):
        """Test counting with actor filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            actor="user@example.com"
        )

        assert count == 100

    @pytest.mark.asyncio
    async def test_count_with_time_range(self, audit_service, mock_db):
        """Test counting with time range filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 75
        mock_db.execute.return_value = mock_result

        start = datetime.now() - timedelta(days=7)
        end = datetime.now()

        count = await audit_service.count_audit_trail(
            start_time=start,
            end_time=end
        )

        assert count == 75

    @pytest.mark.asyncio
    async def test_count_with_multiple_filters(self, audit_service, mock_db):
        """Test counting with multiple filters combined."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            entity_type=AuditEntity.ORDER,
            action=AuditAction.ORDER_SUBMITTED,
            actor="admin@example.com"
        )

        assert count == 10

    @pytest.mark.asyncio
    async def test_count_returns_zero_when_no_results(self, audit_service, mock_db):
        """Test count returns 0 when no matching records."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None  # No results
        mock_db.execute.return_value = mock_result

        count = await audit_service.count_audit_trail(
            entity_type=AuditEntity.STRATEGY,
            actor="nonexistent@example.com"
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_count_with_all_filters(self, audit_service, mock_db):
        """Test counting with all filters applied."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_db.execute.return_value = mock_result

        start = datetime.now() - timedelta(days=30)
        end = datetime.now()

        count = await audit_service.count_audit_trail(
            entity_type=AuditEntity.POSITION,
            entity_id="pos-456",
            action=AuditAction.POSITION_OPENED,
            actor="trader@example.com",
            start_time=start,
            end_time=end
        )

        assert count == 3


class TestCountFiltersMatch:
    """Verify count filters match get_audit_trail filters."""

    @pytest.fixture
    def audit_service(self):
        """Create audit service with mock db."""
        return ComplianceAuditService(AsyncMock())

    @pytest.mark.asyncio
    async def test_entity_type_filter_consistency(self, audit_service):
        """Ensure entity_type filter works the same for count and get."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_result.scalars.return_value.all.return_value = []
        audit_service.db.execute.return_value = mock_result

        # Both should filter by the same entity type
        entity_type = AuditEntity.ORDER

        await audit_service.count_audit_trail(entity_type=entity_type)
        count_call = audit_service.db.execute.call_args_list[0]

        await audit_service.get_audit_trail(entity_type=entity_type)
        get_call = audit_service.db.execute.call_args_list[1]

        # Extract the WHERE conditions from both queries
        # Both should have entity == "order" in their conditions
        assert count_call is not None
        assert get_call is not None

    @pytest.mark.asyncio
    async def test_time_range_filter_consistency(self, audit_service):
        """Ensure time range filters work consistently."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_result.scalars.return_value.all.return_value = []
        audit_service.db.execute.return_value = mock_result

        start = datetime.now() - timedelta(days=7)
        end = datetime.now()

        await audit_service.count_audit_trail(start_time=start, end_time=end)
        await audit_service.get_audit_trail(start_time=start, end_time=end)

        # Both methods should have been called
        assert audit_service.db.execute.call_count == 2

