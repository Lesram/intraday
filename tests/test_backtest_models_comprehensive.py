"""
Comprehensive tests for Backtest Models
Tests Pydantic models for backtest request/response validation
"""

import pytest
from datetime import date, datetime, timedelta
from pydantic import ValidationError

from backend.models.backtest import (
    BacktestRequest,
    EquityPoint,
    Trade,
    PerformanceMetrics,
    BacktestResult,
)


class TestBacktestRequest:
    """Test BacktestRequest model"""
    
    def test_valid_request(self):
        """Test valid backtest request"""
        request = BacktestRequest(
            strategy_id="momentum_v1",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0
        )
        
        assert request.strategy_id == "momentum_v1"
        assert request.start_date == date(2024, 1, 1)
        assert request.initial_capital == 100000.0
        
    def test_with_parameters(self):
        """Test request with strategy parameters"""
        request = BacktestRequest(
            strategy_id="momentum_v1",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            parameters={"lookback": 20, "threshold": 0.02}
        )
        
        assert request.parameters["lookback"] == 20
        
    def test_minimum_capital(self):
        """Test minimum capital is 1000"""
        with pytest.raises(ValidationError):
            BacktestRequest(
                strategy_id="test",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=500.0  # Below minimum
            )
            
    def test_maximum_capital(self):
        """Test maximum capital is 10 million"""
        with pytest.raises(ValidationError):
            BacktestRequest(
                strategy_id="test",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=20_000_000.0  # Above maximum
            )
            
    def test_future_end_date_rejected(self):
        """Test future end date is rejected"""
        future_date = date.today() + timedelta(days=30)
        
        with pytest.raises(ValidationError, match="cannot be in the future"):
            BacktestRequest(
                strategy_id="test",
                start_date=date(2024, 1, 1),
                end_date=future_date,
                initial_capital=100000.0
            )
            
    def test_end_before_start_rejected(self):
        """Test end date before start date is rejected"""
        with pytest.raises(ValidationError, match="must be after start_date"):
            BacktestRequest(
                strategy_id="test",
                start_date=date(2024, 6, 30),
                end_date=date(2024, 1, 1),  # Before start
                initial_capital=100000.0
            )
            
    def test_max_duration_5_years(self):
        """Test maximum duration is 5 years"""
        with pytest.raises(ValidationError, match="Maximum backtest duration"):
            BacktestRequest(
                strategy_id="test",
                start_date=date(2018, 1, 1),
                end_date=date(2024, 1, 1),  # 6 years
                initial_capital=100000.0
            )


class TestEquityPoint:
    """Test EquityPoint model"""
    
    def test_valid_equity_point(self):
        """Test valid equity point creation"""
        point = EquityPoint(
            date=date(2024, 6, 15),
            value=105000.0,
            cash=25000.0,
            positions_value=80000.0
        )
        
        assert point.date == date(2024, 6, 15)
        assert point.value == 105000.0
        assert point.cash == 25000.0
        assert point.positions_value == 80000.0
        
    def test_value_components(self):
        """Test value approximately equals cash + positions"""
        point = EquityPoint(
            date=date(2024, 6, 15),
            value=100000.0,
            cash=50000.0,
            positions_value=50000.0
        )
        
        # Value should be cash + positions_value
        assert point.value == point.cash + point.positions_value


class TestTrade:
    """Test Trade model"""
    
    def test_open_trade(self):
        """Test creating an open trade"""
        trade = Trade(
            symbol="AAPL",
            side="buy",
            quantity=100,
            entry_date=date(2024, 1, 15),
            entry_price=150.0
        )
        
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 100
        assert trade.exit_date is None
        assert trade.pnl is None
        
    def test_closed_trade(self):
        """Test creating a closed trade"""
        trade = Trade(
            symbol="AAPL",
            side="buy",
            quantity=100,
            entry_date=date(2024, 1, 15),
            entry_price=150.0,
            exit_date=date(2024, 2, 15),
            exit_price=165.0,
            pnl=1500.0,
            pnl_percent=10.0,
            duration_days=31
        )
        
        assert trade.exit_date == date(2024, 2, 15)
        assert trade.exit_price == 165.0
        assert trade.pnl == 1500.0
        assert trade.pnl_percent == 10.0
        assert trade.duration_days == 31
        
    def test_with_commission(self):
        """Test trade with commission"""
        trade = Trade(
            symbol="AAPL",
            side="buy",
            quantity=100,
            entry_date=date(2024, 1, 15),
            entry_price=150.0,
            commission=5.0
        )
        
        assert trade.commission == 5.0
        
    def test_default_commission_zero(self):
        """Test default commission is zero"""
        trade = Trade(
            symbol="AAPL",
            side="buy",
            quantity=100,
            entry_date=date(2024, 1, 15),
            entry_price=150.0
        )
        
        assert trade.commission == 0.0


class TestPerformanceMetrics:
    """Test PerformanceMetrics model"""
    
    def test_complete_metrics(self):
        """Test creating complete performance metrics"""
        metrics = PerformanceMetrics(
            total_return=25.5,
            annualized_return=12.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            max_drawdown=8.5,
            max_drawdown_duration_days=45,
            volatility=15.0,
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=60.0,
            profit_factor=2.5,
            avg_trade_pnl=250.0,
            avg_win=500.0,
            avg_loss=-200.0,
            largest_win=2000.0,
            largest_loss=-800.0,
            max_consecutive_wins=8,
            max_consecutive_losses=4,
            avg_trade_duration_days=5.5
        )
        
        assert metrics.total_return == 25.5
        assert metrics.sharpe_ratio == 1.5
        assert metrics.win_rate == 60.0
        assert metrics.profit_factor == 2.5
        
    def test_optional_benchmark_fields(self):
        """Test optional alpha and beta fields"""
        metrics = PerformanceMetrics(
            total_return=25.5,
            annualized_return=12.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            max_drawdown=8.5,
            max_drawdown_duration_days=45,
            volatility=15.0,
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=60.0,
            profit_factor=2.5,
            avg_trade_pnl=250.0,
            avg_win=500.0,
            avg_loss=-200.0,
            largest_win=2000.0,
            largest_loss=-800.0,
            max_consecutive_wins=8,
            max_consecutive_losses=4,
            avg_trade_duration_days=5.5,
            alpha=5.0,
            beta=0.8
        )
        
        assert metrics.alpha == 5.0
        assert metrics.beta == 0.8
        
    def test_default_commission_zero(self):
        """Test default total commission is zero"""
        metrics = PerformanceMetrics(
            total_return=25.5,
            annualized_return=12.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            max_drawdown=8.5,
            max_drawdown_duration_days=45,
            volatility=15.0,
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=60.0,
            profit_factor=2.5,
            avg_trade_pnl=250.0,
            avg_win=500.0,
            avg_loss=-200.0,
            largest_win=2000.0,
            largest_loss=-800.0,
            max_consecutive_wins=8,
            max_consecutive_losses=4,
            avg_trade_duration_days=5.5
        )
        
        assert metrics.total_commission == 0.0


class TestBacktestResult:
    """Test BacktestResult model"""
    
    @pytest.fixture
    def sample_metrics(self):
        """Create sample performance metrics"""
        return PerformanceMetrics(
            total_return=25.5,
            annualized_return=12.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=3.0,
            max_drawdown=8.5,
            max_drawdown_duration_days=45,
            volatility=15.0,
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            win_rate=60.0,
            profit_factor=2.5,
            avg_trade_pnl=250.0,
            avg_win=500.0,
            avg_loss=-200.0,
            largest_win=2000.0,
            largest_loss=-800.0,
            max_consecutive_wins=8,
            max_consecutive_losses=4,
            avg_trade_duration_days=5.5
        )
        
    def test_complete_result(self, sample_metrics):
        """Test creating complete backtest result"""
        result = BacktestResult(
            id="bt_123456",
            strategy_id="momentum_v1",
            strategy_name="Momentum Strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            final_equity=125500.0,
            metrics=sample_metrics,
            equity_curve=[
                EquityPoint(date=date(2024, 1, 1), value=100000, cash=100000, positions_value=0)
            ],
            trade_log=[],
            monthly_returns=[{"month": "2024-01", "return": 5.2}],
            status="completed",
            created_at=datetime.now()
        )
        
        assert result.id == "bt_123456"
        assert result.strategy_name == "Momentum Strategy"
        assert result.initial_capital == 100000.0
        assert result.final_equity == 125500.0
        assert result.metrics.total_return == 25.5
        assert result.status == "completed"
        
    def test_result_profit_calculation(self, sample_metrics):
        """Test result shows profit correctly"""
        result = BacktestResult(
            id="bt_123456",
            strategy_id="momentum_v1",
            strategy_name="Momentum Strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            final_equity=125500.0,
            metrics=sample_metrics,
            equity_curve=[],
            trade_log=[],
            monthly_returns=[],
            status="completed",
            created_at=datetime.now()
        )
        
        profit = result.final_equity - result.initial_capital
        assert profit == 25500.0
