"""
Socket.IO Server for real-time client communication.

Handles WebSocket connections from frontend clients with:
- JWT authentication
- Topic-based subscriptions
- Real-time data broadcasting
- Automatic reconnection support
"""

from datetime import UTC, datetime
import logging
import math
import time
import os
from typing import Any

from fastapi import FastAPI, HTTPException
import socketio

from backend.infra.security import decode_token, is_token_blacklisted

logger = logging.getLogger(__name__)

# Build CORS origins from environment or use defaults
_cors_env = os.environ.get("SOCKETIO_CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    'http://localhost:5173',
    'http://localhost:5174',
    'http://localhost:3000',
    'http://localhost:3001',
]

# Create Socket.IO async server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=_cors_origins,
    logger=True,
    engineio_logger=True,  # Enable Engine.IO logging for debugging
    ping_interval=25,  # Send ping every 25 seconds
    ping_timeout=20,   # Wait 20 seconds for pong before disconnecting
)

# Track client subscriptions
client_subscriptions: dict[str, set[str]] = {}  # {sid: {topic1, topic2, ...}}
topic_subscribers: dict[str, set[str]] = {}      # {topic: {sid1, sid2, ...}}

# Public dashboard channels; personal events use only the authenticated user's
# server-derived room. Never accept arbitrary Socket.IO room names from clients.
DASHBOARD_TOPICS = frozenset({
    'orders', 'positions', 'portfolio', 'market_data', 'signals',
    'strategies', 'alerts', 'risk', 'organism',
})


def _subscription_topics(data: dict, user_id: str) -> list[str]:
    if not isinstance(data, dict) or not isinstance(user_id, str) or not user_id:
        raise ValueError('Invalid subscription')
    if ('topic' in data) == ('topics' in data):
        raise ValueError('Invalid subscription')
    topics = [data['topic']] if 'topic' in data else data['topics']
    if (not isinstance(topics, list) or not 1 <= len(topics) <= len(DASHBOARD_TOPICS) + 1
            or any(not isinstance(topic, str) or
                   (topic not in DASHBOARD_TOPICS and topic != f'user_{user_id}')
                   for topic in topics)):
        raise ValueError('Unauthorized subscription')
    return list(dict.fromkeys(topics))


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None):
    """
    Handle client connection with JWT authentication.

    Args:
        sid: Socket.IO session ID
        environ: ASGI environment
        auth: Authentication data (should contain 'token')

    Returns:
        True to accept connection, False to reject
    """
    try:
        # Extract token from auth dict
        if not auth or 'token' not in auth:
            logger.warning(f"Connection rejected for {sid}: No token provided")
            return False

        token = auth['token']

        # Verify JWT token
        try:
            claims = decode_token(token)
            user_id = claims.get('sub')
            roles = claims.get('roles', [])
            if (not isinstance(user_id, str) or not user_id
                    or not isinstance(roles, list) or any(not isinstance(role, str) for role in roles)
                    or "paper_monitor" in roles):
                return False  # Scoped monitoring tokens cannot open Socket.IO sessions.

            expiry, token_id = claims.get('exp'), claims.get('jti')
            if (type(expiry) not in (int, float) or not math.isfinite(expiry)
                    or expiry <= time.time() or not isinstance(token_id, str) or not token_id
                    or await is_token_blacklisted(token_id)):
                return False
            logger.info("Socket.IO principal verified")
            logger.info(f"Client connected: {sid} (user: {user_id}, roles: {roles})")

            # Store user info in session
            async with sio.session(sid) as session:
                session['user_id'] = user_id
                session['roles'] = roles
                session['authenticated'] = True
                session['expires_at'] = expiry
                session['token_id'] = token_id

            # Initialize subscription tracking
            client_subscriptions[sid] = set()

            # Auto-subscribe to user-specific topic for personal updates
            user_topic = f"user_{user_id}"
            client_subscriptions[sid].add(user_topic)
            if user_topic not in topic_subscribers:
                topic_subscribers[user_topic] = set()
            topic_subscribers[user_topic].add(sid)

            # Join Socket.IO room for O(1) broadcasting
            await sio.enter_room(sid, user_topic)

            logger.info(f"[SUCCESS] Auto-subscribed {sid} to personal topic: '{user_topic}' (room joined)")

            # Send welcome message
            await sio.emit('connected', {
                'message': 'Connected to trading platform',
                'user_id': user_id,
                'timestamp': None  # Will be added by client
            }, to=sid)

            return True

        except HTTPException as e:
            # Extract specific error details from HTTPException
            detail = getattr(e, 'detail', 'unknown')
            logger.error(f"Token verification failed for {sid}: {e.status_code} - {detail}")
            return False
        except Exception as e:
            logger.error(f"Token verification failed for {sid}: {type(e).__name__}: {e}")
            return False

    except Exception as e:
        logger.error(f"Connection error for {sid}: {e}")
        return False


@sio.event
async def disconnect(sid: str):
    """
    Handle client disconnection and cleanup subscriptions.

    Args:
        sid: Socket.IO session ID
    """
    try:
        # Get user info before cleanup
        async with sio.session(sid) as session:
            user_id = session.get('user_id', 'unknown')

        logger.info(f"Client disconnected: {sid} (user: {user_id})")

        # Clean up subscriptions
        if sid in client_subscriptions:
            topics = client_subscriptions[sid]
            for topic in topics:
                if topic in topic_subscribers:
                    topic_subscribers[topic].discard(sid)
                    if not topic_subscribers[topic]:
                        del topic_subscribers[topic]
            del client_subscriptions[sid]

    except Exception as e:
        logger.error(f"Disconnect cleanup error for {sid}: {e}")


async def _session_authorized(sid: str, user_id: str | None = None) -> bool:
    """Recheck bounded session claims before delivering data, including revocation."""
    try:
        async with sio.session(sid) as session:
            expiry = session.get('expires_at')
            token_id = session.get('token_id')
            principal = session.get('user_id')
            valid = (session.get('authenticated') is True and sid in client_subscriptions
                     and isinstance(principal, str) and bool(principal)
                     and (user_id is None or principal == user_id)
                     and 'paper_monitor' not in session.get('roles', [])
                     and type(expiry) in (int, float) and math.isfinite(expiry)
                     and expiry > time.time() and isinstance(token_id, str) and bool(token_id))
        if valid and not await is_token_blacklisted(token_id):
            return True
    except Exception:
        pass  # Failure to verify a session never authorizes delivery.
    await disconnect(sid)
    await sio.disconnect(sid)
    return False


@sio.event
async def subscribe(sid: str, data: dict):
    """
    Subscribe client to a topic.

    Args:
        sid: Socket.IO session ID
        data: {'topic': 'portfolio'} or {'topics': ['orders', 'positions']}
    """
    try:
        # Check authentication, expiry and revocation before room changes.
        if not await _session_authorized(sid):
            return
        async with sio.session(sid) as session:
            if (session.get('authenticated') is not True
                    or 'paper_monitor' in session.get('roles', [])
                    or sid not in client_subscriptions):
                await sio.emit('error', {'message': 'Not authenticated'}, to=sid)
                return

            user_id = session.get('user_id')

        # Validate the whole batch before entering any room or mutating tracking.
        topics = _subscription_topics(data, user_id)

        for topic in topics:
            # Add to tracking
            client_subscriptions[sid].add(topic)
            if topic not in topic_subscribers:
                topic_subscribers[topic] = set()
            topic_subscribers[topic].add(sid)

            # Join Socket.IO room for O(1) broadcasting
            await sio.enter_room(sid, topic)

            logger.debug(f"Client {sid} (user: {user_id}) subscribed to: {topic} (room joined)")

        # Send acknowledgement
        await sio.emit('subscribed', {
            'topics': topics,
            'message': f'Subscribed to {len(topics)} topic(s)'
        }, to=sid)

    except Exception:
        logger.warning("Socket.IO subscription refused")
        await sio.emit('error', {'message': 'Subscription failed'}, to=sid)


@sio.event
async def unsubscribe(sid: str, data: dict):
    """
    Unsubscribe client from a topic.

    Args:
        sid: Socket.IO session ID
        data: {'topic': 'portfolio'} or {'topics': ['orders', 'positions']}
    """
    try:
        # Handle single topic or multiple topics
        topics = []
        if 'topic' in data:
            topics = [data['topic']]
        elif 'topics' in data:
            topics = data['topics']

        for topic in topics:
            # Remove from tracking
            if sid in client_subscriptions:
                client_subscriptions[sid].discard(topic)
            if topic in topic_subscribers:
                topic_subscribers[topic].discard(sid)
                if not topic_subscribers[topic]:
                    del topic_subscribers[topic]

            # Leave Socket.IO room
            await sio.leave_room(sid, topic)

            logger.debug(f"Client {sid} unsubscribed from: {topic} (room left)")

        # Send acknowledgement
        await sio.emit('unsubscribed', {
            'topics': topics,
            'message': f'Unsubscribed from {len(topics)} topic(s)'
        }, to=sid)

    except Exception as e:
        logger.error(f"Unsubscribe error for {sid}: {e}")


@sio.event
async def heartbeat(sid: str, data: dict | None = None):
    """
    Handle heartbeat/ping from client.

    Args:
        sid: Socket.IO session ID
        data: Optional heartbeat data
    """
    try:
        if not await _session_authorized(sid):
            return
        await sio.emit('heartbeat_ack', {'timestamp': data.get('timestamp') if data else None}, to=sid)
    except Exception as e:
        logger.error(f"Heartbeat error for {sid}: {e}")


# Broadcasting functions for backend services to use

async def broadcast_to_topic(topic: str, event: str, data: Any):
    """
    Broadcast message to all clients subscribed to a topic using Socket.IO rooms.

    Each subscribed session is revalidated before delivery.

    Args:
        topic: Topic name (e.g., 'portfolio', 'orders')
        event: Event name (e.g., 'portfolio_update', 'order_filled')
        data: Data to broadcast
    """
    try:
        private_events = {'portfolio_update', 'position_update', 'order_update', 'order_filled'}
        if event in private_events and not topic.startswith('user_'):
            logger.warning("Private Socket.IO event refused on public channel")
            return
        expected_user = topic[5:] if topic.startswith('user_') else None
        for sid in tuple(topic_subscribers.get(topic, ())):
            if await _session_authorized(sid, expected_user):
                await sio.emit(event, data, to=sid)
    except Exception:
        logger.warning("Socket.IO topic delivery unavailable")


async def broadcast_to_user(user_id: str, event: str, data: Any):
    """
    Broadcast message to a specific user (all their sessions).

    Args:
        user_id: User identifier
        event: Event name
        data: Data to broadcast
    """
    for sid in tuple(topic_subscribers.get(f'user_{user_id}', ())):
        try:
            if await _session_authorized(sid, user_id):
                await sio.emit(event, data, to=sid)
        except Exception:
            logger.warning("Socket.IO private delivery unavailable")


async def broadcast_to_all(event: str, data: Any):
    """
    Broadcast message to all connected clients.

    Args:
        event: Event name
        data: Data to broadcast
    """
    if event in {'portfolio_update', 'position_update', 'order_update', 'order_filled'}:
        logger.warning("Private Socket.IO broadcast refused")
        return
    for sid in tuple(client_subscriptions):
        try:
            if await _session_authorized(sid):
                await sio.emit(event, data, to=sid)
        except Exception:
            logger.warning("Socket.IO broadcast unavailable")


async def broadcast_portfolio_update(user_id: str, portfolio_data: dict[str, Any]) -> None:
    """
    Broadcast portfolio update to a specific user's connected clients.

    Args:
        user_id: User ID to broadcast to
        portfolio_data: Portfolio data to broadcast
    """
    await broadcast_to_user(user_id, 'portfolio_update', portfolio_data)


async def broadcast_order_update(user_id: str, order_data: dict[str, Any]) -> None:
    """
    Broadcast order update to a specific user's connected clients.

    Args:
        user_id: User ID to broadcast to
        order_data: Order data to broadcast
    """
    try:
        user_topic = f"user_{user_id}"

        if user_topic in topic_subscribers:
            await broadcast_to_topic(user_topic, 'order_update', order_data)

            logger.info(f"Broadcasted order update to user {user_id}")

    except Exception as e:
        logger.error(f"Failed to broadcast order update for user {user_id}: {e}")


async def broadcast_strategy_update(topic: str, strategy_data: dict[str, Any]) -> None:
    """
    Broadcast strategy update to subscribers of a topic.

    Args:
        topic: Topic to broadcast to (e.g., 'strategies' or 'user_{user_id}')
        strategy_data: Strategy data to broadcast
    """
    try:
        if topic in topic_subscribers:
            await broadcast_to_topic(topic, 'strategy_update', strategy_data)

            logger.info(f"Broadcasted strategy update to topic: {topic}")

    except Exception as e:
        logger.error(f"Failed to broadcast strategy update to topic {topic}: {e}")


async def broadcast_settings_update(settings_data: dict[str, Any]) -> None:
    """
    Broadcast settings update to all connected clients.

    Args:
        settings_data: Settings data including category and new values
    """
    try:
        await broadcast_to_all('settings_update', settings_data)
        logger.debug("Broadcasted settings update")
    except Exception as e:
        logger.error(f"Failed to broadcast settings update: {e}")


def get_subscriber_count(topic: str | None = None) -> int:
    """
    Get number of subscribers for a topic or total connected clients.

    Args:
        topic: Topic name (optional)

    Returns:
        Number of subscribers
    """
    if topic:
        return len(topic_subscribers.get(topic, set()))
    return len(client_subscriptions)


def create_socketio_app(fastapi_app: FastAPI) -> socketio.ASGIApp:
    """
    Create Socket.IO ASGI app that wraps FastAPI app.

    Args:
        fastapi_app: FastAPI application instance

    Returns:
        Combined Socket.IO + FastAPI ASGI app
    """
    # Wrap FastAPI app with Socket.IO
    return socketio.ASGIApp(
        socketio_server=sio,
        other_asgi_app=fastapi_app,
        socketio_path='/socket.io'
    )
