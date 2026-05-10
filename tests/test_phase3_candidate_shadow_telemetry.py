"""Tests for Phase 3 candidate-filter shadow telemetry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

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

    def record_signals(
        self,
        signals,
        *,
        tick: int,
        timestamp: str,
    ) -> int:
        self.calls.append(
            {
                "signals": list(signals),
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
    engine._phase9_shadow_engines = []
    engine._phase9_shadow_signal_events = 0
    engine._phase9_last_shadow_bar = ""
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


def test_build_candidate_shadow_events_preserves_defensive_filter_metadata():
    events = build_candidate_shadow_events(
        [
            {
                "symbol": "AAPL",
                "direction": 1,
                "confidence": 0.60,
                "effective_confidence": 0.58,
                "breakout_score": 0.45,
                "predicted_return": 0.004,
                "ranking_score": 0.2,
                "live_pipeline_candidate": False,
                "defensive_filter_reason": "alpha_breakout_chop_blocked_by_evidence",
            },
        ],
        regime="chop",
        tick=42,
        timestamp="2026-05-04T14:00:00Z",
    )

    assert len(events) == 1
    assert events[0].live_pipeline_candidate is False
    assert events[0].defensive_filter_reason == (
        "alpha_breakout_chop_blocked_by_evidence"
    )
    row = events[0].to_dict()
    assert row["live_pipeline_candidate"] is False
    assert row["defensive_filter_reason"] == (
        "alpha_breakout_chop_blocked_by_evidence"
    )


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


def test_phase9_signal_recorder_writes_candidate_signal_contract(tmp_path: Path):
    from backend.organism.schema import CandidateSignal

    path = tmp_path / "strategy_evidence_events.jsonl"
    recorder = CandidateShadowTelemetryRecorder(path, record_all_candidates=True)
    signal = CandidateSignal(
        signal_id="sig-1",
        strategy_id="etf_intraday_momentum",
        engine_version="etf_intraday_momentum.v1",
        symbol="qqq",
        side="long",
        timeframe="1Min",
        created_at="2026-05-08T19:25:00Z",
        intended_horizon_bars=30,
        regime="high_vol",
        evidence_tier=0,
        shadow_only=True,
        expected_edge_bps=4.0,
        confidence=0.62,
        risk_budget_bps=0.0,
        features={"variant": "mim_a"},
    )

    assert recorder.record_signals([signal], tick=7, timestamp="2026-05-08T19:25:00Z") == 1
    row = json.loads(path.read_text().splitlines()[0])

    assert row["signal_id"] == "sig-1"
    assert row["strategy_id"] == "etf_intraday_momentum"
    assert row["created_at"] == "2026-05-08T19:25:00+00:00"
    assert row["expected_edge_bps"] == 4.0
    assert row["live_pipeline_candidate"] is False
    assert row["shadow_only"] is True
    assert row["risk_budget_bps"] == 0.0
    assert row["matched_filters"] == [
        "phase9_shadow",
        "strategy:etf_intraday_momentum",
        "variant:mim_a",
    ]


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


def test_live_engine_phase9_shadow_signals_record_once_per_bar():
    from backend.organism.schema import CandidateSignal

    class _FakePhase9Engine:
        def generate_signals(self, context):
            assert "features_by_symbol" in context
            return [
                CandidateSignal(
                    signal_id="sig-1",
                    strategy_id="etf_intraday_momentum",
                    engine_version="v1",
                    symbol="QQQ",
                    side="long",
                    timeframe="1Min",
                    created_at="2026-05-08T19:25:00Z",
                    intended_horizon_bars=30,
                    regime=context["regime"],
                    evidence_tier=0,
                    shadow_only=True,
                    confidence=0.6,
                    risk_budget_bps=0.0,
                    features={},
                )
            ]

    engine = _bare_live_engine()
    recorder = _FakeCandidateRecorder(written=1)
    engine._strategy_evidence_recorder = recorder
    engine._phase9_shadow_engines = [_FakePhase9Engine()]
    engine._now_fn = lambda: datetime(2026, 5, 8, 19, 25, tzinfo=UTC)
    frame = pd.DataFrame({"close": [100.0, 101.0]})

    engine._record_phase9_shadow_signals(
        {"SPY": frame, "QQQ": frame},
        regime="high_vol",
        now_iso="2026-05-08T19:25:00Z",
    )
    engine._record_phase9_shadow_signals(
        {"SPY": frame, "QQQ": frame},
        regime="high_vol",
        now_iso="2026-05-08T19:25:10Z",
    )

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["tick"] == 42
    assert engine._strategy_evidence_events == 21
    assert engine._phase9_shadow_signal_events == 1


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


def test_live_engine_defensive_filter_blocks_alpha_breakout_bad_regimes():
    engine = _bare_live_engine()
    candidate = {
        "symbol": "AAPL",
        "direction": 1,
        "confidence": 0.60,
        "effective_confidence": 0.58,
        "breakout_score": 0.45,
        "predicted_return": 0.004,
    }
    rejected: list[dict[str, Any]] = []

    assert engine._record_defensive_filtered_candidate(
        candidate,
        "chop",
        rejected,
    )
    assert rejected[0]["live_pipeline_candidate"] is False
    assert rejected[0]["defensive_filter_reason"] == (
        "alpha_breakout_chop_blocked_by_evidence"
    )
    assert engine._alpha_breakout_defensive_filter_reason(
        candidate,
        "trending_down",
    ) == "alpha_breakout_trending_down_blocked_by_evidence"
    assert engine._alpha_breakout_defensive_filter_reason(
        candidate,
        "trending_up",
    ) == ""
    assert engine._alpha_breakout_defensive_filter_reason(
        {**candidate, "breakout_score": 0.10},
        "chop",
    ) == ""


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

    assert snapshot["alpha_breakout_bad_regime_filter_enabled"] is True
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
    assert snapshot["phase9_shadow_engines_enabled"] is False
