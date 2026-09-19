"""
Tests for Patch Queue C2 -- three targeted fixes:
  Fix 1: Regime aggregation order contamination
  Fix 2: Calibration restore without models
  Fix 3: TradeRecord forensic field persistence
"""

import copy
import csv
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from backend.organism.regime import RegimeDetector, RegimeLabel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_features(close_base: float, trend: float, n: int = 60) -> pd.DataFrame:
    """Build a synthetic features DataFrame with a controllable trend."""
    closes = [close_base + trend * i + np.random.default_rng(42).normal(0, 0.3) for i in range(n)]
    sma = pd.Series(closes).rolling(20, min_periods=1).mean().tolist()
    volumes = [1_000_000 + np.random.default_rng(i).integers(-200_000, 200_000) for i in range(n)]
    return pd.DataFrame({
        "close": closes,
        "sma_50": sma,
        "volume": volumes,
    })


def _make_distinct_features(seed: int, close_base: float, trend: float, n: int = 60) -> pd.DataFrame:
    """Each seed produces a different but deterministic feature set."""
    rng = np.random.default_rng(seed)
    closes = [close_base + trend * i + rng.normal(0, 0.5) for i in range(n)]
    sma = pd.Series(closes).rolling(20, min_periods=1).mean().tolist()
    volumes = [1_000_000 + int(rng.integers(-200_000, 200_000)) for i in range(n)]
    return pd.DataFrame({
        "close": closes,
        "sma_50": sma,
        "volume": volumes,
    })


# ===================================================================
# Fix 1: Regime aggregation order invariance
# ===================================================================

class TestRegimeOrderInvariance:
    """After the fix, symbol/sector iteration order must not affect results."""

    def test_market_regime_order_invariant(self):
        """detect_market_regime() with two different orderings gives the same primary regime."""
        det = RegimeDetector()

        syms = {
            "AAPL": _make_distinct_features(1, 150.0, 0.5),
            "MSFT": _make_distinct_features(2, 300.0, -0.3),
            "TSLA": _make_distinct_features(3, 200.0, 0.1),
        }

        order_a = dict(syms)  # AAPL, MSFT, TSLA
        order_b = {"TSLA": syms["TSLA"], "AAPL": syms["AAPL"], "MSFT": syms["MSFT"]}

        # Reset detector to identical state for both calls
        det._smoothed_probs = {}
        det._history = []
        det._last_state = None
        result_a = det.detect_market_regime(order_a)

        det._smoothed_probs = {}
        det._history = []
        det._last_state = None
        result_b = det.detect_market_regime(order_b)

        assert result_a.primary == result_b.primary, (
            f"Order changed result: {result_a.primary} vs {result_b.primary}"
        )
        # Probabilities should be identical (float equality, same computation)
        for label in result_a.probabilities:
            assert abs(result_a.probabilities[label] - result_b.probabilities[label]) < 1e-10

    def test_cross_asset_order_invariant(self):
        """detect_cross_asset_regime() order-invariant for sector ETFs."""
        det = RegimeDetector()

        per_sym = {"SPY": _make_distinct_features(10, 400.0, 0.2)}
        sectors = {
            "XLK": _make_distinct_features(20, 180.0, 0.4),
            "XLE": _make_distinct_features(21, 80.0, -0.2),
            "XLF": _make_distinct_features(22, 35.0, 0.1),
        }

        order_a = dict(sectors)
        order_b = {"XLF": sectors["XLF"], "XLK": sectors["XLK"], "XLE": sectors["XLE"]}

        det._smoothed_probs = {}
        det._history = []
        det._last_state = None
        result_a = det.detect_cross_asset_regime(per_sym, order_a)

        det._smoothed_probs = {}
        det._history = []
        det._last_state = None
        result_b = det.detect_cross_asset_regime(per_sym, order_b)

        assert result_a.primary == result_b.primary

    def test_per_symbol_detect_matches_standalone(self):
        """Each symbol's regime in aggregation must match standalone detect()."""
        det = RegimeDetector()

        syms = {
            "A": _make_distinct_features(100, 100.0, 0.3),
            "B": _make_distinct_features(101, 200.0, -0.5),
            "C": _make_distinct_features(102, 50.0, 0.0),
        }

        init_probs = {}
        init_history: list[str] = []

        # Standalone results from a clean state each time
        standalone = {}
        for sym, df in syms.items():
            det._smoothed_probs = dict(init_probs)
            det._history = list(init_history)
            standalone[sym] = det.detect(df)

        # After fix, each symbol inside detect_market_regime also starts
        # from the same pristine state, so the per-symbol probabilities
        # must sum to the same aggregate as standalone.
        agg_standalone: dict[str, float] = {}
        for sr in standalone.values():
            for label, prob in sr.probabilities.items():
                agg_standalone[label] = agg_standalone.get(label, 0.0) + prob
        n = len(standalone)
        agg_standalone = {k: v / n for k, v in agg_standalone.items()}

        det._smoothed_probs = dict(init_probs)
        det._history = list(init_history)
        det._last_state = None
        market = det.detect_market_regime(syms)

        for label in agg_standalone:
            assert abs(market.probabilities.get(label, 0) - agg_standalone[label]) < 1e-10, (
                f"Mismatch on {label}: market={market.probabilities.get(label)} "
                f"standalone_agg={agg_standalone[label]}"
            )


# ===================================================================
# Fix 2: Calibration restore without models
# ===================================================================

class TestCalibrationRestoreWithoutModels:

    def test_calibration_restored_without_models(self):
        """Brain with calibration but no clf/reg still calls load_calibration."""
        from backend.organism.brain_persistence import OrganismBrain

        brain = OrganismBrain.__new__(OrganismBrain)
        brain.clf = None
        brain.reg = None
        brain.ml_state = {"calibration": {"slope": 1.1, "intercept": -0.05}}

        sig_gen = MagicMock()
        sig_gen.load_calibration = MagicMock()

        result = brain.apply_to_signal_generator(sig_gen)

        # Models not restored -> returns False
        assert result is False
        # But calibration WAS restored
        sig_gen.load_calibration.assert_called_once_with({"slope": 1.1, "intercept": -0.05})

    def test_old_brain_no_calibration_loads_clean(self):
        """Brain with no calibration key does not error."""
        from backend.organism.brain_persistence import OrganismBrain

        brain = OrganismBrain.__new__(OrganismBrain)
        brain.clf = None
        brain.reg = None
        brain.ml_state = {}

        sig_gen = MagicMock(spec=[])  # no load_calibration attr

        result = brain.apply_to_signal_generator(sig_gen)
        assert result is False


# ===================================================================
# Fix 3: TradeRecord forensic field persistence
# ===================================================================

class TestTradeForensicFields:

    def _make_trade_record(self, **overrides):
        from backend.organism.continuous_learner import TradeRecord
        defaults = dict(
            symbol="AAPL", direction=1.0, entry_price=150.0,
            exit_price=155.0, entry_bar=10, exit_bar=20,
            shares=100, pnl=500.0, exit_reason="target",
            predicted_return=0.03, actual_return=0.033,
            confidence=0.75,
            is_exploration=False, entry_source="alpha",
            regime_at_entry="trending_up", regime_at_exit="chop",
            mfe=600.0, mae=-120.0, bars_held_at_exit=10,
            time_in_trade_seconds=3600.5,
        )
        defaults.update(overrides)
        return TradeRecord(**defaults)

    def test_trade_roundtrip_preserves_forensic_fields(self, tmp_path):
        """Save trades with forensic fields, reload, verify all fields match."""
        from backend.organism.brain_persistence import OrganismBrain

        trades = [
            self._make_trade_record(symbol="AAPL", entry_source="alpha", mfe=600.0),
            self._make_trade_record(symbol="MSFT", entry_source="breakout",
                                    regime_at_entry="high_vol", mae=-200.0,
                                    bars_held_at_exit=5, time_in_trade_seconds=1800.25),
        ]

        brain = OrganismBrain.__new__(OrganismBrain)
        brain.brain_dir = tmp_path
        brain._save_trade_history(tmp_path, trades)

        # Reload the CSV
        csv_path = tmp_path / "trade_history.csv"
        assert csv_path.exists()
        df = pd.read_csv(csv_path)

        # Verify forensic columns are present
        for col in ["is_exploration", "entry_source", "regime_at_entry",
                     "regime_at_exit", "mfe", "mae", "bars_held_at_exit",
                     "time_in_trade_seconds"]:
            assert col in df.columns, f"Missing column: {col}"

        # Verify values round-trip
        assert df.iloc[0]["entry_source"] == "alpha"
        assert df.iloc[0]["regime_at_entry"] == "trending_up"
        assert abs(df.iloc[0]["mfe"] - 600.0) < 0.01
        assert df.iloc[1]["entry_source"] == "breakout"
        assert df.iloc[1]["regime_at_entry"] == "high_vol"
        assert abs(df.iloc[1]["mae"] - (-200.0)) < 0.01
        assert df.iloc[1]["bars_held_at_exit"] == 5

        # Now test get_trade_records() reconstruction
        brain.trade_history = df.to_dict("records")
        records = brain.get_trade_records()
        assert len(records) == 2
        assert records[0].entry_source == "alpha"
        assert records[0].regime_at_entry == "trending_up"
        assert abs(records[0].mfe - 600.0) < 0.01
        assert records[1].bars_held_at_exit == 5
        assert abs(records[1].time_in_trade_seconds - 1800.25) < 0.01

    def test_backward_compat_old_trade_csv(self, tmp_path):
        """Load a trade CSV missing forensic columns -- defaults are used."""
        from backend.organism.brain_persistence import OrganismBrain

        # Write a CSV with only the original 12 fields + correct_direction
        csv_path = tmp_path / "trade_history.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "symbol", "direction", "entry_price", "exit_price",
                "entry_bar", "exit_bar", "shares", "pnl",
                "exit_reason", "predicted_return", "actual_return",
                "confidence", "correct_direction",
            ])
            writer.writeheader()
            writer.writerow({
                "symbol": "GOOG", "direction": 1.0, "entry_price": 100.0,
                "exit_price": 105.0, "entry_bar": 1, "exit_bar": 5,
                "shares": 50, "pnl": 250.0, "exit_reason": "target",
                "predicted_return": 0.05, "actual_return": 0.05,
                "confidence": 0.8, "correct_direction": True,
            })

        df = pd.read_csv(csv_path)
        brain = OrganismBrain.__new__(OrganismBrain)
        brain.trade_history = df.to_dict("records")

        records = brain.get_trade_records()
        assert len(records) == 1
        r = records[0]
        # Forensic fields should have defaults
        assert r.is_exploration is False
        assert r.entry_source == ""
        assert r.regime_at_entry == ""
        assert r.regime_at_exit == ""
        assert r.mfe == 0.0
        assert r.mae == 0.0
        assert r.bars_held_at_exit == 0
        assert r.time_in_trade_seconds == 0.0

    def test_apply_to_learner_restores_forensic_fields(self):
        """apply_to_learner restores forensic fields into TradeRecord objects."""
        from backend.organism.brain_persistence import OrganismBrain

        brain = OrganismBrain.__new__(OrganismBrain)
        brain.learning_state = {
            "generation": 1, "total_bars_seen": 100, "total_trades": 1,
            "cumulative_pnl": 50.0, "best_sharpe": 1.5,
            "best_generation": 1, "retrain_count": 0,
            "drift_events": 0, "generation_accuracies": [],
            "bars_since_retrain": 0,
        }
        brain.ml_state = {}
        brain.reference_features = None
        # V12 W88 (post-cleanup): apply_to_learner now reads
        # evaluation_event_history (added in V8/V9 wave for J4 coverage).
        # Pre-W88 the test fixture didn't carry it; apply_to_learner
        # raised AttributeError and returned False.  Provide an empty
        # list so the restore succeeds.
        brain.evaluation_event_history = []
        brain.extra_counters = {}
        brain.evolved_params = {}
        brain.governance_state = {}
        brain.regime_state = {}
        brain.trade_history = [{
            "symbol": "AAPL", "direction": 1.0, "entry_price": 150.0,
            "exit_price": 155.0, "entry_bar": 10, "exit_bar": 20,
            "shares": 100, "pnl": 500.0, "exit_reason": "target",
            "predicted_return": 0.03, "actual_return": 0.033,
            "confidence": 0.75,
            "is_exploration": False, "entry_source": "alpha",
            "regime_at_entry": "trending_up", "regime_at_exit": "chop",
            "mfe": 600.0, "mae": -120.0, "bars_held_at_exit": 10,
            "time_in_trade_seconds": 3600.5,
        }]

        learner = MagicMock()
        learner.state = None
        learner.trade_history = []
        learner._reference_features = None
        learner._bars_since_retrain = 0

        result = brain.apply_to_learner(learner)
        assert result is True
        assert len(learner.trade_history) == 1
        t = learner.trade_history[0]
        assert t.entry_source == "alpha"
        assert t.regime_at_entry == "trending_up"
        assert t.regime_at_exit == "chop"
        assert abs(t.mfe - 600.0) < 0.01
        assert abs(t.mae - (-120.0)) < 0.01
        assert t.bars_held_at_exit == 10
        assert abs(t.time_in_trade_seconds - 3600.5) < 0.01
