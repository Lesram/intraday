"""Tests for Phase 5 candidate-filter shadow outcome joins."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.phase5_shadow_outcome_join import (
    ShadowOutcomeConfig,
    join_event_to_bars,
    parse_horizons,
    run_outcome_join,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bars(rows: int = 20) -> pd.DataFrame:
    timestamps = pd.date_range("2026-05-05T14:00:00Z", periods=rows, freq="min", tz="UTC")
    close = [100.0 + i for i in range(rows)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": close,
        "high": [value + 0.2 for value in close],
        "low": [value - 0.2 for value in close],
        "close": close,
        "volume": [1000.0 + i for i in range(rows)],
    })


def _event(**overrides):
    event = {
        "_line_number": 1,
        "timestamp": "2026-05-05T14:02:00Z",
        "symbol": "AAPL",
        "regime": "chop",
        "direction": 1,
        "confidence": 0.50,
        "matched_filters": ["conf_45_55", "alpha_breakout_chop"],
    }
    event.update(overrides)
    return event


def test_parse_horizons_validates_positive_values():
    assert parse_horizons("1,5,5,10") == (1, 5, 10)
    assert parse_horizons(None) == (1, 5, 10)
    with pytest.raises(ValueError):
        parse_horizons("0")


def test_join_event_to_bars_computes_directional_returns():
    rows = join_event_to_bars(
        _event(),
        {"AAPL": _bars()},
        ShadowOutcomeConfig(horizons=(1, 5)),
    )

    assert [row["status"] for row in rows] == ["joined", "joined"]
    assert rows[0]["directional_return_bps"] == pytest.approx(98.0392)
    assert rows[1]["directional_return_bps"] == pytest.approx(490.1961)


def test_join_event_to_bars_respects_short_direction():
    rows = join_event_to_bars(
        _event(direction=-1),
        {"AAPL": _bars()},
        ShadowOutcomeConfig(horizons=(1,)),
    )

    assert rows[0]["directional_return_bps"] < 0


def test_join_event_to_bars_flags_missing_symbols_and_large_gaps():
    missing = join_event_to_bars(
        _event(symbol="MSFT"),
        {"AAPL": _bars()},
        ShadowOutcomeConfig(horizons=(1,)),
    )
    stale = join_event_to_bars(
        _event(timestamp="2026-05-05T14:02:30Z"),
        {"AAPL": _bars()},
        ShadowOutcomeConfig(horizons=(1,), max_event_to_bar_gap_seconds=10),
    )

    assert missing[0]["status"] == "symbol_missing_from_bars"
    assert stale[0]["status"] == "bar_gap_too_large"


def test_run_outcome_join_summarizes_filters_and_blocks_promotion():
    config = ShadowOutcomeConfig(
        horizons=(1,),
        min_events_per_filter=2,
        min_outcomes_per_filter=2,
    )
    summary = run_outcome_join(
        [_event(_line_number=1), _event(_line_number=2, timestamp="2026-05-05T14:03:00Z")],
        {"AAPL": _bars()},
        config,
    )

    by_filter = {row["filter"]: row for row in summary["filter_horizon_summary"]}
    assert by_filter["conf_45_55"]["events"] == 2
    assert by_filter["conf_45_55"]["outcomes"] == 2
    assert by_filter["conf_45_55"]["sample_gate_passed"] is True
    assert summary["recommendation"] == "eligible_for_replay_review_not_live_promotion"


def test_run_outcome_join_handles_no_events():
    summary = run_outcome_join([], {"AAPL": _bars()}, ShadowOutcomeConfig())

    assert summary["recommendation"] == "await_live_shadow_session"
    assert summary["valid_events"] == 0


def test_paper_compose_wires_phase5_shadow_telemetry_env():
    src = (REPO_ROOT / "docker-compose.paper.yml").read_text()

    assert (
        "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED="
        "${ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED:-false}"
    ) in src
    assert "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH=" in src
    assert (
        "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED="
        "${ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED:-false}"
    ) in src
    assert "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH=" in src
    assert (
        "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED="
        "${ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED:-false}"
    ) in src
