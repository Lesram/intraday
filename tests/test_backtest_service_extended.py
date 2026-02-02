"""
Extended Test Suite for Backtesting Service - Phase 2 Coverage Boost
Tests comprehensive coverage for backtest_service.py

Target: Improve coverage from 30% to 70%+
Focus areas:
- run_backtest complete flow
- Historical data fetching
- Signal generation with history
- Parameter optimization
- Database persistence methods
"""

import pytest
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4, UUID
import uuid as uuid_module

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from backend.services.backtest_service import BacktestService, PortfolioState
from backend.models.backtest import (
    BacktestResult,
    BacktestSummary,
    PerformanceMetrics,
    Trade,
    EquityPoint,
)
from backend.infra.schemas import Backtest, Strategy
from backend.data.alpaca_client import MarketData

pytestmark = pytest.mark.unit


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Mock database session with comprehensive mocking"""
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def backtest_service_with_mock_alpaca(mock_db_session):
    """
    Create BacktestService in test mode which uses internal mock Alpaca client.
    This tests the actual initialization path that uses _LocalMockAlpacaClient.
    """
    with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
        service = BacktestService(mock_db_session)
    return service


@pytest.fixture
def mock_strategy():
    """Create mock strategy with all required attributes"""
    strategy = Mock(spec=Strategy)
    strategy.id = uuid4()
    strategy.name = "Test Strategy"
    strategy.strategy_type = "momentum"
    strategy.symbols = ["AAPL", "MSFT"]
    strategy.parameters = {"ma_period": 20, "rsi_period": 14}
    strategy.risk_limits = {"max_position_size": 0.1}
    strategy.max_position_size = Decimal("0.1")
    strategy.max_daily_loss = Decimal("0.05")
    strategy.max_drawdown_pct = Decimal("0.15")
    return strategy


@pytest.fixture
def mock_backtest_db_record():
    """Create mock backtest database record"""
    bt = Mock(spec=Backtest)
    bt.id = uuid4()
    bt.strategy_id = uuid4()
    bt.user_id = uuid4()
    bt.start_date = date(2024, 1, 1)
    bt.end_date = date(2024, 6, 30)
    bt.initial_capital = Decimal("100000")
    bt.final_equity = Decimal("110000")
    bt.total_return = Decimal("0.10")
    bt.annualized_return = Decimal("0.20")
    bt.sharpe_ratio = Decimal("1.5")
    bt.max_drawdown = Decimal("0.05")
    bt.win_rate = Decimal("0.6")
    bt.profit_factor = Decimal("1.8")
    bt.total_trades = 50
    bt.winning_trades = 30
    bt.losing_trades = 20
    bt.status = "completed"
    bt.error_message = None  # Explicit None for optional string field
    bt.created_at = datetime.now()
    bt.started_at = datetime.now()
    bt.completed_at = datetime.now()
    bt.equity_curve = []
    bt.trade_log = []
    bt.metrics = {
        "total_return": 0.10,
        "sharpe_ratio": 1.5,
        "max_drawdown": -0.05,
        "win_rate": 60.0,
        "profit_factor": 1.8,
        "total_trades": 50,
        "winning_trades": 30,
        "losing_trades": 20,
        "annualized_return": 0.20,
        "volatility": 0.15,
        "calmar_ratio": 1.33,
        "sortino_ratio": 2.0,
        "avg_win": 500.0,
        "avg_loss": -300.0,
        "avg_trade_duration_days": 5,
    }
    bt.monthly_returns = []
    return bt


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestBacktestServiceInit:
    """Tests for BacktestService initialization"""

    def test_init_with_mock_environment(self, mock_db_session):
        """Test initialization in mock/test environment"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
            assert service.alpaca_client is not None
            # Should be the _LocalMockAlpacaClient
            assert hasattr(service.alpaca_client, 'get_historical_data')

    def test_init_with_use_mock_broker_flag(self, mock_db_session):
        """Test initialization with USE_MOCK_BROKER=true"""
        with patch.dict(os.environ, {
            "USE_MOCK_BROKER": "true",
            "ALPACA_API_KEY_ID": "",
            "ALPACA_API_SECRET_KEY": ""
        }):
            service = BacktestService(mock_db_session)
            assert service.alpaca_client is not None

    def test_init_with_use_mock_data_flag(self, mock_db_session):
        """Test initialization with USE_MOCK_DATA=true"""
        with patch.dict(os.environ, {
            "USE_MOCK_DATA": "true",
            "ALPACA_API_KEY_ID": "",
            "ALPACA_API_SECRET_KEY": ""
        }):
            service = BacktestService(mock_db_session)
            assert service.alpaca_client is not None


# ============================================================================
# LOCAL MOCK ALPACA CLIENT TESTS
# ============================================================================

class TestLocalMockAlpacaClient:
    """Tests for the internal _LocalMockAlpacaClient"""

    def test_get_historical_data_returns_dataframe(self, backtest_service_with_mock_alpaca):
        """Test that mock client returns proper DataFrame structure"""
        start = "2024-01-01"
        end = "2024-01-31"
        
        df = backtest_service_with_mock_alpaca.alpaca_client.get_historical_data(
            symbol="AAPL",
            start=start,
            end=end,
            timeframe="1Day"
        )
        
        # Verify DataFrame structure
        assert df is not None
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        assert "volume" in df.columns
        assert len(df) > 0

    def test_get_historical_data_empty_range(self, backtest_service_with_mock_alpaca):
        """Test mock client with empty date range"""
        # Same start and end should still return data (at least one day)
        df = backtest_service_with_mock_alpaca.alpaca_client.get_historical_data(
            symbol="AAPL",
            start="2024-01-01",
            end="2024-01-01",
            timeframe="1Day"
        )
        
        assert df is not None
        assert len(df) >= 1


# ============================================================================
# PORTFOLIO STATE EXTENDED TESTS
# ============================================================================

class TestPortfolioStateExtended:
    """Extended tests for PortfolioState"""

    def test_empty_positions_value(self):
        """Test positions_value with no positions"""
        portfolio = PortfolioState(initial_capital=100000)
        assert portfolio.positions_value == 0
        assert portfolio.total_equity == 100000

    def test_equity_history_tracking(self):
        """Test that equity history is properly tracked"""
        portfolio = PortfolioState(initial_capital=100000)
        
        # Initial history should have starting capital
        assert 100000 in portfolio.equity_history
        
        # Simulate adding a position and updating
        portfolio.positions["AAPL"] = {
            "quantity": 100,
            "avg_price": 150.0,
            "current_price": 160.0,
            "unrealized_pnl": 1000.0,
        }
        portfolio.cash = 85000
        
        # Add new equity point
        portfolio.equity_history.append(portfolio.total_equity)
        
        assert len(portfolio.equity_history) == 2

    def test_update_position_prices_missing_symbol(self):
        """Test update_position_prices when symbol not in market data"""
        portfolio = PortfolioState(initial_capital=100000)
        portfolio.positions["AAPL"] = {
            "quantity": 100,
            "avg_price": 150.0,
            "current_price": 150.0,
            "unrealized_pnl": 0.0,
        }
        
        # Update with market data that doesn't include AAPL
        market_data = {
            "MSFT": MarketData(
                symbol="MSFT",
                timestamp=datetime.now(),
                open=300.0, high=305.0, low=299.0, close=303.0,
                volume=500000,
            )
        }
        
        portfolio.update_position_prices(market_data)
        
        # AAPL position should remain unchanged
        assert portfolio.positions["AAPL"]["current_price"] == 150.0


# ============================================================================
# SIGNAL GENERATION EXTENDED TESTS
# ============================================================================

class TestSignalGenerationExtended:
    """Extended tests for signal generation methods"""

    def test_generate_signals_with_history_momentum(self, backtest_service_with_mock_alpaca):
        """Test _generate_signals_with_history for momentum strategy"""
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=149.0, close=154.0,
                volume=1000000,
            )
        }
        
        # Create price history (enough for indicator calculation)
        price_history = {
            "AAPL": [100.0 + i for i in range(60)]  # 60 days of prices
        }
        
        portfolio = PortfolioState(100000)
        current_date = date.today()
        
        params = {"sma_period": 20, "rsi_period": 14}
        
        signals = backtest_service_with_mock_alpaca._generate_signals_with_history(
            strategy_type="momentum",
            parameters=params,
            market_data=market_data,
            price_history=price_history,
            portfolio=portfolio,
            current_date=current_date,
        )
        
        assert isinstance(signals, list)

    def test_generate_signals_with_history_mean_reversion(self, backtest_service_with_mock_alpaca):
        """Test _generate_signals_with_history for mean_reversion strategy"""
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=145.0, close=146.0,  # Down day
                volume=1000000,
            )
        }
        
        price_history = {"AAPL": [150.0 - i * 0.5 for i in range(60)]}  # Downtrend
        portfolio = PortfolioState(100000)
        
        signals = backtest_service_with_mock_alpaca._generate_signals_with_history(
            strategy_type="mean_reversion",
            parameters={"rsi_period": 14, "oversold": 30, "overbought": 70},
            market_data=market_data,
            price_history=price_history,
            portfolio=portfolio,
            current_date=date.today(),
        )
        
        assert isinstance(signals, list)

    def test_generate_signals_with_history_breakout(self, backtest_service_with_mock_alpaca):
        """Test _generate_signals_with_history for breakout strategy"""
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=165.0, low=149.0, close=163.0,  # Breakout
                volume=2000000,  # High volume
            )
        }
        
        price_history = {"AAPL": [150.0 for _ in range(60)]}  # Stable prices
        portfolio = PortfolioState(100000)
        
        signals = backtest_service_with_mock_alpaca._generate_signals_with_history(
            strategy_type="breakout",
            parameters={"lookback": 20},
            market_data=market_data,
            price_history=price_history,
            portfolio=portfolio,
            current_date=date.today(),
        )
        
        assert isinstance(signals, list)

    def test_generate_signals_unknown_strategy_fallback(self, backtest_service_with_mock_alpaca):
        """Test signal generation with unknown strategy type"""
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=149.0, close=154.0,
                volume=1000000,
            )
        }
        
        price_history = {"AAPL": [150.0 for _ in range(60)]}
        portfolio = PortfolioState(100000)
        
        # Unknown strategy should fall back to momentum
        signals = backtest_service_with_mock_alpaca._generate_signals_with_history(
            strategy_type="unknown_strategy",
            parameters={},
            market_data=market_data,
            price_history=price_history,
            portfolio=portfolio,
            current_date=date.today(),
        )
        
        assert isinstance(signals, list)


# ============================================================================
# DATABASE METHODS TESTS
# ============================================================================

class TestBacktestHistory:
    """Tests for get_backtest_history method"""

    @pytest.mark.asyncio
    async def test_get_backtest_history_success(self, mock_db_session, mock_backtest_db_record):
        """Test successful history retrieval"""
        # Mock execute to return backtest records
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [mock_backtest_db_record]
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result
        
        # Mock strategy lookup
        mock_strategy_result = Mock()
        mock_strategy = Mock()
        mock_strategy.name = "Test Strategy"
        mock_strategy_result.scalar_one_or_none.return_value = mock_strategy
        
        mock_db_session.execute.side_effect = [mock_result, mock_strategy_result]
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        user_uuid = str(uuid4())
        history = await service.get_backtest_history(
            user_id=user_uuid,
            limit=10,
            offset=0,
        )
        
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_get_backtest_history_invalid_user_uuid(self, mock_db_session):
        """Test history with invalid user UUID"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        # Invalid UUID should return empty list
        history = await service.get_backtest_history(
            user_id="not-a-valid-uuid",
            limit=10,
            offset=0,
        )
        
        assert history == []

    @pytest.mark.asyncio
    async def test_get_backtest_history_invalid_strategy_uuid(self, mock_db_session):
        """Test history with invalid strategy UUID filter"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        user_uuid = str(uuid4())
        history = await service.get_backtest_history(
            user_id=user_uuid,
            strategy_id="not-a-valid-uuid",
            limit=10,
            offset=0,
        )
        
        # Invalid strategy UUID should return empty list
        assert history == []

    @pytest.mark.asyncio
    async def test_get_backtest_history_operational_error_test_mode(self, mock_db_session):
        """Test history gracefully handles missing tables in test mode"""
        mock_db_session.execute.side_effect = OperationalError(
            "no such table: backtests", params=None, orig=None
        )
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        user_uuid = str(uuid4())
        history = await service.get_backtest_history(user_id=user_uuid)
        
        # Should return empty list instead of raising
        assert history == []


class TestBacktestResult:
    """Tests for get_backtest_result method"""

    @pytest.mark.asyncio
    async def test_get_backtest_result_invalid_backtest_uuid(self, mock_db_session):
        """Test result retrieval with invalid backtest UUID"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.get_backtest_result(
            backtest_id="not-a-valid-uuid",
            user_id=str(uuid4()),
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_backtest_result_invalid_user_uuid(self, mock_db_session):
        """Test result retrieval with invalid user UUID"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.get_backtest_result(
            backtest_id=str(uuid4()),
            user_id="not-a-valid-uuid",
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_backtest_result_not_found(self, mock_db_session):
        """Test result retrieval when backtest not found"""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.get_backtest_result(
            backtest_id=str(uuid4()),
            user_id=str(uuid4()),
        )
        
        assert result is None


class TestDeleteBacktest:
    """Tests for delete_backtest method"""

    @pytest.mark.asyncio
    async def test_delete_backtest_invalid_uuid(self, mock_db_session):
        """Test delete with invalid backtest UUID"""
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.delete_backtest(
            backtest_id="not-a-valid-uuid",
            user_id=str(uuid4()),
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_backtest_not_found(self, mock_db_session):
        """Test delete when backtest not found"""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.delete_backtest(
            backtest_id=str(uuid4()),
            user_id=str(uuid4()),
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_backtest_success(self, mock_db_session, mock_backtest_db_record):
        """Test successful backtest deletion"""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_backtest_db_record
        mock_db_session.execute.return_value = mock_result
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        result = await service.delete_backtest(
            backtest_id=str(mock_backtest_db_record.id),
            user_id=str(mock_backtest_db_record.user_id),
        )
        
        assert result is True
        mock_db_session.delete.assert_called_once()
        mock_db_session.commit.assert_called_once()


# ============================================================================
# METRICS CALCULATION TESTS
# ============================================================================

class TestMetricsCalculation:
    """Tests for performance metrics calculation"""

    def test_calculate_metrics_no_trades(self, backtest_service_with_mock_alpaca):
        """Test metrics calculation with no trades"""
        equity_curve = [
            EquityPoint(date=date(2024, 1, 1), value=100000, cash=100000, positions_value=0),
            EquityPoint(date=date(2024, 12, 31), value=100000, cash=100000, positions_value=0),
        ]
        
        metrics = backtest_service_with_mock_alpaca.calculate_metrics(
            trades=[],
            equity_curve=equity_curve,
            initial_capital=100000,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        
        assert metrics.total_trades == 0
        assert metrics.total_return == 0.0

    def test_calculate_metrics_all_winning_trades(self, backtest_service_with_mock_alpaca):
        """Test metrics calculation with all winning trades"""
        trades = [
            Trade(
                symbol="AAPL", side="buy", quantity=100,
                entry_date=date(2024, 1, 15), entry_price=150.0,
                exit_date=date(2024, 1, 20), exit_price=160.0,
                pnl=1000.0, pnl_percent=6.67, commission=0.0,
            ),
            Trade(
                symbol="MSFT", side="buy", quantity=50,
                entry_date=date(2024, 2, 1), entry_price=300.0,
                exit_date=date(2024, 2, 10), exit_price=320.0,
                pnl=1000.0, pnl_percent=6.67, commission=0.0,
            ),
        ]
        
        equity_curve = [
            EquityPoint(date=date(2024, 1, 1), value=100000, cash=100000, positions_value=0),
            EquityPoint(date=date(2024, 12, 31), value=102000, cash=102000, positions_value=0),
        ]
        
        metrics = backtest_service_with_mock_alpaca.calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=100000,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        
        assert metrics.total_trades == 2
        assert metrics.win_rate == 100.0
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 0

    def test_calculate_metrics_all_losing_trades(self, backtest_service_with_mock_alpaca):
        """Test metrics calculation with all losing trades"""
        trades = [
            Trade(
                symbol="AAPL", side="buy", quantity=100,
                entry_date=date(2024, 1, 15), entry_price=160.0,
                exit_date=date(2024, 1, 20), exit_price=150.0,
                pnl=-1000.0, pnl_percent=-6.25, commission=0.0,
            ),
        ]
        
        equity_curve = [
            EquityPoint(date=date(2024, 1, 1), value=100000, cash=100000, positions_value=0),
            EquityPoint(date=date(2024, 12, 31), value=99000, cash=99000, positions_value=0),
        ]
        
        metrics = backtest_service_with_mock_alpaca.calculate_metrics(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=100000,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        
        assert metrics.total_trades == 1
        assert metrics.win_rate == 0.0
        assert metrics.losing_trades == 1


# ============================================================================
# MONTHLY RETURNS TESTS
# ============================================================================

class TestMonthlyReturns:
    """Tests for monthly returns calculation"""

    def test_calculate_monthly_returns_basic(self, backtest_service_with_mock_alpaca):
        """Test basic monthly returns calculation"""
        equity_curve = [
            EquityPoint(date=date(2024, 1, 1), value=100000, cash=100000, positions_value=0),
            EquityPoint(date=date(2024, 1, 15), value=101000, cash=101000, positions_value=0),
            EquityPoint(date=date(2024, 1, 31), value=102000, cash=102000, positions_value=0),
            EquityPoint(date=date(2024, 2, 15), value=103000, cash=103000, positions_value=0),
            EquityPoint(date=date(2024, 2, 28), value=104000, cash=104000, positions_value=0),
        ]
        
        # Use private method _calculate_monthly_returns
        monthly = backtest_service_with_mock_alpaca._calculate_monthly_returns(equity_curve)
        
        assert isinstance(monthly, list)
        # Should have returns for Jan and Feb
        assert len(monthly) >= 1

    def test_calculate_monthly_returns_empty_curve(self, backtest_service_with_mock_alpaca):
        """Test monthly returns with empty equity curve"""
        monthly = backtest_service_with_mock_alpaca._calculate_monthly_returns([])
        
        assert monthly == []


# ============================================================================
# TRADE EXECUTION TESTS
# ============================================================================

class TestTradeExecutionExtended:
    """Extended tests for trade execution"""

    def test_execute_signals_respects_max_position_size(
        self, backtest_service_with_mock_alpaca, mock_strategy
    ):
        """Test that signal execution respects max position size"""
        portfolio = PortfolioState(initial_capital=100000)
        
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=149.0, close=154.0,
                volume=1000000,
            )
        }
        
        signals = [
            {"action": "buy", "symbol": "AAPL", "confidence": 0.9, "reason": "test"}
        ]
        
        trades = backtest_service_with_mock_alpaca._execute_signals(
            signals, market_data, portfolio, mock_strategy
        )
        
        # Position should be limited by max_position_size (10% of 100000 = 10000)
        if trades:
            position_value = trades[0].quantity * trades[0].entry_price
            max_allowed = 100000 * float(mock_strategy.max_position_size)
            assert position_value <= max_allowed * 1.01  # Small tolerance

    def test_execute_signals_sell_with_no_position(
        self, backtest_service_with_mock_alpaca, mock_strategy
    ):
        """Test sell signal with no existing position"""
        portfolio = PortfolioState(initial_capital=100000)
        
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=149.0, close=154.0,
                volume=1000000,
            )
        }
        
        signals = [
            {"action": "sell", "symbol": "AAPL", "confidence": 0.9, "reason": "test"}
        ]
        
        trades = backtest_service_with_mock_alpaca._execute_signals(
            signals, market_data, portfolio, mock_strategy
        )
        
        # Should not execute sell with no position
        assert len(trades) == 0

    def test_execute_pending_signals(
        self, backtest_service_with_mock_alpaca, mock_strategy
    ):
        """Test _execute_pending_signals method"""
        portfolio = PortfolioState(initial_capital=100000)
        
        market_data = {
            "AAPL": MarketData(
                symbol="AAPL",
                timestamp=datetime.now(),
                open=150.0, high=155.0, low=149.0, close=154.0,
                volume=1000000,
            )
        }
        
        pending_signals = {
            "AAPL": {"action": "buy", "symbol": "AAPL", "confidence": 0.8, "reason": "momentum"}
        }
        
        trades = backtest_service_with_mock_alpaca._execute_pending_signals(
            pending_signals, market_data, portfolio, mock_strategy
        )
        
        assert isinstance(trades, list)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_portfolio_state_negative_initial_capital(self):
        """Test portfolio with negative initial capital (should still work)"""
        # This is technically invalid but should not crash
        portfolio = PortfolioState(initial_capital=-1000)
        assert portfolio.cash == -1000
        assert portfolio.total_equity == -1000

    def test_portfolio_state_zero_initial_capital(self):
        """Test portfolio with zero initial capital"""
        portfolio = PortfolioState(initial_capital=0)
        assert portfolio.cash == 0
        assert portfolio.total_equity == 0

    @pytest.mark.asyncio
    async def test_get_history_with_strategy_filter(self, mock_db_session, mock_backtest_db_record):
        """Test history retrieval with strategy ID filter"""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result
        
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "testing"}):
            service = BacktestService(mock_db_session)
        
        user_uuid = str(uuid4())
        strategy_uuid = str(uuid4())
        
        history = await service.get_backtest_history(
            user_id=user_uuid,
            strategy_id=strategy_uuid,
            limit=10,
            offset=0,
        )
        
        assert isinstance(history, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
