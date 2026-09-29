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
        assert len(provider._desired_symbols) <= 30
        assert set(CORE) <= provider.confirmed_symbols()
        assert not engine._entries_blocked, engine._last_entries_blocked_reason
        assert not engine._data_stale
        assert engine._stream_sync_status["status"] in {"complete", "partial"}
        # Symbols beyond the cap are never admitted for entries.
        assert len(engine._stream_admitted) <= 30
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
        # Window capacity = min(ORGANISM_SCANNER_WINDOW_MAX=8, cap 30 - core 20).
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
        assert desired[0] == "HELD1" and len(desired) <= 30
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
    assert desired[:3] == ["D40", "SPY", "QQQ"]
    assert desired[3:3 + len(core_rest)] == core_rest
    assert desired[3 + len(core_rest):] == ["D00"]  # window fills what the cap allows
    assert len(desired) == 22
