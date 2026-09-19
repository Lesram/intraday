"""Patch Queue J2 -- daily bundle, close timestamps, honest signals, split pass."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.organism.continuous_learner import TradeRecord


# -- Helpers ----------------------------------------------------------------

def _make_trade(
    symbol: str = "AAPL",
    pnl: float = 10.0,
    exit_reason: str = "take_profit",
    closed_at: str = "2026-03-10T15:30:00+00:00",
    predicted_return: float = 0.0,
    confidence: float = 0.5,
    entry_source: str = "alpha",
    regime_at_entry: str = "trending_up",
    is_exploration: bool = False,
) -> dict:
    """Create a trade dict mimicking CSV-loaded row."""
    return {
        "symbol": symbol,
        "direction": 1.0,
        "entry_price": 100.0,
        "exit_price": 100.0 + pnl / 10,
        "entry_bar": 0,
        "exit_bar": 10,
        "shares": 10,
        "pnl": pnl,
        "exit_reason": exit_reason,
        "predicted_return": predicted_return,
        "actual_return": pnl / 1000,
        "confidence": confidence,
        "correct_direction": pnl > 0,
        "is_exploration": is_exploration,
        "entry_source": entry_source,
        "regime_at_entry": regime_at_entry,
        "regime_at_exit": regime_at_entry,
        "mfe": abs(pnl) if pnl > 0 else 0,
        "mae": abs(pnl) if pnl < 0 else 0,
        "bars_held_at_exit": 10,
        "time_in_trade_seconds": 600,
        "closed_at": closed_at,
    }


# -- 1. TradeRecord has closed_at ------------------------------------------

class TestTradeRecordClosedAt:
    def test_field_exists_with_default(self):
        tr = TradeRecord(
            symbol="AAPL", direction=1, entry_price=100, exit_price=101,
            entry_bar=0, exit_bar=1, shares=10, pnl=10,
            exit_reason="tp", predicted_return=0, actual_return=0.01,
            confidence=0.5,
        )
        assert tr.closed_at == ""

    def test_field_accepts_iso_timestamp(self):
        ts = "2026-03-10T15:30:00+00:00"
        tr = TradeRecord(
            symbol="AAPL", direction=1, entry_price=100, exit_price=101,
            entry_bar=0, exit_bar=1, shares=10, pnl=10,
            exit_reason="tp", predicted_return=0, actual_return=0.01,
            confidence=0.5, closed_at=ts,
        )
        assert tr.closed_at == ts

    def test_backward_compat_no_closed_at_kwarg(self):
        """Old callers that don't pass closed_at should still work."""
        tr = TradeRecord(
            symbol="X", direction=1, entry_price=1, exit_price=1,
            entry_bar=0, exit_bar=0, shares=1, pnl=0,
            exit_reason="x", predicted_return=0, actual_return=0,
            confidence=0,
        )
        assert hasattr(tr, "closed_at")
        assert tr.closed_at == ""


# -- 2. Date filtering -----------------------------------------------------

class TestDateFiltering:
    def test_filters_to_requested_date(self):
        from scripts.runtime.generate_paper_validation_bundle import _filter_trades_by_date
        trades = [
            _make_trade(closed_at="2026-03-10T10:00:00+00:00"),
            _make_trade(closed_at="2026-03-10T15:30:00+00:00"),
            _make_trade(closed_at="2026-03-11T10:00:00+00:00"),
        ]
        filtered, legacy = _filter_trades_by_date(trades, "2026-03-10")
        assert len(filtered) == 2
        assert legacy == 0

    def test_excludes_legacy_trades_without_timestamp(self):
        from scripts.runtime.generate_paper_validation_bundle import _filter_trades_by_date
        trades = [
            _make_trade(closed_at="2026-03-10T10:00:00+00:00"),
            _make_trade(closed_at=""),  # legacy
            _make_trade(closed_at=""),  # legacy
        ]
        filtered, legacy = _filter_trades_by_date(trades, "2026-03-10")
        assert len(filtered) == 1
        assert legacy == 2

    def test_all_legacy_returns_empty(self):
        from scripts.runtime.generate_paper_validation_bundle import _filter_trades_by_date
        trades = [_make_trade(closed_at=""), _make_trade(closed_at="")]
        filtered, legacy = _filter_trades_by_date(trades, "2026-03-10")
        assert len(filtered) == 0
        assert legacy == 2

    def test_no_trades_on_date(self):
        from scripts.runtime.generate_paper_validation_bundle import _filter_trades_by_date
        trades = [_make_trade(closed_at="2026-03-09T10:00:00+00:00")]
        filtered, legacy = _filter_trades_by_date(trades, "2026-03-10")
        assert len(filtered) == 0
        assert legacy == 0


# -- 3. Runtime snapshot uses resolved config --------------------------------

class TestRuntimeSnapshotSource:
    def test_uses_resolved_snapshot_when_available(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_runtime_snapshot
        resolved = {
            "resolved": {
                "timeframe": "1Min",
                "timeframe_source": "container_env",
                "max_positions": 15,
                "alpha_top_n": 5,
                "universe_size": 22,
                "tick_interval_seconds": 10,
                "exploration_enabled": False,
                "drawdown_kill_pct": 0.2,
                "risk_budget_learning": 0.001,
                "risk_budget_production": 0.0025,
                "confidence_gate_baseline": 0.4,
                "fitness_gate_production": 0.45,
                "horizon_timeout_bars": 18,
            }
        }
        with patch("scripts.runtime.generate_paper_validation_bundle._load_resolved_snapshot", return_value=resolved):
            snap = generate_runtime_snapshot(
                trades=[_make_trade()] * 10,
                day_trades=[_make_trade()] * 3,
                manifest={"ml_is_trained": False, "generation": 0, "total_runs": 5},
                api_status=None, sha="abc1234", date="2026-03-10",
            )
        assert snap["snapshot_source"] == "resolved_config_snapshot"
        assert snap["timeframe"] == "1Min"
        assert snap["max_positions"] == 15
        assert snap["total_trades_lifetime"] == 10
        assert snap["total_trades_today"] == 3

    def test_falls_back_to_code_defaults(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_runtime_snapshot
        with patch("scripts.runtime.generate_paper_validation_bundle._load_resolved_snapshot", return_value=None):
            snap = generate_runtime_snapshot(
                trades=[], day_trades=[], manifest={}, api_status=None,
                sha="abc", date="2026-03-10",
            )
        assert snap["snapshot_source"] == "code_defaults"


# -- 4. Model quality uses actual values ------------------------------------

class TestModelQualityActual:
    def test_includes_system_calibration_values(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality
        ml_state = {
            "generation": 1,
            "calibration": {
                "counts": [[3, 10], [5, 10], [7, 10], [8, 10], [9, 10]],
                "map": [0.3, 0.5, 0.7, 0.8, 0.9],
            },
            "model_metrics_history": [
                {
                    "candidate_calibration_sample_count": 50,
                    "candidate_calibration_monotonic": True,
                    "candidate_calibration_error": 0.05,
                    "accuracy": 0.55,
                    "sharpe": 0.8,
                    "accepted": True,
                },
            ],
        }
        result = generate_model_quality(
            manifest={"ml_is_trained": True, "generation": 1},
            ml_state=ml_state,
            learning_state={"generation": 1, "retrain_count": 3, "total_trades": 250},
        )
        assert result["system_calibration"]["sample_count"] == 50
        assert result["system_calibration"]["monotonic"] is True
        assert "candidate_calibration_sample_count" in result["candidate_calibration"]
        assert result["candidate_calibration"]["accepted"] is True
        assert result["acceptance_events"]["lifetime_accepted"] == 1

    def test_empty_ml_state_shows_nulls(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality
        result = generate_model_quality(
            manifest={}, ml_state={}, learning_state={},
        )
        assert result["system_calibration"]["sample_count"] == 0
        assert "note" in result["candidate_calibration"]


# -- 5. Signal quality honesty -----------------------------------------------

class TestSignalQualityHonesty:
    def test_no_predictions_marks_unavailable(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_signal_quality
        trades = [_make_trade(predicted_return=0.0) for _ in range(10)]
        result = generate_signal_quality(trades)
        assert result["ml_predictions_available"] is False
        assert result["predicted_return_direction_match_rate"] is None
        assert result["total_trades_with_predictions"] == 0

    def test_with_predictions_computes_match_rate(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_signal_quality
        trades = [
            _make_trade(predicted_return=0.01, pnl=5.0),   # correct
            _make_trade(predicted_return=0.01, pnl=-5.0),  # incorrect
            _make_trade(predicted_return=-0.01, pnl=-5.0), # correct (short)
        ]
        # Set actual_return to match pnl sign
        trades[0]["actual_return"] = 0.01
        trades[1]["actual_return"] = -0.01
        trades[2]["actual_return"] = -0.01
        result = generate_signal_quality(trades)
        assert result["ml_predictions_available"] is True
        assert result["total_trades_with_predictions"] == 3
        assert result["predicted_return_direction_match_rate"] == round(2 / 3, 4)

    def test_ranking_quality_marked_unavailable(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_signal_quality
        result = generate_signal_quality([])
        assert result["ranking_quality_available"] is False

    def test_confidence_quintiles_present(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_signal_quality
        trades = [_make_trade(confidence=i * 0.1) for i in range(10)]
        result = generate_signal_quality(trades)
        assert len(result["confidence_quintiles"]) == 5


# -- 6. Operational vs strategy pass ----------------------------------------

class TestSplitPass:
    def test_operational_pass_strategy_fail(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        # Trades with payoff_ratio < 1.0
        trades = [
            _make_trade(pnl=-20, exit_reason="stop_loss"),
            _make_trade(pnl=5, exit_reason="take_profit"),
            _make_trade(pnl=-15, exit_reason="stop_loss"),
            _make_trade(pnl=3, exit_reason="take_profit"),
        ]
        exit_bd = {
            "stop_loss": {"count": 2, "total_pnl": -35, "avg_pnl": -17.5, "win_rate": 0},
            "take_profit": {"count": 2, "total_pnl": 8, "avg_pnl": 4, "win_rate": 1.0},
        }
        kpi = generate_kpi_summary(trades, exit_bd, "2026-03-10", "abc")
        assert kpi["paper_validation_pass"] is True   # operational pass
        assert kpi["strategy_quality_pass"] is False   # strategy fail
        assert len(kpi["strategy_quality_fail_reasons"]) > 0

    def test_both_pass_when_profitable(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        # stop_loss share must be <= 60% of total loss for strategy pass
        trades = [
            _make_trade(pnl=30, exit_reason="take_profit"),
            _make_trade(pnl=20, exit_reason="trailing_stop"),
            _make_trade(pnl=-5, exit_reason="stop_loss"),
            _make_trade(pnl=-10, exit_reason="failure_to_follow"),
        ]
        exit_bd = {
            "take_profit": {"count": 1, "total_pnl": 30},
            "trailing_stop": {"count": 1, "total_pnl": 20},
            "stop_loss": {"count": 1, "total_pnl": -5},
            "failure_to_follow": {"count": 1, "total_pnl": -10},
        }
        kpi = generate_kpi_summary(trades, exit_bd, "2026-03-10", "abc")
        assert kpi["paper_validation_pass"] is True
        assert kpi["strategy_quality_pass"] is True
        assert kpi["strategy_quality_fail_reasons"] == []

    def test_stop_loss_dominant_fails_strategy(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        # All losses from stop_loss (>60% share)
        trades = [
            _make_trade(pnl=-50, exit_reason="stop_loss"),
            _make_trade(pnl=-40, exit_reason="stop_loss"),
            _make_trade(pnl=-30, exit_reason="stop_loss"),
            _make_trade(pnl=100, exit_reason="take_profit"),
            _make_trade(pnl=-5, exit_reason="failure_to_follow"),
        ]
        exit_bd = {
            "stop_loss": {"count": 3, "total_pnl": -120},
            "take_profit": {"count": 1, "total_pnl": 100},
            "failure_to_follow": {"count": 1, "total_pnl": -5},
        }
        kpi = generate_kpi_summary(trades, exit_bd, "2026-03-10", "abc")
        assert kpi["strategy_quality_pass"] is False
        assert any("stop_loss" in r for r in kpi["strategy_quality_fail_reasons"])

    def test_no_trades_fails_strategy(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary([], {}, "2026-03-10", "abc")
        assert kpi["strategy_quality_pass"] is False
        assert "no_trades" in kpi["strategy_quality_fail_reasons"]


# -- 7. Brain persistence round-trip ----------------------------------------

class TestBrainPersistenceClosedAt:
    def test_save_includes_closed_at(self):
        """Verify _save_trade_history dict includes closed_at field."""
        from backend.organism.brain_persistence import OrganismBrain
        tr = TradeRecord(
            symbol="AAPL", direction=1, entry_price=100, exit_price=101,
            entry_bar=0, exit_bar=1, shares=10, pnl=10,
            exit_reason="tp", predicted_return=0, actual_return=0.01,
            confidence=0.5, closed_at="2026-03-10T15:30:00+00:00",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            brain._save_trade_history(Path(tmpdir), [tr])
            import pandas as pd
            df = pd.read_csv(Path(tmpdir) / "trade_history.csv")
            assert "closed_at" in df.columns
            assert df.iloc[0]["closed_at"] == "2026-03-10T15:30:00+00:00"

    def test_load_restores_closed_at(self):
        """Verify round-trip: save -> load -> trade dict has closed_at."""
        from backend.organism.brain_persistence import OrganismBrain
        tr = TradeRecord(
            symbol="AAPL", direction=1, entry_price=100, exit_price=101,
            entry_bar=0, exit_bar=1, shares=10, pnl=10,
            exit_reason="tp", predicted_return=0, actual_return=0.01,
            confidence=0.5, closed_at="2026-03-10T15:30:00+00:00",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            brain._save_trade_history(Path(tmpdir), [tr])
            # Reload
            brain2 = OrganismBrain(brain_dir=tmpdir)
            brain2._load_trade_history()
            assert len(brain2.trade_history) == 1
            assert brain2.trade_history[0]["closed_at"] == "2026-03-10T15:30:00+00:00"

    def test_legacy_csv_without_closed_at_loads_safely(self):
        """Old CSVs without closed_at column should load without error."""
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmpdir:
            df = pd.DataFrame([{
                "symbol": "AAPL", "direction": 1, "entry_price": 100,
                "exit_price": 101, "entry_bar": 0, "exit_bar": 1,
                "shares": 10, "pnl": 10, "exit_reason": "tp",
                "predicted_return": 0, "actual_return": 0.01,
                "confidence": 0.5, "correct_direction": True,
                "is_exploration": False, "entry_source": "",
                "regime_at_entry": "", "regime_at_exit": "",
                "mfe": 0, "mae": 0, "bars_held_at_exit": 0,
                "time_in_trade_seconds": 0,
            }])
            df.to_csv(Path(tmpdir) / "trade_history.csv", index=False)
            from backend.organism.brain_persistence import OrganismBrain
            brain = OrganismBrain(brain_dir=tmpdir)
            brain._load_trade_history()
            assert len(brain.trade_history) == 1
            # closed_at not in CSV, so it won't be in the dict -- that's fine
            # The TradeRecord constructor in apply_to_learner uses .get("closed_at", "")
