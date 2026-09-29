"""Real discovery, subscription state and admission with offline transport only."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.streaming_data_provider import StreamingDataProvider
from tests.test_v13_w100_live_tick_coverage import _assert_real_ticks, _minute_bars, _replay


class FakeTransport:
    """Only WebSocket I/O is fake; provider state and callback ownership are real."""

    def __init__(self, **kwargs):
        self.is_authenticated = False
        self.quote_subscriptions = set()
        self.bar_subscriptions = {"1Min": set()}
        self.calls = []
        self.fail_once = None
        self.fail_forever = set()
        self.fail_unsubscribe = False

    async def connect(self):
        self.is_authenticated = True
        return True

    async def disconnect(self):
        self.is_authenticated = False

    async def _subscribe(self, kind, names):
        self.calls.append((kind, tuple(sorted(names))))
        if self.fail_forever.intersection(names):
            return False
        if self.fail_once == kind and "MSFT" in names:
            self.fail_once = None
            return False
        target = self.quote_subscriptions if kind == "quotes" else self.bar_subscriptions["1Min"]
        target.update(names)
        return True

    async def subscribe_bars(self, names):
        return await self._subscribe("bars", names)

    async def subscribe_quotes(self, names):
        return await self._subscribe("quotes", names)

    async def unsubscribe(self, names):
        self.calls.append(("unsubscribe", tuple(sorted(names))))
        if self.fail_unsubscribe:
            return False
        self.quote_subscriptions.difference_update(names)
        self.bar_subscriptions["1Min"].difference_update(names)
        return True


async def make_provider(monkeypatch, clock, symbols):
    transport = FakeTransport()
    monkeypatch.setattr(
        "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
        lambda **kwargs: transport,
    )
    provider = StreamingDataProvider(time_fn=clock)
    await provider.start(list(symbols), "offline-placeholder", "offline-placeholder")
    return provider, transport


def bar(now, close=100.0):
    return {"timestamp": pd.Timestamp(now, unit="s", tz="UTC").isoformat(),
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": 100_000}


def helper_engine(provider, now, universe):
    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = provider
    engine._time_fn = lambda: now[0]
    engine._streaming_base_symbols = frozenset({"BASE", "SPY", "QQQ"})
    engine._universe = list(universe)
    engine._DATA_STALE_THRESHOLD_S = 120
    engine._data_stale = False
    engine._entries_blocked = False
    engine._last_entries_blocked_reason = ""
    return engine


@pytest.mark.asyncio
async def test_desired_subscriptions_retain_base_benchmarks_and_held_until_flat(monkeypatch):
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE", "SPY", "QQQ", "HELD", "OLD"])
    engine = helper_engine(provider, now, ["NEW"])
    for symbol in provider._subscribed_symbols:
        await transport.on_bar(symbol, bar(now[0]))
    await engine._sync_streaming_subscriptions({"HELD": {"qty": 2}})
    assert provider._subscribed_symbols == {"BASE", "SPY", "QQQ", "NEW", "HELD"}
    assert provider.get_bar_age("NEW") == float("inf")
    # Audit 2026-09-29 (MDP-03): an unseen discovery is excluded on its own;
    # it no longer blocks entries for every other symbol.
    assert not engine._entries_blocked and not engine._data_stale
    assert engine._stale_entry_symbols == frozenset({"NEW"})
    assert not provider.has_data("NEW")  # Subscribing never seeds REST data.
    now[0] += 131
    for symbol in provider._subscribed_symbols - {"NEW"}:
        await transport.on_bar(symbol, bar(now[0]))
    await transport.on_quote("NEW", {"bid": 99, "ask": 101,
                                      "timestamp": pd.Timestamp(now[0], unit="s", tz="UTC").isoformat()})
    await engine._sync_streaming_subscriptions({"HELD": {"qty": 2}})
    assert not engine._entries_blocked and not engine._data_stale
    assert engine._stale_entry_symbols == frozenset({"NEW"})  # A quote is not bar health.
    assert provider.stale_symbols(120) == [("NEW", float("inf"))]
    await transport.on_bar("NEW", bar(now[0]))
    await engine._sync_streaming_subscriptions({})
    assert "HELD" not in provider._subscribed_symbols
    assert not engine._entries_blocked and not engine._data_stale
    assert engine._stale_entry_symbols == frozenset()
    assert all(symbol in provider._subscribed_symbols for symbol in ["BASE", "SPY", "QQQ"])
    await provider.stop()


@pytest.mark.asyncio
async def test_stale_benchmark_still_blocks_every_entry(monkeypatch):
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE", "SPY", "QQQ"])
    engine = helper_engine(provider, now, [])
    for symbol in provider._subscribed_symbols:
        await transport.on_bar(symbol, bar(now[0]))
    now[0] += 131
    for symbol in provider._subscribed_symbols - {"SPY"}:
        await transport.on_bar(symbol, bar(now[0]))
    await engine._sync_streaming_subscriptions({})
    assert engine._entries_blocked and engine._data_stale
    assert engine._last_entries_blocked_reason == "stale_data"
    await provider.stop()


@pytest.mark.asyncio
async def test_desired_set_is_capped_by_priority_and_never_drops_held(monkeypatch):
    monkeypatch.setattr("backend.organism.live_engine.STREAM_MAX_SYMBOLS", 5)
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE", "SPY", "QQQ"])
    engine = helper_engine(provider, now, ["CORE1", "CORE2", "CORE3"])
    engine._core_universe = ["CORE1", "CORE2"]
    desired = engine._bounded_stream_symbols({"HELD": {"qty": 1}})
    assert desired == ["SPY", "QQQ", "HELD", "CORE1", "CORE2"]
    # Held + benchmarks are never truncated even beyond the cap.
    many = {f"H{i}": {} for i in range(6)}
    assert set(many) | {"SPY", "QQQ"} <= set(engine._bounded_stream_symbols(many))
    await provider.stop()


@pytest.mark.asyncio
async def test_failed_unsubscribe_is_partial_then_retries_without_discarding_prior_state(monkeypatch):
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE", "SPY", "QQQ", "OLD"])
    engine = helper_engine(provider, now, [])
    for symbol in provider._subscribed_symbols:
        await transport.on_bar(symbol, bar(now[0]))
    transport.fail_unsubscribe = True
    await engine._sync_streaming_subscriptions({})
    # Benchmarks are confirmed, so a failed retirement is a partial sync:
    # entries stay admitted for confirmed symbols and nothing is discarded.
    assert not engine._entries_blocked
    assert engine._stream_sync_status["status"] == "partial"
    assert provider.has_data("OLD") and "OLD" in provider._subscribed_symbols
    transport.fail_unsubscribe = False
    await engine._sync_streaming_subscriptions({})
    assert not engine._entries_blocked
    assert engine._stream_sync_status["status"] == "complete"
    assert not provider.has_data("OLD") and "OLD" not in provider._subscribed_symbols
    assert not engine._stream_subscription_sync_failed
    await provider.stop()


@pytest.mark.asyncio
async def test_refused_benchmark_still_blocks_every_entry(monkeypatch):
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE"])
    engine = helper_engine(provider, now, [])
    transport.fail_forever.add("SPY")
    await engine._sync_streaming_subscriptions({})
    assert engine._entries_blocked
    assert engine._last_entries_blocked_reason == "stream_subscription_sync"
    await provider.stop()


@pytest.mark.asyncio
async def test_successful_sync_does_not_clear_existing_entry_halt(monkeypatch):
    now = [pd.Timestamp("2026-09-24T15:00:00Z").timestamp()]
    provider, transport = await make_provider(monkeypatch, lambda: now[0], ["BASE", "SPY", "QQQ"])
    engine = helper_engine(provider, now, [])
    for symbol in provider._subscribed_symbols:
        await transport.on_bar(symbol, bar(now[0]))
    engine._entries_blocked = True
    engine._last_entries_blocked_reason = "governance_halt"
    await engine._sync_streaming_subscriptions({})
    assert engine._entries_blocked and engine._last_entries_blocked_reason == "governance_halt"
    assert not engine._data_stale
    await provider.stop()


@pytest.mark.asyncio
async def test_no_streaming_provider_leaves_historical_replay_unchanged():
    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = None
    await engine._sync_streaming_subscriptions({})
    assert not hasattr(engine, "_entries_blocked")


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [False, None, "true"])
async def test_incomplete_subscription_result_cannot_admit_entries(result):
    async def incomplete(symbols):
        return result
    engine = helper_engine(SimpleNamespace(update_subscriptions=incomplete), [1.0], [])
    await engine._sync_streaming_subscriptions({})
    assert engine._entries_blocked
    assert engine._last_entries_blocked_reason == "stream_subscription_sync"


@pytest.mark.asyncio
async def test_subscription_wait_has_bounded_deadline_and_fails_closed(monkeypatch):
    async def stalled(symbols):
        await asyncio.Event().wait()
    wait_for = asyncio.wait_for
    async def bounded(awaitable, timeout):
        assert timeout == 5.0
        return await wait_for(awaitable, timeout=0.01)
    monkeypatch.setattr("backend.organism.live_engine.asyncio.wait_for", bounded)
    engine = helper_engine(SimpleNamespace(update_subscriptions=stalled), [1.0], [])
    await engine._sync_streaming_subscriptions({})
    assert engine._entries_blocked and engine._stream_subscription_sync_failed


async def run_live_provider_replay(monkeypatch, tmp_path, *, fail_once=None, after_entry=None):
    from backend.organism.market_scanner import MarketScanner

    start = "2026-09-22T16:16:00Z" if after_entry else "2026-09-22T10:40:00Z"
    bars = _minute_bars(symbols=("AAPL", "MSFT", "SPY", "QQQ"), start=start)
    base = {"AAPL", "SPY", "QQQ"}
    replay, engines, _ = _replay(monkeypatch, tmp_path, bars, universe=sorted(base))
    scanner = MarketScanner()
    async def discovery(url, params=None):
        if url.endswith("most-actives"):
            return {"most_actives": [{"symbol": "MSFT", "volume": 8_000_000, "trade_count": 100_000}]}
        if url.endswith("movers"):
            return {"gainers": [], "losers": []}
        assert url.endswith("snapshots") and params["symbols"] == "MSFT"
        return {"MSFT": {"dailyBar": {"o": 100., "h": 102.2, "l": 99.8, "c": 102., "v": 8_000_000},
                         "minuteBar": {"o": 101.5, "c": 102., "v": 50_000},
                         "prevDailyBar": {"c": 99., "h": 100., "l": 95., "v": 1_000_000}}}
    monkeypatch.setattr(scanner, "_request", discovery)
    real_tick = OrganismLiveEngine.live_tick
    provider = transport = None
    observations = []
    first_real_bar = None
    held_fault = False

    async def feed_and_observe(engine):
        nonlocal provider, transport, first_real_bar, held_fault
        tick = engine._tick_count + 1
        if provider is None:
            provider, transport = await make_provider(monkeypatch, engine._time_fn, base)
            transport.fail_once = fail_once
            engine._streaming_provider = provider
        held = await engine._positions_service.get_all_positions()
        if after_entry and "MSFT" in held:
            held_fault = True
            # Held symbols must remain subscribed even after feature rotation.
            engine._universe = sorted(base | ({"LAG"} if after_entry == "subscription_failure" else set()))
            if after_entry == "subscription_failure":
                transport.fail_forever.add("LAG")
        for symbol in list(provider._subscribed_symbols):
            if symbol == "MSFT" and (tick <= 8 or held_fault):
                continue
            frame = engine._data_client.get_historical_data(symbol, "1Min", 1)
            assert frame is not None
            await transport.on_bar(symbol, frame.iloc[-1].to_dict())
            close = float(frame.iloc[-1]["close"])
            await transport.on_quote(symbol, {"bid": close - .01, "ask": close + .01,
                                              "timestamp": engine._now_fn().isoformat()})
            if symbol == "MSFT" and first_real_bar is None:
                first_real_bar = engine._now_fn().isoformat()
        engine.market_scanner = scanner
        result = await real_tick(engine)
        observations.append({"tick": tick, "timestamp": result.timestamp,
                             "blocked": engine._entries_blocked, "reason": engine._last_entries_blocked_reason,
                             "data_stale": engine._data_stale, "msft_age": provider.get_bar_age("MSFT"),
                             "subscribed": set(provider._subscribed_symbols), "held_before": set(held),
                             "excluded": set(getattr(engine, "_stale_entry_symbols", ()) or ()),
                             "admitted": set(getattr(engine, "_stream_admitted", None) or ()),
                             "sync": dict(getattr(engine, "_stream_sync_status", {}) or {}).get("status"),
                             "orders": result.orders_submitted})
        return result
    monkeypatch.setattr(OrganismLiveEngine, "live_tick", feed_and_observe)
    ticks = 35 if after_entry else 20
    try:
        result = await replay.run(max_ticks=ticks)
    finally:
        await scanner.close()
        if provider is not None:
            await provider.stop()
    _assert_real_ticks(result, ticks)
    return result, observations, transport, engines, first_real_bar


@pytest.mark.timeout(60)
@pytest.mark.asyncio
@pytest.mark.parametrize("fail_once", [None, "bars", "quotes"])
async def test_scanner_addition_waits_for_live_bar_retries_then_places_actual_order(monkeypatch, tmp_path, record_property, fail_once):
    result, seen, transport, engines, first_bar = await run_live_provider_replay(monkeypatch, tmp_path, fail_once=fail_once)
    added_tick = seen[5]
    # Audit 2026-09-29 (MDP-03): the new, still-unseen discovery is excluded
    # individually (stale or unconfirmed) rather than blocking every entry;
    # other fresh symbols may still be entered meanwhile.
    assert not any(row["blocked"] and row["reason"] in {"stale_data", "stream_subscription_sync"}
                   for row in seen[5:8])
    assert all(("MSFT" in row["excluded"]) or ("MSFT" not in row["admitted"]) for row in seen[5:8])
    assert all(row["msft_age"] == float("inf") for row in seen[:8])
    assert first_bar == seen[8]["timestamp"]
    assert (pd.Timestamp(first_bar) - pd.Timestamp(added_tick["timestamp"])).total_seconds() == 180
    entries = [order for order in result.orders if order["side"] == "buy" and order["symbol"] == "MSFT"]
    assert len(entries) == 1
    assert all(pd.Timestamp(order["submitted_at"]) >= pd.Timestamp(first_bar) for order in entries)
    assert all({"AAPL", "SPY", "QQQ"} <= row["subscribed"] for row in seen)
    assert any(row["msft_age"] == 0 and not row["blocked"] for row in seen[8:])
    if fail_once:
        # Benchmarks stay confirmed, so a refused discovery is a partial sync.
        assert added_tick["sync"] == "partial" and "MSFT" not in added_tick["admitted"]
        assert not added_tick["blocked"]
        assert sum(kind == fail_once and "MSFT" in symbols for kind, symbols in transport.calls) == 2
    ids = [order["order_id"] for order in result.orders]
    assert len(ids) == len(set(ids))
    receipts = [json.loads(line) for line in (tmp_path / "brain/entry_evidence.jsonl").read_text().splitlines()]
    accepted = [receipt for receipt in receipts if receipt["symbol"] == "MSFT"]
    assert accepted and all(receipt["gate_passed"] and 0 <= receipt["bar_age_seconds"] <= 120 for receipt in accepted)
    record_property("actual_msft_entries_after_stream_bar", len(entries))
    record_property("subscription_first_failure", fail_once or "none")


@pytest.mark.timeout(60)
@pytest.mark.asyncio
@pytest.mark.parametrize("after_entry", ["stale", "subscription_failure"])
async def test_stale_or_failed_sync_keeps_held_symbol_and_real_eod_exit(monkeypatch, tmp_path, record_property, after_entry):
    result, seen, transport, engines, first_bar = await run_live_provider_replay(monkeypatch, tmp_path, after_entry=after_entry)
    assert first_bar is not None
    held_rows = [row for row in seen if "MSFT" in row["held_before"]]
    assert held_rows and all("MSFT" in row["subscribed"] for row in held_rows)
    # Audit 2026-09-29 (MDP-03): the faulted held symbol is excluded from new
    # entries individually; its protective/EOD management keeps running.
    faulted = [row for row in held_rows if "MSFT" in row["excluded"] or "MSFT" not in row["admitted"]]
    assert faulted
    if after_entry == "subscription_failure":
        lag_rows = [row for row in held_rows if row["sync"] == "partial"]
        assert lag_rows and all("LAG" not in row["admitted"] for row in lag_rows)
        assert not [order for order in result.orders if order["symbol"] == "LAG"]
    first_fault = pd.Timestamp(faulted[0]["timestamp"])
    assert all(pd.Timestamp(order["submitted_at"]) < first_fault
               for order in result.orders if order["side"] == "buy" and order["symbol"] == "MSFT")
    closes = [trade for trade in result.accounted_trades if trade["symbol"] == "MSFT" and trade["exit_reason"] == "eod_flatten"]
    assert closes and all(pd.Timestamp(trade["closed_at"]) >= first_fault for trade in closes)
    assert not await engines[0]._positions_service.get_all_positions()
    assert not result.accounting_pending
    ids = [order["order_id"] for order in result.orders]
    assert len(ids) == len(set(ids))
    record_property("actual_eod_closes_during_entry_block", len(closes))


@pytest.mark.timeout(60)
@pytest.mark.asyncio
@pytest.mark.parametrize("after_entry", [None, "subscription_failure"])
async def test_actual_transport_ack_recovery_replay_keeps_entries_and_eod_safe(monkeypatch, tmp_path, after_entry):
    """Actual transport/provider/engine; synthetic socket controls server snapshots."""
    from unittest.mock import AsyncMock
    from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
    from tests.test_streaming_subscription_acknowledgement import Socket

    sockets = []
    async def real_provider(_monkeypatch, clock, symbols):
        socket = Socket()
        sockets.append(socket)
        monkeypatch.setattr("backend.integrations.alpaca_market_data_stream.websockets.connect",
                            AsyncMock(return_value=socket))
        provider = StreamingDataProvider(time_fn=clock)
        assert await provider.start(list(symbols), "offline", "offline")
        stream = provider._stream
        stream.fail_once = None
        stream.fail_forever = set()
        original_send = socket.send

        async def server(raw):
            request = json.loads(raw)
            socket.reject = set(stream.fail_forever)
            kind = stream.fail_once
            if kind and "MSFT" in request.get(kind, []):
                socket.reject.add("MSFT")
                stream.fail_once = None
            await original_send(raw)
        socket.send = server
        return provider, stream

    monkeypatch.setitem(run_live_provider_replay.__globals__, "make_provider", real_provider)
    # Replay advances by whole minutes without real waiting; cadence itself is
    # covered separately with the real nonzero bound in transport contracts.
    monkeypatch.setattr(AlpacaMarketDataStream, "SUBSCRIPTION_RETRY_INTERVAL_S", 0.0)
    result, rows, transport, engines, first_bar = await run_live_provider_replay(
        monkeypatch, tmp_path, fail_once="bars", after_entry=after_entry,
    )
    # Audit 2026-09-29: a refused discovery is a partial, per-symbol exclusion.
    assert rows[5]["sync"] == "partial" and "MSFT" not in rows[5]["admitted"]
    assert all(("MSFT" in row["excluded"]) or ("MSFT" not in row["admitted"]) for row in rows[5:8])
    entries = [o for o in result.orders if o["symbol"] == "MSFT" and o["side"] == "buy"]
    assert len(entries) == 1
    assert pd.Timestamp(entries[0]["submitted_at"]) >= pd.Timestamp(first_bar)
    assert all({"AAPL", "SPY", "QQQ"} <= row["subscribed"] for row in rows)
    if after_entry:
        held = [r for r in rows if "MSFT" in r["held_before"]]
        assert any(r["sync"] == "partial" and "LAG" not in r["admitted"] for r in held)
        assert any(t["symbol"] == "MSFT" and t["exit_reason"] == "eod_flatten"
                   for t in result.accounted_trades)
        assert not await engines[0]._positions_service.get_all_positions()
        assert not result.accounting_pending
    ids = [o["order_id"] for o in result.orders]
    assert len(ids) == len(set(ids))
    assert sockets and all(s.closed for s in sockets)
    assert not [t for t in transport.background_tasks if not t.done()]
