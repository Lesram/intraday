"""Real provider lifecycle with an in-memory transport; no network or credentials."""

import asyncio
import copy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.organism.streaming_data_provider import StreamingDataProvider


NOW = datetime(2026, 9, 22, 16, tzinfo=timezone.utc).timestamp()


def bar(stamp=NOW - 1, close=100):
    return {"timestamp": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
            "open": 100, "high": 101, "low": 99, "close": close, "volume": 1000}


class Transport:
    def __init__(self, **_kwargs):
        self.is_authenticated = True
        self.bar_subscriptions = {"1Min": set()}
        self.quote_subscriptions = set()
        self.connect = AsyncMock(return_value=True)
        self.disconnect = AsyncMock()
        self._cleanup_connection = AsyncMock()
        self.subscribe_bars = AsyncMock(side_effect=self._bars)
        self.subscribe_quotes = AsyncMock(side_effect=self._quotes)
        self.unsubscribe = AsyncMock(side_effect=self._unsubscribe)

    async def _bars(self, symbols):
        self.bar_subscriptions["1Min"].update(symbols)
        return True

    async def _quotes(self, symbols):
        self.quote_subscriptions.update(symbols)
        return True

    async def _unsubscribe(self, symbols):
        self.bar_subscriptions["1Min"].difference_update(symbols)
        self.quote_subscriptions.difference_update(symbols)
        return True


@pytest.fixture
def setup(monkeypatch):
    streams = []

    def factory(**kwargs):
        stream = Transport(**kwargs)
        streams.append(stream)
        return stream

    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream", factory)
    clock = [NOW]
    return StreamingDataProvider(time_fn=lambda: clock[0]), streams, clock


async def start(data, symbols, **kwargs):
    await data.start(symbols, "offline-key", "offline-secret", **kwargs)


def assert_empty(data):
    assert not data._bars and not data._quotes and not data._last_bar_ts
    assert not data._subscribed_symbols and not data._retired_symbols
    assert data.last_update_time is None
    assert not data.is_running


@pytest.mark.asyncio
async def test_stop_start_replaces_entire_session_and_keeps_new_unseen_symbols_stale(setup):
    data, streams, clock = setup
    await start(data, ["OLD"])
    await streams[0].on_bar("OLD", bar())
    await streams[0].on_quote("OLD", {"bid": 99, "ask": 101})
    assert data.has_data("OLD") and data.get_latest_quote("OLD")
    await data.stop()
    assert_empty(data)
    clock[0] += 121
    await start(data, ["NEW"])
    assert data._subscribed_symbols == {"NEW"}
    assert data.stale_symbols(120) == [("NEW", float("inf"))]
    await streams[1].on_bar("NEW", bar(clock[0] - 1))
    assert data.stale_symbols(120) == []
    assert data._freshness_symbols() == {"NEW"}
    assert not data.has_data("OLD") and not data.get_latest_quote("OLD")


@pytest.mark.asyncio
@pytest.mark.parametrize("reuse_symbol", [False, True])
async def test_old_callbacks_cannot_repopulate_stopped_or_restarted_session(setup, reuse_symbol):
    data, streams, _ = setup
    await start(data, ["OLD"])
    old_bar, old_quote = streams[0].on_bar, streams[0].on_quote
    await data.stop()
    await old_bar("OLD", bar())
    await old_quote("OLD", {"bid": 1})
    assert_empty(data)
    name = "OLD" if reuse_symbol else "NEW"
    await start(data, [name])
    await old_bar(name, bar(close=77))
    await old_quote(name, {"bid": 1})
    assert not data.has_data(name) and not data.get_latest_quote(name)
    assert data.last_update_time is None
    await streams[1].on_bar(name, bar())
    assert data.get_bars(name).iloc[-1]["close"] == 100
    await streams[1].on_bar("UNREQUESTED", bar())
    await streams[1].on_quote("UNREQUESTED", {"bid": 1})
    assert not data.has_data("UNREQUESTED") and not data.get_latest_quote("UNREQUESTED")


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["connect", "subscribe_bars", "subscribe_quotes"])
@pytest.mark.parametrize("raises", [False, True])
async def test_failed_start_clears_session_and_late_callbacks_before_retry(setup, monkeypatch, stage, raises):
    data, streams, _ = setup
    failed = Transport()

    async def fail(*_args):
        if stage == "subscribe_quotes":
            await failed.on_bar("OLD", bar())
            await failed.on_quote("OLD", {"bid": 99})
        if raises:
            raise RuntimeError("offline start failure")
        return False

    setattr(failed, stage, AsyncMock(side_effect=fail))
    replacement = Transport()
    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream",
                        lambda **_kwargs: failed if not streams else replacement)
    if raises:
        with pytest.raises(RuntimeError, match="offline start failure"):
            await start(data, ["OLD"])
    else:
        await start(data, ["OLD"])
    failed.disconnect.assert_awaited_once()
    assert_empty(data)
    await failed.on_bar("OLD", bar())
    await failed.on_quote("OLD", {"bid": 1})
    assert_empty(data)
    streams.append(failed)
    await start(data, ["NEW"])
    assert data.is_running and data._stream is replacement
    assert data.stale_symbols(120) == [("NEW", float("inf"))]


@pytest.mark.asyncio
async def test_disconnect_failure_holds_reference_but_invalidates_callbacks_and_data(setup):
    data, streams, _ = setup
    await start(data, ["OLD"])
    old = streams[0]
    await old.on_bar("OLD", bar())
    old.disconnect.side_effect = RuntimeError("offline disconnect failure")
    with pytest.raises(RuntimeError, match="offline disconnect failure"):
        await data.stop()
    assert data._stream is old
    assert_empty(data)
    await old.on_bar("OLD", bar())
    assert_empty(data)
    with pytest.raises(RuntimeError, match="offline disconnect failure"):
        await start(data, ["NEW"])
    assert len(streams) == 1
    old.disconnect.side_effect = None
    await start(data, ["NEW"])
    assert len(streams) == 2 and data._subscribed_symbols == {"NEW"}


@pytest.mark.asyncio
async def test_stop_during_prefill_discards_old_result_before_new_session(setup):
    data, streams, _ = setup
    entered, release = asyncio.Event(), asyncio.Event()

    async def historical(*_args, **_kwargs):
        entered.set()
        await release.wait()
        return pd.DataFrame([bar()])

    client = type("Client", (), {"get_historical_bars_df": staticmethod(historical)})()
    starting = asyncio.create_task(start(data, ["OLD"], data_client=client))
    await entered.wait()
    stopping = asyncio.create_task(data.stop())
    await asyncio.sleep(0)
    await streams[0].on_bar("OLD", bar())
    release.set()
    await asyncio.gather(starting, stopping)
    assert_empty(data)
    await start(data, ["NEW"])
    assert data._subscribed_symbols == {"NEW"} and not data.has_data("OLD")


@pytest.mark.asyncio
async def test_stop_during_subscription_cannot_restore_obsolete_membership(setup):
    data, streams, _ = setup
    await start(data, ["OLD"])
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(names):
        entered.set()
        await release.wait()
        return await streams[0]._bars(names)

    streams[0].subscribe_bars.side_effect = delayed
    updating = asyncio.create_task(data.update_subscriptions(["OLD", "LATE"]))
    await entered.wait()
    stopping = asyncio.create_task(data.stop())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(updating, stopping)
    assert_empty(data)
    await start(data, ["NEW"])
    assert data._freshness_symbols() == {"NEW"}


@pytest.mark.asyncio
async def test_reconnect_rotates_callbacks_but_does_not_refresh_stale_health(setup):
    data, streams, clock = setup
    await start(data, ["KEEP"])
    stream = streams[0]
    await stream.on_bar("KEEP", bar())
    old_callback = stream.on_bar
    clock[0] += 301
    before = copy.deepcopy(data._bars)
    assert await data.check_and_recover_stale_stream() is True
    assert data._bars == before and data.get_bar_age("KEEP") == 301
    await old_callback("KEEP", bar(clock[0] - 1))
    assert data._bars == before and data.get_bar_age("KEEP") == 301
    await stream.on_bar("KEEP", bar(clock[0] - 1))
    assert data.get_bar_age("KEEP") == 0


@pytest.mark.asyncio
async def test_stop_during_reconnect_cannot_restart_old_transport(setup):
    data, streams, clock = setup
    await start(data, ["OLD"])
    stream = streams[0]
    await stream.on_bar("OLD", bar())
    clock[0] += 301
    entered, release = asyncio.Event(), asyncio.Event()

    async def cleanup():
        entered.set()
        await release.wait()

    stream._cleanup_connection.side_effect = cleanup
    recovering = asyncio.create_task(data.check_and_recover_stale_stream())
    await entered.wait()
    stopping = asyncio.create_task(data.stop())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(recovering, stopping)
    assert stream.connect.await_count == 1  # Only original start, not obsolete recovery.
    assert_empty(data)


@pytest.mark.asyncio
async def test_stop_clears_a_start_already_queued_ahead_of_it(setup):
    data, _, _ = setup
    await data._lifecycle_lock.acquire()
    starting = asyncio.create_task(start(data, ["NEW"]))
    await asyncio.sleep(0)
    stopping = asyncio.create_task(data.stop())
    await asyncio.sleep(0)
    data._lifecycle_lock.release()
    await asyncio.gather(starting, stopping)
    assert_empty(data)
    assert data._stream is None


@pytest.mark.asyncio
async def test_cancelled_start_invalidates_callbacks_and_cleans_transport(setup, monkeypatch):
    data, _, _ = setup
    entered = asyncio.Event()
    stream = Transport()

    async def connect():
        entered.set()
        await asyncio.Event().wait()

    stream.connect.side_effect = connect
    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream",
                        lambda **_kwargs: stream)
    starting = asyncio.create_task(start(data, ["OLD"]))
    await entered.wait()
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    stream.disconnect.assert_awaited_once()
    assert data._stream is None
    await stream.on_bar("OLD", bar())
    assert_empty(data)


@pytest.mark.asyncio
async def test_stop_during_connect_cannot_resume_subscription_or_running_state(setup, monkeypatch):
    data, _, _ = setup
    entered, release = asyncio.Event(), asyncio.Event()
    stream = Transport()

    async def connect():
        entered.set()
        await release.wait()
        return True

    stream.connect.side_effect = connect
    monkeypatch.setattr("backend.organism.streaming_data_provider.AlpacaMarketDataStream",
                        lambda **_kwargs: stream)
    starting = asyncio.create_task(start(data, ["OLD"]))
    await entered.wait()
    stopping = asyncio.create_task(data.stop())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(starting, stopping)
    stream.subscribe_bars.assert_not_awaited()
    stream.subscribe_quotes.assert_not_awaited()
    stream.disconnect.assert_awaited_once()
    assert_empty(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("offline reconnect failure")])
async def test_failed_reconnect_keeps_stale_evidence_and_revokes_callbacks(setup, failure):
    data, streams, clock = setup
    await start(data, ["KEEP"])
    stream = streams[0]
    await stream.on_bar("KEEP", bar())
    clock[0] += 301
    if isinstance(failure, Exception):
        stream.connect.side_effect = failure
    else:
        stream.connect.return_value = failure
    assert await data.check_and_recover_stale_stream() is True
    await stream.on_bar("KEEP", bar(clock[0] - 1))
    await stream.on_quote("KEEP", {"bid": 1})
    assert data.get_bar_age("KEEP") == 301
    assert data.bar_count("KEEP") == 1
    assert not data.get_latest_quote("KEEP")
    stream.connect.side_effect = None
    stream.connect.return_value = True
    assert await data.check_and_recover_stale_stream() is True
    assert data.get_bar_age("KEEP") == 301
    await stream.on_bar("KEEP", bar(clock[0] - 1))
    assert data.get_bar_age("KEEP") == 0
