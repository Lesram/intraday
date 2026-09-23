"""Adversarial final admission: causal frame time, quote delay and real callers."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from backend.organism import entry_evidence
from backend.organism.entry_freshness import EntryFreshnessRejected, require_fresh_entry
from backend.organism.live_engine import OrganismLiveEngine

NOW = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)


def frame_at(last, rows=30):
    return pd.DataFrame({"timestamp": pd.date_range(end=last, periods=rows, freq="min"),
                         "open": 100., "high": 101., "low": 99., "close": 100.,
                         "volume": 1_000_000.})


@pytest.fixture
def engine(tmp_path):
    engine = OrganismLiveEngine(
        data_client=MagicMock(),
        order_service=SimpleNamespace(submit_symbol_order=AsyncMock(
            return_value={"order_id": "accepted", "idempotency_key": "client-id"})),
        positions_service=SimpleNamespace(get_all_positions=AsyncMock(return_value={
            "AAPL": {"qty": 10, "side": "long", "avg_entry_price": 100}})),
        brain_dir=str(tmp_path / "brain"), universe=["AAPL", "MSFT", "SPY"], timeframe="1Min",
    )
    engine._tick_count = 10
    engine._now_fn = lambda: NOW
    engine._streaming_provider = None
    return engine


def capture(engine, frame, direction=1.):
    assert engine._passes_entry_gates(
        "AAPL", direction, {"AAPL": frame}, set(), set(), fitness_gate=0,
        min_trades_for_fitness=10, allow_short=True,
    ) == (True, "")


@pytest.mark.parametrize("age", [0, 0.000000001, 60, 119.999999999, 120])
async def test_inclusive_start_timestamp_boundary_submits_once(engine, age):
    capture(engine, frame_at(pd.Timestamp(NOW) - pd.Timedelta(seconds=age)))
    assert require_fresh_entry(engine, "AAPL", 1.).age_seconds == pytest.approx(age)
    assert (await engine._submit_entry_order("AAPL", 1))["order_id"] == "accepted"
    engine._order_service.submit_symbol_order.assert_awaited_once()


@pytest.mark.parametrize("age", [120.000000001, 121, 180, 3600])
async def test_old_start_time_has_no_bar_completion_grace(engine, age):
    capture(engine, frame_at(pd.Timestamp(NOW) - pd.Timedelta(seconds=age)))
    with pytest.raises(EntryFreshnessRejected, match="stale_bar") as error:
        await engine._submit_entry_order("AAPL", 1)
    assert error.value.age_seconds == pytest.approx(age)
    engine._order_service.submit_symbol_order.assert_not_awaited()


@pytest.mark.parametrize("fault", ["missing", "naive", "invalid", "nat", "duplicate", "unordered"])
async def test_every_frame_timestamp_must_be_valid(engine, fault):
    frame = frame_at(NOW - timedelta(seconds=60))
    if fault == "missing":
        frame = frame.drop(columns="timestamp")
    elif fault == "naive":
        frame["timestamp"] = frame.timestamp.dt.tz_localize(None)
    else:
        frame["timestamp"] = frame.timestamp.astype(object)
        frame.loc[0, "timestamp"] = {"invalid": "not-a-date", "nat": pd.NaT,
                                     "duplicate": frame.timestamp.iloc[1],
                                     "unordered": frame.timestamp.iloc[2]}[fault]
    capture(engine, frame)
    with pytest.raises(EntryFreshnessRejected):
        await engine._submit_entry_order("AAPL", 1)
    engine._order_service.submit_symbol_order.assert_not_awaited()


async def test_timezone_aware_datetime_index_is_valid(engine):
    frame = frame_at(NOW - timedelta(seconds=90)).set_index("timestamp")
    frame.index = frame.index.tz_convert("America/New_York")
    capture(engine, frame)
    assert require_fresh_entry(engine, "AAPL", 1.).age_seconds == 90


@pytest.mark.parametrize("fault", ["no_gate", "tick", "symbol", "direction", "rejected_gate",
                                  "receipt_tick", "timeframe", "engine_timeframe"])
async def test_exact_admission_context_required(engine, fault):
    capture(engine, frame_at(NOW))
    receipt = engine._entry_evidence_frames[("AAPL", 1.)]
    if fault == "no_gate":
        engine._entry_evidence_frames.clear()
    elif fault == "tick":
        engine._tick_count += 1
    elif fault == "symbol":
        receipt["symbol"] = "MSFT"
    elif fault == "direction":
        receipt["direction"] = -1.
    elif fault == "receipt_tick":
        receipt["tick"] -= 1
    elif fault == "timeframe":
        receipt["timeframe"] = "1Day"
    elif fault == "engine_timeframe":
        engine._timeframe = "1Day"
    else:
        assert not engine._passes_entry_gates("AAPL", 1., {"AAPL": frame_at(NOW)},
            {"AAPL"}, set(), fitness_gate=0, min_trades_for_fitness=10)[0]
    with pytest.raises(EntryFreshnessRejected):
        await engine._submit_entry_order("AAPL", 1)
    engine._order_service.submit_symbol_order.assert_not_awaited()


@pytest.mark.parametrize("fault", ["naive_capture", "naive_submission", "clock_reversed", "future_capture"])
async def test_clock_and_future_capture_fail_closed(engine, fault):
    if fault == "naive_capture":
        engine._now_fn = lambda: NOW.replace(tzinfo=None)
    capture(engine, frame_at(NOW + timedelta(seconds=1) if fault == "future_capture" else NOW))
    engine._now_fn = lambda: ({"naive_submission": NOW.replace(tzinfo=None),
                              "clock_reversed": NOW - timedelta(seconds=1),
                              "future_capture": NOW + timedelta(seconds=2)}.get(fault, NOW))
    with pytest.raises(EntryFreshnessRejected):
        await engine._submit_entry_order("AAPL", 1)
    engine._order_service.submit_symbol_order.assert_not_awaited()


@pytest.mark.parametrize("quote_raises", [False, True])
async def test_quote_processing_delay_rechecked_before_submission(engine, quote_raises):
    capture(engine, frame_at(NOW - timedelta(seconds=119)))
    def quote(_symbol):
        engine._now_fn = lambda: NOW + timedelta(seconds=2)
        if quote_raises:
            raise OSError("quote failed")
        return {"bid": 99, "ask": 100}
    engine._streaming_provider = SimpleNamespace(get_latest_quote=quote)
    with pytest.raises(EntryFreshnessRejected, match="stale_bar") as error:
        await engine._submit_entry_order("AAPL", 1)
    assert error.value.age_seconds == 121
    engine._order_service.submit_symbol_order.assert_not_awaited()


async def test_publication_failure_after_admission_never_retries(engine, monkeypatch):
    capture(engine, frame_at(NOW))
    monkeypatch.setattr(entry_evidence, "append_receipt", MagicMock(side_effect=OSError("unavailable")))
    assert (await engine._submit_entry_order("AAPL", 1))["order_id"] == "accepted"
    engine._order_service.submit_symbol_order.assert_awaited_once()
    assert engine._total_orders_submitted == 1


async def test_receipt_records_final_admission_after_quote_delay(engine, monkeypatch):
    capture(engine, frame_at(NOW - timedelta(seconds=60)))
    def quote(_symbol):
        engine._now_fn = lambda: NOW + timedelta(seconds=30)
        return {"bid": 99., "ask": 100.}
    engine._streaming_provider = SimpleNamespace(get_latest_quote=quote)
    published = []
    monkeypatch.setattr(entry_evidence, "append_receipt", lambda _engine, receipt: published.append(receipt))
    await engine._submit_entry_order("AAPL", 1)
    assert published[0]["submitted_at"] == (NOW + timedelta(seconds=30)).isoformat()
    assert published[0]["bar_age_seconds"] == 90
    engine._order_service.submit_symbol_order.assert_awaited_once()


async def test_overlapping_submissions_keep_their_own_admission_receipt(engine, monkeypatch):
    import asyncio
    capture(engine, frame_at(NOW - timedelta(seconds=60)))
    first_admitted, release_first = asyncio.Event(), asyncio.Event()
    async def submit(**kwargs):
        if kwargs["qty"] == 1:
            first_admitted.set()
            await release_first.wait()
        return {"order_id": str(kwargs["qty"]), "idempotency_key": str(kwargs["qty"])}
    engine._order_service.submit_symbol_order.side_effect = submit
    published = []
    monkeypatch.setattr(entry_evidence, "append_receipt", lambda _engine, receipt: published.append(receipt))
    first = asyncio.create_task(engine._submit_entry_order("AAPL", 1))
    await first_admitted.wait()
    engine._now_fn = lambda: NOW + timedelta(seconds=30)
    await engine._submit_entry_order("AAPL", 2)
    release_first.set()
    await first
    assert {r["entry_order_id"]: r["bar_age_seconds"] for r in published} == {"1": 60, "2": 90}
    assert entry_evidence._submission_receipt.get() is None


@pytest.mark.parametrize("reason", ["stop_loss", "eod_flatten", "pyramid_cut"])
async def test_protective_exits_ignore_missing_frame(engine, reason):
    await engine._submit_exit_order("AAPL", 1, reason=reason)
    assert engine._order_service.submit_symbol_order.await_args.kwargs["reduce_only"] is True


@pytest.mark.parametrize("path", ["alpha", "breakout", "pyramid"])
@pytest.mark.parametrize("age", [60, 121])
@pytest.mark.parametrize("source", ["rest", "streaming"])
async def test_real_tick_callers_share_gate_and_stale_is_normal_skip(tmp_path, monkeypatch, path, age, source):
    from backend.organism.alpha_scanner import AlphaCandidate
    from backend.organism.breakout_scanner import BreakoutSignal
    from backend.organism.kelly_sizer import PositionSize
    from backend.organism.ml_signal import MLSignal
    from backend.organism.pyramider import PyramidLevel, PyramidPosition
    from backend.organism.replay_simulator import SimulatedBroker
    from tests.test_organism_engine_scenarios import MockDataClient, _make_engine

    monkeypatch.setattr("backend.organism.live_engine.FRAMEWORK_ROUTING_V2_ENABLED", False)
    monkeypatch.setattr("backend.organism.live_engine.FRAMEWORK_ROUTING_ENABLED", False)
    features = {s: frame_at(NOW - timedelta(seconds=age), 120) for s in ("AAPL", "MSFT", "SPY")}
    for frame in features.values():
        frame["_nan_missingness"] = 0.
    broker = SimulatedBroker()
    engine = _make_engine(broker, MockDataClient(features), str(tmp_path / "tick-brain"))
    engine._timeframe = "1Min"
    engine._now_fn = lambda: NOW
    engine._time_fn = NOW.timestamp
    await engine.initialize()
    engine._tick_count = 10
    engine._fetch_and_compute_features = AsyncMock(return_value=features)
    engine._reconcile_fills = AsyncMock()  # Outcome accounting is independently covered.
    engine.regime_detector.detect = MagicMock(return_value=SimpleNamespace(primary="trending_up", confidence=.9))
    engine._streaming_provider = None if source == "rest" else MagicMock()
    if source == "streaming":
        engine._streaming_provider.last_update_time = NOW.timestamp()
        engine._streaming_provider.stale_symbols.return_value = []
        engine._streaming_provider.get_bar_age.return_value = 0.
        engine._streaming_provider.is_ready.return_value = True
        engine._streaming_provider.get_latest_quote.return_value = {"bid": 99., "ask": 100.}
    signal = MLSignal(symbol="AAPL", direction=1, confidence=.9, predicted_return=.02,
                      raw_confidence=.9, effective_confidence=.9)
    engine.signal_gen.predict_batch = MagicMock(return_value={"AAPL": signal})
    engine.alpha_scanner.scan = MagicMock(return_value=[AlphaCandidate(
        symbol="AAPL", composite_score=.9, breakout_score=.9, ml_signal=signal,
        direction=1, expected_return_source="ml")] if path == "alpha" else [])
    engine.breakout_scanner.scan = MagicMock(return_value=[BreakoutSignal(
        symbol="AAPL", composite_score=.9, squeeze_score=.9, volume_score=.9,
        contraction_score=.9, rs_score=.9, pivot_score=.9, flow_score=.9,
        direction=1, squeeze_fired=True, volume_ratio=2)] if path in ("alpha", "breakout") else [])
    engine.kelly_sizer.size_positions = MagicMock(side_effect=lambda candidates, *a, **kw: [
        PositionSize(symbol=c["symbol"], direction=1., shares=10, notional=1000.,
                     target_weight=.01, kelly_raw=.01, kelly_half=.005,
                     drawdown_scale=1., vol_scale=1., regime_scale=1., confidence=.9,
                     predicted_return=.02, breakout_score=.9) for c in candidates])
    broker.set_price("AAPL", 100.)
    if path == "pyramid":
        broker.add_position("AAPL", qty=10, avg_entry_price=100.)
        engine._entry_metadata["AAPL"] = {"entry_source": "alpha", "entry_price": 100.,
                                          "entry_tick": 1, "direction": 1., "filled_shares": 10}
        engine._pyramid_positions["AAPL"] = PyramidPosition(
            symbol="AAPL", direction=1., layers=[PyramidLevel(10, 100., 1, 0)],
            target_total_shares=20, atr_at_entry=2., initial_stop=90., current_stop=90.)
        engine.pyramider.check_pyramid = MagicMock(return_value=SimpleNamespace(action="add", shares_to_add=2))
    result = await engine.live_tick()
    assert result.errors == []
    assert engine._ml_isolation_mode and engine._fixed_risk_sizing_mode
    entries = [order for order in broker.filled_orders if order["side"] == "buy"]
    if age == 60:
        assert len(entries) == 1 and result.orders_submitted == 1
    else:
        assert not entries and result.orders_submitted == 0
        skipped = [event for event in result.activity if event.details.get("reason") == "stale_bar"]
        assert len(skipped) == 1 and skipped[0].details["bar_age_seconds"] == 121
        assert "AAPL" not in engine._pending_entry


async def test_admitted_simulated_entry_exit_accounts_exactly_once(engine):
    from backend.organism.replay_simulator import SimulatedBroker
    broker = SimulatedBroker()
    broker._now_fn = engine._now_fn
    engine._positions_service = broker
    engine._order_service = broker
    engine._lookup_closed_position_fills_from_db = broker.lookup_closed_position_fills
    engine._entry_verified_unfilled = broker.entry_verified_unfilled
    engine._save_brain = MagicMock()
    broker.set_price("AAPL", 100.)
    capture(engine, frame_at(NOW - timedelta(seconds=60)))
    entry = await engine._submit_entry_order("AAPL", 2)
    engine._entry_metadata["AAPL"] = {
        "entry_order_id": entry["order_id"], "entry_price": 100., "filled_shares": 2,
        "entry_tick": 1, "entry_time": NOW.timestamp() - 60, "direction": 1.,
        "entry_source": "alpha", "confidence": .6,
    }
    broker.set_price("AAPL", 99.)
    await engine._submit_exit_order("AAPL", 2, reason="stop_loss")
    engine._last_exit_reason["AAPL"] = "stop_loss"
    await engine._reconcile_fills({})
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == engine.learner.state.total_trades == 1
    assert engine._all_trades[0].pnl == engine.learner.state.cumulative_pnl == -2.
    assert engine._all_trades[0].price_source == "simulated_position_fills"
