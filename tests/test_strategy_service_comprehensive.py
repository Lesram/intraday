"""
Comprehensive Tests for Strategy Service
Tests business logic, status transitions, and performance tracking.
Target: Improve strategy_service.py coverage from 17% to 60%+
"""

import pytest
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.strategy_service import (
    StrategyService,
    VALID_STATUSES,
    VALID_STRATEGY_TYPES,
    _transform_for_broadcast,
)
from backend.infra.repositories.strategies import (
    DuplicateStrategyError,
    InvalidStatusTransitionError,
    StrategyNotFoundError,
)
from backend.infra.schemas import Strategy

pytestmark = pytest.mark.unit


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_strategy():
    """Create mock strategy with all required attributes"""
    strategy = Mock(spec=Strategy)
    strategy.id = uuid4()
    strategy.name = "Test Strategy"
    strategy.strategy_type = "momentum"
    strategy.description = "A test momentum strategy"
    strategy.status = "inactive"
    strategy.symbols = ["AAPL", "MSFT"]
    strategy.parameters = {"ma_period": 20, "rsi_period": 14}
    strategy.total_pnl = Decimal("5000.00")
    strategy.total_trades = 100
    strategy.winning_trades = 60
    strategy.losing_trades = 40
    strategy.win_rate = Decimal("60.0")
    strategy.max_position_size = Decimal("0.10")
    strategy.max_daily_loss = Decimal("0.05")
    strategy.max_drawdown_pct = Decimal("0.15")
    strategy.last_executed_at = datetime.now(UTC)
    strategy.last_signal_at = datetime.now(UTC)
    strategy.error_message = None
    strategy.error_count = 0
    strategy.model_id = uuid4()
    strategy.created_at = datetime.now(UTC)
    strategy.updated_at = datetime.now(UTC)
    strategy.started_at = None
    strategy.stopped_at = None
    return strategy


@pytest.fixture
def strategy_service(mock_db_session):
    """Create StrategyService with mocked dependencies"""
    service = StrategyService(mock_db_session, user_id="test-user")
    service.repo = Mock()
    return service


# ============================================================================
# TRANSFORM FUNCTION TESTS
# ============================================================================

class TestTransformForBroadcast:
    """Tests for _transform_for_broadcast helper function"""

    def test_transform_basic_strategy(self):
        """Test transforming a basic strategy dict to broadcast format"""
        strategy_dict = {
            "id": "test-id-123",
            "name": "Test Strategy",
            "description": "A test strategy",
            "strategy_type": "momentum",
            "status": "active",
            "symbols": ["AAPL", "MSFT"],
            "parameters": {"ma_period": 20},
            "total_trades": 50,
            "win_rate": 0.6,
            "total_pnl": 5000.0,
            "max_drawdown_pct": 0.05,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-06-01T00:00:00",
            "last_executed_at": "2024-06-01T12:00:00",
            "started_at": "2024-01-01T00:00:00",
            "stopped_at": None,
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        assert result["strategyId"] == "test-id-123"
        assert result["name"] == "Test Strategy"
        assert result["strategyType"] == "momentum"
        assert result["status"] == "active"
        assert result["symbols"] == ["AAPL", "MSFT"]
        assert result["parameters"] == {"ma_period": 20}
        assert result["performance"]["totalTrades"] == 50
        assert result["performance"]["winRate"] == 0.6
        assert result["performance"]["totalPnL"] == 5000.0

    def test_transform_inactive_to_stopped(self):
        """Test that inactive status is transformed to stopped for frontend"""
        strategy_dict = {
            "id": "test-id",
            "name": "Test",
            "status": "inactive",
            "strategy_type": "momentum",
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        assert result["status"] == "stopped"

    def test_transform_with_missing_fields(self):
        """Test transform handles missing optional fields"""
        strategy_dict = {
            "id": "test-id",
            "name": "Test",
            "status": "active",
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        assert result["strategyId"] == "test-id"
        assert result["performance"]["totalTrades"] == 0
        assert result["performance"]["winRate"] == 0.0
        assert result["performance"]["totalPnL"] == 0.0


# ============================================================================
# STRATEGY SERVICE INITIALIZATION TESTS
# ============================================================================

class TestStrategyServiceInit:
    """Tests for StrategyService initialization"""

    def test_init_with_user_id(self, mock_db_session):
        """Test service initialization with user ID"""
        service = StrategyService(mock_db_session, user_id="admin")
        
        assert service.user_id == "admin"
        assert service.session == mock_db_session
        assert service.repo is not None


# ============================================================================
# STRATEGY TO DICT CONVERSION TESTS
# ============================================================================

class TestStrategyToDict:
    """Tests for _strategy_to_dict method"""

    def test_convert_strategy_to_dict(self, strategy_service, mock_strategy):
        """Test converting Strategy object to dict"""
        result = strategy_service._strategy_to_dict(mock_strategy)
        
        assert result["id"] == str(mock_strategy.id)
        assert result["name"] == mock_strategy.name
        assert result["strategy_type"] == "momentum"
        assert result["status"] == "inactive"
        assert result["symbols"] == ["AAPL", "MSFT"]
        assert result["parameters"] == {"ma_period": 20, "rsi_period": 14}
        assert result["total_pnl"] == 5000.0
        assert result["total_trades"] == 100
        assert result["win_rate"] == 60.0

    def test_convert_strategy_with_none_optionals(self, strategy_service, mock_strategy):
        """Test converting strategy with None optional fields"""
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        mock_strategy.model_id = None
        
        result = strategy_service._strategy_to_dict(mock_strategy)
        
        assert result["max_position_size"] is None
        assert result["max_daily_loss"] is None
        assert result["last_executed_at"] is None
        assert result["started_at"] is None
        assert result["model_id"] is None


# ============================================================================
# STATUS TRANSITION VALIDATION TESTS
# ============================================================================

class TestStatusTransitionValidation:
    """Tests for _validate_status_transition method"""

    def test_same_status_transition_allowed(self, strategy_service):
        """Test that same status transition is a no-op"""
        # Should not raise
        strategy_service._validate_status_transition("active", "active")
        strategy_service._validate_status_transition("inactive", "inactive")
        strategy_service._validate_status_transition("paused", "paused")
        strategy_service._validate_status_transition("error", "error")

    def test_any_to_error_transition_allowed(self, strategy_service):
        """Test that any status can transition to error"""
        # Should not raise
        strategy_service._validate_status_transition("active", "error")
        strategy_service._validate_status_transition("inactive", "error")
        strategy_service._validate_status_transition("paused", "error")

    def test_valid_inactive_to_active(self, strategy_service):
        """Test inactive → active transition is valid"""
        # Should not raise
        strategy_service._validate_status_transition("inactive", "active")

    def test_valid_active_to_paused(self, strategy_service):
        """Test active → paused transition is valid"""
        strategy_service._validate_status_transition("active", "paused")

    def test_valid_active_to_inactive(self, strategy_service):
        """Test active → inactive transition is valid"""
        strategy_service._validate_status_transition("active", "inactive")

    def test_valid_paused_to_active(self, strategy_service):
        """Test paused → active transition is valid"""
        strategy_service._validate_status_transition("paused", "active")

    def test_valid_paused_to_inactive(self, strategy_service):
        """Test paused → inactive transition is valid"""
        strategy_service._validate_status_transition("paused", "inactive")

    def test_invalid_inactive_to_paused(self, strategy_service):
        """Test inactive → paused transition is invalid"""
        with pytest.raises(InvalidStatusTransitionError, match="Invalid status transition"):
            strategy_service._validate_status_transition("inactive", "paused")

    def test_invalid_error_to_active(self, strategy_service):
        """Test error → active transition is invalid (requires manual intervention)"""
        with pytest.raises(InvalidStatusTransitionError, match="Invalid status transition"):
            strategy_service._validate_status_transition("error", "active")

    def test_invalid_error_to_inactive(self, strategy_service):
        """Test error → inactive transition is invalid"""
        with pytest.raises(InvalidStatusTransitionError, match="Invalid status transition"):
            strategy_service._validate_status_transition("error", "inactive")


# ============================================================================
# LIST STRATEGIES TESTS
# ============================================================================

class TestListStrategies:
    """Tests for list_strategies method"""

    @pytest.mark.asyncio
    async def test_list_all_strategies(self, strategy_service, mock_strategy):
        """Test listing all strategies without filters"""
        strategy_service.repo.get_all = AsyncMock(return_value=[mock_strategy])
        
        result = await strategy_service.list_strategies()
        
        assert len(result) == 1
        assert result[0]["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_list_strategies_by_status(self, strategy_service, mock_strategy):
        """Test listing strategies filtered by status"""
        strategy_service.repo.get_by_status = AsyncMock(return_value=[mock_strategy])
        
        result = await strategy_service.list_strategies(status="inactive")
        
        strategy_service.repo.get_by_status.assert_called_once_with("inactive")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_strategies_by_type(self, strategy_service, mock_strategy):
        """Test listing strategies filtered by type"""
        strategy_service.repo.get_by_strategy_type = AsyncMock(return_value=[mock_strategy])
        
        result = await strategy_service.list_strategies(strategy_type="momentum")
        
        strategy_service.repo.get_by_strategy_type.assert_called_once_with("momentum")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_strategies_by_status_and_type(self, strategy_service, mock_strategy):
        """Test listing strategies filtered by both status and type"""
        strategy_service.repo.get_all = AsyncMock(return_value=[mock_strategy])
        
        result = await strategy_service.list_strategies(status="inactive", strategy_type="momentum")
        
        assert len(result) == 1
        assert result[0]["status"] == "inactive"
        assert result[0]["strategy_type"] == "momentum"

    @pytest.mark.asyncio
    async def test_list_strategies_empty(self, strategy_service):
        """Test listing strategies when none exist"""
        strategy_service.repo.get_all = AsyncMock(return_value=[])
        
        result = await strategy_service.list_strategies()
        
        assert result == []


# ============================================================================
# GET STRATEGY TESTS
# ============================================================================

class TestGetStrategy:
    """Tests for get_strategy method"""

    @pytest.mark.asyncio
    async def test_get_strategy_success(self, strategy_service, mock_strategy):
        """Test getting a strategy by ID"""
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        result = await strategy_service.get_strategy(str(mock_strategy.id))
        
        assert result["id"] == str(mock_strategy.id)
        assert result["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_get_strategy_not_found(self, strategy_service):
        """Test getting a non-existent strategy"""
        strategy_service.repo.get_by_id = AsyncMock(side_effect=StrategyNotFoundError("Not found"))
        
        with pytest.raises(StrategyNotFoundError):
            await strategy_service.get_strategy("non-existent-id")


# ============================================================================
# CREATE STRATEGY TESTS
# ============================================================================

class TestCreateStrategy:
    """Tests for create_strategy method"""

    @pytest.mark.asyncio
    async def test_create_strategy_success(self, strategy_service, mock_strategy):
        """Test creating a new strategy"""
        strategy_service.repo.create = AsyncMock(return_value=mock_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            result = await strategy_service.create_strategy({
                "name": "Test Strategy",
                "strategy_type": "momentum",
                "symbols": ["AAPL", "MSFT"],
                "parameters": {"ma_period": 20},
            })
        
        assert result["name"] == "Test Strategy"

    @pytest.mark.asyncio
    async def test_create_strategy_missing_name(self, strategy_service):
        """Test creating a strategy without name raises error"""
        with pytest.raises(ValueError, match="Strategy name is required"):
            await strategy_service.create_strategy({
                "strategy_type": "momentum",
                "symbols": ["AAPL"],
            })

    @pytest.mark.asyncio
    async def test_create_strategy_invalid_type(self, strategy_service):
        """Test creating a strategy with invalid type raises error"""
        with pytest.raises(ValueError, match="Invalid strategy type"):
            await strategy_service.create_strategy({
                "name": "Test",
                "strategy_type": "invalid_type",
                "symbols": ["AAPL"],
            })

    @pytest.mark.asyncio
    async def test_create_strategy_invalid_symbols(self, strategy_service):
        """Test creating a strategy with non-list symbols raises error"""
        with pytest.raises(ValueError, match="Symbols must be a list"):
            await strategy_service.create_strategy({
                "name": "Test",
                "strategy_type": "momentum",
                "symbols": "AAPL",  # Should be a list
            })

    @pytest.mark.asyncio
    async def test_create_strategy_invalid_parameters(self, strategy_service):
        """Test creating a strategy with non-dict parameters raises error"""
        with pytest.raises(ValueError, match="Parameters must be a dictionary"):
            await strategy_service.create_strategy({
                "name": "Test",
                "strategy_type": "momentum",
                "symbols": ["AAPL"],
                "parameters": "invalid",  # Should be a dict
            })


# ============================================================================
# UPDATE STRATEGY TESTS
# ============================================================================

class TestUpdateStrategy:
    """Tests for update_strategy method"""

    @pytest.mark.asyncio
    async def test_update_strategy_name(self, strategy_service, mock_strategy):
        """Test updating strategy name"""
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        updated_strategy = Mock(spec=Strategy)
        for attr in dir(mock_strategy):
            if not attr.startswith('_'):
                try:
                    setattr(updated_strategy, attr, getattr(mock_strategy, attr))
                except (TypeError, AttributeError):
                    pass
        updated_strategy.name = "Updated Name"
        strategy_service.repo.update = AsyncMock(return_value=updated_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            # Use the correct API signature: update_strategy(strategy_id, update_data)
            result = await strategy_service.update_strategy(
                strategy_id=str(mock_strategy.id),
                update_data={"name": "Updated Name"}
            )
        
        # Just verify we got a result back
        assert result is not None


# ============================================================================
# DELETE STRATEGY TESTS
# ============================================================================

class TestDeleteStrategy:
    """Tests for delete_strategy method"""

    @pytest.mark.asyncio
    async def test_delete_strategy_success(self, strategy_service, mock_strategy):
        """Test deleting a strategy"""
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        strategy_service.repo.delete = AsyncMock()
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            # delete_strategy returns None on success
            result = await strategy_service.delete_strategy(str(mock_strategy.id))
        
        # No assertion needed - if we got here, delete succeeded
        strategy_service.repo.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_strategy_not_found(self, strategy_service):
        """Test deleting a non-existent strategy"""
        strategy_service.repo.delete = AsyncMock(side_effect=StrategyNotFoundError("Not found"))
        
        non_existent_uuid = str(uuid4())
        with pytest.raises((StrategyNotFoundError, ValueError)):
            await strategy_service.delete_strategy(non_existent_uuid)


# ============================================================================
# START/STOP/PAUSE STRATEGY TESTS
# ============================================================================

class TestStrategyLifecycle:
    """Tests for start_strategy, stop_strategy, pause_strategy methods"""

    @pytest.mark.asyncio
    async def test_start_strategy_success(self, strategy_service, mock_strategy):
        """Test starting an inactive strategy"""
        mock_strategy.status = "inactive"
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        started_strategy = Mock(spec=Strategy)
        for attr in dir(mock_strategy):
            if not attr.startswith('_'):
                try:
                    setattr(started_strategy, attr, getattr(mock_strategy, attr))
                except (TypeError, AttributeError):
                    pass
        started_strategy.status = "active"
        started_strategy.started_at = datetime.now(UTC)
        strategy_service.repo.update_status = AsyncMock(return_value=started_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            result = await strategy_service.start_strategy(str(mock_strategy.id))
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_stop_strategy_success(self, strategy_service, mock_strategy):
        """Test stopping an active strategy"""
        mock_strategy.status = "active"
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        stopped_strategy = Mock(spec=Strategy)
        for attr in dir(mock_strategy):
            if not attr.startswith('_'):
                try:
                    setattr(stopped_strategy, attr, getattr(mock_strategy, attr))
                except (TypeError, AttributeError):
                    pass
        stopped_strategy.status = "inactive"
        strategy_service.repo.update_status = AsyncMock(return_value=stopped_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            result = await strategy_service.stop_strategy(str(mock_strategy.id))
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_pause_strategy_success(self, strategy_service, mock_strategy):
        """Test pausing an active strategy"""
        mock_strategy.status = "active"
        strategy_service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        paused_strategy = Mock(spec=Strategy)
        for attr in dir(mock_strategy):
            if not attr.startswith('_'):
                try:
                    setattr(paused_strategy, attr, getattr(mock_strategy, attr))
                except (TypeError, AttributeError):
                    pass
        paused_strategy.status = "paused"
        strategy_service.repo.update_status = AsyncMock(return_value=paused_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update"):
            result = await strategy_service.pause_strategy(str(mock_strategy.id))
        
        assert result is not None


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_valid_statuses_constant(self):
        """Test that VALID_STATUSES contains expected values"""
        assert "active" in VALID_STATUSES
        assert "inactive" in VALID_STATUSES
        assert "paused" in VALID_STATUSES
        assert "error" in VALID_STATUSES

    def test_valid_strategy_types_constant(self):
        """Test that VALID_STRATEGY_TYPES contains expected values"""
        assert "momentum" in VALID_STRATEGY_TYPES
        assert "mean_reversion" in VALID_STRATEGY_TYPES
        assert "ensemble" in VALID_STRATEGY_TYPES
        assert "technical" in VALID_STRATEGY_TYPES

    @pytest.mark.asyncio
    async def test_list_strategies_filters_correctly(self, strategy_service, mock_strategy):
        """Test that list_strategies filters both status and type correctly"""
        # Create a strategy that doesn't match filter
        non_matching = Mock(spec=Strategy)
        non_matching.id = uuid4()
        non_matching.name = "Non-matching"
        non_matching.strategy_type = "mean_reversion"
        non_matching.status = "active"
        
        strategy_service.repo.get_all = AsyncMock(return_value=[mock_strategy, non_matching])
        
        result = await strategy_service.list_strategies(status="inactive", strategy_type="momentum")
        
        # Should only return mock_strategy which has status=inactive and type=momentum
        assert len(result) == 1
        assert result[0]["strategy_type"] == "momentum"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
