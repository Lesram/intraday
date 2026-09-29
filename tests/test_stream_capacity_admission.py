"""Audit 2026-09-29: provider symbol cap, bounded discovery and per-symbol admission.

Regression for the 2026-09-28 session: permanent scanner injection grew the
universe 20 -> 68 while the Alpaca IEX stream refuses more than ~30 symbols
("symbol limit exceeded", code 405). Every subscription sync failed and a
single unconfirmed/stale symbol blocked every entry for the whole session.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
from backend.organism.streaming_data_provider import StreamingDataProvider
from tests.test_scanner_streaming_integration import bar, helper_engine
from tests.test_streaming_subscription_acknowledgement import Socket

CORE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "AVGO", "CRM",
    "COST", "WMT", "LLY", "XOM", "CAT", "SPY", "QQQ", "IWM", "XLK", "XLE",
]
DISCOVERED = [f"D{i:02d}" for i in range(48)]


class CappedSocket(Socket):
    """Synthetic Alpaca market-data socket enforcing a per-channel symbol cap."""

    def __init__(self, cap: int):
        super().__init__()
        self.cap = cap
        self.refusals = 0

    async def send(self, raw):
        msg = json.loads(raw)
        if msg["action"] == "subscribe":
            for channel, current in self.channels.items():
                if channel in msg and len(current | set(msg[channel])) > self.cap:
                    self.sent.append(msg)
                    self.refusals += 1
                    await self.push({"T": "error", "code": 405, "msg": "symbol limit exceeded"})
                    return
        await super().send(raw)


async def real_capped_provider(monkeypatch, clock, symbols, cap=30):
    socket = CappedSocket(cap)
    monkeypatch.setattr(
        "backend.integrations.alpaca_market_data_stream.websockets.connect",
        AsyncMock(return_value=socket),
    )
    monkeypatch.setattr(AlpacaMarketDataStream, "SUBSCRIPTION_RETRY_INTERVAL_S", 0.0)
    monkeypatch.setattr(AlpacaMarketDataStream, "SUBSCRIPTION_ACK_TIMEOUT_S", 0.2)
    provider = StreamingDataProvider(time_fn=clock)
    assert await provider.start(list(symbols), "offline", "offline", _prefill_history=False)
    return provider, socket


def core_engine(provider, now, universe):
    engine = helper_engine(provider, now, universe)
    engine._streaming_base_symbols = frozenset(CORE)
    engine._core_universe = list(CORE)
    return engine


async def feed_all(provider, now):
    stream = provider._stream
    for symbol in sorted(provider._subscribed_symbols):
        await stream.on_bar(symbol, bar(now))


@pytest.mark.asyncio
async def test_monday_state_68_symbols_is_bounded_and_does_not_block(monkeypatch):
    """The exact Monday failure: an in-memory universe of 68 symbols."""
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE)
    try:
        engine = core_engine(provider, now, CORE + DISCOVERED)
        await feed_all(provider, now[0])
        await engine._sync_streaming_subscriptions({})
        assert len(provider._desired_symbols) <= 28  # default cap keeps headroom under 30
        assert set(CORE) <= provider.confirmed_symbols()
        assert not engine._entries_blocked, engine._last_entries_blocked_reason
        assert not engine._data_stale
        assert engine._stream_sync_status["status"] in {"complete", "partial"}
        # Symbols beyond the cap are never admitted for entries.
        assert len(engine._stream_admitted) <= 28
        assert set(CORE) <= engine._stream_admitted
        # A reconnect replays only the bounded desired set: core quotes survive.
        stream = provider._stream
        socket2 = CappedSocket(30)
        monkeypatch.setattr(
            "backend.integrations.alpaca_market_data_stream.websockets.connect",
            AsyncMock(return_value=socket2),
        )
        await stream._cleanup_connection()
        assert await stream.connect()
        assert set(CORE) <= set(stream.quote_subscriptions)
        assert socket2.refusals == 0
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_scanner_window_is_bounded_by_cap_and_ttl(monkeypatch):
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, _socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE)
    try:
        engine = core_engine(provider, now, CORE)
        engine._last_positions = {}
        engine._scanner_window = {}
        engine._scanner_scan_seq = 0
        added = engine._refresh_scanner_window(DISCOVERED[:20])
        # Window capacity = min(ORGANISM_SCANNER_WINDOW_MAX=8, cap 28 - core 20).
        assert len(added) == 8 and engine._universe[:20] == CORE
        assert len(engine._universe) == 28
        # Repeated scans never accumulate beyond the window.
        for offset in range(0, 40, 4):
            engine._refresh_scanner_window(DISCOVERED[offset:offset + 20])
            assert len(engine._universe) <= 28
        # Discoveries not re-observed within the TTL are evicted.
        engine._refresh_scanner_window([])
        before = set(engine._scanner_window)
        for _ in range(5):
            engine._refresh_scanner_window([])
        assert not (before & set(engine._scanner_window))
        assert engine._universe == CORE
        # Held discoveries stay tracked (and subscribed) until flat.
        engine._refresh_scanner_window(["HELD1"])
        engine._last_positions = {"HELD1": {"qty": 1}}
        for _ in range(8):
            engine._refresh_scanner_window([])
        assert "HELD1" in engine._universe
        desired = engine._bounded_stream_symbols(engine._last_positions)
        assert desired[:3] == ["SPY", "QQQ", "HELD1"] and len(desired) <= 28
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_sparse_non_critical_symbol_is_excluded_not_global(monkeypatch):
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, _socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE)
    try:
        engine = core_engine(provider, now, CORE)
        await feed_all(provider, now[0])
        now[0] += 125
        for symbol in sorted(set(CORE) - {"LLY"}):
            await provider._stream.on_bar(symbol, bar(now[0]))
        await engine._sync_streaming_subscriptions({})
        assert not engine._entries_blocked and not engine._data_stale
        assert engine._stale_entry_symbols == frozenset({"LLY"})
        # The shared entry gate rejects the stale symbol for every entry path.
        engine._tick_count = 1
        for pyramid in (False, True):
            assert engine._passes_entry_gates(
                "LLY", 1.0, {}, set(), set(), fitness_gate=0.45,
                min_trades_for_fitness=10, for_pyramid_add=pyramid,
            ) == (False, "stale_symbol")
    finally:
        await provider.stop()


def test_bounded_desired_set_orders_by_safety_priority(monkeypatch):
    monkeypatch.setattr("backend.organism.live_engine.STREAM_MAX_SYMBOLS", 22)
    engine = core_engine(None, [0.0], CORE + DISCOVERED[:5])
    desired = engine._bounded_stream_symbols({"D40": {"qty": 3}})
    core_rest = [s for s in CORE if s not in {"SPY", "QQQ"}]
    assert desired[:3] == ["SPY", "QQQ", "D40"]
    assert desired[3:3 + len(core_rest)] == core_rest
    assert desired[3 + len(core_rest):] == ["D00"]  # window fills what the cap allows
    assert len(desired) == 22


def test_pending_entry_symbols_are_protected_like_held(monkeypatch):
    monkeypatch.setattr("backend.organism.live_engine.STREAM_MAX_SYMBOLS", 21)
    engine = core_engine(None, [0.0], CORE + DISCOVERED[:5])
    engine._pending_entry = {"D41": 1}
    engine._pending_entry_order_ids = {"D42": "order-1"}
    desired = engine._bounded_stream_symbols({"D40": {"qty": 3}})
    # Benchmarks, then held + pending (sorted), then core; cap grows to fit them.
    assert desired[:5] == ["SPY", "QQQ", "D40", "D41", "D42"]
    assert len(desired) == 21 and "D00" not in desired
    # Pending symbols are never evicted from the scanner window either.
    engine._last_positions = {}
    engine._scanner_window = {}
    engine._scanner_scan_seq = 0
    engine._refresh_scanner_window(["D41"])
    engine._pending_entry = {"D41": 1}
    engine._pending_entry_order_ids = {}
    for _ in range(8):
        engine._refresh_scanner_window([])
    assert "D41" in engine._universe


def test_scanner_window_capacity_with_small_headroom(monkeypatch):
    engine = core_engine(object(), [0.0], CORE)
    engine._last_positions = {}
    engine._scanner_window = {}
    engine._scanner_scan_seq = 0
    # 27 reserved core symbols under a cap of 28 leave exactly one window slot.
    engine._core_universe = CORE + DISCOVERED[40:47]
    engine._universe = list(engine._core_universe)
    assert engine._scanner_window_capacity() == 1
    added = engine._refresh_scanner_window(DISCOVERED[:5])
    assert added == ["D00"]
    # A held non-core symbol consumes the remaining headroom.
    engine._last_positions = {"H1": {"qty": 1}}
    assert engine._scanner_window_capacity() == 0


def test_held_discovery_retained_beyond_window_capacity(monkeypatch):
    engine = core_engine(object(), [0.0], CORE)
    engine._last_positions = {}
    engine._scanner_window = {}
    engine._scanner_scan_seq = 0
    engine._refresh_scanner_window(DISCOVERED[:8])
    held = DISCOVERED[:3]
    engine._last_positions = {s: {"qty": 1} for s in held}
    # Capacity drops to 28 - (20 core + 3 held) = 5 and fresh scans outrank
    # the held names, yet every held name stays in the universe.
    assert engine._scanner_window_capacity() == 5
    for _ in range(3):
        engine._refresh_scanner_window(DISCOVERED[20:30])
    assert set(held) <= set(engine._universe)
    assert set(DISCOVERED[20:25]) <= set(engine._universe)
    assert len(engine._universe) == 20 + 5 + 3
    desired = engine._bounded_stream_symbols(engine._last_positions)
    assert set(held) <= set(desired) and len(desired) <= 28


def test_scanner_window_prefers_existing_members_to_limit_churn():
    engine = core_engine(None, [0.0], CORE)
    engine._last_positions = {}
    engine._scanner_window = {}
    engine._scanner_scan_seq = 0
    engine._refresh_scanner_window(DISCOVERED[:8])
    first = set(engine._scanner_window)
    # The next scan ranks eight newcomers ahead of the same eight members.
    added = engine._refresh_scanner_window(DISCOVERED[8:16] + DISCOVERED[:8])
    assert set(engine._scanner_window) == first and added == []


def test_session_reset_restores_core_universe():
    engine = core_engine(None, [0.0], CORE + DISCOVERED[:4])
    engine._scanner_window = {s: (0, 1) for s in DISCOVERED[:4]}
    engine._reset_discovery_for_session()
    assert engine._universe == CORE and engine._scanner_window == {}


def test_post_close_escalation_reads_live_position_cache():
    engine = core_engine(None, [0.0], CORE)
    calls = []
    engine._record_unflattened_positions = lambda syms, day, ts: calls.append((syms, day, ts))
    now_et = pd.Timestamp("2026-09-28T16:02:00", tz="America/New_York")
    engine._last_positions = {}
    engine._stage_post_close_escalation(now_et, "2026-09-28T20:02:00+00:00")
    assert calls == []
    engine._last_positions = {"AAPL": {"qty": 5}}
    engine._stage_post_close_escalation(now_et, "2026-09-28T20:02:00+00:00")
    assert calls == [(["AAPL"], "2026-09-28", "2026-09-28T20:02:00+00:00")]


def test_unadmitted_symbol_is_rejected_for_every_entry_path():
    engine = core_engine(object(), [0.0], CORE + ["D00"])
    engine._stale_entry_symbols = frozenset()
    engine._stream_admitted = frozenset(CORE)
    for pyramid in (False, True):
        assert engine._passes_entry_gates(
            "D00", 1.0, {}, set(), set(), fitness_gate=0.45,
            min_trades_for_fitness=10, for_pyramid_add=pyramid,
        ) == (False, "unadmitted_symbol")


@pytest.mark.asyncio
async def test_refused_held_symbol_blocks_entries(monkeypatch):
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE, cap=20)
    try:
        engine = core_engine(provider, now, CORE)
        await feed_all(provider, now[0])
        await engine._sync_streaming_subscriptions({"D40": {"qty": 1}})
        assert socket.refusals >= 1
        assert "D40" not in provider.confirmed_symbols()
        assert engine._entries_blocked
        assert engine._last_entries_blocked_reason == "stream_subscription_sync"
        assert engine._stream_admitted == frozenset()
        assert engine._stream_sync_status["status"] == "failed"
        assert engine._stream_sync_status["error"] == "RuntimeError"
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_refused_discovery_is_excluded_without_global_block(monkeypatch):
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE, cap=20)
    try:
        engine = core_engine(provider, now, CORE + ["D00"])
        await feed_all(provider, now[0])
        await engine._sync_streaming_subscriptions({})
        assert socket.refusals >= 1
        assert not engine._entries_blocked, engine._last_entries_blocked_reason
        assert engine._stream_sync_status["status"] == "partial"
        assert "D00" not in engine._stream_admitted
        assert set(CORE) <= engine._stream_admitted
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_provider_truncation_fails_closed(monkeypatch):
    """An engine desired set beyond the provider cap never admits the overflow."""
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, _socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE)
    try:
        monkeypatch.setattr("backend.organism.live_engine.STREAM_MAX_SYMBOLS", 30)
        monkeypatch.setattr("backend.organism.streaming_data_provider.MAX_STREAM_SYMBOLS", 22)
        engine = core_engine(provider, now, CORE + DISCOVERED[:8])
        engine._scanner_window = {}
        await feed_all(provider, now[0])
        await engine._sync_streaming_subscriptions({})
        assert len(provider._desired_symbols) == 22
        overflow = set(engine._bounded_stream_symbols({})) - provider._desired_symbols
        assert overflow and not (overflow & engine._stream_admitted)
        # A held symbol lost to provider truncation blocks every entry.
        held = {s: {"qty": 1} for s in DISCOVERED[10:15]}
        engine._universe = list(CORE)
        # Provider cap below |benchmarks + held| truncates two held names.
        monkeypatch.setattr("backend.organism.streaming_data_provider.MAX_STREAM_SYMBOLS", 5)
        engine._entries_blocked = False
        engine._last_entries_blocked_reason = ""
        await engine._sync_streaming_subscriptions(held)
        assert engine._entries_blocked and engine._stream_admitted == frozenset()
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_update_subscriptions_defers_to_transport_reconnect(monkeypatch):
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, _socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE)
    try:
        stream = provider._stream
        retry = AsyncMock(return_value=True)
        monkeypatch.setattr(provider, "_retry_start", retry)
        monkeypatch.setattr(type(stream), "reconnecting", property(lambda self: True))
        monkeypatch.setattr(stream, "is_authenticated", False)
        assert await provider.update_subscriptions(list(CORE)) is False
        retry.assert_not_awaited()
        assert provider.confirmed_symbols() == set()
    finally:
        await provider.stop()


def test_held_symbols_outrank_pending_and_pending_stays_within_cap(monkeypatch):
    monkeypatch.setattr("backend.organism.live_engine.STREAM_MAX_SYMBOLS", 5)
    engine = core_engine(None, [0.0], CORE)
    engine._pending_entry = {f"P{i}": 1 for i in range(5)}
    engine._pending_entry_order_ids = {}
    desired = engine._bounded_stream_symbols({"ZHELD": {"qty": 1}})
    # A held name sorting after the pending ones still comes first; pending
    # protection never grows the set past the cap.
    assert desired == ["SPY", "QQQ", "ZHELD", "P0", "P1"]
    # Benchmarks + held beyond the cap: the set grows to fit exactly them.
    held = {f"H{i}": {"qty": 1} for i in range(6)}
    desired = engine._bounded_stream_symbols(held)
    assert desired == ["SPY", "QQQ", "H0", "H1", "H2", "H3", "H4", "H5"]


def test_confirmation_capability_is_judged_by_provider_type():
    from unittest.mock import MagicMock
    from backend.organism.live_engine import OrganismLiveEngine
    # A test double without the capability falls back to the provider result.
    assert OrganismLiveEngine._confirmed_stream_symbols(MagicMock()) is None
    # A real provider that is not running confirms nothing (fail closed).
    assert OrganismLiveEngine._confirmed_stream_symbols(StreamingDataProvider()) == set()


@pytest.mark.asyncio
async def test_refused_names_do_not_drag_new_held_symbol_down(monkeypatch):
    """A provider limit below the configured cap refuses window names once;
    later requests leave them out, so a newly held symbol still subscribes."""
    now = [pd.Timestamp("2026-09-28T14:00:00Z").timestamp()]
    provider, socket = await real_capped_provider(monkeypatch, lambda: now[0], CORE, cap=22)
    try:
        engine = core_engine(provider, now, CORE + ["W1", "W2", "W3"])
        await feed_all(provider, now[0])
        await engine._sync_streaming_subscriptions({})
        assert socket.refusals >= 1
        assert not engine._entries_blocked, engine._last_entries_blocked_reason
        assert engine._stream_sync_status["status"] == "partial"
        assert {"W1", "W2", "W3"} <= provider._stream.refused_names
        refusals = socket.refusals
        await engine._sync_streaming_subscriptions({"H1": {"qty": 1}})
        assert socket.refusals == refusals  # refused names were not re-sent
        assert "H1" in provider.confirmed_symbols()
        assert "H1" in engine._stream_admitted
        assert not engine._entries_blocked, engine._last_entries_blocked_reason
    finally:
        await provider.stop()
