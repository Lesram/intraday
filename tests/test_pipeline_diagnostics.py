"""Observability must survive bad clocks and reconcile real candidate builds."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.organism.pipeline_diagnostics import PipelineDiagnostics, finite_age


def test_stage_segments_are_nonoverlapping_and_finish_is_idempotent():
    clock = iter([1., 3., 8., 11., 99.])
    d = PipelineDiagnostics(lambda: next(clock))
    d.stage("features")
    d.stage("entry_pipeline")
    d.finish()
    d.finish()
    assert d.snapshot()["stage_seconds"] == {
        "stream_health": 2., "features": 5., "entry_pipeline": 3.}


def test_invalid_or_reversed_diagnostic_clock_never_raises_or_emits_nan():
    clock = iter([1., float("nan"), float("inf"), 8., 7.])
    d = PipelineDiagnostics(lambda: next(clock))
    for name in ("features", "entry_pipeline", "exits", "accounting"):
        d.stage(name)
    d.finish()  # exhausted fake clock is observationally unavailable
    assert d.snapshot()["stage_seconds"] == {}
    json.dumps(d.snapshot(), allow_nan=False)


@pytest.mark.parametrize("age,expected", [(float("inf"), None), (float("nan"), None),
                                         (-1, None), (None, None), (20., 20.)])
def test_unknown_receipt_age_is_null(age, expected):
    assert finite_age(age) == expected


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_real_tick_alpha_counts_reconcile_without_entering_replay_hash(monkeypatch, tmp_path):
    from tests.test_v13_w100_live_tick_coverage import _replay, _minute_bars, _assert_real_ticks
    from backend.organism.live_engine import OrganismLiveEngine

    replay, engines, _ = _replay(monkeypatch, tmp_path, _minute_bars())
    observed = []
    real_tick = OrganismLiveEngine.live_tick

    async def collect(engine):
        result = await real_tick(engine)
        d = engine._last_pipeline_diagnostics
        observed.append(d)
        assert "stage_seconds" not in result.to_dict()
        return result

    monkeypatch.setattr(OrganismLiveEngine, "live_tick", collect)
    result = await replay.run(max_ticks=12)
    _assert_real_ticks(result, 12)
    assert observed and any(d["alpha_considered"] > 0 for d in observed)
    assert all(d["alpha_unaccounted"] == 0 for d in observed)
    assert all(d["alpha_considered"] <= d["alpha_scanned"] for d in observed)
    assert any(d["stage_seconds"].get("features", 0) > 0 for d in observed)
    assert any(d["alpha_terminal"].get("candidate_built", 0) for d in observed)
    assert engines[0].status()["pipeline_diagnostics"] == observed[-1]


@pytest.mark.asyncio
async def test_fetch_origin_is_actual_path_not_receipt_age(monkeypatch):
    import pandas as pd
    from backend.organism.live_engine_data import _DataFeederMixin
    from backend.organism.live_engine import MIN_BARS

    rows = pd.DataFrame({"close": [100.] * (MIN_BARS + 1)})
    provider = SimpleNamespace(get_bars=lambda *args: rows)
    rest = SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=rows))
    feeder = _DataFeederMixin()
    feeder._streaming_provider, feeder._data_client = provider, rest
    assert (await feeder._fetch_bars("AAPL")) is rows
    assert feeder._last_bar_fetch_sources["AAPL"] == "stream_buffer"
    rest.get_historical_bars_df.assert_not_awaited()
    provider.get_bars = lambda *args: pd.DataFrame()
    await feeder._fetch_bars("AAPL")
    assert feeder._last_bar_fetch_sources["AAPL"] == "rest"
    rest.get_historical_bars_df.return_value = None
    assert await feeder._fetch_bars("AAPL") is None
    assert feeder._last_bar_fetch_sources["AAPL"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,receipt_age,breakout_score,regime,cooldown,heuristic", [
    ("streaming_receipt_age", 21., .5, "chop", False, False),
    ("below_main_confidence", 0., .5, "chop", False, False),
    ("below_exploration_confidence", 0., .1, "chop", False, False),
    ("heuristic", 21., .5, "trending_down", True, True),
    ("regime_cooldown", 21., .5, "chop", True, False),
    ("trending_down", 21., .5, "trending_down", True, False),
])
async def test_actual_alpha_route_reports_first_terminal_reason(
    monkeypatch, tmp_path, reason, receipt_age, breakout_score, regime, cooldown, heuristic,
):
    """Exercise real alpha routing, including supported legacy confidence gates.

    Mode selection is fixture-only: the current research lock is unchanged.
    Receipt freshness, frame age and actual fetch provenance are distinct.
    Scores stay below the separate pure-breakout entry minimum so a rejected
    alpha cannot be replaced by another strategy in this diagnostic fixture.
    """
    from datetime import timedelta
    from unittest.mock import MagicMock

    from backend.organism.alpha_scanner import AlphaCandidate
    from backend.organism.breakout_scanner import BreakoutSignal
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.organism.ml_signal import MLSignal
    from backend.organism.replay_simulator import SimulatedBroker
    from tests.test_entry_freshness import NOW, frame_at
    from tests.test_organism_engine_scenarios import MockDataClient, _make_engine

    monkeypatch.setattr("backend.organism.live_engine.FRAMEWORK_ROUTING_V2_ENABLED", False)
    monkeypatch.setattr("backend.organism.live_engine.FRAMEWORK_ROUTING_ENABLED", False)
    monkeypatch.setattr(OrganismLiveEngine, "_is_learning_mode", property(lambda _: False))
    monkeypatch.setattr(OrganismLiveEngine, "_is_guarded_production_mode", property(lambda _: False))
    features = {s: frame_at(NOW - timedelta(seconds=60), 120) for s in ("AAPL", "MSFT", "SPY")}
    for frame in features.values():
        frame["_nan_missingness"] = 0.
    engine = _make_engine(SimulatedBroker(), MockDataClient(features), str(tmp_path / "brain"))
    engine._timeframe = "1Min"
    engine._now_fn, engine._time_fn = lambda: NOW, NOW.timestamp
    await engine.initialize()
    engine._tick_count = 10  # Avoid the every-six-tick discovery boundary.
    engine._regime_change_tick = 10 if cooldown else 0
    engine._fetch_and_compute_features = AsyncMock(return_value=features)
    engine._last_bar_fetch_sources = {"AAPL": "rest"}
    engine._reconcile_fills = AsyncMock()
    engine.regime_detector.detect = MagicMock(return_value=SimpleNamespace(primary=regime, confidence=.9))
    engine._streaming_provider = SimpleNamespace(
        update_subscriptions=AsyncMock(return_value=True),
        last_update_time=NOW.timestamp(), stale_symbols=lambda **_: [],
        get_bar_age=lambda _: receipt_age, is_ready=lambda _: True,
        get_latest_quote=lambda _: {"bid": 99., "ask": 100.},
        _subscribed_symbols={"AAPL", "MSFT", "SPY", "QQQ"},
    )
    engine.market_scanner = SimpleNamespace(scanned_stocks=[
        SimpleNamespace(symbol="AAPL", tension_score=.1),
    ])
    signal = MLSignal(symbol="AAPL", direction=1., confidence=.9, predicted_return=.02,
                      raw_confidence=.9, effective_confidence=.9)
    engine.signal_gen.predict_batch = MagicMock(return_value={"AAPL": signal})
    engine.alpha_scanner.scan = MagicMock(return_value=[AlphaCandidate(
        symbol="AAPL", composite_score=.9, breakout_score=breakout_score, ml_signal=signal,
        direction=1., expected_return_source="heuristic" if heuristic else "ml",
    )])
    engine.breakout_scanner.scan = MagicMock(return_value=[BreakoutSignal(
        symbol="AAPL", composite_score=breakout_score, squeeze_score=.9, volume_score=.9,
        contraction_score=.9, rs_score=.9, pivot_score=.9, flow_score=.9,
        direction=1., squeeze_fired=True, volume_ratio=2.,
    )])
    log = MagicMock()
    monkeypatch.setattr("backend.organism.live_engine.logger", log)

    result = await engine.live_tick()

    assert result.errors == []
    assert result.orders_submitted == 0
    assert engine._data_stale is False
    diagnostic = engine._last_pipeline_diagnostics
    assert diagnostic["alpha_scanned"] == diagnostic["alpha_considered"] == 1
    assert diagnostic["alpha_terminal"] == {reason: 1}
    assert diagnostic["alpha_unaccounted"] == 0
    routed = [call.args for call in log.info.call_args_list
              if call.args and call.args[0].startswith("Entry below main-book threshold:")]
    if reason == "below_exploration_confidence":
        assert routed == []
        assert any(call.args[0].startswith("Confidence reject:") for call in log.info.call_args_list)
    else:
        assert len(routed) == 1
        assert routed[0][1] == "AAPL"
        assert routed[0][5:] == (reason, receipt_age, 60., True, "rest")
