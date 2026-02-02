"""
Phase 7: Comprehensive tests for StrategyService
Coverage target: 85%+
Tests strategy CRUD, status transitions, and WebSocket broadcasts.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from decimal import Decimal
from uuid import UUID, uuid4


# ============================================================================
# STRATEGY SERVICE INIT TESTS
# ============================================================================

class TestStrategyServiceInit:
    """Test StrategyService initialization."""
    
    def test_init_with_session_and_user_id(self):
        """Test StrategyService initializes with session and user_id."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        assert service.session is mock_session
        assert service.user_id == "admin"
        assert service.repo is not None
    
    def test_module_constants(self):
        """Test module constants are defined."""
        from backend.services.strategy_service import (
            VALID_STATUSES,
            VALID_STRATEGY_TYPES,
            IMPLEMENTATION_TYPES,
            CLASSIFICATION_TYPES,
        )
        
        assert "active" in VALID_STATUSES
        assert "inactive" in VALID_STATUSES
        assert "paused" in VALID_STATUSES
        assert "error" in VALID_STATUSES
        
        assert "momentum" in IMPLEMENTATION_TYPES
        assert "mean_reversion" in IMPLEMENTATION_TYPES
        
        assert "technical" in CLASSIFICATION_TYPES
        assert "quantitative" in CLASSIFICATION_TYPES


# ============================================================================
# TRANSFORM FOR BROADCAST TESTS
# ============================================================================

class TestTransformForBroadcast:
    """Test _transform_for_broadcast helper function."""
    
    def test_transform_basic_fields(self):
        """Test transformation of basic strategy fields."""
        from backend.services.strategy_service import _transform_for_broadcast
        
        strategy_dict = {
            "id": "abc-123",
            "name": "Test Strategy",
            "description": "A test",
            "strategy_type": "momentum",
            "status": "active",
            "symbols": ["AAPL", "MSFT"],
            "parameters": {"lookback": 20},
            "total_trades": 100,
            "win_rate": 0.55,
            "total_pnl": 5000.0,
            "max_drawdown_pct": 10.0,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-15T00:00:00",
            "last_executed_at": None,
            "started_at": "2024-01-01T10:00:00",
            "stopped_at": None,
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        assert result["strategyId"] == "abc-123"
        assert result["name"] == "Test Strategy"
        assert result["strategyType"] == "momentum"
        assert result["status"] == "active"
        assert result["symbols"] == ["AAPL", "MSFT"]
        assert result["parameters"] == {"lookback": 20}
        assert result["performance"]["totalTrades"] == 100
        assert result["performance"]["winRate"] == 0.55
    
    def test_transform_inactive_to_stopped(self):
        """Test inactive status is converted to stopped for frontend."""
        from backend.services.strategy_service import _transform_for_broadcast
        
        strategy_dict = {
            "id": "abc-123",
            "name": "Test Strategy",
            "status": "inactive",
            "symbols": [],
            "parameters": {},
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        # inactive -> stopped for frontend
        assert result["status"] == "stopped"
    
    def test_transform_with_missing_optional_fields(self):
        """Test transformation handles missing optional fields."""
        from backend.services.strategy_service import _transform_for_broadcast
        
        strategy_dict = {
            "id": "abc-123",
            "name": "Minimal Strategy",
            "status": "active",
        }
        
        result = _transform_for_broadcast(strategy_dict)
        
        assert result["symbols"] == []
        assert result["parameters"] == {}
        assert result["performance"]["totalTrades"] == 0
        assert result["performance"]["winRate"] == 0.0


# ============================================================================
# STRATEGY TO DICT TESTS
# ============================================================================

class TestStrategyToDict:
    """Test _strategy_to_dict method."""
    
    def test_strategy_to_dict_full(self):
        """Test _strategy_to_dict with all fields populated."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        # Create mock strategy
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Test Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = "Test description"
        mock_strategy.status = "active"
        mock_strategy.symbols = ["AAPL"]
        mock_strategy.parameters = {"lookback": 20}
        mock_strategy.total_pnl = Decimal("1000.50")
        mock_strategy.total_trades = 50
        mock_strategy.winning_trades = 30
        mock_strategy.losing_trades = 20
        mock_strategy.win_rate = Decimal("0.60")
        mock_strategy.max_position_size = Decimal("10000")
        mock_strategy.max_daily_loss = Decimal("500")
        mock_strategy.max_drawdown_pct = Decimal("15.5")
        mock_strategy.last_executed_at = datetime.now(UTC)
        mock_strategy.last_signal_at = datetime.now(UTC)
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = uuid4()
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = datetime.now(UTC)
        mock_strategy.stopped_at = None
        
        result = service._strategy_to_dict(mock_strategy)
        
        assert result["id"] == str(mock_strategy.id)
        assert result["name"] == "Test Strategy"
        assert result["strategy_type"] == "momentum"
        assert result["status"] == "active"
        assert result["total_pnl"] == 1000.50
        assert result["total_trades"] == 50
        assert result["win_rate"] == 0.60
        assert result["model_id"] is not None
    
    def test_strategy_to_dict_none_values(self):
        """Test _strategy_to_dict handles None values properly."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Minimal"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "inactive"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        result = service._strategy_to_dict(mock_strategy)
        
        assert result["max_position_size"] is None
        assert result["max_daily_loss"] is None
        assert result["max_drawdown_pct"] is None
        assert result["last_executed_at"] is None
        assert result["model_id"] is None
        assert result["started_at"] is None
        assert result["stopped_at"] is None


# ============================================================================
# STATUS TRANSITION VALIDATION TESTS
# ============================================================================

class TestValidateStatusTransition:
    """Test _validate_status_transition method."""
    
    def test_same_status_allowed(self):
        """Test transition to same status is allowed (no-op)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        # Should not raise
        service._validate_status_transition("active", "active")
        service._validate_status_transition("inactive", "inactive")
        service._validate_status_transition("paused", "paused")
    
    def test_any_to_error_allowed(self):
        """Test any status can transition to error."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        # Should not raise
        service._validate_status_transition("active", "error")
        service._validate_status_transition("inactive", "error")
        service._validate_status_transition("paused", "error")
    
    def test_inactive_to_active_allowed(self):
        """Test inactive -> active transition (start)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        # Should not raise
        service._validate_status_transition("inactive", "active")
    
    def test_active_to_paused_allowed(self):
        """Test active -> paused transition (pause)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        service._validate_status_transition("active", "paused")
    
    def test_paused_to_active_allowed(self):
        """Test paused -> active transition (resume)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        service._validate_status_transition("paused", "active")
    
    def test_active_to_inactive_allowed(self):
        """Test active -> inactive transition (stop)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        service._validate_status_transition("active", "inactive")
    
    def test_paused_to_inactive_allowed(self):
        """Test paused -> inactive transition (stop)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        service._validate_status_transition("paused", "inactive")
    
    def test_inactive_to_paused_not_allowed(self):
        """Test inactive -> paused transition is NOT allowed."""
        from backend.services.strategy_service import StrategyService
        from backend.infra.repositories.strategies import InvalidStatusTransitionError
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(InvalidStatusTransitionError):
            service._validate_status_transition("inactive", "paused")
    
    def test_error_to_active_not_allowed(self):
        """Test error -> active transition is NOT allowed."""
        from backend.services.strategy_service import StrategyService
        from backend.infra.repositories.strategies import InvalidStatusTransitionError
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(InvalidStatusTransitionError):
            service._validate_status_transition("error", "active")
    
    def test_error_to_inactive_not_allowed(self):
        """Test error -> inactive transition is NOT allowed."""
        from backend.services.strategy_service import StrategyService
        from backend.infra.repositories.strategies import InvalidStatusTransitionError
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(InvalidStatusTransitionError):
            service._validate_status_transition("error", "inactive")


# ============================================================================
# LIST STRATEGIES TESTS
# ============================================================================

class TestListStrategies:
    """Test list_strategies method."""
    
    @pytest.mark.asyncio
    async def test_list_strategies_no_filter(self):
        """Test listing all strategies without filters."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        # Create mock strategies
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Test"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        service.repo.get_all = AsyncMock(return_value=[mock_strategy])
        
        result = await service.list_strategies()
        
        assert len(result) == 1
        assert result[0]["name"] == "Test"
        service.repo.get_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_strategies_with_status_filter(self):
        """Test listing strategies with status filter."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Active Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        service.repo.get_by_status = AsyncMock(return_value=[mock_strategy])
        
        result = await service.list_strategies(status="active")
        
        assert len(result) == 1
        service.repo.get_by_status.assert_called_once_with("active")
    
    @pytest.mark.asyncio
    async def test_list_strategies_with_type_filter(self):
        """Test listing strategies with strategy_type filter."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Momentum Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "inactive"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        service.repo.get_by_strategy_type = AsyncMock(return_value=[mock_strategy])
        
        result = await service.list_strategies(strategy_type="momentum")
        
        assert len(result) == 1
        service.repo.get_by_strategy_type.assert_called_once_with("momentum")
    
    @pytest.mark.asyncio
    async def test_list_strategies_with_both_filters(self):
        """Test listing strategies with both status and type filters."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        mock_strategy = MagicMock()
        mock_strategy.id = uuid4()
        mock_strategy.name = "Active Momentum"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        # Mock returns all strategies, filtering done in memory
        service.repo.get_all = AsyncMock(return_value=[mock_strategy])
        
        result = await service.list_strategies(status="active", strategy_type="momentum")
        
        assert len(result) == 1


# ============================================================================
# GET STRATEGY TESTS
# ============================================================================

class TestGetStrategy:
    """Test get_strategy method."""
    
    @pytest.mark.asyncio
    async def test_get_strategy_success(self):
        """Test getting a strategy by ID."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Test Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = ["AAPL"]
        mock_strategy.parameters = {"lookback": 20}
        mock_strategy.total_pnl = Decimal("1000")
        mock_strategy.total_trades = 50
        mock_strategy.winning_trades = 30
        mock_strategy.losing_trades = 20
        mock_strategy.win_rate = Decimal("0.60")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        result = await service.get_strategy(str(strategy_id))
        
        assert result["id"] == str(strategy_id)
        assert result["name"] == "Test Strategy"
    
    @pytest.mark.asyncio
    async def test_get_strategy_invalid_uuid(self):
        """Test getting strategy with invalid UUID format."""
        from backend.services.strategy_service import StrategyService
        from backend.infra.repositories.strategies import StrategyNotFoundError
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(StrategyNotFoundError):
            await service.get_strategy("not-a-valid-uuid")
    
    @pytest.mark.asyncio
    async def test_get_strategy_not_found(self):
        """Test getting non-existent strategy."""
        from backend.services.strategy_service import StrategyService
        from backend.infra.repositories.strategies import StrategyNotFoundError
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        service.repo.get_by_id = AsyncMock(side_effect=StrategyNotFoundError("Not found"))
        
        with pytest.raises(StrategyNotFoundError):
            await service.get_strategy(str(uuid4()))


# ============================================================================
# CREATE STRATEGY TESTS
# ============================================================================

class TestCreateStrategy:
    """Test create_strategy method."""
    
    @pytest.mark.asyncio
    async def test_create_strategy_success(self):
        """Test creating a strategy with valid data."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "New Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = "A new strategy"
        mock_strategy.status = "inactive"
        mock_strategy.symbols = ["AAPL", "MSFT"]
        mock_strategy.parameters = {"lookback": 20}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        service.repo.create = AsyncMock(return_value=mock_strategy)
        
        result = await service.create_strategy({
            "name": "New Strategy",
            "strategy_type": "momentum",
            "description": "A new strategy",
            "symbols": ["AAPL", "MSFT"],
            "parameters": {"lookback": 20}
        })
        
        assert result["name"] == "New Strategy"
        assert result["strategy_type"] == "momentum"
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_strategy_missing_name(self):
        """Test creating strategy without name raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "strategy_type": "momentum"
            })
        
        assert "name is required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_strategy_missing_type(self):
        """Test creating strategy without type raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "name": "Test Strategy"
            })
        
        assert "type is required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_strategy_invalid_type(self):
        """Test creating strategy with invalid type raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "name": "Test Strategy",
                "strategy_type": "invalid_type"
            })
        
        assert "Invalid strategy type" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_strategy_invalid_symbols(self):
        """Test creating strategy with invalid symbols raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "name": "Test Strategy",
                "strategy_type": "momentum",
                "symbols": "AAPL"  # Should be a list
            })
        
        assert "Symbols must be a list" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_strategy_invalid_parameters(self):
        """Test creating strategy with invalid parameters raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "name": "Test Strategy",
                "strategy_type": "momentum",
                "parameters": "not a dict"
            })
        
        assert "Parameters must be a dictionary" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_strategy_invalid_status(self):
        """Test creating strategy with invalid status raises ValueError."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy({
                "name": "Test Strategy",
                "strategy_type": "momentum",
                "status": "invalid_status"
            })
        
        assert "Invalid status" in str(exc_info.value)


# ============================================================================
# START / STOP / PAUSE STRATEGY TESTS
# ============================================================================

class TestStartStrategy:
    """Test start_strategy method."""
    
    @pytest.mark.asyncio
    async def test_start_strategy_success(self):
        """Test starting an inactive strategy."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        
        # Initial inactive strategy
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Test Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "inactive"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = None
        mock_strategy.stopped_at = None
        
        # Updated active strategy
        updated_strategy = MagicMock()
        updated_strategy.id = strategy_id
        updated_strategy.name = "Test Strategy"
        updated_strategy.strategy_type = "momentum"
        updated_strategy.description = None
        updated_strategy.status = "active"
        updated_strategy.symbols = []
        updated_strategy.parameters = {}
        updated_strategy.total_pnl = Decimal("0")
        updated_strategy.total_trades = 0
        updated_strategy.winning_trades = 0
        updated_strategy.losing_trades = 0
        updated_strategy.win_rate = Decimal("0")
        updated_strategy.max_position_size = None
        updated_strategy.max_daily_loss = None
        updated_strategy.max_drawdown_pct = None
        updated_strategy.last_executed_at = None
        updated_strategy.last_signal_at = None
        updated_strategy.error_message = None
        updated_strategy.error_count = 0
        updated_strategy.model_id = None
        updated_strategy.created_at = datetime.now(UTC)
        updated_strategy.updated_at = datetime.now(UTC)
        updated_strategy.started_at = datetime.now(UTC)
        updated_strategy.stopped_at = None
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        service.repo.update_status = AsyncMock(return_value=updated_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update", new_callable=AsyncMock):
            result = await service.start_strategy(str(strategy_id))
        
        assert result["status"] == "active"
        assert result["started_at"] is not None
    
    @pytest.mark.asyncio
    async def test_start_already_active_strategy(self):
        """Test starting an already active strategy (no-op)."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Active Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"  # Already active
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = datetime.now(UTC)
        mock_strategy.stopped_at = None
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        service.repo.update_status = AsyncMock()  # Should not be called
        
        result = await service.start_strategy(str(strategy_id))
        
        assert result["status"] == "active"
        # update_status should NOT be called for no-op
        service.repo.update_status.assert_not_called()


class TestStopStrategy:
    """Test stop_strategy method."""
    
    @pytest.mark.asyncio
    async def test_stop_strategy_success(self):
        """Test stopping an active strategy."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Active Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = datetime.now(UTC)
        mock_strategy.stopped_at = None
        
        stopped_strategy = MagicMock()
        stopped_strategy.id = strategy_id
        stopped_strategy.name = "Active Strategy"
        stopped_strategy.strategy_type = "momentum"
        stopped_strategy.description = None
        stopped_strategy.status = "inactive"
        stopped_strategy.symbols = []
        stopped_strategy.parameters = {}
        stopped_strategy.total_pnl = Decimal("0")
        stopped_strategy.total_trades = 0
        stopped_strategy.winning_trades = 0
        stopped_strategy.losing_trades = 0
        stopped_strategy.win_rate = Decimal("0")
        stopped_strategy.max_position_size = None
        stopped_strategy.max_daily_loss = None
        stopped_strategy.max_drawdown_pct = None
        stopped_strategy.last_executed_at = None
        stopped_strategy.last_signal_at = None
        stopped_strategy.error_message = None
        stopped_strategy.error_count = 0
        stopped_strategy.model_id = None
        stopped_strategy.created_at = datetime.now(UTC)
        stopped_strategy.updated_at = datetime.now(UTC)
        stopped_strategy.started_at = datetime.now(UTC)
        stopped_strategy.stopped_at = datetime.now(UTC)
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        service.repo.update_status = AsyncMock(return_value=stopped_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update", new_callable=AsyncMock):
            result = await service.stop_strategy(str(strategy_id))
        
        assert result["status"] == "inactive"
        assert result["stopped_at"] is not None


class TestPauseStrategy:
    """Test pause_strategy method."""
    
    @pytest.mark.asyncio
    async def test_pause_strategy_success(self):
        """Test pausing an active strategy."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Active Strategy"
        mock_strategy.strategy_type = "momentum"
        mock_strategy.description = None
        mock_strategy.status = "active"
        mock_strategy.symbols = []
        mock_strategy.parameters = {}
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_position_size = None
        mock_strategy.max_daily_loss = None
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        mock_strategy.last_signal_at = None
        mock_strategy.error_message = None
        mock_strategy.error_count = 0
        mock_strategy.model_id = None
        mock_strategy.created_at = datetime.now(UTC)
        mock_strategy.updated_at = datetime.now(UTC)
        mock_strategy.started_at = datetime.now(UTC)
        mock_strategy.stopped_at = None
        
        paused_strategy = MagicMock()
        paused_strategy.id = strategy_id
        paused_strategy.name = "Active Strategy"
        paused_strategy.strategy_type = "momentum"
        paused_strategy.description = None
        paused_strategy.status = "paused"
        paused_strategy.symbols = []
        paused_strategy.parameters = {}
        paused_strategy.total_pnl = Decimal("0")
        paused_strategy.total_trades = 0
        paused_strategy.winning_trades = 0
        paused_strategy.losing_trades = 0
        paused_strategy.win_rate = Decimal("0")
        paused_strategy.max_position_size = None
        paused_strategy.max_daily_loss = None
        paused_strategy.max_drawdown_pct = None
        paused_strategy.last_executed_at = None
        paused_strategy.last_signal_at = None
        paused_strategy.error_message = None
        paused_strategy.error_count = 0
        paused_strategy.model_id = None
        paused_strategy.created_at = datetime.now(UTC)
        paused_strategy.updated_at = datetime.now(UTC)
        paused_strategy.started_at = datetime.now(UTC)
        paused_strategy.stopped_at = None
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        service.repo.update_status = AsyncMock(return_value=paused_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update", new_callable=AsyncMock):
            result = await service.pause_strategy(str(strategy_id))
        
        assert result["status"] == "paused"


# ============================================================================
# GET STRATEGY PERFORMANCE TESTS
# ============================================================================

class TestGetStrategyPerformance:
    """Test get_strategy_performance method."""
    
    @pytest.mark.asyncio
    async def test_get_performance_success(self):
        """Test getting strategy performance metrics."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Profitable Strategy"
        mock_strategy.total_pnl = Decimal("5000.00")
        mock_strategy.total_trades = 100
        mock_strategy.winning_trades = 60
        mock_strategy.losing_trades = 40
        mock_strategy.win_rate = Decimal("0.60")
        mock_strategy.max_drawdown_pct = Decimal("12.5")
        mock_strategy.last_executed_at = datetime.now(UTC)
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        result = await service.get_strategy_performance(str(strategy_id))
        
        assert result["strategy_id"] == str(strategy_id)
        assert result["name"] == "Profitable Strategy"
        assert result["total_pnl"] == 5000.0
        assert result["total_trades"] == 100
        assert result["win_rate"] == 0.60
        assert result["max_drawdown_pct"] == 12.5
    
    @pytest.mark.asyncio
    async def test_get_performance_none_drawdown(self):
        """Test performance with None max_drawdown_pct."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = MagicMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        mock_strategy = MagicMock()
        mock_strategy.id = strategy_id
        mock_strategy.name = "Strategy"
        mock_strategy.total_pnl = Decimal("0")
        mock_strategy.total_trades = 0
        mock_strategy.winning_trades = 0
        mock_strategy.losing_trades = 0
        mock_strategy.win_rate = Decimal("0")
        mock_strategy.max_drawdown_pct = None
        mock_strategy.last_executed_at = None
        
        service.repo.get_by_id = AsyncMock(return_value=mock_strategy)
        
        result = await service.get_strategy_performance(str(strategy_id))
        
        assert result["max_drawdown_pct"] == 0.0


# ============================================================================
# UPDATE PERFORMANCE METRICS TESTS
# ============================================================================

class TestUpdatePerformanceMetrics:
    """Test update_performance_metrics method."""
    
    @pytest.mark.asyncio
    async def test_update_performance_with_trades(self):
        """Test updating performance with trade counts."""
        from backend.services.strategy_service import StrategyService
        
        mock_session = AsyncMock()
        service = StrategyService(mock_session, user_id="admin")
        
        strategy_id = uuid4()
        
        updated_strategy = MagicMock()
        updated_strategy.id = strategy_id
        updated_strategy.name = "Strategy"
        updated_strategy.strategy_type = "momentum"
        updated_strategy.description = None
        updated_strategy.status = "active"
        updated_strategy.symbols = []
        updated_strategy.parameters = {}
        updated_strategy.total_pnl = Decimal("1000")
        updated_strategy.total_trades = 100
        updated_strategy.winning_trades = 60
        updated_strategy.losing_trades = 40
        updated_strategy.win_rate = Decimal("0.60")
        updated_strategy.max_position_size = None
        updated_strategy.max_daily_loss = None
        updated_strategy.max_drawdown_pct = None
        updated_strategy.last_executed_at = None
        updated_strategy.last_signal_at = None
        updated_strategy.error_message = None
        updated_strategy.error_count = 0
        updated_strategy.model_id = None
        updated_strategy.created_at = datetime.now(UTC)
        updated_strategy.updated_at = datetime.now(UTC)
        updated_strategy.started_at = None
        updated_strategy.stopped_at = None
        
        service.repo.update_performance = AsyncMock(return_value=updated_strategy)
        
        with patch("backend.services.strategy_service.broadcast_strategy_update", new_callable=AsyncMock):
            result = await service.update_performance_metrics(str(strategy_id), {
                "total_pnl": 1000.0,
                "total_trades": 100,
                "winning_trades": 60,
                "losing_trades": 40,
            })
        
        assert result is not None
