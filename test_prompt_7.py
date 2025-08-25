#!/usr/bin/env python3
"""
Test script for Prompt 7: WebSocket Manager Compatibility

Tests the WebSocket manager tweaks:
- connect alias for open method
- open method with websocket, client_id parameter order
- client info structure with expected keys including last_ping
- disconnect method that calls close() on websocket
"""

import asyncio
import time
from unittest.mock import Mock, AsyncMock
from backend.api.websocket_manager import WebSocketClientManager

print("=== Testing WebSocket Manager Compatibility ===")

async def test_connect_alias():
    """Test that connect is an alias for open method."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()
    
    # Test connect method (alias)
    result = await manager.connect(mock_websocket, "test_client_1")
    assert result is True, "Connect method should return True"
    
    # Verify client was added
    assert "test_client_1" in manager._clients, "Client should be in _clients dict"
    
    print("✅ Test 1: Connect alias works")

async def test_open_parameter_order():
    """Test open method with websocket, client_id parameter order."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()
    
    # Test open method with correct parameter order
    now_func = lambda: time.time()
    result = await manager.open(mock_websocket, "test_client_2", queue_max=500, now=now_func)
    assert result is True, "Open method should return True"
    
    # Verify client info structure
    client_info = manager._clients["test_client_2"]
    expected_keys = {"websocket", "client_id", "queue", "last_ping"}
    assert all(key in client_info for key in expected_keys), f"Client info missing expected keys. Got: {list(client_info.keys())}"
    
    # Verify values
    assert client_info["websocket"] is mock_websocket, "WebSocket should be stored correctly"
    assert client_info["client_id"] == "test_client_2", "Client ID should be stored correctly"
    assert hasattr(client_info["queue"], "put_nowait"), "Queue should be an asyncio Queue"
    assert "last_ping" in client_info, "last_ping should be initialized"
    
    print("✅ Test 2: Open parameter order and client info structure works")

async def test_client_info_keys():
    """Test that client info has all expected keys."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()
    
    # Open connection
    await manager.open(mock_websocket, "test_client_3")
    
    # Check client info structure
    info = manager._clients["test_client_3"]
    required_keys = ["websocket", "client_id", "queue", "last_ping"]
    
    for key in required_keys:
        assert key in info, f"Missing required key: {key}"
    
    # Verify last_ping is a number (timestamp from asyncio.get_event_loop().time())
    last_ping = info["last_ping"]
    assert isinstance(last_ping, (int, float)), f"last_ping should be a timestamp number, got {type(last_ping)}: {last_ping}"
    
    print("✅ Test 3: Client info has all required keys")

async def test_disconnect_calls_close():
    """Test that disconnect method calls close() on websocket."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket with close method tracking
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()
    
    # Open connection
    await manager.open(mock_websocket, "test_client_4")
    assert "test_client_4" in manager._clients, "Client should be connected"
    
    # Disconnect
    await manager.disconnect("test_client_4")
    
    # Verify close was called
    mock_websocket.close.assert_called_once()
    
    # Verify client was removed
    assert "test_client_4" not in manager._clients, "Client should be removed from _clients"
    assert "test_client_4" not in manager.clients, "Client should be removed from clients"
    
    print("✅ Test 4: Disconnect calls close() on websocket")

async def test_disconnect_error_handling():
    """Test that disconnect handles close() errors gracefully."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket that raises exception on close
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock(side_effect=Exception("Connection already closed"))
    
    # Open connection
    await manager.open(mock_websocket, "test_client_5")
    
    # Disconnect should not raise exception
    try:
        await manager.disconnect("test_client_5")
        print("✅ Test 5: Disconnect handles close() errors gracefully")
    except Exception as e:
        raise AssertionError(f"Disconnect should handle close errors gracefully, but raised: {e}")

async def test_last_ping_initialization():
    """Test that last_ping is properly initialized."""
    manager = WebSocketClientManager()
    
    # Mock WebSocket
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()
    
    # Test with custom now function
    test_time = 1234567890.0
    custom_now = lambda: test_time
    
    await manager.open(mock_websocket, "test_client_6", now=custom_now)
    
    info = manager._clients["test_client_6"]
    assert info["last_ping"] == test_time, f"last_ping should be {test_time}, got {info['last_ping']}"
    
    print("✅ Test 6: last_ping initialization works correctly")

async def main():
    """Run all tests."""
    try:
        await test_connect_alias()
        await test_open_parameter_order()
        await test_client_info_keys()
        await test_disconnect_calls_close()
        await test_disconnect_error_handling()
        await test_last_ping_initialization()
        
        print("\n🎉 All WebSocket Manager Compatibility tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
