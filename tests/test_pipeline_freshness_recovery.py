"""Offline callback, subscription and PP-6 recovery contracts.

Construct providers and minimal engine shells only; never load a saved brain or
connect a stream. REST can support feature/exit data without clearing PP-6.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from backend.organism.live_engine import LiveTickResult, OrganismLiveEngine
from backend.organism.streaming_data_provider import StreamingDataProvider


NOW = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc).timestamp()


def bar(stamp, close=100.0):
    if isinstance(stamp, (int, float)):
        stamp = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    return {
        "timestamp": stamp,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": close,
        "volume": 1000,
    }


def provider():
    clock = [NOW]
    return StreamingDataProvider(time_fn=lambda: clock[0]), clock


def engine_for(stream, clock):
    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = stream
    engine._time_fn = lambda: clock[0]
    engine._DATA_STALE_THRESHOLD_S = 120.0
    engine._data_stale = False
    engine._entries_blocked = False
    engine._tick_count = 50
    engine._WARMUP_TICKS = 5
    engine.governance = SimpleNamespace(is_trading_halted=False)
    return engine


def stream_for(symbols):
    stream = SimpleNamespace(
        is_authenticated=True,
        quote_subscriptions=set(symbols),
        bar_subscriptions={"1Min": set(symbols)},
    )

    async def subscribe_bars(names):
        stream.bar_subscriptions["1Min"].update(names)
        return True

    async def subscribe_quotes(names):
        stream.quote_subscriptions.update(names)
        return True

    async def unsubscribe(names):
        stream.bar_subscriptions["1Min"].difference_update(names)
        stream.quote_subscriptions.difference_update(names)
        return True

    stream.subscribe_bars = AsyncMock(side_effect=subscribe_bars)
    stream.subscribe_quotes = AsyncMock(side_effect=subscribe_quotes)
    stream.unsubscribe = AsyncMock(side_effect=unsubscribe)
    return stream


@pytest.mark.asyncio
async def test_active_sparse_symbol_blocks_despite_aggregate_and_quotes_then_recovers(monkeypatch):
    data, clock = provider()
    data._subscribed_symbols.update({"FAST", "SLOW"})
    await data._on_bar("SLOW", bar(NOW - 60))
    clock[0] += 121
    await data._on_bar("FAST", bar(clock[0] - 1))
    await data._on_quote(
        "SLOW",
        {
            "timestamp": datetime.fromtimestamp(clock[0], timezone.utc).isoformat(),
            "bid": 99,
            "ask": 101,
        },
    )
    engine = engine_for(data, clock)
    log = MagicMock()
    monkeypatch.setattr("backend.organism.live_engine.logger", log)
    engine._stage_update_data_staleness()
    engine._stage_check_entry_blockers(LiveTickResult(), "now")
    assert engine._data_stale and engine._entries_blocked
    assert engine._last_entries_blocked_reason == "stale_data"
    engine._stage_update_data_staleness()
    assert log.info.call_count == 0  # No false recovery behind fresh aggregate.
    assert data.get_bar_age("SLOW") == 121
    assert data.get_latest_quote("SLOW")["bid"] == 99  # Quote is not bar health.
    await data._on_bar("SLOW", bar(clock[0] - 1))
    engine._stage_update_data_staleness()
    assert engine._data_stale is False
    assert log.info.call_count == 1
    assert "freshness check passed" in log.info.call_args.args[0]
    engine._stage_update_data_staleness()
    assert log.info.call_count == 1


@pytest.mark.asyncio
async def test_duplicate_correction_does_not_extend_receipt_or_recover_stale_symbol():
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] += 121
    await data._on_bar("AAPL", bar(NOW - 60, close=100.5))
    assert data.bar_count("AAPL") == 1
    assert data._bars["AAPL"][-1]["close"] == 100.5
    assert data.get_bar_age("AAPL") == 121
    assert data.get_bars("AAPL").empty
    assert data.stale_symbols(120) == [("AAPL", 121)]


@pytest.mark.asyncio
async def test_out_of_order_bar_cannot_replace_latest_or_refresh_health():
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] += 121
    before = copy.deepcopy(data._bars)
    await data._on_bar("AAPL", bar(NOW - 120, close=77.0))
    assert data._bars == before
    assert data.get_bar_age("AAPL") == 121


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timestamp", [None, float("nan"), pd.NaT, "NaT", "bad", "2026-09-22T16:00:00", NOW]
)
async def test_invalid_timestamp_cannot_create_or_refresh_bar(timestamp):
    data, _ = provider()
    data._subscribed_symbols.add("AAPL")
    payload = bar(NOW - 60)
    payload["timestamp"] = timestamp
    await data._on_bar("AAPL", payload)
    assert not data.has_data("AAPL")
    assert data.last_update_time is None
    assert data.stale_symbols(120) == [("AAPL", float("inf"))]


@pytest.mark.asyncio
async def test_future_bar_cannot_recover_existing_state_and_zoned_bar_is_normalized():
    data, clock = provider()
    await data._on_bar("AAPL", bar("2026-09-22T11:59:00-04:00"))
    assert data._bars["AAPL"][-1]["timestamp"] == "2026-09-22T15:59:00+00:00"
    clock[0] += 121
    before = copy.deepcopy(data._bars)
    await data._on_bar("AAPL", bar(clock[0] + 1))
    assert data._bars == before
    assert data.get_bar_age("AAPL") == 121


@pytest.mark.asyncio
async def test_newer_delayed_history_does_not_refresh_but_new_fresh_bar_does():
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] += 180
    await data._on_bar("AAPL", bar(NOW, close=101.0))
    assert data.bar_count("AAPL") == 2  # Still usable ordered history.
    assert data.get_bar_age("AAPL") == 180
    assert data.get_bars("AAPL").empty
    await data._on_bar("AAPL", bar(clock[0] - 60, close=102.0))
    assert data.get_bar_age("AAPL") == 0
    assert len(data.get_bars("AAPL")) == 3


@pytest.mark.asyncio
async def test_first_delayed_bar_uses_event_time_not_recent_delivery():
    data, _ = provider()
    await data._on_bar("AAPL", bar(NOW - 180))
    assert data.bar_count("AAPL") == 1
    assert data.get_bar_age("AAPL") == 180
    assert data.get_bars("AAPL").empty


@pytest.mark.asyncio
async def test_delayed_newer_history_never_shortens_or_extends_prior_health():
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 100))
    clock[0] += 50
    await data._on_bar("AAPL", bar(NOW - 90))
    assert data.get_bar_age("AAPL") == 50
    assert data.last_update_time == NOW


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_clock", [float("nan"), float("inf"), NOW - 121])
async def test_invalid_or_rolled_back_clock_fails_closed(bad_clock):
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] = bad_clock
    assert data.get_bar_age("AAPL") == float("inf")
    assert data.get_bars("AAPL").empty
    engine = engine_for(data, clock)
    engine._stage_update_data_staleness()
    assert engine._data_stale


@pytest.mark.asyncio
async def test_advancing_callback_cannot_launder_rolled_back_receipt_clock():
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] = NOW - 10
    before = copy.deepcopy(data._bars)
    await data._on_bar("AAPL", bar(NOW - 20))
    assert data._bars == before
    assert data._last_bar_ts["AAPL"] == NOW
    assert data.last_update_time == NOW
    assert data.get_bar_age("AAPL") == float("inf")
    engine = engine_for(data, clock)
    engine._stage_update_data_staleness()
    assert engine._data_stale


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_feed", ["bars", "quotes"])
async def test_failed_start_subscription_disconnects_before_retry(monkeypatch, failed_feed):
    data, _ = provider()
    streams = []
    for _ in range(2):
        stream = stream_for(set())
        stream.connect = AsyncMock(return_value=True)
        stream.disconnect = AsyncMock()
        streams.append(stream)
    setattr(streams[0], "subscribe_" + failed_feed, AsyncMock(return_value=False))
    factory = MagicMock(side_effect=streams)
    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream", factory)
    await data.start(["AAPL"], "test-key", "test-secret")
    assert not data.is_running
    assert data._stream is None
    streams[0].disconnect.assert_awaited_once()
    await data.start(["AAPL"], "test-key", "test-secret")
    assert data.is_running
    assert data._stream is streams[1]
    assert data.stale_symbols(120) == [("AAPL", float("inf"))]


@pytest.mark.asyncio
async def test_failed_start_disconnect_keeps_reference_until_cleanup_succeeds(monkeypatch):
    data, _ = provider()
    stream = stream_for(set())
    stream.connect = AsyncMock(return_value=True)
    stream.subscribe_bars = AsyncMock(return_value=False)
    stream.disconnect = AsyncMock(side_effect=RuntimeError("disconnect failed"))
    factory = MagicMock(return_value=stream)
    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream", factory)
    with pytest.raises(RuntimeError, match="disconnect failed"):
        await data.start(["AAPL"], "test-key", "test-secret")
    assert data._stream is stream and not data.is_running
    with pytest.raises(RuntimeError, match="disconnect failed"):
        await data.start(["AAPL"], "test-key", "test-secret")
    assert factory.call_count == 1  # Never lose a still-connected old reference.
    assert stream.disconnect.await_count == 2


@pytest.mark.asyncio
async def test_reconnect_requires_all_stale_and_never_clears_entry_health():
    data, clock = provider()
    data._stream = stream_for({"AAPL", "UNSEEN"})
    data._stream._cleanup_connection = AsyncMock()
    data._stream.connect = AsyncMock(return_value=True)
    data._running = True
    data._subscribed_symbols.update({"AAPL", "UNSEEN"})
    assert len(data.stale_symbols(120)) == 2
    # Preserve startup grace; no reconnect loop before any first bar exists.
    assert await data.check_and_recover_stale_stream() is False
    await data._on_bar("AAPL", bar(NOW - 60))
    assert await data.check_and_recover_stale_stream() is False
    clock[0] += 301
    before = copy.deepcopy(data._last_bar_ts)
    assert await data.check_and_recover_stale_stream() is True
    data._stream._cleanup_connection.assert_awaited_once()
    data._stream.connect.assert_awaited_once()
    assert data._last_bar_ts == before
    assert dict(data.stale_symbols(120)) == {"AAPL": 301, "UNSEEN": float("inf")}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("unsubscribe failed")])
async def test_failed_unsubscribe_retains_guard_and_retry_cleans_retired_state(failure):
    data, clock = provider()
    data._stream = stream_for({"KEEP", "REMOVE"})
    data._subscribed_symbols.update({"KEEP", "REMOVE"})
    await data._on_bar("REMOVE", bar(NOW - 60))
    await data._on_quote("REMOVE", {"bid": 99, "ask": 101})
    clock[0] += 121
    await data._on_bar("KEEP", bar(clock[0] - 1))
    real_unsubscribe = data._stream.unsubscribe
    data._stream.unsubscribe = (
        AsyncMock(side_effect=failure)
        if isinstance(failure, Exception)
        else AsyncMock(return_value=failure)
    )
    if isinstance(failure, Exception):
        with pytest.raises(RuntimeError):
            await data.update_subscriptions(["KEEP"])
    else:
        await data.update_subscriptions(["KEEP"])
    assert dict(data.stale_symbols(120))["REMOVE"] == 121
    assert data.has_data("REMOVE") and data.get_latest_quote("REMOVE")
    data._stream.unsubscribe = real_unsubscribe
    await data.update_subscriptions(["KEEP"])
    assert data.stale_symbols(120) == []
    assert "REMOVE" not in data._last_bar_ts
    assert not data.has_data("REMOVE") and not data.get_latest_quote("REMOVE")
    assert data.last_update_time == clock[0]
    await data._on_bar("REMOVE", bar(clock[0] - 1))
    await data._on_quote("REMOVE", {"bid": 1, "ask": 2})
    assert not data.has_data("REMOVE") and not data.get_latest_quote("REMOVE")
    await data.update_subscriptions(["KEEP", "REMOVE"])
    assert dict(data.stale_symbols(120))["REMOVE"] == float("inf")
    await data._on_bar("REMOVE", bar(clock[0] - 1))
    assert data.stale_symbols(120) == []
    assert data.bar_count("REMOVE") == 1


@pytest.mark.asyncio
async def test_quote_subscription_failure_retries_missing_feed_without_false_seed():
    data, _ = provider()
    data._stream = stream_for(set())
    real_quotes = data._stream.subscribe_quotes
    data._stream.subscribe_quotes = AsyncMock(return_value=False)
    await data.update_subscriptions(["NEW"])
    assert data._subscribed_symbols == {"NEW"}
    assert data.stale_symbols(120) == [("NEW", float("inf"))]
    data._stream.subscribe_quotes = real_quotes
    await data.update_subscriptions(["NEW"])
    assert data._stream.subscribe_bars.await_count == 1
    assert real_quotes.await_count == 1
    assert data.stale_symbols(120) == [("NEW", float("inf"))]


@pytest.mark.asyncio
async def test_rest_fallback_data_does_not_clear_global_stream_entry_block(monkeypatch):
    data, clock = provider()
    await data._on_bar("AAPL", bar(NOW - 60))
    clock[0] += 121
    engine = engine_for(data, clock)
    engine._stage_update_data_staleness()
    engine._stage_check_entry_blockers(LiveTickResult(), "now")
    expected = pd.DataFrame([bar(clock[0] - 60)])
    engine._data_client = SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=expected))
    monkeypatch.setattr("backend.organism.live_engine.MIN_BARS", 1)
    actual = await engine._fetch_bars("AAPL")
    pd.testing.assert_frame_equal(actual, expected)
    assert engine._data_stale and engine._entries_blocked
    assert engine._last_entries_blocked_reason == "stale_data"
    assert data.get_bar_age("AAPL") == 121


@pytest.mark.timeout(60)
@pytest.mark.asyncio
async def test_stale_stream_blocks_new_entries_but_real_eod_exit_still_flattens(
    monkeypatch, tmp_path, record_property
):
    from tests.test_v13_w100_live_tick_coverage import (
        _assert_real_ticks,
        _minute_bars,
        _replay,
    )

    replay, engines, _ = _replay(monkeypatch, tmp_path, _minute_bars(start="2026-09-22T16:16:00Z"))
    real_tick = OrganismLiveEngine.live_tick
    stale_data = None
    blocked_at = None
    blocked_ticks = []

    async def make_stream_stale_after_real_entry(engine):
        nonlocal stale_data, blocked_at
        held = await engine._positions_service.get_all_positions()
        if stale_data is None and held:
            # All entry decisions and the first fill are real. Thereafter the
            # real provider has no fresh bars; historical data remains usable
            # for exits, and reconnects cannot create stream health.
            stale_data = StreamingDataProvider(time_fn=engine._time_fn)
            stale_data._subscribed_symbols.update(engine._universe)
            stale_data._last_bar_ts = {
                symbol: engine._time_fn() - 121 for symbol in engine._universe
            }
            stale_data.last_update_time = max(stale_data._last_bar_ts.values())
            blocked_at = pd.Timestamp(engine._now_fn())
        if stale_data is not None:
            engine._streaming_provider = stale_data
        result = await real_tick(engine)
        if stale_data is not None:
            blocked_ticks.append((engine._data_stale, engine._entries_blocked))
        return result

    monkeypatch.setattr(OrganismLiveEngine, "live_tick", make_stream_stale_after_real_entry)
    result = await replay.run(max_ticks=35)
    _assert_real_ticks(result, 35)
    assert blocked_at is not None and blocked_ticks
    assert all(stale and blocked for stale, blocked in blocked_ticks)
    buys = [order for order in result.orders if order["side"] == "buy"]
    assert buys and all(pd.Timestamp(order["submitted_at"]) < blocked_at for order in buys)
    closes = [trade for trade in result.accounted_trades if trade["exit_reason"] == "eod_flatten"]
    assert closes and all(pd.Timestamp(trade["closed_at"]) >= blocked_at for trade in closes)
    assert not await engines[0]._positions_service.get_all_positions()
    assert not result.accounting_pending
    record_property("stale_entry_blocked_ticks", len(blocked_ticks))
    record_property("actual_eod_closes_while_stream_stale", len(closes))
