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
import os
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
import socketio

from backend.infra.security import decode_token

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

            logger.info(f"[AUTH] JWT decoded - user_id: '{user_id}', roles: {roles}")
            logger.info(f"Client connected: {sid} (user: {user_id}, roles: {roles})")

            # Store user info in session
            async with sio.session(sid) as session:
                session['user_id'] = user_id
                session['roles'] = roles
                session['authenticated'] = True

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


@sio.event
async def subscribe(sid: str, data: dict):
    """
    Subscribe client to a topic.

    Args:
        sid: Socket.IO session ID
        data: {'topic': 'portfolio'} or {'topics': ['orders', 'positions']}
    """
    try:
        # Check authentication
        async with sio.session(sid) as session:
            if not session.get('authenticated'):
                await sio.emit('error', {'message': 'Not authenticated'}, to=sid)
                return

            user_id = session.get('user_id')

        # Handle single topic or multiple topics
        topics = []
        if 'topic' in data:
            topics = [data['topic']]
        elif 'topics' in data:
            topics = data['topics']

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

    except Exception as e:
        logger.error(f"Subscribe error for {sid}: {e}")
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
        await sio.emit('heartbeat_ack', {'timestamp': data.get('timestamp') if data else None}, to=sid)
    except Exception as e:
        logger.error(f"Heartbeat error for {sid}: {e}")


# Broadcasting functions for backend services to use

async def broadcast_to_topic(topic: str, event: str, data: Any):
    """
    Broadcast message to all clients subscribed to a topic using Socket.IO rooms.

    Uses room-based broadcasting for O(1) performance instead of O(n) iteration.

    Args:
        topic: Topic name (e.g., 'portfolio', 'orders')
        event: Event name (e.g., 'portfolio_update', 'order_filled')
        data: Data to broadcast
    """
    try:
        # Use Socket.IO room for O(1) broadcasting
        subscriber_count = len(topic_subscribers.get(topic, set()))
        logger.debug(f"Broadcasting '{event}' to room '{topic}' ({subscriber_count} subscribers)")

        await sio.emit(event, data, room=topic)

    except Exception as e:
        logger.error(f"Broadcast error for topic '{topic}': {e}")


async def broadcast_to_user(user_id: str, event: str, data: Any):
    """
    Broadcast message to a specific user (all their sessions).

    Args:
        user_id: User identifier
        event: Event name
        data: Data to broadcast
    """
    try:
        sent_count = 0
        for sid in client_subscriptions:
            try:
                async with sio.session(sid) as session:
                    if session.get('user_id') == user_id:
                        await sio.emit(event, data, to=sid)
                        sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to user {user_id} session {sid}: {e}")

        if sent_count > 0:
            logger.debug(f"Sent '{event}' to user '{user_id}' ({sent_count} session(s))")

    except Exception as e:
        logger.error(f"Broadcast error for user '{user_id}': {e}")


async def broadcast_to_all(event: str, data: Any):
    """
    Broadcast message to all connected clients.

    Args:
        event: Event name
        data: Data to broadcast
    """
    try:
        await sio.emit(event, data)
        logger.debug(f"Broadcasted '{event}' to all clients")
    except Exception as e:
        logger.error(f"Broadcast to all error: {e}")


async def broadcast_portfolio_update(user_id: str, portfolio_data: dict[str, Any]) -> None:
    """
    Broadcast portfolio update to a specific user's connected clients.

    Args:
        user_id: User ID to broadcast to
        portfolio_data: Portfolio data to broadcast
    """
    try:
        # Find all sessions for this user
        user_topic = f"user_{user_id}"

        if user_topic in topic_subscribers:
            subscriber_count = len(topic_subscribers[user_topic])
            subscribers = topic_subscribers[user_topic]

            logger.info(f"🎯 Broadcasting portfolio update to user {user_id} ({subscriber_count} clients)")

            # FIXED: Emit to each subscriber's session directly
            for sid in subscribers:
                try:
                    # Emit the portfolio_update event directly to this client
                    await sio.emit('portfolio_update', portfolio_data, to=sid)
                    logger.info(f"✅ Sent portfolio_update to client {sid}")
                except Exception as e:
                    logger.error(f"❌ Failed to send to client {sid}: {e}")

            logger.info(f"Broadcasted portfolio update to {subscriber_count} clients for user {user_id}")
        else:
            logger.warning(f"⚠️ No connected clients for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error broadcasting portfolio update: {e}")
        logger.error(traceback.format_exc())


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
