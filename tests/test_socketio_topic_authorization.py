"""Exercise the wired Socket.IO handlers with synthetic sessions and no sockets."""
from contextlib import asynccontextmanager
import time
from unittest.mock import AsyncMock

import pytest

from backend.api import socketio_server as server


class Sessions:
    def __init__(self):
        self.values = {}
        self.rooms = []
        self.emits = []

    @asynccontextmanager
    async def session(self, sid):
        yield self.values.setdefault(sid, {})

    async def disconnect(self, sid):
        self.values.pop(sid, None)

    async def enter_room(self, sid, room):
        self.rooms.append((sid, room))

    async def emit(self, event, data, **kwargs):
        self.emits.append((event, data, kwargs))


@pytest.fixture
def sockets(monkeypatch):
    fake = Sessions()
    monkeypatch.setattr(server, 'sio', fake)
    monkeypatch.setattr(server, 'client_subscriptions', {})
    monkeypatch.setattr(server, 'topic_subscribers', {})
    monkeypatch.setattr(server, 'decode_token', lambda token: {'sub': token, 'roles': ['viewer'], 'jti': token + '-id', 'exp': time.time() + 60})
    monkeypatch.setattr(server, 'is_token_blacklisted', AsyncMock(return_value=False))
    return fake


@pytest.mark.asyncio
async def test_other_users_private_room_and_mixed_batch_never_join(sockets):
    assert await server.connect('a', {}, {'token': 'alice'}) is True
    assert await server.connect('b', {}, {'token': 'bob'}) is True
    initial = list(sockets.rooms)
    for data in ({'topic': 'user_bob'}, {'topics': ['organism', 'user_bob']}):
        await server.subscribe('a', data)
    assert sockets.rooms == initial
    assert server.client_subscriptions['a'] == {'user_alice'}
    assert server.topic_subscribers['user_bob'] == {'b'}
    sockets.emits.clear()
    await server.broadcast_portfolio_update('bob', {'synthetic': 'private'})
    assert [v[2]['to'] for v in sockets.emits if v[0] == 'portfolio_update'] == ['b']
    await server.broadcast_order_update('bob', {'synthetic': 'order'})
    assert sockets.emits[-1][2]['to'] == 'b'
    assert all(item[2].get('to') != 'a' for item in sockets.emits)


@pytest.mark.asyncio
async def test_own_private_and_all_supported_dashboard_topics_work(sockets):
    assert await server.connect('a', {}, {'token': 'alice'}) is True
    topics = sorted(server.DASHBOARD_TOPICS) + ['user_alice']
    await server.subscribe('a', {'topics': topics})
    assert server.client_subscriptions['a'] == set(topics)
    assert sockets.emits[-1][0] == 'subscribed'
    assert sockets.emits[-1][1]['topics'] == topics


@pytest.mark.asyncio
@pytest.mark.parametrize('data', [None, [], {}, {'topic': 'unknown'}, {'topic': ''},
    {'topic': ['organism']}, {'topics': 'organism'}, {'topics': []},
    {'topics': ['organism', 12]}, {'topic': 'organism', 'topics': ['risk']},
    {'topics': ['organism'] * 11}])
async def test_invalid_batches_fail_before_mutation(sockets, data):
    await server.connect('a', {}, {'token': 'alice'})
    initial = list(sockets.rooms)
    await server.subscribe('a', data)
    assert sockets.rooms == initial
    assert server.client_subscriptions['a'] == {'user_alice'}
    assert sockets.emits[-1][0] == 'error'


@pytest.mark.asyncio
async def test_unauthenticated_or_monitor_session_cannot_subscribe(sockets):
    await server.subscribe('missing', {'topic': 'organism'})
    sockets.values['monitor'] = {'authenticated': True, 'roles': ['paper_monitor'], 'user_id': 'monitor'}
    server.client_subscriptions['monitor'] = set()
    await server.subscribe('monitor', {'topic': 'organism'})
    assert sockets.rooms == []


@pytest.mark.asyncio
@pytest.mark.parametrize('claims', [{'sub': 'monitor', 'roles': ['paper_monitor']},
    {'sub': None, 'roles': ['viewer']}, {'sub': 'alice', 'roles': 'admin'}])
async def test_connection_requires_valid_principal_and_preserves_monitor_denial(sockets, monkeypatch, claims):
    monkeypatch.setattr(server, 'decode_token', lambda _: claims)
    assert await server.connect('x', {}, {'token': 'synthetic'}) is False
    assert 'x' not in server.client_subscriptions and sockets.rooms == []

@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['expired', 'revoked', 'lookup_failed'])
async def test_existing_session_is_rechecked_before_personal_delivery(sockets, monkeypatch, failure):
    await server.connect('a', {}, {'token': 'alice'})
    sockets.emits.clear()
    if failure == 'expired':
        sockets.values['a']['expires_at'] = time.time() - 1
    else:
        monkeypatch.setattr(server, 'is_token_blacklisted', AsyncMock(
            side_effect=RuntimeError('synthetic') if failure == 'lookup_failed' else None,
            return_value=failure == 'revoked'))
    await server.broadcast_portfolio_update('alice', {'private': True})
    await server.broadcast_order_update('alice', {'private': True})
    assert sockets.emits == []
    assert 'a' not in server.client_subscriptions


@pytest.mark.asyncio
async def test_revoked_connection_and_private_public_channel_emission_denied(sockets, monkeypatch):
    monkeypatch.setattr(server, 'is_token_blacklisted', AsyncMock(return_value=True))
    assert await server.connect('revoked', {}, {'token': 'alice'}) is False
    monkeypatch.setattr(server, 'is_token_blacklisted', AsyncMock(return_value=False))
    await server.connect('a', {}, {'token': 'alice'})
    await server.subscribe('a', {'topics': ['orders', 'positions', 'portfolio']})
    sockets.emits.clear()
    for event, topic in [('order_update', 'orders'), ('position_update', 'positions'), ('portfolio_update', 'portfolio')]:
        await server.broadcast_to_topic(topic, event, {'private': True})
        await server.broadcast_to_all(event, {'private': True})
    assert sockets.emits == []
