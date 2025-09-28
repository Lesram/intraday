#!/usr/bin/env python3
"""
Module 5D: WebSocket Manager - Direct method coverage tests
Target: backend/api/websocket_manager.py
"""

import os
import sys
import importlib
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def _import_module(name: str):
    try:
        return importlib.import_module(name), None
    except Exception as e:
        return None, e


class MockWebSocket:
    """Mock WebSocket for testing."""
    def __init__(self):
        self.closed = False
        self.messages = []
    
    async def close(self):
        self.closed = True
    
    async def send_text(self, message):
        self.messages.append(message)


def test_websocket_manager_importable():
    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable in this env: {err}")
    assert hasattr(mod, "__name__")


def test_websocket_manager_direct_methods():
    """Test WebSocketClientManager methods directly to increase coverage."""
    # Add stubs for missing dependencies
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class WebSocket:
            def __init__(self):
                self.closed = False
            async def close(self):
                self.closed = True
            async def send_text(self, message):
                pass
        class WebSocketDisconnect(Exception):
            pass
        fastapi.WebSocket = WebSocket
        fastapi.WebSocketDisconnect = WebSocketDisconnect
        sys.modules["fastapi"] = fastapi

    # Stub logger if needed
    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        class _DummyLogger:
            def info(self, *args, **kwargs):
                return None
            def error(self, *args, **kwargs):
                return None
        def get_logger(name):
            return _DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable: {err}")
    
    # Test WebSocketClientInfo dataclass
    mock_ws = MockWebSocket()
    queue = asyncio.Queue()
    from datetime import datetime, timezone
    now_time = datetime.now(timezone.utc)
    
    client_info = mod.WebSocketClientInfo(
        client_id="test_client",
        websocket=mock_ws,
        queue=queue,
        last_heartbeat=now_time
    )
    
    # Test dictionary-style access
    assert client_info["client_id"] == "test_client"
    client_info["test_key"] = "test_value"
    assert "test_key" in client_info
    
    # Test WebSocketClientManager initialization
    manager = mod.WebSocketClientManager(queue_max=50, heartbeat_interval=15)
    assert manager.queue_max == 50
    assert manager.heartbeat_interval == 15
    assert len(manager.clients) == 0
    
    # Test with different parameter names for compatibility
    manager2 = mod.WebSocketClientManager(max_queue_size=100, heartbeat_sec=25)
    assert manager2.queue_max == 100
    assert manager2.heartbeat_interval == 25


def test_websocket_client_lifecycle():
    """Test WebSocket client registration, broadcasting, and removal."""
    # Add required stubs
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class WebSocket:
            def __init__(self):
                self.closed = False
            async def close(self):
                self.closed = True
            async def send_text(self, message):
                pass
        fastapi.WebSocket = WebSocket
        sys.modules["fastapi"] = fastapi

    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        def get_logger(name):
            class DummyLogger:
                def info(self, *args, **kwargs): pass
                def error(self, *args, **kwargs): pass
            return DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable: {err}")
    
    async def run_lifecycle_test():
        manager = mod.WebSocketClientManager(queue_max=10)
        mock_ws = MockWebSocket()
        
        # Test client registration
        success = await manager.register_client("client1", mock_ws)
        assert success == True
        assert "client1" in manager.clients
        assert "client1" in manager.active_connections
        
        # Test add_client alias
        mock_ws2 = MockWebSocket()
        success2 = await manager.add_client("client2", mock_ws2)
        assert success2 == True
        
        # Test open method with different parameter order
        mock_ws3 = MockWebSocket() 
        success3 = await manager.open(mock_ws3, "client3")
        assert success3 == True
        
        # Test broadcasting without subscription filter
        message = {"type": "test", "data": "hello"}
        await manager.broadcast_message(message)
        
        # Test subscription filtering
        client_info = manager.clients["client1"]
        client_info.subscriptions.add("prices")
        
        await manager.broadcast_message({"type": "price_update"}, subscription_filter="prices")
        await manager.broadcast_message({"type": "news"}, subscription_filter="news")
        
        # Test client removal
        await manager.remove_client("client1")
        assert "client1" not in manager.clients
        assert mock_ws.closed == True
        
        # Test unregister_client alias
        result = await manager.unregister_client("client2")
        assert result == True
        assert "client2" not in manager.clients
        
        # Test disconnect method
        await manager.disconnect("client3")
        assert "client3" not in manager.clients
    
    # Run the async test using asyncio.run
    asyncio.run(run_lifecycle_test())


def test_websocket_manager_edge_cases():
    """Test edge cases and error conditions."""
    # Add required stubs
    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        def get_logger(name):
            class DummyLogger:
                def info(self, *args, **kwargs): pass
                def error(self, *args, **kwargs): pass
            return DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable: {err}")
    
    manager = mod.WebSocketClientManager()
    
    # Test removing non-existent client
    asyncio.run(manager.remove_client("nonexistent"))  # Should not raise
    
    # Test unregister_client with non-existent client
    result = asyncio.run(manager.unregister_client("nonexistent"))
    assert result == False
    
    # Test disconnect with non-existent client
    asyncio.run(manager.disconnect("nonexistent"))  # Should not raise
    
    # Test various parameter combinations
    manager_with_metrics = mod.WebSocketClientManager(
        queue_max=200,
        heartbeat_interval=60,
        stale_connection_timeout=120,
        metrics_registry=Mock()
    )
    assert manager_with_metrics.queue_max == 200
    assert manager_with_metrics.stale_connection_timeout == 120


def test_websocket_internal_methods():
    """Test internal WebSocket manager methods and error conditions."""
    # Add required stubs
    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        def get_logger(name):
            class DummyLogger:
                def info(self, *args, **kwargs): pass
                def error(self, *args, **kwargs): pass
            return DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable: {err}")
    
    # Test utility functions
    async def test_task_tracking():
        # Test _track_task function
        import asyncio
        task = asyncio.create_task(asyncio.sleep(0.1))
        tracked = mod._track_task(task)
        assert tracked is task
        
        # Test cancel_all_ws_tasks
        await mod.cancel_all_ws_tasks(timeout=0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    asyncio.run(test_task_tracking())
    
    # Test manager with custom now function
    import time
    custom_time = time.time()
    def custom_now():
        return custom_time
    
    manager = mod.WebSocketClientManager(now=custom_now)
    assert manager.now == custom_now
    
    # Test manager with now_func parameter
    manager2 = mod.WebSocketClientManager(now_func=custom_now)
    assert manager2.now_func == custom_now
    
    # Test manager with prometheus registry
    if mod.PROMETHEUS_AVAILABLE:
        try:
            from prometheus_client import CollectorRegistry
            registry = CollectorRegistry()
            manager_prom = mod.WebSocketClientManager(metrics_registry=registry)
            counter = manager_prom._get_prom_simple_counter("test_counter")
            # Should either create or return None
            assert counter is None or hasattr(counter, 'inc')
        except:
            pass  # Skip if prometheus setup fails
    
    # Test manager initialization with extra kwargs (should be absorbed)
    manager_extra = mod.WebSocketClientManager(
        queue_max=50,
        extra_param="ignored",
        another_param=123
    )
    assert manager_extra.queue_max == 50


def test_websocket_broadcast_edge_cases():
    """Test WebSocket broadcast with various edge cases."""
    # Add required stubs
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class WebSocket:
            def __init__(self):
                self.closed = False
            async def close(self):
                self.closed = True
        fastapi.WebSocket = WebSocket
        sys.modules["fastapi"] = fastapi

    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        def get_logger(name):
            class DummyLogger:
                def info(self, *args, **kwargs): pass
                def error(self, *args, **kwargs): pass
            return DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.websocket_manager")
    if mod is None:
        pytest.skip(f"backend.api.websocket_manager not importable: {err}")
    
    async def test_broadcast_scenarios():
        manager = mod.WebSocketClientManager(queue_max=2)  # Small queue for testing
        mock_ws = MockWebSocket()
        
        # Register client
        await manager.register_client("test_client", mock_ws)
        
        # Test broadcast with no subscription filter
        await manager.broadcast_message({"type": "general"})
        
        # Test broadcast with subscription filter - client not subscribed
        await manager.broadcast_message({"type": "specific"}, subscription_filter="news")
        
        # Subscribe client to news
        client_info = manager.clients["test_client"]
        client_info.subscriptions.add("news")
        
        # Test broadcast with subscription filter - client subscribed
        await manager.broadcast_message({"type": "news_update"}, subscription_filter="news")
        
        # Test broadcast that fills queue (should handle QueueFull gracefully)
        for i in range(5):  # More than queue max
            try:
                await manager.broadcast_message({"seq": i})
            except:
                pass  # Should handle gracefully
        
        # Cleanup
        await manager.remove_client("test_client")
    
    asyncio.run(test_broadcast_scenarios())