"""Patch Queue J3 -- evidence-based operational pass, daily model events, SHA verification."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# -- Helpers ----------------------------------------------------------------

def _make_trade(
    symbol: str = "AAPL",
    pnl: float = 10.0,
    exit_reason: str = "take_profit",
    closed_at: str = "2026-03-10T15:30:00+00:00",
    confidence: float = 0.5,
    is_exploration: bool = False,
    **kwargs,
) -> dict:
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
        "predicted_return": 0.0,
        "actual_return": pnl / 1000,
        "confidence": confidence,
        "correct_direction": pnl > 0,
        "is_exploration": is_exploration,
        "entry_source": "alpha",
        "regime_at_entry": "trending_up",
        "regime_at_exit": "trending_up",
        "mfe": 0,
        "mae": 0,
        "bars_held_at_exit": 10,
        "time_in_trade_seconds": 600,
        "closed_at": closed_at,
        **kwargs,
    }


# -- 1. paper_validation_pass is evidence-based ----------------------------

class TestEvidenceBasedPass:
    def test_not_hardcoded_true(self):
        """pass should fail when exploration > 0."""
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        trades = [_make_trade(is_exploration=True)]
        kpi = generate_kpi_summary(trades, {}, "2026-03-10", "abc")
        assert kpi["paper_validation_pass"] is False
        assert kpi["operational_checks"]["exploration_count_zero"] is False

    def test_bundle_incomplete_fails_pass(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            bundle_files_ok=False,
        )
        assert kpi["paper_validation_pass"] is False
        assert kpi["operational_checks"]["bundle_files_complete"] is False

    def test_stale_runtime_fails_pass(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            runtime_stale=True,
        )
        assert kpi["paper_validation_pass"] is False
        assert kpi["operational_checks"]["no_stale_runtime"] is False

    def test_api_unreachable_noted_not_failed(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            api_reachable=False,
        )
        # Should still pass (API offline is a note, not a failure)
        assert kpi["paper_validation_pass"] is True
        assert "api_not_reachable" in kpi["operational_notes"]

    def test_legacy_excluded_noted(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade()], {}, "2026-03-10", "abc",
            legacy_excluded=42,
        )
        assert any("legacy" in n for n in kpi["operational_notes"])

    def test_all_checks_pass(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_kpi_summary
        kpi = generate_kpi_summary(
            [_make_trade(pnl=50), _make_trade(pnl=-10, exit_reason="stop_loss")],
            {"take_profit": {"count": 1}, "stop_loss": {"count": 1}},
            "2026-03-10", "abc",
            bundle_files_ok=True, api_reachable=True,
        )
        assert kpi["paper_validation_pass"] is True
        assert all(kpi["operational_checks"].values())


# -- 2. Daily model acceptance/rejection filtering -------------------------

class TestDailyModelEvents:
    def test_filters_acceptance_by_date(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality
        ml_state = {
            "calibration": {"counts": [], "map": []},
            "model_metrics_history": [
                {"evaluated_at": "2026-03-09T10:00:00+00:00", "accepted": True, "generation": 1},
                {"evaluated_at": "2026-03-10T10:00:00+00:00", "accepted": True, "generation": 2},
                {"evaluated_at": "2026-03-10T14:00:00+00:00", "accepted": True, "generation": 3},
                {"evaluated_at": "2026-03-11T10:00:00+00:00", "accepted": True, "generation": 4},
            ],
        }
        result = generate_model_quality({}, ml_state, {}, date="2026-03-10")
        events = result["acceptance_events"]
        assert events["lifetime_evaluations"] == 4
        assert events["lifetime_accepted"] == 4
        assert events["today_evaluations"] == 2
        assert events["today_accepted"] == 2

    def test_old_records_without_timestamp_backward_compat(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality
        ml_state = {
            "calibration": {"counts": [], "map": []},
            "model_metrics_history": [
                {"generation": 1},  # no evaluated_at
                {"generation": 2, "evaluated_at": "2026-03-10T10:00:00+00:00", "accepted": True},
            ],
        }
        result = generate_model_quality({}, ml_state, {}, date="2026-03-10")
        events = result["acceptance_events"]
        assert events["lifetime_evaluations"] == 2
        assert events["today_evaluations"] == 1  # only the one with timestamp

    def test_no_history_returns_zeros(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_model_quality
        result = generate_model_quality({}, {}, {}, date="2026-03-10")
        events = result["acceptance_events"]
        assert events["lifetime_evaluations"] == 0
        assert events["today_evaluations"] == 0


# -- 3. ModelMetrics evaluated_at field ------------------------------------

class TestModelMetricsTimestamp:
    def test_field_exists_with_default(self):
        from backend.organism.ml_signal import ModelMetrics
        mm = ModelMetrics(generation=1)
        assert mm.evaluated_at == ""

    def test_field_serialized_in_to_dict(self):
        from backend.organism.ml_signal import ModelMetrics
        mm = ModelMetrics(generation=1, evaluated_at="2026-03-10T10:00:00+00:00")
        d = mm.to_dict()
        assert d["evaluated_at"] == "2026-03-10T10:00:00+00:00"

    def test_backward_compat_no_kwarg(self):
        from backend.organism.ml_signal import ModelMetrics
        mm = ModelMetrics(generation=1)
        assert hasattr(mm, "evaluated_at")


# -- 4. SHA match logic ----------------------------------------------------

class TestSHAVerification:
    def test_sha_match_true(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_runtime_snapshot
        with patch("scripts.runtime.generate_paper_validation_bundle._load_resolved_snapshot", return_value=None):
            with patch("scripts.runtime.generate_paper_validation_bundle._get_runtime_sha", return_value="abc1234"):
                snap = generate_runtime_snapshot(
                    trades=[], day_trades=[], manifest={},
                    api_status=None, sha="abc1234", date="2026-03-10",
                )
        assert snap["sha_match"] is True
        assert snap["runtime_reported_sha"] == "abc1234"

    def test_sha_mismatch(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_runtime_snapshot
        with patch("scripts.runtime.generate_paper_validation_bundle._load_resolved_snapshot", return_value=None):
            with patch("scripts.runtime.generate_paper_validation_bundle._get_runtime_sha", return_value="def5678"):
                snap = generate_runtime_snapshot(
                    trades=[], day_trades=[], manifest={},
                    api_status=None, sha="abc1234", date="2026-03-10",
                )
        assert snap["sha_match"] is False

    def test_sha_unknown_when_unreachable(self):
        from scripts.runtime.generate_paper_validation_bundle import generate_runtime_snapshot
        with patch("scripts.runtime.generate_paper_validation_bundle._load_resolved_snapshot", return_value=None):
            with patch("scripts.runtime.generate_paper_validation_bundle._get_runtime_sha", return_value=None):
                snap = generate_runtime_snapshot(
                    trades=[], day_trades=[], manifest={},
                    api_status=None, sha="abc1234", date="2026-03-10",
                )
        assert snap["sha_match"] == "unknown"
        assert snap["runtime_reported_sha"] == "unknown"


# -- 5. Unrealized PnL extraction -----------------------------------------

class TestUnrealizedPnL:
    def test_direct_field(self):
        from scripts.runtime.generate_paper_validation_bundle import _extract_unrealized_pnl
        assert _extract_unrealized_pnl({"unrealized_pnl": -42.5}) == -42.5

    def test_nested_in_live_engine(self):
        from scripts.runtime.generate_paper_validation_bundle import _extract_unrealized_pnl
        api = {"live_engine": {"engine": {"unrealized_pnl": 100.0}}}
        assert _extract_unrealized_pnl(api) == 100.0

    def test_open_positions_pnl(self):
        from scripts.runtime.generate_paper_validation_bundle import _extract_unrealized_pnl
        assert _extract_unrealized_pnl({"open_positions_pnl": -5.0}) == -5.0

    def test_returns_none_when_absent(self):
        from scripts.runtime.generate_paper_validation_bundle import _extract_unrealized_pnl
        assert _extract_unrealized_pnl({"tick_count": 100}) is None

    def test_returns_none_for_no_api(self):
        from scripts.runtime.generate_paper_validation_bundle import _extract_unrealized_pnl
        assert _extract_unrealized_pnl(None) is None


# -- 6. Brain persistence preserves evaluated_at --------------------------

class TestBrainPersistenceEvaluatedAt:
    def test_save_history_includes_evaluated_at(self):
        """Verify _save_model_metrics_history includes evaluated_at and accepted."""
        import json
        import tempfile
        from backend.organism.brain_persistence import OrganismBrain, _read_json
        from backend.organism.ml_signal import ModelMetrics

        class FakeLearnerState:
            model_metrics = [
                ModelMetrics(generation=1, evaluated_at="2026-03-10T10:00:00+00:00"),
            ]

        class FakeLearner:
            state = FakeLearnerState()

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            # Write an empty ml_state.json first
            (Path(tmpdir) / "ml_state.json").write_text("{}")
            brain._save_model_metrics_history(Path(tmpdir), FakeLearner())
            ml_state = json.loads((Path(tmpdir) / "ml_state.json").read_text())
            history = ml_state["model_metrics_history"]
            assert len(history) == 1
            assert history[0]["evaluated_at"] == "2026-03-10T10:00:00+00:00"
            assert history[0]["accepted"] is True
