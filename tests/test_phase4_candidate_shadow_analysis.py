"""Tests for Phase 4 candidate-filter shadow telemetry analysis."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.phase4_candidate_shadow_analysis import (
    CandidateShadowAnalysisConfig,
    load_shadow_events,
    summarize_shadow_events,
    write_outputs,
)


def test_missing_shadow_file_is_not_an_error(tmp_path: Path):
    events = load_shadow_events(tmp_path / "missing.jsonl")
    summary = summarize_shadow_events(events, CandidateShadowAnalysisConfig())

    assert events == []
    assert summary["recommendation"] == "await_live_shadow_session"
    assert summary["valid_events"] == 0


def test_shadow_summary_counts_filters_and_outcomes():
    events = [
        {
            "symbol": "AAPL",
            "regime": "chop",
            "confidence": 0.50,
            "matched_filters": ["conf_45_55", "alpha_breakout_chop"],
            "outcome_bps": 12.5,
        },
        {
            "symbol": "AAPL",
            "regime": "chop",
            "confidence": 0.60,
            "matched_filters": ["alpha_breakout_chop"],
            "outcome_bps": -5.0,
        },
    ]

    summary = summarize_shadow_events(
        events,
        CandidateShadowAnalysisConfig(min_events=1, min_outcome_events=1),
    )

    by_filter = {row["filter"]: row for row in summary["filters"]}
    assert by_filter["alpha_breakout_chop"]["events"] == 2
    assert by_filter["alpha_breakout_chop"]["events_with_outcome"] == 2
    assert by_filter["conf_45_55"]["win_rate"] == 1.0
    assert summary["recommendation"] == "eligible_for_replay_review_not_live_promotion"


def test_load_shadow_events_preserves_invalid_rows(tmp_path: Path):
    path = tmp_path / "shadow.jsonl"
    path.write_text(
        json.dumps({"symbol": "AAPL", "matched_filters": ["conf_45_55"]})
        + "\nnot-json\n"
    )

    events = load_shadow_events(path)
    summary = summarize_shadow_events(events, CandidateShadowAnalysisConfig())

    assert len(events) == 2
    assert summary["invalid_rows"] == 1
    assert summary["valid_events"] == 1


def test_write_outputs_creates_summary_and_filter_csv(tmp_path: Path):
    summary = summarize_shadow_events(
        [
            {
                "symbol": "AAPL",
                "regime": "chop",
                "confidence": 0.50,
                "matched_filters": ["conf_45_55"],
            }
        ],
        CandidateShadowAnalysisConfig(min_events=1),
    )

    outputs = write_outputs(summary, tmp_path)

    assert Path(outputs["summary"]).is_file()
    assert Path(outputs["filters"]).read_text().startswith("filter,events")
