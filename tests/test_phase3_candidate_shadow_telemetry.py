"""Tests for Phase 3 candidate-filter shadow telemetry."""

from __future__ import annotations

import json
from pathlib import Path

from backend.organism.candidate_shadow_telemetry import (
    CandidateShadowTelemetryRecorder,
    build_candidate_shadow_events,
    candidate_filter_tags,
    infer_entry_source,
)


def test_candidate_filter_tags_match_phase3_filters():
    candidate = {
        "symbol": "AAPL",
        "confidence": 0.50,
        "breakout_score": 0.45,
        "predicted_return": 0.01,
    }

    assert infer_entry_source(candidate) == "alpha+breakout"
    assert candidate_filter_tags(candidate, "chop") == [
        "conf_45_55",
        "alpha_breakout_chop",
    ]
    assert candidate_filter_tags({**candidate, "confidence": 0.60}, "chop") == [
        "alpha_breakout_chop",
    ]
    assert candidate_filter_tags({**candidate, "confidence": 0.50}, "trend") == [
        "conf_45_55",
    ]


def test_build_candidate_shadow_events_records_only_matching_candidates():
    events = build_candidate_shadow_events(
        [
            {
                "symbol": "AAPL",
                "direction": 1,
                "confidence": 0.50,
                "effective_confidence": 0.48,
                "breakout_score": 0.45,
                "predicted_return": 0.004,
                "ranking_score": 0.2,
            },
            {
                "symbol": "MSFT",
                "direction": 1,
                "confidence": 0.70,
                "breakout_score": 0.10,
                "predicted_return": 0.004,
            },
        ],
        regime="chop",
        tick=42,
        timestamp="2026-05-04T14:00:00Z",
    )

    assert len(events) == 1
    assert events[0].symbol == "AAPL"
    assert events[0].live_pipeline_candidate is True
    assert events[0].matched_filters == ["conf_45_55", "alpha_breakout_chop"]
    assert events[0].to_dict()["confidence"] == 0.5


def test_candidate_shadow_recorder_writes_jsonl(tmp_path: Path):
    path = tmp_path / "shadow" / "candidate_filter_shadow_telemetry.jsonl"
    recorder = CandidateShadowTelemetryRecorder(path)

    written = recorder.record_candidates(
        [
            {
                "symbol": "AAPL",
                "direction": 1,
                "confidence": 0.50,
                "breakout_score": 0.45,
                "predicted_return": 0.004,
            },
            {
                "symbol": "MSFT",
                "direction": 1,
                "confidence": 0.80,
                "breakout_score": 0.10,
                "predicted_return": 0.004,
            },
        ],
        regime="chop",
        tick=1,
        timestamp="2026-05-04T14:00:00Z",
    )

    assert written == 1
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["matched_filters"] == ["conf_45_55", "alpha_breakout_chop"]


def test_live_engine_shadow_telemetry_is_disabled_by_default_and_pre_sizing():
    src = (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()

    assert (
        'ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED", False'
        in src
    )
    block_start = src.find(
        "This records\n"
        "                # only proposed no-entry filter matches"
    )
    assert block_start >= 0
    sizing_start = src.find("# 8. SIZE POSITIONS", block_start)
    block = src[block_start:sizing_start]
    assert "record_candidates(" in block
    forbidden = [
        "cand_dicts.append",
        "_submit_entry_order",
        "submit_symbol_order",
        "size_positions(",
    ]
    for token in forbidden:
        assert token not in block


def test_runtime_snapshot_includes_shadow_telemetry_switches():
    from scripts.runtime.write_runtime_snapshot import _build_defaults_snapshot

    snapshot = _build_defaults_snapshot()

    assert snapshot["candidate_filter_shadow_telemetry_enabled"] is False
    assert (
        snapshot["candidate_filter_shadow_telemetry_path"]
        == "organism_brain/candidate_filter_shadow_telemetry.jsonl"
    )
