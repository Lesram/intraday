"""
WebSocket Integration Tests
Tests the complete WebSocket infrastructure including:
- Connection and authentication
- Subscription management
- Broadcasting
- Reconnection handling
- Message delivery

Note: These tests require a running server at localhost:8000
"""

import os
import asyncio
import pytest
from datetime import datetime, timezone
from typing import List, Dict, Any

RUN_LIVE = os.getenv("RUN_LIVE_WS_TESTS") == "1"

# Disabled by default to keep normal test lanes stable.
pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="WebSocket integration tests are disabled by default. Set RUN_LIVE_WS_TESTS=1 and run the server on localhost:8000 to enable.",
)

if RUN_LIVE:
    import requests
    import socketio

    from backend.api.socketio_server import broadcast_portfolio_update
    from backend.infra.security import create_access_token


    def _server_is_running() -> bool:
        """Check if the backend server is running."""
        try:
            resp = requests.get("http://localhost:8000/health", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False


    def _auth_works() -> bool:
        """Check if test auth credentials work with the live server."""
        try:
            resp = requests.post(
                "http://localhost:8000/auth/login",
                json={"username": "admin@example.com", "password": "Admin123!@#"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False


    # Mark all tests in this module as requiring live server with working auth
    pytestmark = pytest.mark.skipif(
        not _server_is_running() or not _auth_works(),
        reason="WebSocket integration tests require running server at localhost:8000 with working auth. "
        "Start server with 'python start_backend.py' and ensure admin user exists.",
    )


class WebSocketTestClient:
    """Test client for WebSocket connections"""
    
    def __init__(self):
        self.client = socketio.AsyncClient()
        self.received_messages: List[Dict[str, Any]] = []
        self.connected = False
        self.connection_error = None
        
    async def connect(self, token: str, server_url: str = 'http://localhost:8000'):
        """Connect to WebSocket server with authentication"""
        
        @self.client.on('connect')
        def on_connect():
            self.connected = True
            
        @self.client.on('connect_error')
        def on_connect_error(data):
            self.connection_error = data
            
        @self.client.on('portfolio_update')
        def on_portfolio_update(data):
            self.received_messages.append({
                'type': 'portfolio_update',
                'data': data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
        @self.client.on('order_update')
        def on_order_update(data):
            self.received_messages.append({
                'type': 'order_update',
                'data': data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
        await self.client.connect(
            server_url,
            auth={'token': token},
            transports=['websocket']
        )
        
        # Wait for connection to establish
        await asyncio.sleep(0.5)
        
    async def subscribe(self, topic: str):
        """Subscribe to a topic"""
        await self.client.emit('subscribe', {
            'type': 'subscribe',
            'topic': topic,
            'timestamp': datetime.now(timezone.utc).timestamp()
        })
        await asyncio.sleep(0.1)
        
    async def disconnect(self):
        """Disconnect from server"""
        await self.client.disconnect()
        self.connected = False
        
    def clear_messages(self):
        """Clear received messages buffer"""
        self.received_messages.clear()


@pytest.fixture
def auth_token():
    """Create a valid JWT token for testing"""
    return create_access_token(
        sub="test@example.com",
        roles=["USER"]
    )


@pytest.fixture
def admin_token():
    """Create an admin JWT token for testing"""
    return create_access_token(
        sub="admin@example.com",
        roles=["ADMIN"]
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketConnection:
    """Test WebSocket connection and authentication"""
    
    async def test_connect_with_valid_token(self, auth_token):
        """Test successful connection with valid JWT token"""
        client = WebSocketTestClient()
        
        try:
            await client.connect(auth_token)
            assert client.connected is True
            assert client.connection_error is None
        finally:
            await client.disconnect()
            
    async def test_connect_without_token(self):
        """Test connection rejection without token"""
        client = socketio.AsyncClient()
        
        try:
            await client.connect(
                'http://localhost:8000',
                transports=['websocket']
            )
            # Should fail - no token provided
            assert False, "Connection should have been rejected"
        except socketio.exceptions.ConnectionError:
            # Expected behavior
            pass
            
    async def test_connect_with_invalid_token(self):
        """Test connection rejection with invalid token"""
        client = socketio.AsyncClient()
        
        try:
            await client.connect(
                'http://localhost:8000',
                auth={'token': 'invalid_token_12345'},
                transports=['websocket']
            )
            # Should fail - invalid token
            assert False, "Connection should have been rejected"
        except socketio.exceptions.ConnectionError:
            # Expected behavior
            pass


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketSubscriptions:
    """Test topic subscription and unsubscription"""
    
    async def test_subscribe_to_portfolio(self, auth_token):
        """Test subscribing to portfolio updates"""
        client = WebSocketTestClient()
        
        try:
            await client.connect(auth_token)
            await client.subscribe('portfolio')
            
            # Verify subscription by triggering a broadcast
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': 100000.0,
                    'cash': 100000.0,
                    'buyingPower': 100000.0,
                    'dayPnL': 0.0,
                    'dayPnLPercent': 0.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            # Wait for message delivery
            await asyncio.sleep(0.5)
            
            # Should have received the portfolio update
            assert len(client.received_messages) > 0
            assert client.received_messages[0]['type'] == 'portfolio_update'
            
        finally:
            await client.disconnect()
            
    async def test_multiple_subscriptions(self, auth_token):
        """Test subscribing to multiple topics"""
        client = WebSocketTestClient()
        
        try:
            await client.connect(auth_token)
            await client.subscribe('portfolio')
            await client.subscribe('orders')
            await client.subscribe('strategies')
            
            # Trigger portfolio broadcast
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': 105000.0,
                    'cash': 105000.0,
                    'buyingPower': 105000.0,
                    'dayPnL': 5000.0,
                    'dayPnLPercent': 5.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Should receive portfolio updates
            portfolio_msgs = [m for m in client.received_messages if m['type'] == 'portfolio_update']
            assert len(portfolio_msgs) > 0
            
        finally:
            await client.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketBroadcasting:
    """Test message broadcasting functionality"""
    
    async def test_broadcast_to_single_user(self, auth_token):
        """Test broadcasting to a single user"""
        client = WebSocketTestClient()
        
        try:
            await client.connect(auth_token)
            await client.subscribe('portfolio')
            client.clear_messages()
            
            # Broadcast portfolio update
            test_equity = 125000.0
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': test_equity,
                    'cash': test_equity,
                    'buyingPower': test_equity,
                    'dayPnL': 25000.0,
                    'dayPnLPercent': 25.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Verify message received
            assert len(client.received_messages) == 1
            msg = client.received_messages[0]
            assert msg['type'] == 'portfolio_update'
            assert msg['data']['data']['totalEquity'] == test_equity
            
        finally:
            await client.disconnect()
            
    async def test_broadcast_to_multiple_clients(self, auth_token):
        """Test broadcasting to multiple connected clients"""
        client1 = WebSocketTestClient()
        client2 = WebSocketTestClient()
        
        try:
            # Connect two clients
            await client1.connect(auth_token)
            await client2.connect(auth_token)
            
            await client1.subscribe('portfolio')
            await client2.subscribe('portfolio')
            
            client1.clear_messages()
            client2.clear_messages()
            
            # Broadcast to both
            test_equity = 150000.0
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': test_equity,
                    'cash': test_equity,
                    'buyingPower': test_equity,
                    'dayPnL': 50000.0,
                    'dayPnLPercent': 50.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Both clients should receive the message
            assert len(client1.received_messages) >= 1
            assert len(client2.received_messages) >= 1
            assert client1.received_messages[0]['data']['data']['totalEquity'] == test_equity
            assert client2.received_messages[0]['data']['data']['totalEquity'] == test_equity
            
        finally:
            await client1.disconnect()
            await client2.disconnect()
            
    async def test_broadcast_sequence(self, auth_token):
        """Test receiving a sequence of broadcasts"""
        client = WebSocketTestClient()
        
        try:
            await client.connect(auth_token)
            await client.subscribe('portfolio')
            client.clear_messages()
            
            # Send sequence of updates
            test_values = [100000.0, 110000.0, 105000.0, 115000.0]
            
            for value in test_values:
                await broadcast_portfolio_update(
                    user_id="test@example.com",
                    portfolio_data={
                        'totalEquity': value,
                        'cash': value,
                        'buyingPower': value,
                        'dayPnL': value - 100000.0,
                        'dayPnLPercent': ((value - 100000.0) / 100000.0) * 100,
                        'positions': [],
                        'userId': 'test@example.com',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                )
                await asyncio.sleep(0.2)
                
            await asyncio.sleep(0.5)
            
            # Should have received all updates
            assert len(client.received_messages) >= len(test_values)
            
            # Verify sequence
            received_values = [
                msg['data']['data']['totalEquity'] 
                for msg in client.received_messages[:len(test_values)]
            ]
            assert received_values == test_values
            
        finally:
            await client.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketReconnection:
    """Test reconnection handling"""
    
    async def test_reconnect_after_disconnect(self, auth_token):
        """Test that client can reconnect after disconnect"""
        client = WebSocketTestClient()
        
        try:
            # First connection
            await client.connect(auth_token)
            assert client.connected is True
            
            # Disconnect
            await client.disconnect()
            assert client.connected is False
            
            # Reconnect
            await client.connect(auth_token)
            assert client.connected is True
            
            # Should be able to receive messages after reconnect
            await client.subscribe('portfolio')
            client.clear_messages()
            
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': 100000.0,
                    'cash': 100000.0,
                    'buyingPower': 100000.0,
                    'dayPnL': 0.0,
                    'dayPnLPercent': 0.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            assert len(client.received_messages) > 0
            
        finally:
            await client.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestWebSocketUserIsolation:
    """Test that users only receive their own updates"""
    
    async def test_user_isolation(self, auth_token, admin_token):
        """Test that user A doesn't receive user B's updates"""
        user_client = WebSocketTestClient()
        admin_client = WebSocketTestClient()
        
        try:
            # Connect both users
            await user_client.connect(auth_token)
            await admin_client.connect(admin_token)
            
            await user_client.subscribe('portfolio')
            await admin_client.subscribe('portfolio')
            
            user_client.clear_messages()
            admin_client.clear_messages()
            
            # Broadcast to user only
            await broadcast_portfolio_update(
                user_id="test@example.com",
                portfolio_data={
                    'totalEquity': 100000.0,
                    'cash': 100000.0,
                    'buyingPower': 100000.0,
                    'dayPnL': 0.0,
                    'dayPnLPercent': 0.0,
                    'positions': [],
                    'userId': 'test@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            
            # User client should receive, admin should not
            assert len(user_client.received_messages) > 0
            assert len(admin_client.received_messages) == 0
            
            # Clear and test admin broadcast
            user_client.clear_messages()
            admin_client.clear_messages()
            
            await broadcast_portfolio_update(
                user_id="admin@example.com",
                portfolio_data={
                    'totalEquity': 200000.0,
                    'cash': 200000.0,
                    'buyingPower': 200000.0,
                    'dayPnL': 0.0,
                    'dayPnLPercent': 0.0,
                    'positions': [],
                    'userId': 'admin@example.com',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            
            await asyncio.sleep(0.5)
            
            # Admin client should receive, user should not
            assert len(admin_client.received_messages) > 0
            assert len(user_client.received_messages) == 0
            
        finally:
            await user_client.disconnect()
            await admin_client.disconnect()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
