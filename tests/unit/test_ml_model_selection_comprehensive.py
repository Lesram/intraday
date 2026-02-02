"""
Comprehensive tests for backend/ml/model_selection.py
Targets: BacktestEvalResult, time_split_by_fraction, positions_from_predictions,
         simulate_pnl_long_flat, compute_backtest_metrics, evaluate_model_on_ohlcv,
         evaluate_baseline_buy_and_hold
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from backend.ml.model_selection import (
    BacktestEvalResult,
    time_split_by_fraction,
    positions_from_predictions,
    simulate_pnl_long_flat,
    compute_backtest_metrics,
    evaluate_model_on_ohlcv,
    evaluate_baseline_buy_and_hold,
    _to_numpy_float,
)


# =============================================================================
# BacktestEvalResult Tests
# =============================================================================
class TestBacktestEvalResult:
    """Tests for BacktestEvalResult dataclass."""

    def test_basic_creation(self):
        """Test creating BacktestEvalResult with all fields."""
        result = BacktestEvalResult(
            n_samples=100,
            total_return=0.15,
            cagr=0.12,
            sharpe=1.5,
            max_drawdown=-0.10,
        )
        assert result.n_samples == 100
        assert result.total_return == 0.15
        assert result.cagr == 0.12
        assert result.sharpe == 1.5
        assert result.max_drawdown == -0.10

    def test_is_frozen(self):
        """Test that dataclass is frozen (immutable)."""
        result = BacktestEvalResult(
            n_samples=100,
            total_return=0.15,
            cagr=0.12,
            sharpe=1.5,
            max_drawdown=-0.10,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.n_samples = 200

    def test_zero_values(self):
        """Test with zero values."""
        result = BacktestEvalResult(
            n_samples=0,
            total_return=0.0,
            cagr=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
        )
        assert result.n_samples == 0
        assert result.total_return == 0.0

    def test_negative_values(self):
        """Test with negative return values."""
        result = BacktestEvalResult(
            n_samples=50,
            total_return=-0.25,
            cagr=-0.15,
            sharpe=-0.5,
            max_drawdown=-0.30,
        )
        assert result.total_return == -0.25
        assert result.max_drawdown == -0.30


# =============================================================================
# _to_numpy_float Tests
# =============================================================================
class TestToNumpyFloat:
    """Tests for _to_numpy_float helper function."""

    def test_series_to_numpy(self):
        """Test converting pandas Series to numpy array."""
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _to_numpy_float(series)
        assert isinstance(result, np.ndarray)
        assert result.dtype == float
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0, 4.0, 5.0])

    def test_series_with_int_values(self):
        """Test converting integer Series to float array."""
        series = pd.Series([1, 2, 3, 4, 5])
        result = _to_numpy_float(series)
        assert result.dtype == float

    def test_empty_series(self):
        """Test converting empty Series."""
        series = pd.Series([], dtype=float)
        result = _to_numpy_float(series)
        assert len(result) == 0
        assert result.dtype == float


# =============================================================================
# time_split_by_fraction Tests
# =============================================================================
class TestTimeSplitByFraction:
    """Tests for time_split_by_fraction function."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame with datetime index."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        return pd.DataFrame({"value": range(100)}, index=dates)

    def test_basic_split(self, sample_df):
        """Test basic time split."""
        train_df, eval_df = time_split_by_fraction(sample_df, 0.2)
        assert len(train_df) == 80
        assert len(eval_df) == 20

    def test_split_preserves_order(self, sample_df):
        """Test that split preserves chronological order."""
        train_df, eval_df = time_split_by_fraction(sample_df, 0.2)
        # Train should have earlier dates
        assert train_df.index[-1] < eval_df.index[0]

    def test_various_fractions(self, sample_df):
        """Test with various eval fractions."""
        for frac in [0.1, 0.2, 0.3, 0.5]:
            train_df, eval_df = time_split_by_fraction(sample_df, frac)
            expected_eval = max(1, int(round(100 * frac)))
            expected_train = max(1, 100 - expected_eval)
            assert len(train_df) == expected_train
            assert len(eval_df) == expected_eval

    def test_invalid_fraction_zero(self, sample_df):
        """Test that fraction of 0 raises ValueError."""
        with pytest.raises(ValueError, match="eval_fraction must be in"):
            time_split_by_fraction(sample_df, 0.0)

    def test_invalid_fraction_one(self, sample_df):
        """Test that fraction of 1 raises ValueError."""
        with pytest.raises(ValueError, match="eval_fraction must be in"):
            time_split_by_fraction(sample_df, 1.0)

    def test_invalid_fraction_negative(self, sample_df):
        """Test that negative fraction raises ValueError."""
        with pytest.raises(ValueError, match="eval_fraction must be in"):
            time_split_by_fraction(sample_df, -0.1)

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        empty_df = pd.DataFrame()
        train_df, eval_df = time_split_by_fraction(empty_df, 0.2)
        assert train_df.empty
        assert eval_df.empty

    def test_none_dataframe(self):
        """Test with None DataFrame."""
        train_df, eval_df = time_split_by_fraction(None, 0.2)
        assert train_df is None
        assert eval_df is None

    def test_small_dataframe(self):
        """Test with very small DataFrame."""
        small_df = pd.DataFrame({"value": [1, 2, 3]}, index=pd.date_range("2024-01-01", periods=3))
        train_df, eval_df = time_split_by_fraction(small_df, 0.3)
        assert len(train_df) >= 1
        assert len(eval_df) >= 1


# =============================================================================
# positions_from_predictions Tests
# =============================================================================
class TestPositionsFromPredictions:
    """Tests for positions_from_predictions function."""

    def test_direction_up_above_threshold(self):
        """Test direction_up predictions above threshold."""
        predictions = np.array([0.7, 0.8, 0.9, 0.6])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="direction_up",
            prob_threshold=0.5,
        )
        np.testing.assert_array_equal(positions, [1.0, 1.0, 1.0, 1.0])

    def test_direction_up_below_threshold(self):
        """Test direction_up predictions below threshold."""
        predictions = np.array([0.3, 0.2, 0.1, 0.4])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="direction_up",
            prob_threshold=0.5,
        )
        np.testing.assert_array_equal(positions, [0.0, 0.0, 0.0, 0.0])

    def test_direction_up_mixed(self):
        """Test direction_up with mixed predictions."""
        predictions = np.array([0.3, 0.7, 0.4, 0.6, 0.5])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="direction_up",
            prob_threshold=0.5,
        )
        np.testing.assert_array_equal(positions, [0.0, 1.0, 0.0, 1.0, 1.0])

    def test_direction_up_custom_threshold(self):
        """Test direction_up with custom threshold."""
        predictions = np.array([0.6, 0.7, 0.8, 0.9])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="direction_up",
            prob_threshold=0.75,
        )
        np.testing.assert_array_equal(positions, [0.0, 0.0, 1.0, 1.0])

    def test_next_close_passthrough(self):
        """Test next_close predictions pass through unchanged."""
        predictions = np.array([100.0, 105.0, 102.0, 108.0])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="next_close",
        )
        np.testing.assert_array_equal(positions, predictions)

    def test_empty_predictions(self):
        """Test with empty predictions."""
        predictions = np.array([])
        positions = positions_from_predictions(
            predictions=predictions,
            target_kind="direction_up",
        )
        assert len(positions) == 0


# =============================================================================
# simulate_pnl_long_flat Tests
# =============================================================================
class TestSimulatePnlLongFlat:
    """Tests for simulate_pnl_long_flat function."""

    @pytest.fixture
    def sample_data(self):
        """Create sample close/next_close data."""
        dates = pd.date_range("2024-01-01", periods=5)
        close = pd.Series([100.0, 102.0, 101.0, 103.0, 105.0], index=dates)
        next_close = pd.Series([102.0, 101.0, 103.0, 105.0, 104.0], index=dates)
        return close, next_close

    def test_all_long_position(self, sample_data):
        """Test PnL with all long positions."""
        close, next_close = sample_data
        positions = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        
        pnl = simulate_pnl_long_flat(
            close=close,
            next_close=next_close,
            position_long=positions,
            transaction_cost_bps=0.0,
        )
        
        assert len(pnl) == 5
        # First return: (102-100)/100 = 0.02
        assert abs(pnl.iloc[0] - 0.02) < 1e-9

    def test_all_flat_position(self, sample_data):
        """Test PnL with all flat positions (no trades)."""
        close, next_close = sample_data
        positions = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        
        pnl = simulate_pnl_long_flat(
            close=close,
            next_close=next_close,
            position_long=positions,
            transaction_cost_bps=0.0,
        )
        
        assert len(pnl) == 5
        np.testing.assert_array_almost_equal(pnl.values, [0.0, 0.0, 0.0, 0.0, 0.0])

    def test_with_transaction_costs(self, sample_data):
        """Test PnL with transaction costs."""
        close, next_close = sample_data
        positions = np.array([1.0, 0.0, 1.0, 0.0, 1.0])  # Alternating positions
        
        pnl_no_cost = simulate_pnl_long_flat(
            close=close,
            next_close=next_close,
            position_long=positions,
            transaction_cost_bps=0.0,
        )
        
        pnl_with_cost = simulate_pnl_long_flat(
            close=close,
            next_close=next_close,
            position_long=positions,
            transaction_cost_bps=10.0,  # 10 bps
        )
        
        # PnL with costs should be less than without costs
        assert pnl_with_cost.sum() < pnl_no_cost.sum()

    def test_none_close_raises(self):
        """Test that None close raises ValueError."""
        next_close = pd.Series([102.0, 103.0])
        positions = np.array([1.0, 1.0])
        
        with pytest.raises(ValueError, match="close and next_close are required"):
            simulate_pnl_long_flat(
                close=None,
                next_close=next_close,
                position_long=positions,
            )

    def test_none_next_close_raises(self):
        """Test that None next_close raises ValueError."""
        close = pd.Series([100.0, 102.0])
        positions = np.array([1.0, 1.0])
        
        with pytest.raises(ValueError, match="close and next_close are required"):
            simulate_pnl_long_flat(
                close=close,
                next_close=None,
                position_long=positions,
            )

    def test_length_mismatch_raises(self, sample_data):
        """Test that position length mismatch raises ValueError."""
        close, next_close = sample_data
        positions = np.array([1.0, 1.0])  # Too short
        
        with pytest.raises(ValueError, match="position_long length must match"):
            simulate_pnl_long_flat(
                close=close,
                next_close=next_close,
                position_long=positions,
            )


# =============================================================================
# compute_backtest_metrics Tests
# =============================================================================
class TestComputeBacktestMetrics:
    """Tests for compute_backtest_metrics function."""

    def test_positive_returns(self):
        """Test metrics with positive returns."""
        returns = pd.Series([0.01, 0.02, 0.01, 0.02, 0.01])
        result = compute_backtest_metrics(returns)
        
        assert result.n_samples == 5
        assert result.total_return > 0
        assert result.cagr > 0
        assert result.sharpe > 0
        assert result.max_drawdown <= 0  # Drawdowns are negative or zero

    def test_negative_returns(self):
        """Test metrics with negative returns."""
        returns = pd.Series([-0.01, -0.02, -0.01, -0.02, -0.01])
        result = compute_backtest_metrics(returns)
        
        assert result.n_samples == 5
        assert result.total_return < 0
        assert result.cagr < 0
        assert result.sharpe < 0
        assert result.max_drawdown < 0

    def test_mixed_returns(self):
        """Test metrics with mixed returns."""
        returns = pd.Series([0.02, -0.01, 0.03, -0.02, 0.01])
        result = compute_backtest_metrics(returns)
        
        assert result.n_samples == 5
        assert result.max_drawdown <= 0

    def test_empty_returns(self):
        """Test metrics with empty returns."""
        returns = pd.Series([], dtype=float)
        result = compute_backtest_metrics(returns)
        
        assert result.n_samples == 0
        assert result.total_return == 0.0
        assert result.cagr == 0.0
        assert result.sharpe == 0.0
        assert result.max_drawdown == 0.0

    def test_none_returns(self):
        """Test metrics with None returns."""
        result = compute_backtest_metrics(None)
        
        assert result.n_samples == 0
        assert result.total_return == 0.0

    def test_zero_volatility(self):
        """Test metrics with zero volatility (constant returns)."""
        returns = pd.Series([0.01, 0.01, 0.01, 0.01, 0.01])
        result = compute_backtest_metrics(returns)
        
        assert result.n_samples == 5
        # Sharpe should be 0 when std is 0
        assert result.sharpe == 0.0

    def test_custom_periods_per_year(self):
        """Test with custom periods per year."""
        returns = pd.Series([0.01, 0.02, 0.01, 0.02, 0.01])
        
        result_252 = compute_backtest_metrics(returns, periods_per_year=252)
        result_12 = compute_backtest_metrics(returns, periods_per_year=12)
        
        # Same total return
        assert abs(result_252.total_return - result_12.total_return) < 1e-9
        # Different CAGR due to different annualization
        assert result_252.cagr != result_12.cagr


# =============================================================================
# evaluate_model_on_ohlcv Tests
# =============================================================================
class TestEvaluateModelOnOhlcv:
    """Tests for evaluate_model_on_ohlcv function."""

    @pytest.fixture
    def sample_eval_data(self):
        """Create sample evaluation data."""
        dates = pd.date_range("2024-01-01", periods=100)
        X_eval = pd.DataFrame({"feature1": np.random.randn(100)}, index=dates)
        close_eval = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5), index=dates)
        next_close_eval = close_eval.shift(-1).fillna(close_eval.iloc[-1])
        return X_eval, close_eval, next_close_eval

    def test_direction_up_with_predict_proba(self, sample_eval_data):
        """Test evaluation with classifier using predict_proba."""
        X_eval, close_eval, next_close_eval = sample_eval_data
        
        model = MagicMock()
        model.predict_proba.return_value = np.column_stack([
            np.random.rand(100), np.random.rand(100)
        ])
        
        result = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close_eval,
            next_close_eval=next_close_eval,
            target_kind="direction_up",
        )
        
        assert isinstance(result, BacktestEvalResult)
        assert result.n_samples == 100

    def test_direction_up_with_predict_only(self, sample_eval_data):
        """Test evaluation with classifier using predict only."""
        X_eval, close_eval, next_close_eval = sample_eval_data
        
        model = MagicMock()
        del model.predict_proba  # Remove predict_proba
        model.predict.return_value = np.random.randint(0, 2, 100).astype(float)
        
        result = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close_eval,
            next_close_eval=next_close_eval,
            target_kind="direction_up",
        )
        
        assert isinstance(result, BacktestEvalResult)
        assert result.n_samples == 100

    def test_next_close_regression(self, sample_eval_data):
        """Test evaluation with regression model."""
        X_eval, close_eval, next_close_eval = sample_eval_data
        
        model = MagicMock()
        del model.predict_proba
        # Predict slightly above current close for long signals
        model.predict.return_value = close_eval.values + np.random.randn(100) * 0.5
        
        result = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close_eval,
            next_close_eval=next_close_eval,
            target_kind="next_close",
        )
        
        assert isinstance(result, BacktestEvalResult)
        assert result.n_samples == 100

    def test_empty_dataframe(self):
        """Test with empty X_eval DataFrame."""
        result = evaluate_model_on_ohlcv(
            model=MagicMock(),
            X_eval=pd.DataFrame(),
            close_eval=pd.Series(dtype=float),
            next_close_eval=pd.Series(dtype=float),
            target_kind="direction_up",
        )
        
        assert result.n_samples == 0
        assert result.total_return == 0.0

    def test_none_dataframe(self):
        """Test with None X_eval."""
        result = evaluate_model_on_ohlcv(
            model=MagicMock(),
            X_eval=None,
            close_eval=pd.Series(dtype=float),
            next_close_eval=pd.Series(dtype=float),
            target_kind="direction_up",
        )
        
        assert result.n_samples == 0

    def test_with_transaction_costs(self, sample_eval_data):
        """Test with transaction costs."""
        X_eval, close_eval, next_close_eval = sample_eval_data
        
        model = MagicMock()
        model.predict_proba.return_value = np.column_stack([
            np.random.rand(100), np.random.rand(100)
        ])
        
        result_no_cost = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close_eval,
            next_close_eval=next_close_eval,
            target_kind="direction_up",
            transaction_cost_bps=0.0,
        )
        
        result_with_cost = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close_eval,
            next_close_eval=next_close_eval,
            target_kind="direction_up",
            transaction_cost_bps=10.0,
        )
        
        # Result with costs should have lower or equal return
        assert result_with_cost.total_return <= result_no_cost.total_return

    def test_length_mismatch_raises(self, sample_eval_data):
        """Test that close length mismatch raises ValueError."""
        X_eval, close_eval, next_close_eval = sample_eval_data
        
        model = MagicMock()
        del model.predict_proba
        # Return predictions of different length
        model.predict.return_value = np.random.randn(50)  # Wrong length
        
        with pytest.raises(ValueError, match="close_eval length must match"):
            evaluate_model_on_ohlcv(
                model=model,
                X_eval=X_eval,
                close_eval=close_eval,
                next_close_eval=next_close_eval,
                target_kind="next_close",
            )


# =============================================================================
# evaluate_baseline_buy_and_hold Tests
# =============================================================================
class TestEvaluateBaselineBuyAndHold:
    """Tests for evaluate_baseline_buy_and_hold function."""

    @pytest.fixture
    def sample_price_data(self):
        """Create sample price data."""
        dates = pd.date_range("2024-01-01", periods=100)
        close = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5), index=dates)
        next_close = close.shift(-1).fillna(close.iloc[-1])
        return close, next_close

    def test_basic_buy_and_hold(self, sample_price_data):
        """Test basic buy and hold evaluation."""
        close, next_close = sample_price_data
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert isinstance(result, BacktestEvalResult)
        assert result.n_samples == 100

    def test_with_transaction_costs(self, sample_price_data):
        """Test buy and hold with transaction costs."""
        close, next_close = sample_price_data
        
        result_no_cost = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
            transaction_cost_bps=0.0,
        )
        
        result_with_cost = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
            transaction_cost_bps=10.0,
        )
        
        # For buy and hold, there's minimal trading so costs should be minimal
        # First bar has a position change from 0 to 1
        assert result_with_cost.total_return <= result_no_cost.total_return

    def test_upward_trend(self):
        """Test buy and hold with upward trending prices."""
        dates = pd.date_range("2024-01-01", periods=20)
        close = pd.Series([100 + i * 0.5 for i in range(20)], index=dates)
        next_close = close.shift(-1).fillna(close.iloc[-1])
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert result.total_return > 0
        assert result.cagr > 0

    def test_downward_trend(self):
        """Test buy and hold with downward trending prices."""
        dates = pd.date_range("2024-01-01", periods=20)
        close = pd.Series([100 - i * 0.5 for i in range(20)], index=dates)
        next_close = close.shift(-1).fillna(close.iloc[-1])
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert result.total_return < 0


# =============================================================================
# Integration Tests
# =============================================================================
class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_evaluation_pipeline(self):
        """Test full evaluation pipeline."""
        # Create sample data
        dates = pd.date_range("2024-01-01", periods=200)
        df = pd.DataFrame({
            "feature1": np.random.randn(200),
            "feature2": np.random.randn(200),
            "close": 100 + np.cumsum(np.random.randn(200) * 0.5),
        }, index=dates)
        df["next_close"] = df["close"].shift(-1).fillna(df["close"].iloc[-1])
        
        # Split data
        train_df, eval_df = time_split_by_fraction(df, 0.2)
        
        assert len(train_df) > 0
        assert len(eval_df) > 0
        
        # Create mock model
        model = MagicMock()
        model.predict_proba.return_value = np.column_stack([
            np.random.rand(len(eval_df)),
            np.random.rand(len(eval_df))
        ])
        
        # Evaluate model
        X_eval = eval_df[["feature1", "feature2"]]
        result = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=eval_df["close"],
            next_close_eval=eval_df["next_close"],
            target_kind="direction_up",
        )
        
        assert result.n_samples == len(eval_df)
        
        # Compare with buy and hold
        baseline = evaluate_baseline_buy_and_hold(
            close_eval=eval_df["close"],
            next_close_eval=eval_df["next_close"],
        )
        
        assert baseline.n_samples == len(eval_df)

    def test_model_vs_baseline_comparison(self):
        """Test comparing model vs baseline."""
        dates = pd.date_range("2024-01-01", periods=100)
        close = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5), index=dates)
        next_close = close.shift(-1).fillna(close.iloc[-1])
        
        # Perfect predictor model (knows the future)
        model = MagicMock()
        del model.predict_proba
        model.predict.return_value = next_close.values
        
        X_eval = pd.DataFrame({"feature": np.random.randn(100)}, index=dates)
        
        model_result = evaluate_model_on_ohlcv(
            model=model,
            X_eval=X_eval,
            close_eval=close,
            next_close_eval=next_close,
            target_kind="next_close",
        )
        
        baseline_result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        # Perfect predictor should perform at least as well as buy-and-hold
        # (or better if it avoids down moves)
        assert model_result.n_samples == baseline_result.n_samples


# =============================================================================
# Edge Cases
# =============================================================================
class TestEdgeCases:
    """Edge case tests."""

    def test_single_sample(self):
        """Test with single sample."""
        dates = pd.date_range("2024-01-01", periods=1)
        close = pd.Series([100.0], index=dates)
        next_close = pd.Series([102.0], index=dates)
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert result.n_samples == 1
        assert abs(result.total_return - 0.02) < 1e-9  # Float comparison

    def test_very_small_returns(self):
        """Test with very small returns."""
        dates = pd.date_range("2024-01-01", periods=100)
        close = pd.Series([100.0 + i * 0.0001 for i in range(100)], index=dates)
        next_close = close.shift(-1).fillna(close.iloc[-1])
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert result.n_samples == 100
        # Should handle very small values without numerical issues

    def test_very_large_returns(self):
        """Test with very large returns."""
        dates = pd.date_range("2024-01-01", periods=10)
        close = pd.Series([100.0 * (2 ** i) for i in range(10)], index=dates)  # Doubling each day
        next_close = close.shift(-1).fillna(close.iloc[-1])
        
        result = evaluate_baseline_buy_and_hold(
            close_eval=close,
            next_close_eval=next_close,
        )
        
        assert result.n_samples == 10
        assert result.total_return > 0

    def test_alternating_positions(self):
        """Test with rapidly alternating positions."""
        dates = pd.date_range("2024-01-01", periods=100)
        close = pd.Series([100.0] * 100, index=dates)
        next_close = pd.Series([101.0] * 100, index=dates)
        positions = np.array([1.0, 0.0] * 50)
        
        pnl = simulate_pnl_long_flat(
            close=close,
            next_close=next_close,
            position_long=positions,
            transaction_cost_bps=10.0,
        )
        
        assert len(pnl) == 100
        # High transaction costs from alternating should reduce returns
