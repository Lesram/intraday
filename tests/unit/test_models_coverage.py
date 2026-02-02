"""
Comprehensive tests for backend.models modules

Tests all Pydantic models for request/response validation.
Target: 0% → 85%+ coverage for:
- backend/models/backtest.py (178 lines)
- backend/models/ml_models.py (512 lines)
"""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4, UUID

from backend.models.backtest import (
    BacktestRequest,
    EquityPoint,
    Trade,
    PerformanceMetrics,
    BacktestResult,
    BacktestSummary,
)

from backend.models.ml_models import (
    ModelType,
    ModelStatus,
    TrainingStatus,
    ModelTrainingRequest,
    ModelActivationRequest,
    ModelComparisonRequest,
    PredictionRequest,
    ModelMetrics,
    FeatureImportance,
)


class TestBacktestRequest:
    """Test BacktestRequest model"""
    
    def test_backtest_request_valid(self):
        """Test valid backtest request"""
        request = BacktestRequest(
            strategy_id="strategy_123",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=10000.0
        )
        
        assert request.strategy_id == "strategy_123"
        assert request.initial_capital == 10000.0
    
    def test_backtest_request_with_parameters(self):
        """Test backtest request with custom parameters"""
        params = {"fast_period": 12, "slow_period": 26}
        request = BacktestRequest(
            strategy_id="strategy_123",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=50000.0,
            parameters=params
        )
        
        assert request.parameters == params
    
    def test_backtest_request_capital_limits(self):
        """Test capital validation"""
        # Below minimum
        with pytest.raises(ValueError):
            BacktestRequest(
                strategy_id="s1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 2, 1),
                initial_capital=500.0  # Below 1000 minimum
            )
        
        # Above maximum
        with pytest.raises(ValueError):
            BacktestRequest(
                strategy_id="s1",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 2, 1),
                initial_capital=20_000_000.0  # Above 10M maximum
            )
    
    def test_backtest_request_end_before_start(self):
        """Test validation fails when end_date < start_date"""
        with pytest.raises(ValueError, match="must be after start_date"):
            BacktestRequest(
                strategy_id="s1",
                start_date=date(2024, 6, 1),
                end_date=date(2024, 1, 1),  # Before start
                initial_capital=10000.0
            )
    
    def test_backtest_request_future_end_date(self):
        """Test validation fails for future end_date"""
        with pytest.raises(ValueError, match="cannot be in the future"):
            BacktestRequest(
                strategy_id="s1",
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),  # Future
                initial_capital=10000.0
            )
    
    def test_backtest_request_duration_too_long(self):
        """Test validation fails for backtest > 5 years"""
        with pytest.raises(ValueError, match="Maximum backtest duration is 5 years"):
            BacktestRequest(
                strategy_id="s1",
                start_date=date(2018, 1, 1),
                end_date=date(2025, 1, 1),  # > 5 years
                initial_capital=10000.0
            )


class TestEquityPoint:
    """Test EquityPoint model"""
    
    def test_equity_point_creation(self):
        """Test creating equity point"""
        point = EquityPoint(
            date=date(2024, 1, 1),
            value=10500.0,
            cash=5000.0,
            positions_value=5500.0
        )
        
        assert point.value == 10500.0
        assert point.cash == 5000.0
        assert point.positions_value == 5500.0


class TestTrade:
    """Test Trade model"""
    
    def test_trade_complete(self):
        """Test complete trade with entry and exit"""
        trade = Trade(
            symbol="AAPL",
            side="buy",
            quantity=10,
            entry_date=date(2024, 1, 1),
            entry_price=150.0,
            exit_date=date(2024, 1, 10),
            exit_price=160.0,
            pnl=100.0,
            pnl_percent=6.67,
            duration_days=9,
            commission=2.0
        )
        
        assert trade.symbol == "AAPL"
        assert trade.quantity == 10
        assert trade.pnl == 100.0
    
    def test_trade_open_position(self):
        """Test open trade without exit"""
        trade = Trade(
            symbol="MSFT",
            side="sell",
            quantity=5,
            entry_date=date(2024, 1, 1),
            entry_price=300.0,
            commission=1.5
        )
        
        assert trade.exit_date is None
        assert trade.exit_price is None
        assert trade.pnl is None


class TestPerformanceMetrics:
    """Test PerformanceMetrics model"""
    
    def test_performance_metrics_complete(self):
        """Test complete performance metrics"""
        metrics = PerformanceMetrics(
            total_return=25.5,
            annualized_return=15.2,
            sharpe_ratio=1.8,
            sortino_ratio=2.1,
            calmar_ratio=3.5,
            max_drawdown=-8.5,
            max_drawdown_duration_days=45,
            volatility=12.3,
            total_trades=100,
            winning_trades=65,
            losing_trades=35,
            win_rate=65.0,
            profit_factor=2.1,
            avg_trade_pnl=25.5,
            avg_win=50.0,
            avg_loss=-25.0,
            largest_win=200.0,
            largest_loss=-100.0,
            max_consecutive_wins=8,
            max_consecutive_losses=4,
            total_commission=50.0,
            avg_trade_duration_days=3.5
        )
        
        assert metrics.total_return == 25.5
        assert metrics.win_rate == 65.0
        assert metrics.profit_factor == 2.1
    
    def test_performance_metrics_with_benchmark(self):
        """Test metrics with benchmark comparison"""
        metrics = PerformanceMetrics(
            total_return=20.0,
            annualized_return=12.0,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            calmar_ratio=2.5,
            max_drawdown=-10.0,
            max_drawdown_duration_days=30,
            volatility=15.0,
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=60.0,
            profit_factor=1.8,
            avg_trade_pnl=20.0,
            avg_win=40.0,
            avg_loss=-20.0,
            largest_win=150.0,
            largest_loss=-80.0,
            max_consecutive_wins=5,
            max_consecutive_losses=3,
            alpha=5.0,  # Outperformance vs benchmark
            beta=0.8,    # Lower volatility than market
            avg_trade_duration_days=5.2
        )
        
        assert metrics.alpha == 5.0
        assert metrics.beta == 0.8


class TestBacktestResult:
    """Test BacktestResult model"""
    
    def test_backtest_result_complete(self):
        """Test complete backtest result"""
        metrics = PerformanceMetrics(
            total_return=15.0,
            annualized_return=10.0,
            sharpe_ratio=1.2,
            sortino_ratio=1.5,
            calmar_ratio=2.0,
            max_drawdown=-5.0,
            max_drawdown_duration_days=20,
            volatility=10.0,
            total_trades=25,
            winning_trades=15,
            losing_trades=10,
            win_rate=60.0,
            profit_factor=1.5,
            avg_trade_pnl=15.0,
            avg_win=30.0,
            avg_loss=-15.0,
            largest_win=100.0,
            largest_loss=-50.0,
            max_consecutive_wins=4,
            max_consecutive_losses=2,
            avg_trade_duration_days=4.0
        )
        
        result = BacktestResult(
            id="bt_123",
            strategy_id="strat_456",
            strategy_name="Test Strategy",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=10000.0,
            final_equity=11500.0,
            metrics=metrics,
            equity_curve=[],
            trade_log=[],
            monthly_returns=[],
            status="completed",
            created_at=datetime(2024, 1, 1),
            completed_at=datetime(2024, 1, 1, 1, 0)
        )
        
        assert result.final_equity == 11500.0
        assert result.status == "completed"
    
    def test_backtest_result_duration_days(self):
        """Test duration_days property"""
        metrics = PerformanceMetrics(
            total_return=10.0,
            annualized_return=8.0,
            sharpe_ratio=1.0,
            sortino_ratio=1.2,
            calmar_ratio=1.5,
            max_drawdown=-3.0,
            max_drawdown_duration_days=10,
            volatility=8.0,
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=60.0,
            profit_factor=1.5,
            avg_trade_pnl=10.0,
            avg_win=20.0,
            avg_loss=-10.0,
            largest_win=50.0,
            largest_loss=-30.0,
            max_consecutive_wins=3,
            max_consecutive_losses=2,
            avg_trade_duration_days=3.0
        )
        
        result = BacktestResult(
            id="bt_123",
            strategy_id="strat_456",
            strategy_name="Test",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),  # 91 days
            initial_capital=10000.0,
            final_equity=11000.0,
            metrics=metrics,
            equity_curve=[],
            trade_log=[],
            monthly_returns=[],
            status="completed",
            created_at=datetime(2024, 1, 1)
        )
        
        assert result.duration_days == 91
    
    def test_backtest_result_trades_per_day(self):
        """Test trades_per_day property"""
        metrics = PerformanceMetrics(
            total_return=10.0,
            annualized_return=8.0,
            sharpe_ratio=1.0,
            sortino_ratio=1.2,
            calmar_ratio=1.5,
            max_drawdown=-3.0,
            max_drawdown_duration_days=10,
            volatility=8.0,
            total_trades=30,  # 30 trades
            winning_trades=18,
            losing_trades=12,
            win_rate=60.0,
            profit_factor=1.5,
            avg_trade_pnl=10.0,
            avg_win=20.0,
            avg_loss=-10.0,
            largest_win=50.0,
            largest_loss=-30.0,
            max_consecutive_wins=3,
            max_consecutive_losses=2,
            avg_trade_duration_days=3.0
        )
        
        result = BacktestResult(
            id="bt_123",
            strategy_id="strat_456",
            strategy_name="Test",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),  # 30 days
            initial_capital=10000.0,
            final_equity=11000.0,
            metrics=metrics,
            equity_curve=[],
            trade_log=[],
            monthly_returns=[],
            status="completed",
            created_at=datetime(2024, 1, 1)
        )
        
        assert result.trades_per_day == 1.0  # 30 trades in 30 days


class TestBacktestSummary:
    """Test BacktestSummary model"""
    
    def test_backtest_summary(self):
        """Test backtest summary creation"""
        from datetime import datetime
        summary = BacktestSummary(
            id="bt_789",
            strategy_id="strat_123",
            strategy_name="MA Crossover",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=25000.0,
            status="completed",
            created_at=datetime.now()
        )
        
        assert summary.strategy_name == "MA Crossover"
        assert summary.initial_capital == 25000.0


# ============================================================================
# ML MODELS TESTS
# ============================================================================

class TestModelEnums:
    """Test ML model enums"""
    
    def test_model_type_enum(self):
        """Test ModelType enum values"""
        assert ModelType.ENSEMBLE.value == "ensemble"
        assert ModelType.LSTM.value == "lstm"
        assert ModelType.XGBOOST.value == "xgboost"
        assert ModelType.RANDOM_FOREST.value == "random_forest"
    
    def test_model_status_enum(self):
        """Test ModelStatus enum values"""
        assert ModelStatus.TRAINING.value == "training"
        assert ModelStatus.READY.value == "ready"
        assert ModelStatus.FAILED.value == "failed"
        assert ModelStatus.INACTIVE.value == "inactive"
    
    def test_training_status_enum(self):
        """Test TrainingStatus enum values"""
        assert TrainingStatus.PENDING.value == "pending"
        assert TrainingStatus.RUNNING.value == "running"
        assert TrainingStatus.COMPLETED.value == "completed"
        assert TrainingStatus.FAILED.value == "failed"


class TestModelTrainingRequest:
    """Test ModelTrainingRequest model"""
    
    def test_training_request_minimal(self):
        """Test training request with minimal fields"""
        request = ModelTrainingRequest(
            model_type=ModelType.ENSEMBLE,
            model_name="test_model"
        )
        
        assert request.model_type == ModelType.ENSEMBLE
        assert request.model_name == "test_model"
        assert request.lookback_days == 90  # Default
        assert request.test_size == 0.2  # Default
    
    def test_training_request_complete(self):
        """Test training request with all fields"""
        request = ModelTrainingRequest(
            model_type=ModelType.XGBOOST,
            model_name="xgb_price_predictor",
            features=["technical", "sentiment", "volume"],
            symbols=["AAPL", "GOOGL", "MSFT"],
            lookback_days=120,
            test_size=0.25,
            hyperparameters={"n_estimators": 100, "max_depth": 10},
            retrain=True
        )
        
        assert len(request.features) == 3
        assert len(request.symbols) == 3
        assert request.lookback_days == 120
        assert request.retrain is True


class TestModelActivationRequest:
    """Test ModelActivationRequest model"""
    
    def test_activation_request(self):
        """Test model activation request"""
        request = ModelActivationRequest(active=True)
        assert request.active is True
        
        request = ModelActivationRequest(active=False)
        assert request.active is False


class TestModelComparisonRequest:
    """Test ModelComparisonRequest model"""
    
    def test_comparison_request(self):
        """Test model comparison request"""
        model_ids = [uuid4(), uuid4(), uuid4()]
        request = ModelComparisonRequest(
            model_ids=model_ids,
            metric="f1_score"
        )
        
        assert len(request.model_ids) == 3
        assert request.metric == "f1_score"


class TestPredictionRequest:
    """Test PredictionRequest model"""
    
    def test_prediction_request_simple(self):
        """Test simple prediction request"""
        request = PredictionRequest(
            symbol="AAPL"
        )
        
        assert request.symbol == "AAPL"
        assert request.model_id is None
    
    def test_prediction_request_with_model(self):
        """Test prediction request with specific model"""
        model_id = uuid4()
        request = PredictionRequest(
            symbol="MSFT",
            model_id=model_id,
            data={"feature1": 1.5, "feature2": 2.3}
        )
        
        assert request.model_id == model_id
        assert request.data["feature1"] == 1.5


class TestModelMetrics:
    """Test ModelMetrics model"""
    
    def test_model_metrics_classification(self):
        """Test classification metrics"""
        metrics = ModelMetrics(
            accuracy=0.85,
            precision=0.83,
            recall=0.87,
            f1_score=0.85,
            training_time=120.5,
            inference_time=15.2
        )
        
        assert metrics.accuracy == 0.85
        assert metrics.f1_score == 0.85
    
    def test_model_metrics_regression(self):
        """Test regression metrics"""
        metrics = ModelMetrics(
            mae=1.23,
            rmse=1.87,
            r2_score=0.92,
            mape=3.5,
            training_time=245.5,
            inference_time=12.3
        )
        
        assert metrics.mae == 1.23
        assert metrics.r2_score == 0.92
    
    def test_model_metrics_with_custom(self):
        """Test metrics with custom fields"""
        metrics = ModelMetrics(
            accuracy=0.90,
            custom_metrics={
                "custom_score": 0.88,
                "business_metric": 1500.0
            }
        )
        
        assert metrics.custom_metrics["custom_score"] == 0.88


class TestFeatureImportance:
    """Test FeatureImportance model"""
    
    def test_feature_importance(self):
        """Test feature importance creation"""
        importance = FeatureImportance(
            feature_name="volume",
            importance=0.25,
            rank=1
        )
        
        assert importance.feature_name == "volume"
        assert importance.importance == 0.25
        assert importance.rank == 1
