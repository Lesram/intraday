"""Tests for Phase 3 candidate-filter counterfactual replay."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.phase3_candidate_filter_replay import (
    ReplayConfig,
    _selected_scenarios,
    default_scenarios,
    evaluate_scenario,
    max_drawdown,
    run_counterfactuals,
    write_outputs,
)
from scripts.phase3_trade_attribution import is_reconciliation_artifact, normalise_trade


def _record(
    pnl: float,
    *,
    symbol: str = "AAPL",
    confidence: float = 0.6,
    entry_source: str = "alpha",
    regime_at_entry: str = "chop",
    exit_reason: str = "stop_loss",
):
    row = {
        "symbol": symbol,
        "direction": "1.0",
        "pnl": str(pnl),
        "exit_reason": exit_reason,
        "predicted_return": "0.001",
        "actual_return": "0.001",
        "confidence": str(confidence),
        "correct_direction": "true" if pnl > 0 else "false",
        "is_reconciliation_artifact": "false",
        "entry_source": entry_source,
        "regime_at_entry": regime_at_entry,
        "regime_at_exit": regime_at_entry,
        "mfe": "1.0",
        "mae": "-1.0",
        "bars_held_at_exit": "5",
        "time_in_trade_seconds": "300",
        "closed_at": "2026-05-04T14:00:00Z",
    }
    assert not is_reconciliation_artifact(row)
    record = normalise_trade(row)
    assert record is not None
    return record


def test_max_drawdown_uses_ordered_pnl_curve():
    records = [_record(5), _record(-2), _record(4), _record(-10), _record(3)]

    assert max_drawdown(records) == -10.0


def test_alpha_breakout_chop_filter_improves_bad_slice():
    scenario = next(s for s in default_scenarios() if s.name == "skip_alpha_breakout_chop")
    records = [
        *[
            _record(
                -2.0,
                entry_source="alpha+breakout",
                regime_at_entry="chop",
            )
            for _ in range(12)
        ],
        *[
            _record(
                1.0,
                entry_source="breakout",
                regime_at_entry="trending_up",
                exit_reason="max_holding_period",
            )
            for _ in range(12)
        ],
    ]

    result = evaluate_scenario(
        records,
        scenario,
        window="last_50",
        config=ReplayConfig(min_recent_skipped_trades=10, min_net_pnl_delta=5.0),
    )

    assert result["skipped"]["n_trades"] == 12
    assert result["skipped_total_pnl"] == -24.0
    assert result["net_pnl_delta"] == 24.0
    assert result["opportunity_cost"] == 0.0
    assert result["recommendation"] == "shadow_candidate_from_trade_history_counterfactual"


def test_counterfactual_accounts_for_opportunity_cost():
    scenario = next(s for s in default_scenarios() if s.name == "skip_conf_45_55")
    records = [
        _record(-5.0, confidence=0.50),
        _record(3.0, confidence=0.50, exit_reason="take_profit"),
        _record(2.0, confidence=0.70, exit_reason="take_profit"),
    ]

    result = evaluate_scenario(
        records,
        scenario,
        window="all",
        config=ReplayConfig(min_all_skipped_trades=1, min_net_pnl_delta=1.0),
    )

    assert result["skipped"]["n_trades"] == 2
    assert result["avoided_loss"] == 5.0
    assert result["opportunity_cost"] == 3.0
    assert result["net_pnl_delta"] == 2.0


def test_insufficient_sample_blocks_promotion_language():
    scenario = next(s for s in default_scenarios() if s.name == "skip_avgo")
    records = [
        _record(-100.0, symbol="AVGO"),
        _record(1.0, symbol="MSFT", exit_reason="take_profit"),
    ]

    result = evaluate_scenario(records, scenario, window="all", config=ReplayConfig())

    assert result["net_pnl_delta"] == 100.0
    assert result["recommendation"] == "insufficient_sample"


def test_run_counterfactuals_and_outputs(tmp_path: Path):
    records = [
        *[
            _record(
                -2.0,
                confidence=0.50,
                entry_source="alpha+breakout",
                regime_at_entry="chop",
            )
            for _ in range(12)
        ],
        *[
            _record(
                1.0,
                confidence=0.70,
                entry_source="breakout",
                regime_at_entry="trending_up",
                exit_reason="max_holding_period",
            )
            for _ in range(12)
        ],
    ]
    scenarios = _selected_scenarios("skip_alpha_breakout_chop,skip_conf_45_55")

    summary = run_counterfactuals(
        records,
        {"source_csv": "synthetic", "strategy_rows": len(records)},
        scenarios,
        ReplayConfig(min_recent_skipped_trades=10, min_all_skipped_trades=10),
    )
    outputs = write_outputs(summary, tmp_path)

    loaded = json.loads(Path(outputs["summary"]).read_text())
    assert loaded["scope"] == "closed_trade_counterfactual_no_live_behavior_change"
    assert loaded["windows"]["all"][0]["net_pnl_delta"] == 24.0
    assert Path(outputs["results"]).read_text().startswith("window,scenario,recommendation")
