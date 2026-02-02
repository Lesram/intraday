"""
Comprehensive tests for RiskManager service.
Tests risk metric calculations, violation detection, limits, and emergency stops.
"""

import pytest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from backend.services.risk_manager import RiskManager
from backend.models.risk import RiskStatus, ViolationType, EmergencyStopStatus


class MockDBRiskLimit:
    """Mock database risk limit."""
    def __init__(self, limit_name, limit_value=1000, enabled=True,
                 warning_threshold=80, critical_threshold=95, user_id=None):
        self.id = uuid4()
        self.user_id = user_id or uuid4()
        self.limit_name = limit_name
        self.limit_value = limit_value
        self.enabled = enabled
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class MockDBRiskMetric:
    """Mock database risk metric."""
    def __init__(self, metric_name, current_value=0, limit_value=1000,
                 percent_used=0, status="NORMAL", user_id=None):
        self.id = uuid4()
        self.user_id = user_id or uuid4()
        self.metric_name = metric_name
        self.current_value = current_value
        self.limit_value = limit_value
        self.percent_used = percent_used
        self.status = status
        self.last_updated = datetime.utcnow()
        self.created_at = datetime.utcnow()


class MockDBRiskViolation:
    """Mock database risk violation."""
    def __init__(self, metric_name, violation_type="BREACH", severity="CRITICAL",
                 resolved=False, user_id=None):
        self.id = uuid4()
        self.user_id = user_id or uuid4()
        self.metric_name = metric_name
        self.violation_type = violation_type
        self.current_value = Decimal("150")
        self.limit_value = Decimal("100")
        self.severity = severity
        self.message = f"{metric_name} {violation_type}"
        self.resolved = resolved
        self.created_at = datetime.utcnow()
        self.resolved_at = None


class MockDBEmergencyStop:
    """Mock database emergency stop."""
    def __init__(self, status="active", user_id=None, triggered_by=None):
        self.id = uuid4()
        self.user_id = user_id or uuid4()
        self.triggered_by = triggered_by or uuid4()
        self.reason = "Test emergency stop"
        self.strategies_stopped = 3
        self.orders_cancelled = 5
        self.status = status
        self.triggered_at = datetime.utcnow()
        self.resolved_at = None
        self.resolved_by = None


class MockPosition:
    """Mock position model."""
    def __init__(self, symbol, quantity=100, current_price=150.0, avg_entry_price=140.0, user_id=None):
        self.symbol = symbol
        self.quantity = quantity
        self.current_price = current_price
        self.avg_entry_price = avg_entry_price
        self.user_id = str(user_id) if user_id else "demo"


class MockOrder:
    """Mock order model."""
    def __init__(self, symbol, status="filled", user_id=None):
        self.id = uuid4()
        self.symbol = symbol
        self.status = status
        self.user_id = str(user_id) if user_id else "demo"
        self.created_at = datetime.utcnow()


class MockStrategy:
    """Mock strategy model."""
    def __init__(self, name, status="active"):
        self.id = uuid4()
        self.name = name
        self.status = status
        self.stopped_at = None


class TestRiskManagerInit:
    """Tests for RiskManager initialization."""

    def test_init_with_db_session(self):
        """Test service initialization with database session."""
        mock_db = MagicMock()
        manager = RiskManager(db_session=mock_db)
        
        assert manager.db is mock_db

    def test_has_metric_name_constants(self):
        """Test service has all metric name constants."""
        mock_db = MagicMock()
        manager = RiskManager(db_session=mock_db)
        
        assert manager.DAILY_LOSS == "daily_loss"
        assert manager.MAX_DRAWDOWN == "max_drawdown"
        assert manager.POSITION_COUNT == "position_count"
        assert manager.TOTAL_EXPOSURE == "total_exposure"
        assert manager.ORDER_COUNT_DAILY == "order_count_daily"
        assert manager.BUYING_POWER_USED == "buying_power_used"


class TestGetStatusFromPercent:
    """Tests for status calculation from percentage used."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_status_normal_below_warning(self, manager, mock_db):
        """Test NORMAL status when below warning threshold."""
        # Mock limit with thresholds
        limit = MockDBRiskLimit("daily_loss", warning_threshold=80, critical_threshold=95)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("50"))
        
        assert status == RiskStatus.NORMAL

    @pytest.mark.asyncio
    async def test_status_warning_at_threshold(self, manager, mock_db):
        """Test WARNING status at warning threshold."""
        limit = MockDBRiskLimit("daily_loss", warning_threshold=80, critical_threshold=95)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("80"))
        
        assert status == RiskStatus.WARNING

    @pytest.mark.asyncio
    async def test_status_critical_at_threshold(self, manager, mock_db):
        """Test CRITICAL status at critical threshold."""
        limit = MockDBRiskLimit("daily_loss", warning_threshold=80, critical_threshold=95)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("95"))
        
        assert status == RiskStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_status_breached_at_100_percent(self, manager, mock_db):
        """Test BREACHED status at 100% or above."""
        limit = MockDBRiskLimit("daily_loss", warning_threshold=80, critical_threshold=95)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("100"))
        
        assert status == RiskStatus.BREACHED

    @pytest.mark.asyncio
    async def test_status_breached_above_100_percent(self, manager, mock_db):
        """Test BREACHED status above 100%."""
        limit = MockDBRiskLimit("daily_loss", warning_threshold=80, critical_threshold=95)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("150"))
        
        assert status == RiskStatus.BREACHED

    @pytest.mark.asyncio
    async def test_status_uses_default_thresholds_when_no_limit(self, manager, mock_db):
        """Test default thresholds are used when no limit exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        # Default warning=80, critical=95
        status = await manager._get_status_from_percent(user_id, "daily_loss", Decimal("85"))
        
        assert status == RiskStatus.WARNING


class TestGetLimitValue:
    """Tests for getting limit values."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_get_existing_enabled_limit(self, manager, mock_db):
        """Test getting an existing enabled limit."""
        limit = MockDBRiskLimit("daily_loss", limit_value=5000, enabled=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        result = await manager._get_limit_value(user_id, "daily_loss")
        
        assert result == Decimal("5000")

    @pytest.mark.asyncio
    async def test_get_nonexistent_limit(self, manager, mock_db):
        """Test getting a limit that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        result = await manager._get_limit_value(user_id, "daily_loss")
        
        assert result is None


class TestGetCurrentMetrics:
    """Tests for getting current risk metrics."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_get_empty_metrics(self, manager, mock_db):
        """Test getting metrics when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskMetric.from_orm') as mock_from_orm:
            result = await manager.get_current_metrics(user_id)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_multiple_metrics(self, manager, mock_db):
        """Test getting multiple metrics."""
        metrics = [
            MockDBRiskMetric("daily_loss", current_value=500, status="NORMAL"),
            MockDBRiskMetric("max_drawdown", current_value=200, status="WARNING")
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = metrics
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskMetric.from_orm') as mock_from_orm:
            mock_from_orm.side_effect = lambda m: MagicMock(metric_name=m.metric_name)
            result = await manager.get_current_metrics(user_id)
        
        assert len(result) == 2


class TestGetRecentViolations:
    """Tests for getting recent violations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_get_no_violations(self, manager, mock_db):
        """Test getting violations when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskViolation.from_orm'):
            result = await manager.get_recent_violations(user_id)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_violations_with_custom_hours(self, manager, mock_db):
        """Test getting violations with custom time window."""
        violations = [MockDBRiskViolation("daily_loss", "BREACH")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = violations
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskViolation.from_orm') as mock_from_orm:
            mock_from_orm.return_value = MagicMock()
            result = await manager.get_recent_violations(user_id, hours=48)
        
        assert len(result) == 1


class TestGetRiskLimits:
    """Tests for getting risk limits."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_get_empty_limits(self, manager, mock_db):
        """Test getting limits when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskLimit.from_orm'):
            result = await manager.get_risk_limits(user_id)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_multiple_limits(self, manager, mock_db):
        """Test getting multiple limits."""
        limits = [
            MockDBRiskLimit("daily_loss", limit_value=5000),
            MockDBRiskLimit("max_drawdown", limit_value=10000)
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = limits
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        
        with patch('backend.models.risk.RiskLimit.from_orm') as mock_from_orm:
            mock_from_orm.side_effect = lambda l: MagicMock(limit_name=l.limit_name)
            result = await manager.get_risk_limits(user_id)
        
        assert len(result) == 2


class TestUpdateRiskLimit:
    """Tests for updating risk limits."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_update_existing_limit(self, manager, mock_db):
        """Test updating an existing limit."""
        existing_limit = MockDBRiskLimit("daily_loss", limit_value=5000)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_limit
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        updated_by = uuid4()
        
        request = MagicMock()
        request.limit_value = 10000
        request.warning_threshold = 75
        request.critical_threshold = 90
        request.enabled = True
        
        with patch('backend.models.risk.RiskLimit.from_orm') as mock_from_orm:
            mock_from_orm.return_value = MagicMock(limit_value=10000)
            result = await manager.update_risk_limit(user_id, "daily_loss", request, updated_by)
        
        mock_db.commit.assert_called_once()
        assert existing_limit.limit_value == 10000

    @pytest.mark.asyncio
    async def test_create_new_limit(self, manager, mock_db):
        """Test creating a new limit when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        updated_by = uuid4()
        
        request = MagicMock()
        request.limit_value = 10000
        request.warning_threshold = 75
        request.critical_threshold = 90
        request.enabled = True
        
        with patch('backend.models.risk.RiskLimit.from_orm') as mock_from_orm:
            mock_from_orm.return_value = MagicMock()
            result = await manager.update_risk_limit(user_id, "new_limit", request, updated_by)
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestDeleteRiskLimit:
    """Tests for deleting risk limits."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_delete_existing_limit(self, manager, mock_db):
        """Test deleting an existing limit."""
        limit_id = uuid4()
        existing_limit = MockDBRiskLimit("daily_loss")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_limit
        mock_db.execute.return_value = mock_result
        
        await manager.delete_risk_limit(user_id=1, limit_id=str(limit_id))
        
        mock_db.delete.assert_called_once_with(existing_limit)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_limit_raises_error(self, manager, mock_db):
        """Test deleting a limit that doesn't exist raises an error."""
        limit_id = uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(ValueError, match="Risk limit not found"):
            await manager.delete_risk_limit(user_id=1, limit_id=str(limit_id))

    @pytest.mark.asyncio
    async def test_delete_with_invalid_uuid_raises_error(self, manager, mock_db):
        """Test deleting with invalid UUID format raises an error."""
        with pytest.raises(ValueError, match="Invalid limit_id format"):
            await manager.delete_risk_limit(user_id=1, limit_id="not-a-uuid")


class TestEmergencyStop:
    """Tests for emergency stop functionality."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_trigger_emergency_stop(self, manager, mock_db):
        """Test triggering an emergency stop."""
        user_id = uuid4()
        triggered_by = uuid4()
        
        # Mock strategies and orders
        strategies = [MockStrategy("strat1"), MockStrategy("strat2")]
        orders = [MockOrder("AAPL", "pending"), MockOrder("GOOGL", "new")]
        
        call_count = [0]
        
        def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalars.return_value.all.return_value = strategies
            elif call_count[0] == 2:
                mock_result.scalars.return_value.all.return_value = orders
            return mock_result
        
        mock_db.execute = AsyncMock(side_effect=mock_execute)
        
        request = MagicMock()
        request.reason = "Market crash"
        
        with patch('backend.models.risk.EmergencyStop.from_orm') as mock_from_orm:
            mock_stop = MagicMock()
            mock_stop.strategies_stopped = 2
            mock_stop.orders_cancelled = 2
            mock_from_orm.return_value = mock_stop
            
            result = await manager.trigger_emergency_stop(user_id, request, triggered_by)
        
        # Verify strategies were stopped
        for strategy in strategies:
            assert strategy.status == "inactive"
        
        # Verify orders were cancelled
        for order in orders:
            assert order.status == "cancelled"
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_emergency_stop_rollback_on_error(self, manager, mock_db):
        """Test that emergency stop rolls back on error."""
        user_id = uuid4()
        triggered_by = uuid4()
        
        mock_db.execute = AsyncMock(side_effect=Exception("Database error"))
        
        request = MagicMock()
        request.reason = "Test"
        
        with pytest.raises(Exception, match="Database error"):
            await manager.trigger_emergency_stop(user_id, request, triggered_by)
        
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_emergency_stop(self, manager, mock_db):
        """Test resolving an active emergency stop."""
        stop_id = uuid4()
        user_id = uuid4()
        resolved_by = uuid4()
        
        active_stop = MockDBEmergencyStop(status="active", user_id=user_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active_stop
        mock_db.execute.return_value = mock_result
        
        with patch('backend.models.risk.EmergencyStop.from_orm') as mock_from_orm:
            mock_from_orm.return_value = MagicMock(status="resolved")
            result = await manager.resolve_emergency_stop(stop_id, user_id, resolved_by)
        
        assert active_stop.status == EmergencyStopStatus.RESOLVED.value
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_stop_raises_error(self, manager, mock_db):
        """Test resolving a non-existent stop raises an error."""
        stop_id = uuid4()
        user_id = uuid4()
        resolved_by = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(ValueError, match="not found or already resolved"):
            await manager.resolve_emergency_stop(stop_id, user_id, resolved_by)


class TestGetActiveEmergencyStop:
    """Tests for getting active emergency stop."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_get_active_stop_when_exists(self, manager, mock_db):
        """Test getting active stop when one exists."""
        active_stop = MockDBEmergencyStop(status="active")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active_stop
        mock_db.execute.return_value = mock_result
        
        with patch('backend.models.risk.EmergencyStop.from_orm') as mock_from_orm:
            mock_from_orm.return_value = MagicMock(status="active")
            result = await manager.get_active_emergency_stop(user_id=1)
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_active_stop_when_none(self, manager, mock_db):
        """Test getting active stop when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await manager.get_active_emergency_stop(user_id=1)
        
        assert result is None


class TestIsEmergencyStopActive:
    """Tests for checking if emergency stop is active."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_returns_true_when_active(self, manager, mock_db):
        """Test returns True when emergency stop is active."""
        active_stop = MockDBEmergencyStop(status="active")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active_stop
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        result = await manager.is_emergency_stop_active(user_id)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_active(self, manager, mock_db):
        """Test returns False when no emergency stop is active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        user_id = uuid4()
        result = await manager.is_emergency_stop_active(user_id)
        
        assert result is False


class TestCalculateMetrics:
    """Tests for metric calculation methods."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_calculate_position_count_returns_none_without_limit(self, manager, mock_db):
        """Test calculating position count returns None when no limit exists."""
        user_id = uuid4()
        
        # Mock that _get_limit_value returns None
        with patch.object(manager, '_get_limit_value', return_value=None) as mock_get_limit:
            result = await manager._calculate_position_count(user_id)
        
        assert result is None
        mock_get_limit.assert_called_once_with(user_id, manager.POSITION_COUNT)

    @pytest.mark.asyncio
    async def test_calculate_metric_returns_none_when_no_limit(self, manager, mock_db):
        """Test metric calculation returns None when no limit configured."""
        user_id = uuid4()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await manager._calculate_daily_loss(user_id)
        
        assert result is None


class TestCheckViolations:
    """Tests for violation checking."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_creates_violation_for_breached_metric(self, manager, mock_db):
        """Test that violations are created for breached metrics."""
        user_id = uuid4()
        
        # Create a breached metric
        breached_metric = MagicMock()
        breached_metric.status = RiskStatus.BREACHED
        breached_metric.metric_name = "daily_loss"
        breached_metric.current_value = Decimal("1500")
        breached_metric.limit_value = Decimal("1000")
        breached_metric.percent_used = Decimal("150")
        
        with patch.object(manager, '_create_violation') as mock_create:
            await manager._check_violations(user_id, [breached_metric])
        
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.kwargs['violation_type'] == ViolationType.BREACH

    @pytest.mark.asyncio
    async def test_creates_violation_for_critical_metric(self, manager, mock_db):
        """Test that violations are created for critical metrics."""
        user_id = uuid4()
        
        critical_metric = MagicMock()
        critical_metric.status = RiskStatus.CRITICAL
        critical_metric.metric_name = "daily_loss"
        critical_metric.current_value = Decimal("950")
        critical_metric.limit_value = Decimal("1000")
        critical_metric.percent_used = Decimal("95")
        
        with patch.object(manager, '_create_violation') as mock_create:
            await manager._check_violations(user_id, [critical_metric])
        
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args.kwargs['violation_type'] == ViolationType.WARNING

    @pytest.mark.asyncio
    async def test_no_violation_for_normal_metric(self, manager, mock_db):
        """Test that no violations are created for normal metrics."""
        user_id = uuid4()
        
        normal_metric = MagicMock()
        normal_metric.status = RiskStatus.NORMAL
        
        with patch.object(manager, '_create_violation') as mock_create:
            await manager._check_violations(user_id, [normal_metric])
        
        mock_create.assert_not_called()


class TestCreateViolation:
    """Tests for violation creation."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def manager(self, mock_db):
        """Create RiskManager with mocked database."""
        return RiskManager(db_session=mock_db)

    @pytest.mark.asyncio
    async def test_create_violation_adds_to_db(self, manager, mock_db):
        """Test that violation is added to database."""
        user_id = uuid4()
        
        metric = MagicMock()
        metric.metric_name = "daily_loss"
        metric.current_value = Decimal("1500")
        metric.limit_value = Decimal("1000")
        metric.percent_used = Decimal("150")
        
        with patch('backend.services.risk_manager.get_alert_manager') as mock_alert:
            mock_alert.return_value.risk_violation = AsyncMock()
            await manager._create_violation(user_id, metric, ViolationType.BREACH)
        
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_violation_sends_alert(self, manager, mock_db):
        """Test that violation sends an alert."""
        user_id = uuid4()
        
        metric = MagicMock()
        metric.metric_name = "daily_loss"
        metric.current_value = Decimal("1500")
        metric.limit_value = Decimal("1000")
        metric.percent_used = Decimal("150")
        
        with patch('backend.services.risk_manager.get_alert_manager') as mock_alert:
            mock_alert_manager = MagicMock()
            mock_alert_manager.risk_violation = AsyncMock()
            mock_alert.return_value = mock_alert_manager
            
            await manager._create_violation(user_id, metric, ViolationType.BREACH)
        
        mock_alert_manager.risk_violation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_violation_continues_on_alert_failure(self, manager, mock_db):
        """Test that violation creation continues even if alerting fails."""
        user_id = uuid4()
        
        metric = MagicMock()
        metric.metric_name = "daily_loss"
        metric.current_value = Decimal("1500")
        metric.limit_value = Decimal("1000")
        metric.percent_used = Decimal("150")
        
        with patch('backend.services.risk_manager.get_alert_manager') as mock_alert:
            mock_alert.return_value.risk_violation = AsyncMock(side_effect=Exception("Alert failed"))
            
            # Should not raise
            await manager._create_violation(user_id, metric, ViolationType.BREACH)
        
        # Violation should still be added
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
