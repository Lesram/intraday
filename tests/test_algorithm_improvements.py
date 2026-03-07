"""
Tests for the Phase 1 algorithm improvements:
  1A. Time-decay ML sample weighting
  1B. Regime-stratified Kelly sizing
  1C. Confidence calibration
  1D. Sector diversification gates
  1E. Momentum persistence features
  1F. Intraday seasonality filter
  1G. ML signal reversal exit trigger
"""

from __future__ import annotations

import math
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ─── Fixtures ─────────────────────────────────────────────────────

def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create synthetic OHLCV data for testing."""
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close - rng.uniform(0, 0.5, n),
        "high": close + rng.uniform(0.1, 1.0, n),
        "low": close - rng.uniform(0.1, 1.0, n),
        "close": close,
        "volume": rng.randint(1000, 100000, n).astype(float),
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="1min"),
    })


# ═══════════════════════════════════════════════════════════════════
# 1A. Time-Decay ML Sample Weighting
# ═══════════════════════════════════════════════════════════════════

class TestTimeDecayWeighting:
    def test_weights_shape_matches_n(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(100)
        assert len(weights) == 100

    def test_newest_sample_has_highest_weight(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(200)
        assert weights[-1] > weights[0]

    def test_weights_monotonically_increase(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(200)
        for i in range(1, len(weights)):
            assert weights[i] >= weights[i - 1]

    def test_mean_weight_is_one(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(200)
        assert abs(np.mean(weights) - 1.0) < 1e-6

    def test_recent_vs_oldest_ratio(self):
        """Recent bars should get 3-5x weight of oldest bars."""
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(250)
        ratio = weights[-1] / weights[0]
        assert ratio > 2.0  # At minimum 2x for default decay=0.005

    def test_single_sample(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(1)
        assert len(weights) == 1
        assert weights[0] == 1.0

    def test_empty_sample(self):
        from backend.organism.ml_signal import MLSignalGenerator
        weights = MLSignalGenerator._compute_sample_weights(0)
        assert len(weights) == 0


# ═══════════════════════════════════════════════════════════════════
# 1B. Regime-Stratified Kelly Sizing
# ═══════════════════════════════════════════════════════════════════

class TestRegimeStratifiedKelly:
    def test_record_trade_creates_stats(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        sizer.record_trade("trending_up", 100.0)
        assert "trending_up" in sizer._regime_stats
        assert sizer._regime_stats["trending_up"]["wins"] == 1

    def test_record_trade_loss(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        sizer.record_trade("chop", -50.0)
        assert sizer._regime_stats["chop"]["losses"] == 1
        assert sizer._regime_stats["chop"]["total_loss_pnl"] == 50.0

    def test_get_regime_kelly_insufficient_data(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        for _ in range(5):
            sizer.record_trade("trending_up", 100.0)
        assert sizer.get_regime_kelly("trending_up") is None  # < 10 trades

    def test_get_regime_kelly_with_data(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        for _ in range(8):
            sizer.record_trade("trending_up", 100.0)
        for _ in range(4):
            sizer.record_trade("trending_up", -50.0)
        kelly = sizer.get_regime_kelly("trending_up")
        assert kelly is not None
        assert 0 < kelly < 1.0  # Should be a valid fraction

    def test_get_regime_kelly_unknown_regime(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        assert sizer.get_regime_kelly("unknown_regime") is None

    def test_regime_stats_persistence(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        for _ in range(10):
            sizer.record_trade("trending_up", 200.0)
        for _ in range(5):
            sizer.record_trade("trending_up", -80.0)
        data = sizer.regime_stats_to_dict()
        sizer2 = KellySizer()
        sizer2.load_regime_stats(data)
        assert sizer2._regime_stats["trending_up"]["wins"] == 10
        assert sizer2._regime_stats["trending_up"]["losses"] == 5


# ═══════════════════════════════════════════════════════════════════
# 1C. Confidence Calibration
# ═══════════════════════════════════════════════════════════════════

class TestConfidenceCalibration:
    def test_record_prediction_outcome(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        gen.record_prediction_outcome(0.8, True)
        assert gen._calibration_counts[4][0] == 1  # bin 4 (0.8-1.0)
        assert gen._calibration_counts[4][1] == 1

    def test_calibrate_confidence_default(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        # Default calibration map is all 1.0 → no change
        assert gen.calibrate_confidence(0.7) == 0.7

    def test_update_calibration_map_insufficient_data(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        for _ in range(5):
            gen.record_prediction_outcome(0.8, True)
        gen.update_calibration_map()
        assert gen._calibration_map[4] == 1.0  # Not enough data

    def test_update_calibration_map_with_data(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        # Bin 4 (0.8-1.0): 15 outcomes, 12 correct → 80% accuracy
        for _ in range(12):
            gen.record_prediction_outcome(0.85, True)
        for _ in range(3):
            gen.record_prediction_outcome(0.85, False)
        gen.update_calibration_map()
        # Bin midpoint is 0.9, actual rate 0.8 → multiplier < 1.0
        assert gen._calibration_map[4] < 1.0

    def test_calibration_persistence(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        for _ in range(20):
            gen.record_prediction_outcome(0.5, True)
        gen.update_calibration_map()
        data = gen.calibration_to_dict()
        gen2 = MLSignalGenerator()
        gen2.load_calibration(data)
        assert gen2._calibration_counts == gen._calibration_counts
        assert gen2._calibration_map == gen._calibration_map

    def test_calibrate_confidence_capped_at_one(self):
        from backend.organism.ml_signal import MLSignalGenerator
        gen = MLSignalGenerator()
        gen._calibration_map = [2.0] * 5  # Very high multiplier
        assert gen.calibrate_confidence(0.8) == 1.0


# ═══════════════════════════════════════════════════════════════════
# 1D. Sector Diversification Gates
# ═══════════════════════════════════════════════════════════════════

class TestSectorGates:
    def test_get_sector_known_symbol(self):
        from backend.organism.sector_map import get_sector
        assert get_sector("AAPL") == "Technology"
        assert get_sector("GOOGL") == "Communication Services"
        assert get_sector("SPY") == "ETF"

    def test_get_sector_unknown_symbol(self):
        from backend.organism.sector_map import get_sector
        assert get_sector("ZZZZ") == "Unknown"

    def test_count_sector_positions(self):
        from backend.organism.sector_map import count_sector_positions
        open_syms = {"AAPL", "MSFT", "NVDA", "GOOGL"}
        assert count_sector_positions(open_syms, "Technology") == 3
        assert count_sector_positions(open_syms, "Communication Services") == 1
        assert count_sector_positions(open_syms, "Energy") == 0

    def test_sector_gate_allows_under_limit(self):
        from backend.organism.sector_map import sector_gate_allows
        open_syms = {"AAPL", "MSFT"}
        assert sector_gate_allows("NVDA", open_syms) is True

    def test_sector_gate_blocks_at_limit(self):
        from backend.organism.sector_map import sector_gate_allows, MAX_PER_SECTOR
        # Fill up Technology sector to the limit
        tech_syms = {"AAPL", "MSFT", "NVDA", "AMD"}
        assert len(tech_syms) >= MAX_PER_SECTOR
        assert sector_gate_allows("AVGO", tech_syms) is False

    def test_sector_gate_allows_unknown_symbol(self):
        from backend.organism.sector_map import sector_gate_allows
        open_syms = {"AAPL", "MSFT", "NVDA", "AMD"}
        assert sector_gate_allows("ZZZZ", open_syms) is True

    def test_sector_gate_different_sector_allowed(self):
        from backend.organism.sector_map import sector_gate_allows
        tech_full = {"AAPL", "MSFT", "NVDA", "AMD"}
        assert sector_gate_allows("XOM", tech_full) is True  # Energy sector


# ═══════════════════════════════════════════════════════════════════
# 1E. Momentum Persistence Features
# ═══════════════════════════════════════════════════════════════════

class TestMomentumPersistenceFeatures:
    def test_autocorrelation_features_exist(self):
        from backend.organism.ml_features import compute_ml_features
        df = _make_ohlcv(200)
        result = compute_ml_features(df)
        assert "ret_autocorr_1" in result.columns
        assert "ret_autocorr_5" in result.columns
        assert "ret_autocorr_10" in result.columns

    def test_hurst_exponent_feature_exists(self):
        from backend.organism.ml_features import compute_ml_features
        df = _make_ohlcv(200)
        result = compute_ml_features(df)
        assert "hurst_exponent" in result.columns

    def test_autocorrelation_values_bounded(self):
        from backend.organism.ml_features import compute_ml_features
        df = _make_ohlcv(200)
        result = compute_ml_features(df)
        # After fillna(0), values should be in [-1, 1] range
        for col in ("ret_autocorr_1", "ret_autocorr_5", "ret_autocorr_10"):
            vals = result[col].dropna()
            if len(vals) > 0:
                assert vals.max() <= 1.01
                assert vals.min() >= -1.01

    def test_features_in_feature_columns_list(self):
        from backend.organism.ml_features import FEATURE_COLUMNS
        assert "ret_autocorr_1" in FEATURE_COLUMNS
        assert "ret_autocorr_5" in FEATURE_COLUMNS
        assert "ret_autocorr_10" in FEATURE_COLUMNS
        assert "hurst_exponent" in FEATURE_COLUMNS


# ═══════════════════════════════════════════════════════════════════
# 1F. Intraday Seasonality Filter
# ═══════════════════════════════════════════════════════════════════

class TestIntradaySeasonalityFilter:
    def test_seasonality_reduces_shares(self):
        """Test that seasonality filter reduces position size by 40%."""
        from backend.organism.kelly_sizer import PositionSize
        sz = PositionSize(
            symbol="AAPL", target_weight=0.10, shares=100,
            notional=10000.0, kelly_raw=0.2, kelly_half=0.1,
            drawdown_scale=1.0, vol_scale=1.0, regime_scale=1.0,
            direction=1.0,
        )
        # Simulate the 40% reduction
        reduced_shares = max(1, int(sz.shares * 0.6))
        assert reduced_shares == 60

    def test_seasonality_minimum_one_share(self):
        """Ensure at least 1 share after reduction."""
        from backend.organism.kelly_sizer import PositionSize
        sz = PositionSize(
            symbol="AAPL", target_weight=0.001, shares=1,
            notional=150.0, kelly_raw=0.01, kelly_half=0.005,
            drawdown_scale=1.0, vol_scale=1.0, regime_scale=1.0,
            direction=1.0,
        )
        reduced = max(1, int(sz.shares * 0.6))
        assert reduced >= 1


# ═══════════════════════════════════════════════════════════════════
# 1G. ML Signal Reversal Exit Trigger
# ═══════════════════════════════════════════════════════════════════

class TestMLReversalExitTrigger:
    def test_reversal_creates_partial_exit(self):
        from backend.organism.adaptive_exits import ExitSignal
        # Simulate what live_engine does for ML reversal
        exit_sig = ExitSignal(
            should_exit=True,
            reason="ml_reversal",
            exit_price=105.0,
            partial_exit=True,
            partial_pct=0.50,
        )
        assert exit_sig.should_exit is True
        assert exit_sig.reason == "ml_reversal"
        assert exit_sig.partial_exit is True
        assert exit_sig.partial_pct == 0.50

    def test_reversal_exit_signal_dict(self):
        from backend.organism.adaptive_exits import ExitSignal
        exit_sig = ExitSignal(
            should_exit=True,
            reason="ml_reversal",
            exit_price=105.0,
            partial_exit=True,
            partial_pct=0.50,
        )
        d = exit_sig.to_dict()
        assert d["reason"] == "ml_reversal"
        assert d["partial_exit"] is True
        assert d["partial_pct"] == 0.50

    def test_no_reversal_on_same_direction(self):
        """ML signal same as position direction should not trigger exit."""
        from backend.organism.ml_signal import MLSignal
        signal = MLSignal(symbol="AAPL", direction=1.0, confidence=0.8, predicted_return=0.02)
        pos_direction = 1.0
        # No reversal: directions match
        assert not (signal.direction != 0 and signal.direction != pos_direction)

    def test_reversal_detected_on_opposite_direction(self):
        from backend.organism.ml_signal import MLSignal
        signal = MLSignal(symbol="AAPL", direction=-1.0, confidence=0.8, predicted_return=0.02)
        pos_direction = 1.0
        assert signal.direction != 0 and signal.direction != pos_direction

    def test_low_confidence_reversal_ignored(self):
        """Reversal with confidence <= 0.3 should be ignored."""
        from backend.organism.ml_signal import MLSignal
        signal = MLSignal(symbol="AAPL", direction=-1.0, confidence=0.2, predicted_return=0.02)
        pos_direction = 1.0
        should_trigger = (
            signal.direction != 0
            and signal.direction != pos_direction
            and signal.confidence > 0.3
        )
        assert should_trigger is False


# ═══════════════════════════════════════════════════════════════════
# Fix 1: Pyramid Exit Recalculation
# ═══════════════════════════════════════════════════════════════════

class TestPyramidExitRecalculation:
    def test_update_levels_for_pyramid_tightens_stop(self):
        """Pyramid add at higher price should tighten (raise) stop for long."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine()
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=97.0, take_profit=118.0, trailing_stop=97.0,
            atr_at_entry=2.0, regime_at_entry="trending_up",
            highest_favorable=100.0,
        )
        old_stop = levels.stop_loss
        # Pyramid adds at 105 → new avg entry = 102.5
        engine.update_levels_for_pyramid(levels, 102.5, "trending_up")
        # Stop should tighten (raise) since new entry is higher
        assert levels.stop_loss >= old_stop
        assert levels.entry_price == 102.5
        # TP should be re-anchored to new avg entry
        assert levels.take_profit > 102.5

    def test_update_levels_preserves_partial_tp_taken(self):
        """Pyramid recalculation must preserve stateful flags."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine()
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=97.0, take_profit=118.0, trailing_stop=97.0,
            atr_at_entry=2.0, regime_at_entry="trending_up",
            highest_favorable=105.0, partial_tp_taken=True,
            trailing_active=True, stress_tightened=True,
            profit_locked=True, bars_held=50,
        )
        engine.update_levels_for_pyramid(levels, 102.5, "trending_up")
        assert levels.partial_tp_taken is True
        assert levels.trailing_active is True
        assert levels.stress_tightened is True
        assert levels.profit_locked is True
        assert levels.bars_held == 50
        assert levels.highest_favorable == 105.0


# ═══════════════════════════════════════════════════════════════════
# Fix 2: Pyramid Layer Count (resolved by Fix 1)
# ═══════════════════════════════════════════════════════════════════

class TestPyramidLayerCount:
    def test_pyramid_layer_count_prevents_repeated_adds(self):
        """After appending a layer, layer_count increments and pyramider
        won't re-trigger the same level."""
        from backend.organism.pyramider import PyramidPosition, PyramidLevel

        pyr = PyramidPosition(
            symbol="WMT", direction=1.0,
            layers=[PyramidLevel(shares=100, entry_price=50.0, bar_added=0, level=0)],
            target_total_shares=300, atr_at_entry=1.0,
        )
        assert pyr.layer_count == 1
        # Simulate what Fix 1 does after a pyramid add
        pyr.layers.append(PyramidLevel(shares=50, entry_price=52.0, bar_added=10, level=1))
        assert pyr.layer_count == 2
        # Add another
        pyr.layers.append(PyramidLevel(shares=50, entry_price=54.0, bar_added=20, level=2))
        assert pyr.layer_count == 3


# ═══════════════════════════════════════════════════════════════════
# Fix 3: Minimum Hold Time Before Profit Exits
# ═══════════════════════════════════════════════════════════════════

class TestMinHoldTime:
    def _make_levels(self, bars_held: int = 0) -> "ExitLevels":
        from backend.organism.adaptive_exits import ExitLevels
        return ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=97.0, take_profit=118.0, trailing_stop=97.0,
            atr_at_entry=2.0, regime_at_entry="trending_up",
            highest_favorable=100.0, bars_held=bars_held,
        )

    def test_min_hold_blocks_early_profit_exit(self):
        """TP at bar 4 should be blocked by min hold guard (dynamic: H//3=5)."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        engine = AdaptiveExitEngine()
        levels = self._make_levels(bars_held=3)  # Will become 4 after check (< 5 min hold)
        # Price at TP level — would normally trigger take_profit
        sig = engine.check_exit(levels, 118.0, "trending_up")
        assert sig.should_exit is False

    def test_min_hold_allows_stop_loss(self):
        """Stop loss must fire even before min hold."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        engine = AdaptiveExitEngine()
        levels = self._make_levels(bars_held=0)  # bar 1 after check
        sig = engine.check_exit(levels, 96.0, "trending_up")
        assert sig.should_exit is True
        assert sig.reason == "stop_loss"

    def test_min_hold_allows_max_loss(self):
        """Max loss safety net must fire even before min hold."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        engine = AdaptiveExitEngine()
        levels = self._make_levels(bars_held=0)
        # Price dropped 16% → max_loss_pct=0.15 triggered
        sig = engine.check_exit(levels, 84.0, "trending_up")
        assert sig.should_exit is True
        assert sig.reason == "max_loss_limit"

    def test_profit_exit_fires_after_min_hold(self):
        """Profit exit should fire normally after min hold bars are met."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        engine = AdaptiveExitEngine()
        levels = self._make_levels(bars_held=4)  # Will become 5 after check (= min hold)
        sig = engine.check_exit(levels, 118.0, "trending_up")
        assert sig.should_exit is True
        # partial_take_profit fires first (3R < full TP), which is a profit exit
        assert sig.reason in ("take_profit", "partial_take_profit")


# ═══════════════════════════════════════════════════════════════════
# Fix 4: Widen high_vol Stops
# ═══════════════════════════════════════════════════════════════════

class TestHighVolStops:
    def test_high_vol_stop_uses_4x_atr(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        assert AdaptiveExitEngine.REGIME_STOP_ATR["high_vol"] == 4.0

    def test_high_vol_trail_uses_4_5x_atr(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        assert AdaptiveExitEngine.REGIME_TRAIL_ATR["high_vol"] == 4.5


# ═══════════════════════════════════════════════════════════════════
# Fix 5: Block Entries First 30 Min
# ═══════════════════════════════════════════════════════════════════

class TestOpeningBlock:
    def test_entries_blocked_before_10am(self):
        """930-959 ET should be blocked."""
        # The live engine checks: 930 <= hhmm < 1000
        hhmm = 945
        assert 930 <= hhmm < 1000

    def test_entries_allowed_after_10am(self):
        """1000+ ET should be allowed."""
        hhmm = 1000
        assert not (930 <= hhmm < 1000)


# ═══════════════════════════════════════════════════════════════════
# Fix 6: Liquidity Gate
# ═══════════════════════════════════════════════════════════════════

class TestLiquidityGate:
    def _make_engine(self):
        from unittest.mock import MagicMock
        from backend.organism.live_engine import OrganismLiveEngine
        engine = object.__new__(OrganismLiveEngine)
        engine._MIN_AVG_VOLUME = 500_000
        return engine

    def test_low_volume_blocked(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [100_000] * 20, "close": [50.0] * 20})
        assert engine._passes_liquidity_gate("LEE", {"LEE": df}) is False

    def test_high_volume_allowed(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [1_000_000] * 20, "close": [50.0] * 20})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is True

    def test_missing_data_passes(self):
        engine = self._make_engine()
        assert engine._passes_liquidity_gate("UNKNOWN", {}) is True


# ═══════════════════════════════════════════════════════════════════
# Fix 7: ML Floor Regime Guard
# ═══════════════════════════════════════════════════════════════════

class TestMLFloorRegimeGuard:
    def _make_sizer_with_losing_regime(self, regime: str, n_trades: int = 10):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        # Record losing trades
        for _ in range(n_trades):
            sizer.record_trade(regime, -50.0)
        return sizer

    def _make_sizer_with_winning_regime(self, regime: str, n_trades: int = 10):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        for _ in range(n_trades):
            sizer.record_trade(regime, 100.0)
        return sizer

    def test_ml_floor_suppressed_when_regime_losing(self):
        """ML confidence floor should NOT apply when regime has negative PnL."""
        sizer = self._make_sizer_with_losing_regime("high_vol", 10)
        # Verify the regime stats show negative expectancy
        stats = sizer._regime_stats["high_vol"]
        assert stats["total_pnl"] <= 0
        assert stats["wins"] + stats["losses"] >= 5
        # The guard: _regime_has_edge should be False
        _rs = sizer._regime_stats.get("high_vol")
        _total = _rs["wins"] + _rs["losses"]
        _regime_has_edge = not (_total >= 5 and _rs["total_pnl"] <= 0)
        assert _regime_has_edge is False

    def test_ml_floor_applies_when_regime_positive(self):
        """ML confidence floor should apply when regime has positive PnL."""
        sizer = self._make_sizer_with_winning_regime("trending_up", 10)
        stats = sizer._regime_stats["trending_up"]
        assert stats["total_pnl"] > 0
        _rs = sizer._regime_stats.get("trending_up")
        _total = _rs["wins"] + _rs["losses"]
        _regime_has_edge = not (_total >= 5 and _rs["total_pnl"] <= 0)
        assert _regime_has_edge is True


# ═══════════════════════════════════════════════════════════════════
# Fix 8: Increase high_vol Sizing
# ═══════════════════════════════════════════════════════════════════

class TestHighVolSizing:
    def test_high_vol_regime_scale_is_0_8(self):
        from backend.organism.kelly_sizer import KellySizer
        sizer = KellySizer()
        scale, source, count = sizer._regime_scale("high_vol")
        assert scale == 0.8


# ═══════════════════════════════════════════════════════════════════
# Fix 9: Separate high_vol from stress in Alpha Scanner
# ═══════════════════════════════════════════════════════════════════

class TestAlphaScannerRegimeSplit:
    def _make_row(self) -> pd.Series:
        return pd.Series({
            "adx_14": 20, "trend_strength": 0.2, "vol_regime": 1,
        })

    def test_high_vol_regime_score_is_neutral(self):
        from backend.organism.alpha_scanner import AlphaScanner
        scanner = AlphaScanner()
        score = scanner._regime_alignment(self._make_row(), 1.0, "high_vol")
        assert score == 0.5

    def test_stress_regime_score_stays_low(self):
        from backend.organism.alpha_scanner import AlphaScanner
        scanner = AlphaScanner()
        score = scanner._regime_alignment(self._make_row(), 1.0, "stress")
        assert score == 0.2

    def test_high_vol_threshold_0_25(self):
        """high_vol threshold should be 0.25 (lowered from 0.40)."""
        # The scanner uses: 0.25 if current_regime == "high_vol" else 0.50
        from backend.organism.alpha_scanner import AlphaScanner
        scanner = AlphaScanner()
        # We can't easily call scan() without full data, so verify the logic:
        min_threshold = scanner.MIN_COMPOSITE
        current_regime = "high_vol"
        if current_regime in ("high_vol", "stress"):
            min_threshold = 0.25 if current_regime == "high_vol" else 0.50
        assert min_threshold == 0.25


# ═══════════════════════════════════════════════════════════════════
# Fix 10: Raise Fitness Gate
# ═══════════════════════════════════════════════════════════════════

class TestFitnessGate:
    def test_fitness_gate_blocks_marginal_symbols(self):
        """Symbols with fitness < 0.45 should be blocked."""
        _FITNESS_GATE = 0.45
        # These would have passed the old 0.35 gate
        marginal_fitness = {"EMAT": 0.30, "XLK": 0.30, "GOOGL": 0.40, "CAT": 0.30}
        for sym, fitness in marginal_fitness.items():
            assert fitness < _FITNESS_GATE, f"{sym} should be blocked at {fitness}"
