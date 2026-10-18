"""Audit 2026-10-05 C11-01: live buffers carry the engine's history window.

After a streaming-provider restart (``_retry_start`` clears every buffer) and
for every symbol subscribed after startup, the feeder used to switch from 500
REST bars to the live buffer as soon as it held MIN_BARS (50) bars, so
features, regime and scans ran on a truncated history for hours (and the
alpha/breakout scanners skipped 50-78-bar frames). Now each symbol gets one
background REST history seed (the startup prefill's merge: history only,
stream rows kept, never a receipt, generation-guarded), and ``_fetch_bars``
does not serve a short unseeded buffer while bounded REST can replace it.

Real ``StreamingDataProvider`` and real ``_DataFeederMixin`` throughout; only
the websocket transport and the REST client are in-memory fakes.
"""
from __future__ import annotations

import asyncio
import math
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from backend.organism import live_engine_data
from backend.organism.feature_store import VersionedFeatureStore
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.live_engine_data import _DataFeederMixin
from backend.organism.streaming_data_provider import StreamingDataProvider

LOOKBACK = 500      # production ORGANISM_LIVE_LOOKBACK
MIN_BARS = 50       # production ORGANISM_MIN_BARS (intraday)
T_START = pd.Timestamp("2026-10-05T04:00:00Z")
N_CORPUS = 1400


# ── fakes ────────────────────────────────────────────────────────────


def make_corpus(symbols, start=T_START, n=N_CORPUS):
    out = {}
    for i, symbol in enumerate(symbols):
        rng = np.random.default_rng(1000 + i)
        stamps = pd.date_range(start=start, periods=n, freq="min")
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.0008, n)))
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0005, n))
        low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0005, n))
        volume = rng.integers(1_000, 50_000, n).astype(float)
        out[symbol] = pd.DataFrame({"timestamp": stamps, "open": open_, "high": high,
                                    "low": low, "close": close, "volume": volume})
    return out


def as_rest_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """The AlpacaDataClient shape: tz-aware ISO timestamps, float OHLCV."""
    return pd.DataFrame({
        "timestamp": [stamp.isoformat() for stamp in rows["timestamp"]],
        **{column: rows[column].astype(float).to_numpy()
           for column in ("open", "high", "low", "close", "volume")},
    })


class History:
    """Fake REST history: the latest closed bars as of the shared clock."""

    def __init__(self, corpus, clock):
        self.corpus = corpus
        self.clock = clock
        self.calls: list[tuple[str, int, str]] = []
        self.fail: dict[str, int] = {}          # symbol -> failures left
        self.gates: dict[str, asyncio.Event] = {}
        self.cap: dict[str, int] = {}           # sparse symbols: rows REST holds
        self.empty: set[str] = set()

    def window(self, symbol, lookback):
        last_closed = pd.Timestamp(math.floor(self.clock[0] / 60) * 60 - 60, unit="s", tz="UTC")
        frame = self.corpus[symbol]
        rows = frame[frame["timestamp"] <= last_closed].tail(min(lookback, self.cap.get(symbol, lookback)))
        return as_rest_frame(rows)

    async def get_historical_bars_df(self, symbol, lookback, timeframe):
        self.calls.append((symbol, lookback, timeframe))
        answer = self.window(symbol, lookback)      # the server answers as of the request
        gate = self.gates.get(symbol)
        if gate is not None:
            await gate.wait()
        if self.fail.get(symbol, 0) > 0:
            self.fail[symbol] -= 1
            raise ConnectionError("offline REST failure")
        if symbol in self.empty:
            return pd.DataFrame()
        return answer

    def count(self, symbol=None):
        return sum(1 for call in self.calls if symbol is None or call[0] == symbol)


class Transport:
    """In-memory market-data websocket: provider state and callbacks are real."""

    def __init__(self, **_kwargs):
        self.is_authenticated = False
        self.bar_subscriptions = {"1Min": set()}
        self.quote_subscriptions: set[str] = set()
        self.on_bar = None
        self.on_quote = None

    async def connect(self):
        self.is_authenticated = True
        return True

    async def disconnect(self):
        self.is_authenticated = False

    async def _cleanup_connection(self):
        self.is_authenticated = False

    async def subscribe_bars(self, names):
        self.bar_subscriptions["1Min"].update(names)
        return True

    async def subscribe_quotes(self, names):
        self.quote_subscriptions.update(names)
        return True

    async def unsubscribe(self, names):
        self.bar_subscriptions["1Min"].difference_update(names)
        self.quote_subscriptions.difference_update(names)
        return True


@pytest.fixture
def env(monkeypatch):
    """Production data constants, an in-memory transport factory and a clock."""
    monkeypatch.setattr("backend.organism.live_engine.LIVE_LOOKBACK", LOOKBACK)
    monkeypatch.setattr("backend.organism.live_engine.LIVE_TIMEFRAME", "1Min")
    monkeypatch.setattr("backend.organism.live_engine.MIN_BARS", MIN_BARS)
    transports: list[Transport] = []

    def factory(**kwargs):
        transport = Transport(**kwargs)
        transports.append(transport)
        return transport

    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream", factory)
    clock = [0.0]
    return SimpleNamespace(transports=transports, clock=clock)


def minute(index: int) -> pd.Timestamp:
    return T_START + pd.Timedelta(minutes=index)


def at_close_of(index: int) -> float:
    """One second after bar ``index`` closed: when the stream delivers it."""
    return minute(index).timestamp() + 61.0


async def deliver(env, provider, corpus, symbol, index, **override):
    """Deliver corpus bar ``index`` through the provider's wired callback."""
    env.clock[0] = max(env.clock[0], at_close_of(index))
    row = corpus[symbol].iloc[index]
    bar = {"timestamp": minute(index).isoformat(), "open": float(row["open"]),
           "high": float(row["high"]), "low": float(row["low"]),
           "close": float(row["close"]), "volume": float(row["volume"]), **override}
    await provider._stream.on_bar(symbol, bar)


async def deliver_range(env, provider, corpus, symbols, first, last):
    for index in range(first, last + 1):
        for symbol in symbols:
            await deliver(env, provider, corpus, symbol, index)


async def drain_seed(provider, timeout=5.0):
    task = getattr(provider, "_seed_task", None)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout)


def feeder(provider, client, universe, store=False):
    host = _DataFeederMixin()
    host._streaming_provider = provider
    host._data_client = client
    host._feature_store = VersionedFeatureStore() if store else None
    host._bars_per_day = 390
    host._universe = list(universe)
    host._positions_service = SimpleNamespace(get_all_positions=AsyncMock(return_value={}))
    return host


async def started_provider(env, client, symbols, start_index, prefill=True):
    env.clock[0] = at_close_of(start_index)
    provider = StreamingDataProvider(time_fn=lambda: env.clock[0])
    if prefill:
        assert await provider.start(list(symbols), "offline", "offline", feed="iex", data_client=client)
    else:
        assert await provider.start(list(symbols), "offline", "offline", feed="iex",
                                    data_client=client, _prefill_history=False)
    return provider


async def restart_provider(provider, symbols):
    """The transport gave up (10 reconnects): the next sync restarts the provider."""
    provider._stream.is_authenticated = False
    provider._recovery_due_at = 0
    assert await provider.update_subscriptions(list(symbols)) is True


# ── 1. provider restart -> full history ──────────────────────────────


@pytest.mark.asyncio
async def test_after_provider_restart_features_use_full_history_like_rest(env):
    symbols = ["SPY", "QQQ", "AAA"]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600)
    try:
        await deliver_range(env, provider, corpus, symbols, 600, 602)
        env.clock[0] = at_close_of(610)
        calls_before = rest.count()
        await restart_provider(provider, symbols)
        assert len(env.transports) == 2
        # The restart cleared every buffer and fetched no history inline.
        assert rest.count() == calls_before
        assert all(provider.bar_count(s) == 0 for s in symbols)
        await drain_seed(provider)
        assert rest.count() == calls_before + len(symbols)
        assert all(provider.bar_count(s) == LOOKBACK for s in symbols)
        # History is never a receipt.
        assert provider._last_bar_ts == {} and provider.last_update_time is None
        assert {s for s, _ in provider.stale_symbols(120)} == set(symbols)
        # 60 live bars (>= MIN_BARS): the old feeder served a 60-bar buffer.
        await deliver_range(env, provider, corpus, symbols, 611, 670)
        calls_before = rest.count()
        live = await feeder(provider, rest, symbols, store=True)._fetch_and_compute_features()
        assert rest.count() == calls_before
        reference = await feeder(None, rest, symbols, store=True)._fetch_and_compute_features()
        assert set(live) == set(reference) == set(symbols)
        for symbol in symbols:
            # Same 500 bars -> identical features (481 rows after the store's
            # warm-up), well above the alpha (50) and breakout (60) row gates.
            assert len(live[symbol]) == len(reference[symbol]) == LOOKBACK - 19
            pd.testing.assert_frame_equal(live[symbol], reference[symbol])
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_failed_initial_start_retry_seeds_history(env, monkeypatch):
    symbols = ["SPY", "QQQ"]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    env.clock[0] = at_close_of(700)
    provider = StreamingDataProvider(time_fn=lambda: env.clock[0])
    refuse = {"on": True}
    real_connect = Transport.connect

    async def connect(self):
        return False if refuse["on"] else await real_connect(self)

    monkeypatch.setattr(Transport, "connect", connect)
    try:
        assert await provider.start(symbols, "offline", "offline", feed="iex", data_client=rest) is False
        assert rest.count() == 0
        refuse["on"] = False
        provider._recovery_due_at = 0
        assert await provider.check_and_recover_stale_stream() is True
        await drain_seed(provider)
        assert sorted(call[0] for call in rest.calls) == sorted(symbols)
        assert all(provider.history_complete(s, LOOKBACK) for s in symbols)
        assert all(provider.get_bar_age(s) == float("inf") for s in symbols)
    finally:
        await provider.stop()


# ── 2. new subscription -> seeded ────────────────────────────────────


@pytest.mark.asyncio
async def test_newly_subscribed_symbol_is_seeded_in_background_without_receipt(env):
    symbols = ["SPY", "QQQ", "AAA"]
    corpus = make_corpus(symbols + ["NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600)
    try:
        await deliver_range(env, provider, corpus, symbols, 600, 601)
        assert rest.count("NEW") == 0
        assert await provider.update_subscriptions(symbols + ["NEW"]) is True
        assert "NEW" in provider._subscribed_symbols
        assert rest.count("NEW") == 0 and provider.bar_count("NEW") == 0   # not inside the sync
        await drain_seed(provider)
        assert rest.calls[-1] == ("NEW", LOOKBACK, "1Min")
        assert provider.bar_count("NEW") == LOOKBACK
        assert provider.history_complete("NEW", LOOKBACK)
        assert "NEW" not in provider._last_bar_ts
        assert provider.get_bar_age("NEW") == float("inf")
        assert ("NEW", float("inf")) in provider.stale_symbols(120)
        assert provider.get_bars("NEW").empty                      # still no stream use
        # Repeated syncs never seed it again.
        for _ in range(3):
            assert await provider.update_subscriptions(symbols + ["NEW"]) is True
        await drain_seed(provider)
        assert rest.count("NEW") == 1
        # The first advancing live bar makes the full buffer usable.
        await deliver(env, provider, corpus, "NEW", 602)
        assert provider.get_bar_age("NEW") == 0
        host = feeder(provider, rest, symbols + ["NEW"])
        frame = await host._fetch_bars("NEW")
        assert host._last_bar_fetch_sources["NEW"] == "stream_buffer"
        assert rest.count("NEW") == 1
        pd.testing.assert_frame_equal(frame, rest.window("NEW", LOOKBACK))
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_seeds_run_outside_the_engine_subscription_sync_deadline(env):
    core = ["SPY", "QQQ", "AAA"]
    window = [f"W{i}" for i in range(8)]
    corpus = make_corpus(core + window)
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, core, 600)
    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = provider
    engine._time_fn = lambda: env.clock[0]
    engine._streaming_base_symbols = frozenset(core)
    engine._core_universe = list(core)
    engine._universe = core + window
    engine._DATA_STALE_THRESHOLD_S = 120
    engine._data_stale = False
    engine._entries_blocked = False
    engine._last_entries_blocked_reason = ""

    async def slow_history(symbol, lookback, timeframe):
        rest.calls.append((symbol, lookback, timeframe))
        await asyncio.sleep(0.3)
        return rest.window(symbol, lookback)

    rest.get_historical_bars_df = slow_history
    try:
        await deliver_range(env, provider, corpus, core, 600, 601)
        started = time.monotonic()
        await engine._sync_streaming_subscriptions({})
        elapsed = time.monotonic() - started
        # Eight sequential 0.3 s seeds (2.4 s) do not run inside the sync: it
        # returned before the first one completed.
        assert engine._stream_sync_status["status"] == "complete"
        assert set(window) <= provider._subscribed_symbols
        assert not any(provider.bar_count(s) for s in window)
        assert elapsed < 2.0
        await drain_seed(provider)
        assert all(provider.history_complete(s, LOOKBACK) for s in window)
        assert [call[0] for call in rest.calls[-len(window):]] == window   # priority order, one each
    finally:
        await provider.stop()


# ── 3. concurrent stream rows survive ────────────────────────────────


@pytest.mark.asyncio
async def test_stream_rows_received_during_seed_survive_and_keep_their_receipt(env):
    symbols = ["SPY", "QQQ"]
    corpus = make_corpus(symbols + ["NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600)
    gate = asyncio.Event()
    rest.gates["NEW"] = gate
    try:
        assert await provider.update_subscriptions(symbols + ["NEW"]) is True
        await asyncio.sleep(0)                # the worker is now waiting on REST
        assert provider._seed_inflight == "NEW"
        # Live bars arrive while REST is awaited. REST will also hold bar 600,
        # with different values: the stream's row must win that minute.
        await deliver(env, provider, corpus, "NEW", 600, close=999.0)
        await deliver(env, provider, corpus, "NEW", 601, close=998.0)
        receipt = provider._last_bar_ts["NEW"]
        assert provider.bar_count("NEW") == 2
        gate.set()
        await drain_seed(provider)
        rows = list(provider._bars["NEW"])
        stamps = [pd.Timestamp(row["timestamp"]) for row in rows]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
        assert len(rows) == LOOKBACK + 1                        # 500 REST (to 600) + 601
        assert rows[-2]["timestamp"] == minute(600).isoformat() and rows[-2]["close"] == 999.0
        assert rows[-1]["timestamp"] == minute(601).isoformat() and rows[-1]["close"] == 998.0
        assert provider._last_bar_ts["NEW"] == receipt        # the seed wrote no receipt
        assert provider.get_bars("NEW", LOOKBACK).iloc[-1]["close"] == 998.0
    finally:
        await provider.stop()


# ── 4. generation guard ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_during_seed_writes_nothing_and_cancels_the_worker(env):
    corpus = make_corpus(["SPY", "NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, ["SPY"], 600)
    rest.gates["NEW"] = asyncio.Event()
    assert await provider.update_subscriptions(["SPY", "NEW"]) is True
    await asyncio.sleep(0)
    task = provider._seed_task
    assert task is not None and provider._seed_inflight == "NEW"
    await provider.stop()
    await asyncio.wait({task}, timeout=1)
    assert task.cancelled()
    rest.gates["NEW"].set()
    await asyncio.sleep(0)
    assert not provider._bars and not provider._last_bar_ts and not provider._history_seeded
    assert provider._seed_task is None and not provider._seed_queue


@pytest.mark.asyncio
async def test_restart_during_seed_never_writes_old_session_history(env):
    corpus = make_corpus(["SPY", "NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, ["SPY"], 600)
    old_gate = asyncio.Event()
    rest.gates["NEW"] = old_gate
    try:
        assert await provider.update_subscriptions(["SPY", "NEW"]) is True
        await asyncio.sleep(0)
        old_task = provider._seed_task
        # The new session's seeds wait on their own gate.
        new_gate = asyncio.Event()
        rest.gates["NEW"] = new_gate
        rest.gates["SPY"] = new_gate
        await restart_provider(provider, ["SPY", "NEW"])
        old_gate.set()
        await asyncio.wait({old_task}, timeout=1)
        assert old_task.cancelled()
        assert provider.bar_count("NEW") == 0 and "NEW" not in provider._history_seeded
        new_gate.set()
        await drain_seed(provider)
        assert provider.history_complete("NEW", LOOKBACK) and provider.bar_count("NEW") == LOOKBACK
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_stale_stream_reconnect_during_seed_drops_the_result_then_reseeds(env):
    corpus = make_corpus(["SPY", "NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, ["SPY"], 600)
    gate = asyncio.Event()
    rest.gates["NEW"] = gate
    try:
        await deliver(env, provider, corpus, "SPY", 601)    # 600 is the prefill's last bar
        assert provider.get_bar_age("SPY") == 0
        assert await provider.update_subscriptions(["SPY", "NEW"]) is True
        await asyncio.sleep(0)
        env.clock[0] += 301                          # every symbol stale -> reconnect
        assert await provider.check_and_recover_stale_stream() is True
        gate.set()
        await drain_seed(provider)
        assert provider.bar_count("NEW") == 0 and "NEW" not in provider._history_seeded
        assert provider._seed_task is None and provider._seed_inflight is None
        del rest.gates["NEW"]
        assert await provider.update_subscriptions(["SPY", "NEW"]) is True
        await drain_seed(provider)
        assert provider.history_complete("NEW", LOOKBACK)
        assert rest.count("NEW") == 2
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_symbol_retired_during_seed_is_not_resurrected(env):
    corpus = make_corpus(["SPY", "OLD"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, ["SPY"], 600)
    gate = asyncio.Event()
    rest.gates["OLD"] = gate
    try:
        assert await provider.update_subscriptions(["SPY", "OLD"]) is True
        await asyncio.sleep(0)
        assert provider._seed_inflight == "OLD"
        assert await provider.update_subscriptions(["SPY"]) is True    # confirmed removal
        gate.set()
        await drain_seed(provider)
        assert not provider.has_data("OLD") and "OLD" not in provider._history_seeded
        await provider._stream.on_bar("OLD", {"timestamp": minute(600).isoformat(), "close": 1.0})
        assert not provider.has_data("OLD")
    finally:
        await provider.stop()


# ── 5. failed seed -> REST, tick not blocked ────────────────────────


@pytest.mark.asyncio
async def test_failed_seed_degrades_to_rest_with_full_history_then_retries(env):
    symbols = ["SPY", "QQQ", "AAA"]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600)
    rest.fail["AAA"] = 1                              # one transient failure
    try:
        env.clock[0] = at_close_of(610)
        await restart_provider(provider, symbols)
        await drain_seed(provider)
        assert "AAA" not in provider._history_seeded and "AAA" in provider._seed_failed_at
        assert provider.history_complete("SPY", LOOKBACK)
        await deliver_range(env, provider, corpus, symbols, 611, 670)   # 60 live bars
        assert provider.bar_count("AAA") == 60
        host = feeder(provider, rest, symbols)
        frame = await host._fetch_bars("AAA")
        # Not the 60-bar buffer: REST supplies the full window.
        assert host._last_bar_fetch_sources["AAA"] == "rest"
        pd.testing.assert_frame_equal(frame, rest.window("AAA", LOOKBACK))
        # The failed seed is not retried before HISTORY_SEED_RETRY_S ...
        aaa_calls = rest.count("AAA")
        assert await provider.update_subscriptions(symbols) is True
        await drain_seed(provider)
        assert rest.count("AAA") == aaa_calls
        # ... and is retried after it; then the stream buffer is served.
        provider._seed_failed_at["AAA"] -= provider.HISTORY_SEED_RETRY_S
        assert await provider.update_subscriptions(symbols) is True
        await drain_seed(provider)
        assert provider.history_complete("AAA", LOOKBACK)
        assert rest.count("AAA") == aaa_calls + 1
        frame = await host._fetch_bars("AAA")
        assert host._last_bar_fetch_sources["AAA"] == "stream_buffer"
        assert rest.count("AAA") == aaa_calls + 1
        pd.testing.assert_frame_equal(frame, rest.window("AAA", LOOKBACK))
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_hanging_seed_and_rest_never_block_the_tick(env, monkeypatch):
    monkeypatch.setattr(live_engine_data, "HISTORY_FALLBACK_TIMEOUT_S", 0.05)
    symbols = ["SPY", "QQQ", "AAA"]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600)
    try:
        env.clock[0] = at_close_of(610)
        rest.gates["AAA"] = asyncio.Event()           # every AAA request hangs
        await restart_provider(provider, symbols)
        for _ in range(100):                          # SPY and QQQ seed, AAA hangs
            if provider._seed_inflight == "AAA":
                break
            await asyncio.sleep(0.01)
        assert provider._seed_inflight == "AAA"
        await deliver_range(env, provider, corpus, symbols, 611, 670)
        started = time.monotonic()
        features = await asyncio.wait_for(
            feeder(provider, rest, symbols)._fetch_and_compute_features(), timeout=20)
        # Only the 0.05 s REST deadline is spent on AAA (feature CPU aside).
        assert time.monotonic() - started < 10
        assert provider._seed_inflight == "AAA"
        # SPY/QQQ were seeded; AAA's REST read timed out, so the short
        # buffer is served exactly as before this change.
        assert set(features) == set(symbols)
        assert len(features["SPY"]) == len(features["QQQ"]) == LOOKBACK
        assert len(features["AAA"]) == 60
    finally:
        await provider.stop()


# ── 6. REST load stays bounded ───────────────────────────────────────


@pytest.mark.asyncio
async def test_short_buffer_rest_reads_are_bounded_per_window(env, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(live_engine_data, "_monotonic", lambda: now[0])
    symbols = ["SPY", "QQQ"] + [f"S{i:02d}" for i in range(10)]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    # A provider without a REST client cannot seed: every buffer stays short.
    provider = await started_provider(env, None, symbols, 600, prefill=False)
    try:
        await deliver_range(env, provider, corpus, symbols, 601, 660)   # 60 live bars each
        host = feeder(provider, rest, symbols)
        features = await host._fetch_and_compute_features()
        cap = live_engine_data.HISTORY_FALLBACK_MAX_CALLS
        assert rest.count() == cap == 5
        sources = host._last_bar_fetch_sources
        assert sum(1 for s in symbols if sources[s] == "rest") == cap
        assert sum(1 for s in symbols if sources[s] == "stream_buffer") == len(symbols) - cap
        assert sources["SPY"] == "rest"                      # fetched first
        assert {len(features[s]) for s in symbols if sources[s] == "rest"} == {LOOKBACK}
        assert {len(features[s]) for s in symbols if sources[s] == "stream_buffer"} == {60}
        # Same window: no further REST reads, every short buffer served.
        await host._fetch_and_compute_features()
        assert rest.count() == cap
        # Next window: the budget refills, never beyond the cap.
        now[0] += live_engine_data.HISTORY_FALLBACK_WINDOW_S
        await host._fetch_and_compute_features()
        assert rest.count() == 2 * cap
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_seed_requests_are_one_per_symbol_and_failed_retries_are_spaced(env):
    symbols = ["SPY", "QQQ", "AAA", "BBB"]
    corpus = make_corpus(symbols)
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, symbols, 600, prefill=False)
    rest.fail["BBB"] = 1000                          # REST down for BBB
    try:
        for tick in range(30):                       # ~5 minutes of 10 s syncs
            assert await provider.update_subscriptions(symbols) is True
            await drain_seed(provider)
        assert {s: rest.count(s) for s in symbols} == {"SPY": 1, "QQQ": 1, "AAA": 1, "BBB": 1}
        provider._seed_failed_at["BBB"] -= provider.HISTORY_SEED_RETRY_S
        assert await provider.update_subscriptions(symbols) is True
        await drain_seed(provider)
        assert rest.count("BBB") == 2 and rest.count("SPY") == 1
    finally:
        await provider.stop()


# ── 7. defence in depth and contract details ────────────────────────


@pytest.mark.asyncio
async def test_short_buffer_served_as_before_when_rest_is_missing_shorter_or_failing(env):
    corpus = make_corpus(["SPY", "AAA"])
    provider = await started_provider(env, None, ["SPY", "AAA"], 600, prefill=False)
    try:
        await deliver_range(env, provider, corpus, ["AAA"], 601, 660)
        stream = provider.get_bars("AAA", LOOKBACK)
        assert len(stream) == 60 and not provider.history_complete("AAA", LOOKBACK)
        for client in (
            SimpleNamespace(),                                                   # no REST method
            SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=None)),
            SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=stream.iloc[:10])),
            SimpleNamespace(get_historical_bars_df=AsyncMock(side_effect=ConnectionError("down"))),
        ):
            host = feeder(provider, client, ["AAA"])
            frame = await host._fetch_bars("AAA")
            pd.testing.assert_frame_equal(frame, stream)
            assert host._last_bar_fetch_sources["AAA"] == "stream_buffer"
        # Below MIN_BARS the ordinary REST path is unchanged (no budget).
        host = feeder(provider, SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=None)), ["SPY"])
        assert await host._fetch_bars("SPY") is None
        assert host._last_bar_fetch_sources["SPY"] == "unavailable"
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_sparse_symbol_seeded_with_all_rest_history_is_served_without_rest(env):
    corpus = make_corpus(["SPY", "THIN"])
    rest = History(corpus, env.clock)
    rest.cap["THIN"] = 120                           # REST holds only 120 bars
    provider = await started_provider(env, rest, ["SPY", "THIN"], 600)
    try:
        assert provider.bar_count("THIN") == 120 and provider.history_complete("THIN", LOOKBACK)
        await deliver(env, provider, corpus, "THIN", 601)
        host = feeder(provider, rest, ["THIN"])
        calls = rest.count()
        frame = await host._fetch_bars("THIN")
        assert len(frame) == 121 and host._last_bar_fetch_sources["THIN"] == "stream_buffer"
        assert rest.count() == calls
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_completeness_rule_seeded_or_window_or_ring_capacity(env):
    provider = StreamingDataProvider(buffer_size=300, time_fn=lambda: env.clock[0])
    from collections import deque
    provider._bars["A"] = deque([{"timestamp": "x"}] * 299, maxlen=300)
    assert not provider.history_complete("A", LOOKBACK)
    provider._bars["A"].append({"timestamp": "y"})
    assert provider.history_complete("A", LOOKBACK)          # ring capacity < window
    provider._bars["B"] = deque([{"timestamp": "x"}] * 60, maxlen=300)
    assert not provider.history_complete("b", LOOKBACK)
    provider._history_seeded.add("B")
    assert provider.history_complete("b", LOOKBACK)
    assert not provider.history_complete("MISSING", LOOKBACK)


@pytest.mark.asyncio
async def test_provider_without_history_contract_keeps_min_bars_rule(env):
    rows = pd.DataFrame({"close": [100.0] * MIN_BARS})
    provider = SimpleNamespace(get_bars=lambda *args: rows)
    client = SimpleNamespace(get_historical_bars_df=AsyncMock(return_value=rows))
    host = feeder(provider, client, ["AAA"])
    assert await host._fetch_bars("AAA") is rows
    assert host._last_bar_fetch_sources["AAA"] == "stream_buffer"
    client.get_historical_bars_df.assert_not_awaited()


@pytest.mark.asyncio
async def test_prefill_and_seed_request_the_engine_history_window(env, monkeypatch):
    # The old prefill re-read ORGANISM_LIVE_LOOKBACK with a default of 100.
    monkeypatch.delenv("ORGANISM_LIVE_LOOKBACK", raising=False)
    monkeypatch.delenv("ORGANISM_LIVE_TIMEFRAME", raising=False)
    corpus = make_corpus(["SPY", "NEW"])
    rest = History(corpus, env.clock)
    provider = await started_provider(env, rest, ["SPY"], 600)
    try:
        assert rest.calls == [("SPY", LOOKBACK, "1Min")]
        assert await provider.update_subscriptions(["SPY", "NEW"]) is True
        await drain_seed(provider)
        assert rest.calls[-1] == ("NEW", LOOKBACK, "1Min")
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_empty_or_invalid_seed_is_a_failure_not_history(env):
    corpus = make_corpus(["SPY", "NONE", "BAD"])
    rest = History(corpus, env.clock)
    rest.empty.add("NONE")
    provider = await started_provider(env, rest, ["SPY"], 600)

    async def bad_history(symbol, lookback, timeframe):
        rest.calls.append((symbol, lookback, timeframe))
        if symbol == "BAD":
            return pd.DataFrame({"timestamp": ["2026-10-05T14:00:00"], "open": [1.0], "high": [1.0],
                                 "low": [1.0], "close": [1.0], "volume": [1.0]})   # naive time
        return await History.get_historical_bars_df(rest, symbol, lookback, timeframe)

    rest.get_historical_bars_df = bad_history
    try:
        assert await provider.update_subscriptions(["SPY", "NONE", "BAD"]) is True
        await drain_seed(provider)
        for symbol in ("NONE", "BAD"):
            assert symbol in provider._seed_failed_at and symbol not in provider._history_seeded
            assert not provider.has_data(symbol)
    finally:
        await provider.stop()


def test_runtime_snapshot_reports_the_history_bounds(monkeypatch):
    from scripts.runtime import write_runtime_snapshot as snapshot
    from unittest.mock import patch

    monkeypatch.setattr(StreamingDataProvider, "HISTORY_SEED_TIMEOUT_S", 12.0)
    monkeypatch.setattr(StreamingDataProvider, "HISTORY_SEED_RETRY_S", 34.0)
    monkeypatch.setattr(live_engine_data, "HISTORY_FALLBACK_MAX_CALLS", 3)
    monkeypatch.setattr(live_engine_data, "HISTORY_FALLBACK_WINDOW_S", 7.0)
    monkeypatch.setattr(live_engine_data, "HISTORY_FALLBACK_TIMEOUT_S", 2.0)
    defaults = snapshot._build_defaults_snapshot()
    with patch.object(snapshot, "_find_api_container", return_value=""):
        resolved = snapshot._build_resolved_config_snapshot()
    policy = defaults["stream_history"]
    assert policy["seed_timeout_seconds"] == 12.0
    assert policy["seed_retry_after_failure_seconds"] == 34.0
    assert policy["short_buffer_rest_max_calls"] == 3
    assert policy["short_buffer_rest_window_seconds"] == 7.0
    assert policy["short_buffer_rest_timeout_seconds"] == 2.0
    assert policy["ring_capacity_bars"] == 2000
    assert resolved["resolved"]["stream_history"] == policy
    assert defaults["streaming_subscription_sync"]["new_symbols"] == (
        "freshness_waits_for_actual_bars_background_REST_history_seed")
