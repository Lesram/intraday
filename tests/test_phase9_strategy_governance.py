from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_candidate_signal_normalizes_and_round_trips() -> None:
    from backend.organism.schema import CandidateSignal

    signal = CandidateSignal(
        signal_id="sig-1",
        strategy_id="ETF_INTRADAY_MOMENTUM",
        engine_version="mim.v1",
        symbol="qqq",
        side="long",
        timeframe="1Min",
        created_at=datetime(2026, 5, 9, 20, 0, tzinfo=UTC),
        intended_horizon_bars=30,
        regime="High_Vol",
        evidence_tier=0,
        shadow_only=True,
        expected_edge_bps=3.5,
        confidence=0.62,
        risk_budget_bps=0.0,
        features={"volume_z": 2.1},
    )

    payload = signal.to_dict()
    restored = CandidateSignal.from_dict(payload)

    assert restored.strategy_id == "etf_intraday_momentum"
    assert restored.symbol == "QQQ"
    assert restored.direction == 1.0
    assert restored.features["volume_z"] == 2.1


def test_candidate_signal_parses_persisted_boolean_strings() -> None:
    from backend.organism.schema import CandidateSignal

    payload = {
        "signal_id": "sig-1",
        "strategy_id": "etf_intraday_momentum",
        "engine_version": "mim.v1",
        "symbol": "QQQ",
        "side": "long",
        "timeframe": "1Min",
        "created_at": "2026-05-09T20:00:00+00:00",
        "intended_horizon_bars": 30,
        "regime": "high_vol",
        "evidence_tier": 2,
        "shadow_only": "false",
        "risk_budget_bps": 5.0,
    }

    restored = CandidateSignal.from_dict(payload)

    assert restored.shadow_only is False
    assert restored.to_dict()["shadow_only"] is False


def test_candidate_signal_rejects_bad_strategy_id() -> None:
    from backend.organism.schema import CandidateSignal

    with pytest.raises(ValueError, match="Invalid strategy_id"):
        CandidateSignal(
            signal_id="sig-1",
            strategy_id="Unknown Strategy",
            engine_version="v1",
            symbol="SPY",
            side="long",
            timeframe="1Min",
            created_at="2026-05-09T20:00:00+00:00",
            intended_horizon_bars=10,
            regime="unknown",
            evidence_tier=0,
            shadow_only=True,
        )


def test_strategy_governor_blocks_unknown_and_shadow_only_live_intent() -> None:
    from backend.organism.schema import CandidateSignal
    from backend.organism.strategy_governor import StrategyGovernor

    governor = StrategyGovernor()
    unknown = CandidateSignal(
        signal_id="sig-unknown",
        strategy_id="mystery_edge",
        engine_version="v1",
        symbol="SPY",
        side="long",
        timeframe="1Min",
        created_at="2026-05-09T20:00:00+00:00",
        intended_horizon_bars=10,
        regime="unknown",
        evidence_tier=0,
        shadow_only=True,
    )
    mim = CandidateSignal(
        signal_id="sig-mim",
        strategy_id="etf_intraday_momentum",
        engine_version="v1",
        symbol="QQQ",
        side="long",
        timeframe="1Min",
        created_at="2026-05-09T20:00:00+00:00",
        intended_horizon_bars=30,
        regime="high_vol",
        evidence_tier=0,
        shadow_only=True,
    )

    assert governor.authorize_signal(unknown, live_intent=True).reason == (
        "unknown_strategy_id"
    )
    shadow = governor.authorize_signal(mim, live_intent=False)
    live = governor.authorize_signal(mim, live_intent=True)
    assert shadow.allowed is True
    assert shadow.reason == "shadow_authorized"
    assert live.allowed is False
    assert live.reason == "signal_shadow_only"


def test_benchmark_and_null_helpers_measure_alpha() -> None:
    from backend.organism.evidence.benchmark_report import (
        BenchmarkComparison,
        directional_return_bps,
        summarize_benchmarks,
    )
    from backend.organism.evidence.null_models import delayed_entry_return_bps

    realized = directional_return_bps(100, 101, "long")
    delayed = delayed_entry_return_bps(
        [100, 100.2, 100.5, 101.0],
        entry_index=0,
        exit_index=3,
        delay_bars=1,
        side="long",
    )
    row = BenchmarkComparison(
        signal_id="sig-1",
        strategy_id="etf_intraday_momentum",
        symbol="QQQ",
        side="long",
        realized_bps=realized,
        same_symbol_hold_bps=50.0,
        market_benchmark_bps=40.0,
        random_null_bps=20.0,
        delay_1_bps=delayed,
        cost_bps=10.0,
    )

    assert realized == pytest.approx(100.0)
    assert row.net_realized_bps == pytest.approx(90.0)
    assert row.alpha_over_symbol_hold_bps == pytest.approx(40.0)
    assert row.alpha_over_market_bps == pytest.approx(50.0)
    assert row.alpha_over_delay_bps(1) is not None
    summary = summarize_benchmarks([row])
    assert summary["avg_alpha_over_symbol_hold_bps"] == pytest.approx(40.0)


def test_strategy_league_verdicts_reject_and_replay_eligible() -> None:
    from backend.organism.evidence.strategy_league import build_strategy_league

    good_rows = [
        {
            "strategy_id": "etf_intraday_momentum",
            "symbol": f"ETF{i % 5}",
            "session": f"2026-05-{i % 10 + 1:02d}",
            "pnl": 2.0 if i % 3 else -0.5,
            "r_multiple": 0.4 if i % 3 else -0.1,
            "alpha_over_symbol_hold_bps": 4.0,
            "alpha_over_random_bps": 3.0,
            "alpha_over_delay_1_bps": 2.0,
        }
        for i in range(40)
    ]
    bad_rows = [
        {
            "strategy_id": "orb_sip_v2",
            "symbol": f"S{i % 6}",
            "session": f"2026-05-{i % 10 + 1:02d}",
            "pnl": -1.0,
            "r_multiple": -0.2,
            "alpha_over_symbol_hold_bps": -2.0,
        }
        for i in range(40)
    ]

    league = {
        row["strategy_id"]: row
        for row in build_strategy_league(
            good_rows + bad_rows,
            min_replay_samples=30,
            max_symbol_concentration=0.35,
            max_session_concentration=0.35,
        )
    }

    assert league["etf_intraday_momentum"]["verdict"] == "replay_eligible"
    assert league["orb_sip_v2"]["verdict"] == "reject"


def test_strategy_league_can_relax_avg_r_for_shadow_replay_nomination() -> None:
    from backend.organism.evidence.strategy_league import build_strategy_league

    shadow_rows = [
        {
            "strategy_id": "etf_intraday_momentum",
            "symbol": f"ETF{i % 5}",
            "session": f"2026-05-{i % 10 + 1:02d}",
            "pnl": 2.0 if i % 4 else -0.25,
            "r_multiple": 0.0,
            "alpha_over_symbol_hold_bps": 4.0,
            "alpha_over_random_bps": 3.0,
            "alpha_over_delay_1_bps": 2.0,
        }
        for i in range(40)
    ]

    default = build_strategy_league(shadow_rows)
    shadow = build_strategy_league(shadow_rows, require_positive_avg_r=False)

    assert default[0]["verdict"] == "reject"
    assert shadow[0]["verdict"] == "replay_eligible"


def test_strategy_attribution_segments_legacy_rows_by_alpha_baseline() -> None:
    from backend.organism.strategy_attribution import compute_from_trades

    output = compute_from_trades([
        {
            "pnl": 1.0,
            "entry_source": "alpha+breakout",
            "exit_reason": "max_holding_period",
            "regime_at_entry": "trending_up",
            "confidence": 0.6,
        },
        {
            "pnl": -2.0,
            "strategy_id": "etf_intraday_momentum",
            "entry_source": "eod_momentum",
            "exit_reason": "stop_loss",
            "regime_at_entry": "high_vol",
            "confidence": 0.5,
        },
    ])

    strategy_segments = output["segments"]["strategy_id"]
    assert any(
        segment["value"] == "alpha_baseline"
        for segment in strategy_segments
    )
    assert any(
        segment["value"] == "etf_intraday_momentum"
        for segment in strategy_segments
    )


def test_live_entry_order_uses_strategy_governor_as_hard_gate() -> None:
    import asyncio
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import pytest

    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._tick_count = 7
    engine._session_id = "test"
    engine._streaming_provider = None
    engine._ENTRY_SLIPPAGE_CAP = 0.001
    engine._total_orders_submitted = 0
    engine._last_regime = "chop"
    engine._now_fn = lambda: datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    order_service = SimpleNamespace(submit_symbol_order=AsyncMock())
    engine._order_service = order_service

    with pytest.raises(RuntimeError, match="unknown_strategy_id"):
        asyncio.run(
            engine._submit_entry_order(
                "SPY",
                1,
                strategy_id="mystery_edge",
                entry_source="mystery_edge",
            )
        )

    order_service.submit_symbol_order.assert_not_awaited()
    assert engine._total_orders_submitted == 0


def test_live_entry_order_persists_strategy_identity_on_allowed_submit() -> None:
    import asyncio
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._tick_count = 8
    engine._session_id = "test"
    engine._streaming_provider = None
    engine._ENTRY_SLIPPAGE_CAP = 0.001
    engine._total_orders_submitted = 0
    engine._last_regime = "chop"
    engine._now_fn = lambda: datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    order_service = SimpleNamespace(
        submit_symbol_order=AsyncMock(return_value={"order_id": "ord-1"})
    )
    engine._order_service = order_service

    result = asyncio.run(
        engine._submit_entry_order(
            "SPY",
            1,
            strategy_id="alpha_baseline",
            entry_source="alpha+breakout",
        )
    )

    assert result["order_id"] == "ord-1"
    call = order_service.submit_symbol_order.await_args.kwargs
    assert call["attributes"]["strategy_id"] == "alpha_baseline"
    assert call["attributes"]["entry_source"] == "alpha+breakout"
    assert engine._total_orders_submitted == 1


def test_trim_feature_frames_asof_removes_future_rows() -> None:
    import pandas as pd

    from backend.organism.live_engine import trim_feature_frames_asof

    frame = pd.DataFrame({
        "timestamp": [
            "2026-05-10T14:00:00Z",
            "2026-05-10T14:01:00Z",
            "2026-05-10T14:02:00Z",
        ],
        "close": [100.0, 101.0, 999.0],
    })

    trimmed = trim_feature_frames_asof(
        {"SPY": frame},
        "2026-05-10T14:01:00Z",
    )

    assert trimmed["SPY"]["close"].tolist() == [100.0, 101.0]
    assert frame["close"].tolist() == [100.0, 101.0, 999.0]
