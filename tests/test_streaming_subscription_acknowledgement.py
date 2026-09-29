"""Real stream/provider contracts; only websocket I/O is synthetic."""
import asyncio
import json
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
from backend.organism.streaming_data_provider import StreamingDataProvider


class Socket:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.respond = True
        self.reject = set()
        self.channels = {k: set() for k in ('bars', 'quotes', 'trades')}
        self.queue.put_nowait(json.dumps([{'T': 'success', 'msg': 'connected'}]))

    async def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        if msg['action'] == 'auth':
            await self.push({'T': 'success', 'msg': 'authenticated'})
        elif self.respond:
            for channel, current in self.channels.items():
                if channel in msg:
                    names = set(msg[channel]) - self.reject
                    if msg['action'] == 'subscribe':
                        current.update(names)
                    else:
                        current.difference_update(names)
            await self.push({'T': 'subscription', **{k: sorted(v) for k, v in self.channels.items()}})

    async def push(self, message):
        await self.queue.put(json.dumps([message]))

    async def recv(self):
        return await self.queue.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.closed = True
        await self.queue.put(None)


@pytest.fixture
async def stream(monkeypatch):
    socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=socket))
    value = AlpacaMarketDataStream('offline-key', 'offline-secret')
    value.SUBSCRIPTION_ACK_TIMEOUT_S = .03
    value.SUBSCRIPTION_RETRY_INTERVAL_S = .06
    assert await value.connect()
    try:
        yield value, socket
    finally:
        await value.disconnect()


@pytest.mark.asyncio
async def test_send_success_without_server_ack_is_incomplete_and_retries(stream):
    value, socket = stream
    socket.respond = False
    assert await value.subscribe_bars(['NEW']) is False
    assert 'NEW' not in value.bar_subscriptions.get('1Min', set())
    count = len(socket.sent)
    assert await value.subscribe_bars(['NEW']) is False
    assert len(socket.sent) == count  # bounded cadence, not a busy loop
    await asyncio.sleep(.065)
    socket.respond = True
    assert await value.subscribe_bars(['NEW']) is True
    assert value.bar_subscriptions['1Min'] == {'NEW'}


@pytest.mark.asyncio
async def test_partial_subscription_does_not_launder_missing_symbol(stream):
    value, socket = stream
    socket.reject = {'NEW'}
    assert await value.subscribe_bars(['SPY', 'NEW']) is False
    assert value.bar_subscriptions['1Min'] == {'SPY'}
    await asyncio.sleep(.065)
    socket.reject.clear()
    assert await value.subscribe_bars(['SPY', 'NEW']) is True


@pytest.mark.asyncio
async def test_channel_omission_is_not_empty_or_ack_for_another_channel(stream):
    value, socket = stream
    assert await value.subscribe_quotes(['SPY'])
    socket.respond = False
    task = asyncio.create_task(value.subscribe_bars(['SPY']))
    await asyncio.sleep(0)
    await socket.push({'T': 'subscription', 'trades': []})
    assert await task is False
    assert value.quote_subscriptions == {'SPY'}
    await socket.push({'T': 'subscription', 'quotes': []})
    await asyncio.sleep(.005)
    assert value.quote_subscriptions == set()


@pytest.mark.asyncio
async def test_unsubscribe_waits_for_explicit_all_channel_confirmation(stream):
    value, socket = stream
    assert await value.subscribe_bars(['OLD'])
    assert await value.subscribe_quotes(['OLD'])
    socket.respond = False
    task = asyncio.create_task(value.unsubscribe(['OLD']))
    await asyncio.sleep(0)
    await socket.push({'T': 'subscription', 'quotes': [], 'trades': []})
    assert await task is False
    assert value.bar_subscriptions['1Min'] == {'OLD'}
    await asyncio.sleep(.065)
    socket.respond = True
    assert await value.unsubscribe(['OLD']) is True
    assert not value.bar_subscriptions['1Min']


@pytest.mark.asyncio
async def test_clean_close_clears_state_and_reconnects_once(stream, monkeypatch):
    value, socket = stream
    reconnect = AsyncMock()
    monkeypatch.setattr(value, '_reconnect', reconnect)
    await socket.close()
    await asyncio.sleep(.005)
    assert not value.is_connected and not value.is_authenticated
    reconnect.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect", "bars", "quotes"])
async def test_provider_failed_start_retries_without_rest_freshness(monkeypatch, failure):
    sockets = [Socket(), Socket()]
    if failure == "bars":
        sockets[0].reject = {'SPY'}
    elif failure == "quotes":
        original_send = sockets[0].send
        async def reject_quotes(raw):
            sockets[0].reject = {'SPY'} if 'quotes' in json.loads(raw) else set()
            await original_send(raw)
        sockets[0].send = reject_quotes
    make_socket = AsyncMock(side_effect=[OSError('offline connect refusal'), sockets[1]] if failure == 'connect' else sockets)
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', make_socket)
    monkeypatch.setattr(AlpacaMarketDataStream, 'SUBSCRIPTION_ACK_TIMEOUT_S', .02, raising=False)
    now = pd.Timestamp('2026-09-27T15:00:00Z').timestamp()
    provider = StreamingDataProvider(time_fn=lambda: now)
    try:
        assert await provider.start(['SPY'], 'offline', 'offline') is False
        assert not provider.is_running
        provider._recovery_due_at = 0
        assert await provider.update_subscriptions(['SPY']) is True
        assert provider.is_running
        assert provider.get_bar_age('SPY') == float('inf')
        await sockets[1].push({'T': 'b', 'S': 'SPY', 't': '2026-09-27T14:59:00Z', 'o': 100, 'h': 101, 'l': 99, 'c': 100, 'v': 1000})
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') == 0
    finally:
        await provider.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('reply', [
    {'T': 'error', 'code': 405, 'msg': 'symbol limit exceeded'},
    {'T': 'subscription', 'bars': None},
    {'T': 'subscription', 'bars': [123]},
])
async def test_server_error_or_malformed_channel_never_confirms(stream, reply):
    value, socket = stream
    socket.respond = False
    pending = asyncio.create_task(value.subscribe_bars(['NEW']))
    await asyncio.sleep(0)
    await socket.push(reply)
    assert await pending is False
    assert value.bar_subscriptions['1Min'] == set()
    if reply.get('code') == 405:
        # Audit 2026-09-29 (MDP-04a): a provider symbol-cap refusal is a
        # refusal. The name is dropped from the desired set so it is neither
        # retried forever nor replayed (and refused wholesale) on reconnect.
        assert value._desired['bars'] == set()
        assert value.symbol_limit_exceeded and value.last_error_code == 405
        assert value.get_stats()['symbol_limit_exceeded'] is True
    else:
        # Malformed snapshots are not refusals: keep retrying the request.
        assert value._desired['bars'] == {'NEW'}
        assert not value.symbol_limit_exceeded


class CappedSocket(Socket):
    """Synthetic provider that enforces a per-channel symbol cap like Alpaca IEX."""

    def __init__(self, cap):
        super().__init__()
        self.cap = cap

    async def send(self, raw):
        msg = json.loads(raw)
        if msg['action'] == 'subscribe':
            for channel, current in self.channels.items():
                if channel in msg and len(current | set(msg[channel])) > self.cap:
                    self.sent.append(msg)
                    await self.push({'T': 'error', 'code': 405, 'msg': 'symbol limit exceeded'})
                    return
        await super().send(raw)


@pytest.mark.asyncio
async def test_cap_refusal_is_not_replayed_on_reconnect(monkeypatch):
    socket = CappedSocket(cap=3)
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect',
                        AsyncMock(return_value=socket))
    value = AlpacaMarketDataStream('offline-key', 'offline-secret')
    value.SUBSCRIPTION_ACK_TIMEOUT_S = .05
    value.SUBSCRIPTION_RETRY_INTERVAL_S = 0.0
    assert await value.connect()
    try:
        assert await value.subscribe_quotes(['SPY', 'QQQ']) is True
        assert await value.subscribe_quotes(['A1', 'A2']) is False  # 4 > cap 3
        assert value.quote_subscriptions == {'SPY', 'QQQ'}
        assert value._desired['quotes'] == {'SPY', 'QQQ'}
        # A reconnect replays only what is still desired, so the confirmed
        # core survives instead of the whole replay being refused.
        socket2 = CappedSocket(cap=3)
        monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect',
                            AsyncMock(return_value=socket2))
        await value._cleanup_connection()
        assert await value.connect()
        assert value.quote_subscriptions == {'SPY', 'QQQ'}
    finally:
        await value.disconnect()


@pytest.mark.asyncio
async def test_obsolete_generation_cannot_acknowledge_or_deliver_bar(stream):
    value, socket = stream
    generation = value.connection_generation
    callback = AsyncMock()
    value.on_bar = callback
    await value._cleanup_connection()
    await value._handle_message(json.dumps([{'T': 'subscription', 'bars': ['OLD']},
                                            {'T': 'b', 'S': 'OLD'}]), generation=generation)
    assert not value.bar_subscriptions
    callback.assert_not_awaited()
    assert not value.is_connected and not value.is_authenticated


@pytest.mark.asyncio
async def test_cancelled_ack_wait_keeps_desired_and_can_retry(stream):
    value, socket = stream
    socket.respond = False
    pending = asyncio.create_task(value.subscribe_bars(['NEW']))
    await asyncio.sleep(.005)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert value._desired['bars'] == {'NEW'}
    assert not value.bar_subscriptions['1Min']
    await asyncio.sleep(.065)
    socket.respond = True
    assert await value.subscribe_bars(['NEW'])


@pytest.mark.asyncio
async def test_reconnect_reader_precedes_ack_and_has_one_current_listener(stream, monkeypatch):
    value, socket = stream
    assert await value.subscribe_bars(['SPY'])
    assert await value.subscribe_quotes(['SPY'])
    next_socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=next_socket))
    value.current_backoff = .001
    await socket.close()
    for _ in range(100):
        if value.connection_count == 2 and value.quote_subscriptions == {'SPY'}:
            break
        await asyncio.sleep(.002)
    assert value.connection_count == 2
    assert value.bar_subscriptions['1Min'] == {'SPY'}
    assert value.quote_subscriptions == {'SPY'}
    assert len([t for t in value.background_tasks if not t.done()]) == 2
    value._start_background_tasks()
    assert len([t for t in value.background_tasks if not t.done()]) == 2


@pytest.mark.asyncio
async def test_stop_during_backoff_never_reconnects(stream, monkeypatch):
    value, socket = stream
    connect = AsyncMock()
    monkeypatch.setattr(value, 'connect', connect)
    value.current_backoff = .05
    await socket.close()
    await asyncio.sleep(.005)
    await value.disconnect()
    await asyncio.sleep(.065)
    connect.assert_not_awaited()
    assert not value.should_reconnect and not value.is_authenticated
    assert not [t for t in value.background_tasks if not t.done()]


@pytest.mark.asyncio
async def test_late_authentication_after_disconnect_cannot_resurrect(monkeypatch):
    socket = Socket()
    auth_sent = asyncio.Event()
    async def auth_send(raw):
        auth_sent.set()
    socket.send = auth_send
    socket.close = AsyncMock()  # Keep the pending receive alive to deliver an actual late ACK.
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=socket))
    value = AlpacaMarketDataStream('offline', 'offline')
    pending = asyncio.create_task(value.connect())
    await auth_sent.wait()
    await value.disconnect()
    # A late receive already waiting on the old socket must not restore auth.
    await socket.push({'T': 'success', 'msg': 'authenticated'})
    assert await pending is False
    assert not value.is_connected and not value.is_authenticated
    assert not [t for t in value.background_tasks if not t.done()]


@pytest.mark.asyncio
async def test_real_scheduler_retains_failed_provider_and_recovers(monkeypatch, tmp_path):
    from backend.organism.scheduler import OrganismScheduler
    from backend.organism.live_engine import OrganismLiveEngine
    sockets = [Socket(), Socket()]
    sockets[0].reject = {'SPY'}
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(side_effect=sockets))
    monkeypatch.setattr(AlpacaMarketDataStream, 'SUBSCRIPTION_ACK_TIMEOUT_S', .02)
    # Only engine persistence/background work is isolated; scheduler/provider/transport are real.
    monkeypatch.setattr(OrganismLiveEngine, 'initialize', AsyncMock(return_value=False))
    monkeypatch.setattr(OrganismLiveEngine, 'shutdown', AsyncMock())
    async def idle(scheduler):
        await scheduler._stop.wait()
    monkeypatch.setattr(OrganismScheduler, '_run_loop', idle)
    scheduler = OrganismScheduler(data_client=None, order_service=None, positions_service=None,
                                   brain_dir=str(tmp_path), universe=['SPY'], use_streaming=True,
                                   alpaca_api_key='offline', alpaca_api_secret='offline')
    try:
        await scheduler.start()
        provider = scheduler._streaming_provider
        assert provider is not None and not provider.is_running
        assert scheduler._engine._streaming_provider is provider
        provider._recovery_due_at = 0
        assert await provider.update_subscriptions(['SPY'])
        assert provider.is_running and provider.get_bar_age('SPY') == float('inf')
        now = pd.Timestamp.now(tz='UTC').floor('min').isoformat()
        await sockets[1].push({'T': 'b', 'S': 'SPY', 't': now, 'o': 1, 'h': 2, 'l': 1, 'c': 2, 'v': 1})
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') < 1
    finally:
        await scheduler.stop()
    assert provider._stream is None and not provider._recovery_enabled
    assert await provider.update_subscriptions(['SPY']) is False


@pytest.mark.asyncio
async def test_reconnect_revokes_old_receipt_until_actual_current_session_bar(monkeypatch):
    sockets = [Socket(), Socket()]
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(side_effect=sockets))
    now = pd.Timestamp('2026-09-27T15:00:00Z').timestamp()
    provider = StreamingDataProvider(time_fn=lambda: now)
    data = {'T': 'b', 'S': 'SPY', 't': '2026-09-27T14:59:00Z', 'o': 1, 'h': 2, 'l': 1, 'c': 2, 'v': 1}
    try:
        assert await provider.start(['SPY'], 'offline', 'offline')
        await sockets[0].push(data)
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') == 0
        stream = provider._stream
        stream.current_backoff = .001
        await sockets[0].close()
        for _ in range(100):
            if stream.connection_count == 2 and stream.quote_subscriptions == {'SPY'}:
                break
            await asyncio.sleep(.002)
        assert stream.connection_count == 2
        assert provider.get_bar_age('SPY') == float('inf')
        assert await provider.update_subscriptions(['SPY'])
        assert provider.get_bar_age('SPY') == float('inf')
        # A duplicate old bar cannot renew provenance after reconnect.
        await sockets[1].push(data)
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') == float('inf')
        await sockets[1].push({**data, 't': '2026-09-27T15:00:00Z'})
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') == 0
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_fresh_spy_does_not_hide_refused_new_symbol_in_status(monkeypatch):
    socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=socket))
    now = pd.Timestamp('2026-09-27T15:00:00Z').timestamp()
    provider = StreamingDataProvider(time_fn=lambda: now)
    try:
        assert await provider.start(['SPY'], 'offline', 'offline')
        await socket.push({'T': 'b', 'S': 'SPY', 't': '2026-09-27T14:59:00Z', 'o': 1, 'h': 2, 'l': 1, 'c': 2, 'v': 1})
        await asyncio.sleep(.005)
        socket.reject = {'NEW'}
        assert await provider.update_subscriptions(['SPY', 'NEW']) is False
        stats = provider.get_stats()
        assert stats['running'] is True
        assert stats['subscriptions_complete'] is False
        assert stats['max_staleness_s'] is None  # Unknown, not a healthy zero.
        assert stats['unseen_or_unconfirmed_symbols'] == ['NEW']
        assert stats['stream_stats']['subscriptions_confirmed'] is False
        assert provider.stale_symbols(120) == [('NEW', float('inf'))]
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_startup_whole_deadline_cleans_socket_and_retains_retry(monkeypatch):
    socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=socket))
    provider = StreamingDataProvider()
    provider.STARTUP_TIMEOUT_S = .02
    client = type('Client', (), {})()
    async def stuck_history(*args, **kwargs):
        await asyncio.Event().wait()
    client.get_historical_bars_df = stuck_history
    with pytest.raises(TimeoutError):
        await provider.start(['SPY'], 'offline', 'offline', data_client=client)
    assert socket.closed and provider._stream is None
    assert provider._recovery_enabled and provider._desired_symbols == {'SPY'}
    assert await provider.update_subscriptions(['SPY']) is False
    await provider.stop()


@pytest.mark.asyncio
async def test_provider_preserves_old_buffers_until_all_unsubscribe_channels_confirm(monkeypatch):
    socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect', AsyncMock(return_value=socket))
    now = pd.Timestamp('2026-09-27T15:00:00Z').timestamp()
    provider = StreamingDataProvider(time_fn=lambda: now)
    try:
        assert await provider.start(['SPY', 'OLD'], 'offline', 'offline')
        for symbol in ['SPY', 'OLD']:
            await socket.push({'T': 'b', 'S': symbol, 't': '2026-09-27T14:59:00Z', 'o': 1, 'h': 2, 'l': 1, 'c': 2, 'v': 1})
        await asyncio.sleep(.005)
        stream = provider._stream
        stream.SUBSCRIPTION_ACK_TIMEOUT_S = .02
        stream.SUBSCRIPTION_RETRY_INTERVAL_S = .04
        socket.respond = False
        pending = asyncio.create_task(provider.update_subscriptions(['SPY']))
        await asyncio.sleep(.002)
        await socket.push({'T': 'subscription', 'quotes': ['SPY'], 'trades': []})
        assert await pending is False
        assert 'OLD' in provider._subscribed_symbols
        assert provider.bar_count('OLD') == 1
        assert provider.get_stats()['subscriptions_complete'] is False
        await asyncio.sleep(.045)
        socket.respond = True
        assert await provider.update_subscriptions(['SPY']) is True
        assert 'OLD' not in provider._subscribed_symbols
        assert provider.bar_count('OLD') == 0
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_failed_start_retry_does_not_repeat_slow_prefill_inside_sync_deadline(monkeypatch):
    from backend.organism.live_engine_data import _DataFeederMixin

    socket = Socket()
    monkeypatch.setattr('backend.integrations.alpaca_market_data_stream.websockets.connect',
                        AsyncMock(side_effect=[OSError('initial offline refusal'), socket]))
    now = pd.Timestamp('2026-09-27T15:00:00Z')
    historical = pd.DataFrame({
        'timestamp': pd.date_range(end=now, periods=100, freq='min'),
        'open': 100., 'high': 101., 'low': 99., 'close': 100., 'volume': 1000.,
    })
    async def slow_history(*args, **kwargs):
        await asyncio.sleep(.1)
        return historical.copy()
    client = type('Client', (), {})()
    client.get_historical_bars_df = AsyncMock(side_effect=slow_history)
    provider = StreamingDataProvider(time_fn=lambda: now.timestamp())
    try:
        assert await provider.start(['SPY'], 'offline', 'offline', data_client=client) is False
        provider._recovery_due_at = 0
        # Scale only the caller deadline; the defect is repeated historical
        # warmup on a healthy reconnect, not a changed production gate/bound.
        assert await asyncio.wait_for(provider.update_subscriptions(['SPY']), timeout=.04)
        client.get_historical_bars_df.assert_not_awaited()
        assert provider._start_config['data_client'] is client
        assert provider.get_bar_age('SPY') == float('inf')
        await socket.push({'T': 'b', 'S': 'SPY', 't': now.isoformat(), 'o': 100, 'h': 101, 'l': 99, 'c': 100, 'v': 1})
        await asyncio.sleep(.005)
        assert provider.get_bar_age('SPY') == 0
        # Ordinary data fetching still supplies full feature/held-exit history
        # when the newly confirmed live buffer has fewer than MIN_BARS.
        feeder = _DataFeederMixin()
        feeder._streaming_provider = provider
        feeder._data_client = client
        result = await feeder._fetch_bars('SPY')
        pd.testing.assert_frame_equal(result, historical)
        client.get_historical_bars_df.assert_awaited_once()
        assert feeder._last_bar_fetch_sources['SPY'] == 'rest'
    finally:
        await provider.stop()
