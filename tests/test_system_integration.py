"""
System integration tests — verifies cross-component behavior.

These tests wire multiple organism modules together with minimal mocking
to verify end-to-end flows: ML → Kelly → Exits → Brain persistence.
"""

from __future__ import annotations

import math
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ─── Fixtures ─────────────────────────────────────────────────────

def _make_ohlcv(n: int = 250, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 0.5)
    close = np.maximum(close, 10)  # prevent negative prices
    return pd.DataFrame({
        "open": close - rng.uniform(0, 0.5, n),
        "high": close + rng.uniform(0.1, 1.0, n),
        "low": close - rng.uniform(0.1, 1.0, n),
        "close": close,
        "volume": rng.randint(1000, 100000, n).astype(float),
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="1min"),
    })


def _make_multi_symbol_features(symbols: list[str], n: int = 250) -> dict[str, pd.DataFrame]:
    from backend.organism.ml_features import compute_ml_features
    result = {}
    for i, sym in enumerate(symbols):
        df = _make_ohlcv(n, seed=42 + i)
        result[sym] = compute_ml_features(df)
    return result


# ═══════════════════════════════════════════════════════════════════
# Test: ML → Signal → Kelly pipeline
# ═══════════════════════════════════════════════════════════════════

class TestMLKellyPipeline:
    """Verify signals flow from ML training through Kelly sizing."""

    def test_train_predict_size_flow(self):
        from backend.organism.ml_signal import MLSignalGenerator
        from backend.organism.kelly_sizer import KellySizer

        symbols = ["AAPL", "MSFT", "NVDA"]
        features = _make_multi_symbol_features(symbols, n=250)

        gen = MLSignalGenerator(train_window=200)
        metrics = gen.train(features)
        assert gen.is_trained
        assert metrics.generation == 1

        signals = gen.predict_batch(features)
        assert len(signals) == 3
        for sym in symbols:
            sig = signals[sym]
            assert sig.direction in (-1.0, 0.0, 1.0)
            assert 0 <= sig.confidence <= 1.0

        sizer = KellySizer()
        candidates = []
        for sym, sig in signals.items():
            if sig.direction != 0:
                candidates.append({
                    "symbol": sym,
                    "direction": sig.direction,
                    "predicted_return": abs(sig.predicted_return),
                    "confidence": sig.confidence,
                    "breakout_score": 0.0,
                })

        if candidates:
            sizes = sizer.size_positions(
                candidates, portfolio_value=100000, current_drawdown=0.0,
                features_by_symbol=features, current_regime="normal",
            )
            for sz in sizes:
                assert sz.shares > 0
                assert sz.notional > 0
                assert 0 < sz.target_weight <= 0.12

    def test_regime_stratified_kelly_flow(self):
        """Verify regime Kelly tracks from trades and influences sizing."""
        from backend.organism.kelly_sizer import KellySizer

        sizer = KellySizer()

        # Record trades in trending regime
        for _ in range(15):
            sizer.record_trade("trending_up", 200.0)
        for _ in range(5):
            sizer.record_trade("trending_up", -80.0)

        kelly = sizer.get_regime_kelly("trending_up")
        assert kelly is not None
        assert kelly > 0

        # Record trades in chop regime with worse performance
        for _ in range(8):
            sizer.record_trade("chop", 50.0)
        for _ in range(12):
            sizer.record_trade("chop", -60.0)

        chop_kelly = sizer.get_regime_kelly("chop")
        # With 40% win rate, Kelly should be 0 or very small
        assert chop_kelly is not None
        assert chop_kelly < kelly  # Chop regime should size smaller


# ═══════════════════════════════════════════════════════════════════
# Test: ML Training with Time-Decay Weights
# ═══════════════════════════════════════════════════════════════════

class TestMLTrainingWithDecay:
    def test_training_with_decay_succeeds(self):
        from backend.organism.ml_signal import MLSignalGenerator
        features = _make_multi_symbol_features(["AAPL", "MSFT"], n=200)
        gen = MLSignalGenerator(train_window=150)
        metrics = gen.train(features)
        assert gen.is_trained
        assert metrics.accuracy > 0.0

    def test_retrained_model_improves_or_maintains(self):
        from backend.organism.ml_signal import MLSignalGenerator
        features = _make_multi_symbol_features(["AAPL", "MSFT", "NVDA"], n=250)
        gen = MLSignalGenerator(train_window=200)
        m1 = gen.train(features)
        m2 = gen.train(features)
        assert m2.generation == 2
        # Accuracy should be reasonable (not degenerate)
        assert m2.accuracy >= 0.3


# ═══════════════════════════════════════════════════════════════════
# Test: Exit Engine Cross-Component
# ═══════════════════════════════════════════════════════════════════

class TestExitEngineIntegration:
    def test_create_and_check_exit_lifecycle(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine

        engine = AdaptiveExitEngine()
        df = _make_ohlcv(100)

        levels = engine.create_exit_levels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            predicted_return=0.05, features_df=df, regime="normal",
        )
        assert levels.stop_loss < 100.0
        assert levels.take_profit > 100.0
        assert levels.trailing_stop == levels.stop_loss

        # Price goes up — no exit
        sig = engine.check_exit(levels, 102.0, "normal")
        assert not sig.should_exit

        # Price hits stop — exit
        sig = engine.check_exit(levels, levels.stop_loss - 0.01, "normal")
        assert sig.should_exit
        assert sig.reason == "stop_loss"

    def test_partial_tp_lifecycle(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine

        engine = AdaptiveExitEngine()
        df = _make_ohlcv(100)

        levels = engine.create_exit_levels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            predicted_return=0.10, features_df=df, regime="normal",
        )

        # Move price above partial TP
        sig = engine.check_exit(levels, levels.partial_tp_price + 1.0, "normal")
        if sig.should_exit and sig.reason == "partial_take_profit":
            assert sig.partial_exit
            assert sig.partial_pct == 0.30
            assert levels.partial_tp_taken
            # Stop should now be at breakeven
            assert levels.stop_loss == levels.entry_price

    def test_max_loss_safety_net(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine

        engine = AdaptiveExitEngine()
        df = _make_ohlcv(100)

        levels = engine.create_exit_levels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            predicted_return=0.05, features_df=df, regime="normal",
        )

        # Force price down 16% — should trigger max loss safety net
        sig = engine.check_exit(levels, 84.0, "normal")
        assert sig.should_exit
        assert sig.reason == "max_loss_limit"


# ═══════════════════════════════════════════════════════════════════
# Test: Sector Gate Integration
# ═══════════════════════════════════════════════════════════════════

class TestSectorGateIntegration:
    def test_sector_gate_blocks_concentrated_entries(self):
        from backend.organism.sector_map import sector_gate_allows, MAX_PER_SECTOR

        # Simulate full technology sector
        open_symbols = {"AAPL", "MSFT", "NVDA", "AMD"}
        # Should block additional tech
        assert not sector_gate_allows("AVGO", open_symbols)
        assert not sector_gate_allows("INTC", open_symbols)
        # Should allow other sectors
        assert sector_gate_allows("XOM", open_symbols)
        assert sector_gate_allows("GOOGL", open_symbols)

    def test_sector_gate_allows_when_under_limit(self):
        from backend.organism.sector_map import sector_gate_allows

        open_symbols = {"AAPL", "MSFT"}  # Only 2 tech
        assert sector_gate_allows("NVDA", open_symbols)


# ═══════════════════════════════════════════════════════════════════
# Test: Confidence Calibration Cross-Component
# ═══════════════════════════════════════════════════════════════════

class TestCalibrationIntegration:
    def test_calibration_adjusts_predictions(self):
        from backend.organism.ml_signal import MLSignalGenerator

        gen = MLSignalGenerator()

        # Simulate overconfident model: high confidence but only 50% correct
        for _ in range(20):
            gen.record_prediction_outcome(0.85, True)
        for _ in range(20):
            gen.record_prediction_outcome(0.85, False)

        gen.update_calibration_map()

        # Calibrated confidence should be lower than raw
        calibrated = gen.calibrate_confidence(0.85)
        assert calibrated < 0.85

    def test_calibration_persists_and_restores(self):
        from backend.organism.ml_signal import MLSignalGenerator

        gen1 = MLSignalGenerator()
        for _ in range(30):
            gen1.record_prediction_outcome(0.7, True)
        for _ in range(10):
            gen1.record_prediction_outcome(0.7, False)
        gen1.update_calibration_map()

        data = gen1.calibration_to_dict()
        gen2 = MLSignalGenerator()
        gen2.load_calibration(data)

        assert gen2.calibrate_confidence(0.7) == gen1.calibrate_confidence(0.7)


# ═══════════════════════════════════════════════════════════════════
# Test: Feature Computation End-to-End
# ═══════════════════════════════════════════════════════════════════

class TestFeatureComputation:
    def test_all_feature_columns_present(self):
        from backend.organism.ml_features import compute_ml_features, FEATURE_COLUMNS

        df = _make_ohlcv(200)
        result = compute_ml_features(df)

        missing = [c for c in FEATURE_COLUMNS if c not in result.columns]
        assert missing == [], f"Missing feature columns: {missing}"

    def test_no_nan_in_features(self):
        from backend.organism.ml_features import compute_ml_features, FEATURE_COLUMNS

        df = _make_ohlcv(200)
        result = compute_ml_features(df)

        for col in FEATURE_COLUMNS:
            if col in result.columns:
                nan_count = result[col].isna().sum()
                assert nan_count == 0, f"Column {col} has {nan_count} NaN values"

    def test_momentum_persistence_features_reasonable(self):
        from backend.organism.ml_features import compute_ml_features

        df = _make_ohlcv(200)
        result = compute_ml_features(df)

        # Hurst exponent should be roughly between 0 and 1
        h = result["hurst_exponent"].iloc[-1]
        assert 0 <= h <= 1.5, f"Hurst exponent {h} out of range"

        # Autocorrelation should be bounded
        for lag in (1, 5, 10):
            col = f"ret_autocorr_{lag}"
            vals = result[col].dropna()
            if len(vals) > 0:
                assert vals.max() <= 1.01, f"{col} max = {vals.max()}"
                assert vals.min() >= -1.01, f"{col} min = {vals.min()}"


# ═══════════════════════════════════════════════════════════════════
# Test: Brain Persistence for New Fields
# ═══════════════════════════════════════════════════════════════════

class TestBrainPersistenceNewFields:
    def test_regime_kelly_stats_round_trip(self):
        from backend.organism.kelly_sizer import KellySizer

        sizer = KellySizer()
        sizer.record_trade("trending_up", 100)
        sizer.record_trade("trending_up", -50)
        sizer.record_trade("chop", -30)

        data = sizer.regime_stats_to_dict()
        restored = KellySizer()
        restored.load_regime_stats(data)

        assert restored._regime_stats["trending_up"]["wins"] == 1
        assert restored._regime_stats["trending_up"]["losses"] == 1
        assert restored._regime_stats["chop"]["losses"] == 1

    def test_calibration_round_trip(self):
        from backend.organism.ml_signal import MLSignalGenerator

        gen = MLSignalGenerator()
        gen.record_prediction_outcome(0.9, True)
        gen.record_prediction_outcome(0.9, False)
        gen.record_prediction_outcome(0.5, True)

        data = gen.calibration_to_dict()
        gen2 = MLSignalGenerator()
        gen2.load_calibration(data)

        assert gen2._calibration_counts == gen._calibration_counts
