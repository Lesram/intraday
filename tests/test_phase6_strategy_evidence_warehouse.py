"""Tests for Phase 6 strategy evidence warehouse."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.phase5_shadow_outcome_join import ShadowOutcomeConfig
from scripts.phase6_strategy_evidence_warehouse import (
    build_advisory_policy,
    build_warehouse,
    expand_events_for_warehouse,
    write_warehouse_outputs,
)


def _bars() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-05-05T14:00:00Z", periods=20, freq="min", tz="UTC"),
        "open": [100.0 + i for i in range(20)],
        "high": [100.5 + i for i in range(20)],
        "low": [99.5 + i for i in range(20)],
        "close": [100.0 - (i * 0.1) for i in range(20)],
        "volume": [1000.0] * 20,
    })


def test_expand_events_adds_all_candidate_and_untagged_buckets():
    events = expand_events_for_warehouse([
        {"symbol": "AAPL", "matched_filters": ["conf_45_55"]},
        {"symbol": "MSFT", "matched_filters": []},
    ])

    assert events[0]["matched_filters"] == ["all_candidates", "conf_45_55"]
    assert events[1]["matched_filters"] == ["all_candidates", "untagged"]


def test_build_advisory_policy_rejects_negative_passed_sample_and_collects_small_sample():
    policy = build_advisory_policy(
        [
            {
                "filter": "alpha_breakout_chop",
                "horizon_bars": 5,
                "events": 56,
                "outcomes": 56,
                "sample_gate_passed": True,
                "outcome_gate_passed": True,
                "mean_directional_bps": -3.0,
                "win_rate": 0.34,
            },
            {
                "filter": "conf_45_55",
                "horizon_bars": 5,
                "events": 14,
                "outcomes": 14,
                "sample_gate_passed": False,
                "outcome_gate_passed": False,
                "mean_directional_bps": 7.0,
                "win_rate": 0.5,
            },
        ],
        primary_horizon=5,
        min_mean_directional_bps=1.0,
        min_win_rate=0.5,
    )

    actions = {row["filter"]: row["shadow_action"] for row in policy["actions"]}
    assert actions["alpha_breakout_chop"] == "reject_or_redesign"
    assert actions["conf_45_55"] == "collect_more_shadow_sample"


def test_build_warehouse_writes_research_outputs(tmp_path: Path):
    telemetry = tmp_path / "strategy_evidence_events.jsonl"
    telemetry.write_text(
        "\n".join(
            json.dumps({
                "timestamp": "2026-05-05T14:00:00Z",
                "tick": i,
                "symbol": "AAPL",
                "direction": 1,
                "confidence": 0.5,
                "effective_confidence": 0.5,
                "breakout_score": 0.45,
                "predicted_return": 0.01,
                "ranking_score": 0.2,
                "entry_source": "alpha+breakout",
                "matched_filters": ["conf_45_55"],
            })
            for i in range(3)
        )
        + "\n"
    )
    payload = build_warehouse(
        telemetry_path=telemetry,
        bars={"AAPL": _bars()},
        config=ShadowOutcomeConfig(
            horizons=(1, 5),
            min_events_per_filter=3,
            min_outcomes_per_filter=3,
        ),
        primary_horizon=5,
        min_mean_directional_bps=1.0,
        min_win_rate=0.5,
    )
    outputs = write_warehouse_outputs(payload, tmp_path / "out")

    assert Path(outputs["events"]).is_file()
    assert Path(outputs["outcomes"]).is_file()
    assert Path(outputs["advisory_policy"]).is_file()
    assert Path(outputs["postclose_report"]).read_text().startswith(
        "# Phase 6 Post-Close Strategy Research Report"
    )
    policy = json.loads(Path(outputs["advisory_policy"]).read_text())
    actions = {row["filter"]: row["shadow_action"] for row in policy["actions"]}
    assert actions["conf_45_55"] == "reject_or_redesign"
