"""Tests for Phase 3 candidate-filter shadow telemetry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from backend.organism.candidate_shadow_telemetry import (
    CandidateShadowTelemetryRecorder,
    build_candidate_shadow_events,
    candidate_filter_tags,
    infer_entry_source,
)


class _FakeCandidateRecorder:
    def __init__(
        self,
        *,
        written: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.written = written
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def record_candidates(
        self,
        candidates,
        *,
        regime: str,
        tick: int,
        timestamp: str,
    ) -> int:
        self.calls.append(
            {
                "candidates": candidates,
                "regime": regime,
                "tick": tick,
                "timestamp": timestamp,
            }
        )
        if self.error is not None:
            raise self.error
        return self.written


def _bare_live_engine():
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._tick_count = 42
    engine._candidate_filter_shadow_events = 10
    engine._strategy_evidence_events = 20
    engine._candidate_filter_shadow_recorder = None
    engine._strategy_evidence_recorder = None
    return engine


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
        "alpha_breakout_chop_or_trending_down",
    ]
    assert candidate_filter_tags({**candidate, "confidence": 0.60}, "chop") == [
        "conf_55_65",
        "alpha_breakout_chop",
        "alpha_breakout_chop_or_trending_down",
    ]
    assert candidate_filter_tags({**candidate, "confidence": 0.50}, "trend") == [
        "conf_45_55",
    ]
    assert candidate_filter_tags(
        {**candidate, "symbol": "PSQ", "confidence": 0.60},
        "trending_down",
    ) == [
        "conf_55_65",
        "alpha_breakout_trending_down",
        "alpha_breakout_chop_or_trending_down",
        "inverse_etf_alpha_breakout",
        "inverse_etf_alpha_breakout_trending_down",
        "inverse_etf_alpha_breakout_chop_or_trending_down",
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
    assert events[0].matched_filters == [
        "conf_45_55",
        "alpha_breakout_chop",
        "alpha_breakout_chop_or_trending_down",
    ]
    assert events[0].to_dict()["confidence"] == 0.5


def test_build_candidate_shadow_events_can_record_all_candidates_for_phase6():
    events = build_candidate_shadow_events(
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
                "confidence": 0.70,
                "breakout_score": 0.10,
                "predicted_return": 0.004,
            },
        ],
        regime="chop",
        tick=42,
        timestamp="2026-05-04T14:00:00Z",
        record_all_candidates=True,
    )

    assert [event.symbol for event in events] == ["AAPL", "MSFT"]
    assert events[0].matched_filters == [
        "conf_45_55",
        "alpha_breakout_chop",
        "alpha_breakout_chop_or_trending_down",
    ]
    assert events[1].matched_filters == []


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
    assert rows[0]["matched_filters"] == [
        "conf_45_55",
        "alpha_breakout_chop",
        "alpha_breakout_chop_or_trending_down",
    ]


def test_phase6_strategy_evidence_recorder_writes_untagged_candidates(tmp_path: Path):
    path = tmp_path / "strategy_evidence_events.jsonl"
    recorder = CandidateShadowTelemetryRecorder(path, record_all_candidates=True)

    written = recorder.record_candidates(
        [
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
    assert rows[0]["symbol"] == "MSFT"
    assert rows[0]["matched_filters"] == []


def test_live_engine_candidate_evidence_fanout_records_without_mutating_candidates():
    engine = _bare_live_engine()
    shadow = _FakeCandidateRecorder(written=1)
    evidence = _FakeCandidateRecorder(written=2)
    engine._candidate_filter_shadow_recorder = shadow
    engine._strategy_evidence_recorder = evidence
    candidates = [
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
    ]
    before = deepcopy(candidates)

    engine._record_candidate_evidence(
        candidates,
        regime="chop",
        now_iso="2026-05-04T14:00:00Z",
    )

    assert candidates == before
    assert shadow.calls == [
        {
            "candidates": candidates,
            "regime": "chop",
            "tick": 42,
            "timestamp": "2026-05-04T14:00:00Z",
        }
    ]
    assert evidence.calls == shadow.calls
    assert engine._candidate_filter_shadow_events == 11
    assert engine._strategy_evidence_events == 22


def test_live_engine_candidate_evidence_fanout_is_noop_when_disabled():
    engine = _bare_live_engine()
    candidates = [{"symbol": "AAPL", "confidence": 0.5}]
    before = deepcopy(candidates)

    engine._record_candidate_evidence(
        candidates,
        regime="trend",
        now_iso="2026-05-04T14:00:00Z",
    )

    assert candidates == before
    assert engine._candidate_filter_shadow_events == 10
    assert engine._strategy_evidence_events == 20


def test_live_engine_candidate_evidence_fanout_failures_do_not_block_other_recorders(caplog):
    engine = _bare_live_engine()
    shadow = _FakeCandidateRecorder(error=RuntimeError("shadow boom"))
    evidence = _FakeCandidateRecorder(written=3)
    engine._candidate_filter_shadow_recorder = shadow
    engine._strategy_evidence_recorder = evidence
    candidates = [{"symbol": "AAPL", "confidence": 0.5}]
    before = deepcopy(candidates)

    with caplog.at_level("WARNING"):
        engine._record_candidate_evidence(
            candidates,
            regime="chop",
            now_iso="2026-05-04T14:00:00Z",
        )

    assert candidates == before
    assert len(shadow.calls) == 1
    assert len(evidence.calls) == 1
    assert engine._candidate_filter_shadow_events == 10
    assert engine._strategy_evidence_events == 23
    assert "Candidate filter shadow telemetry write failed" in caplog.text


def test_live_engine_signal_activity_helper_records_first_ten_candidates():
    from backend.organism.live_engine import LiveTickResult

    engine = _bare_live_engine()
    result = LiveTickResult(timestamp="2026-05-04T14:00:00Z")
    candidates = [
        {
            "symbol": f"S{i}",
            "direction": 1 if i % 2 == 0 else -1,
            "confidence": 0.5,
            "breakout_score": 0.4,
        }
        for i in range(12)
    ]

    engine._record_signal_activity(
        result,
        candidates,
        now_iso="2026-05-04T14:00:00Z",
    )

    assert len(result.activity) == 10
    assert result.activity[0].symbol == "S0"
    assert result.activity[0].message == (
        "BUY signal: S0 (confidence=0.50, breakout=0.40)"
    )
    assert result.activity[1].message == (
        "SELL signal: S1 (confidence=0.50, breakout=0.40)"
    )
    assert result.activity[-1].symbol == "S9"


def test_live_engine_sizer_rejection_helper_updates_gate_counts():
    engine = _bare_live_engine()
    engine._last_gate_rejections = {"missingness": 1}

    class _FakeSizer:
        _exploration_rejects = [
            {"reason": "weight_too_small"},
            {"reason": "below_min_notional"},
            {"reason": "below_min_notional"},
            {"reason": "other"},
        ]

    engine.kelly_sizer = _FakeSizer()

    engine._record_sizer_rejections()

    assert engine._last_gate_rejections == {
        "missingness": 1,
        "cost_gate": 1,
        "min_notional": 2,
    }


@dataclass
class _FakeSize:
    shares: int
    notional: float
    target_weight: float


def test_live_engine_intraday_seasonality_helper_reduces_late_session_sizes():
    engine = _bare_live_engine()
    engine._is_intraday = True
    engine._now_fn = lambda: datetime(2026, 5, 4, 19, 50, tzinfo=UTC)
    sizes = [_FakeSize(shares=10, notional=1000.0, target_weight=0.05)]

    engine._apply_intraday_seasonality_filter(sizes)

    assert sizes == [_FakeSize(shares=6, notional=600.0, target_weight=0.03)]


def test_live_engine_intraday_seasonality_helper_noops_outside_late_session():
    engine = _bare_live_engine()
    engine._is_intraday = True
    engine._now_fn = lambda: datetime(2026, 5, 4, 18, 0, tzinfo=UTC)
    sizes = [_FakeSize(shares=10, notional=1000.0, target_weight=0.05)]

    engine._apply_intraday_seasonality_filter(sizes)

    assert sizes == [_FakeSize(shares=10, notional=1000.0, target_weight=0.05)]


def test_live_engine_shadow_telemetry_is_disabled_by_default_and_pre_sizing():
    src = (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()

    assert (
        'ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED", False'
        in src
    )
    assert 'ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED", False' in src
    assert "record_all_candidates=True" in src
    helper_start = src.find("def _record_candidate_evidence(")
    live_tick_start = src.find("async def _live_tick_inner(", helper_start)
    assert helper_start >= 0
    assert live_tick_start > helper_start
    block = src[helper_start:live_tick_start]
    assert block.count("record_candidates(") == 2
    forbidden = [
        "cand_dicts.append",
        "_submit_entry_order",
        "submit_symbol_order",
        "size_positions(",
    ]
    for token in forbidden:
        assert token not in block
    call_start = src.find("self._record_candidate_evidence(", live_tick_start)
    sizing_start = src.find("# 8. SIZE POSITIONS", live_tick_start)
    assert live_tick_start < call_start < sizing_start


def test_runtime_snapshot_includes_shadow_telemetry_switches():
    from scripts.runtime.write_runtime_snapshot import _build_defaults_snapshot

    snapshot = _build_defaults_snapshot()

    assert snapshot["candidate_filter_shadow_telemetry_enabled"] is False
    assert (
        snapshot["candidate_filter_shadow_telemetry_path"]
        == "organism_brain/candidate_filter_shadow_telemetry.jsonl"
    )
    assert snapshot["strategy_evidence_telemetry_enabled"] is False
    assert (
        snapshot["strategy_evidence_telemetry_path"]
        == "organism_brain/strategy_evidence_events.jsonl"
    )
