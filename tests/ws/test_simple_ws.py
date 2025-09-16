"""Simple WebSocket Manager test"""

import pytest
import asyncio
from unittest.mock import AsyncMock

class TestSimpleWebSocket:
    
    @pytest.mark.asyncio
    async def test_simple_import(self):
        """Test simple import and creation"""
        from backend.api.websocket_manager import WebSocketClientManager
        
        # Simple mock without any complexity
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.send_text = AsyncMock()
        
        # Mock metrics registry
        class MockRegistry:
            def counter(self, name, labels=None):
                class MockCounter:
                    def inc(self, amount=1):
                        pass
                return MockCounter()
        
        manager = WebSocketClientManager(
            queue_max=10,
            heartbeat_sec=30,
            now_func=lambda: 1000.0,  # Fixed timestamp
            metrics_registry=MockRegistry()
        )
        
        # Try to add client
        await manager.add_client("test_client", mock_ws)
        
        # Basic assertions
        assert "test_client" in manager.clients
        assert len(manager.clients) == 1
        
        print("✅ Simple WebSocket manager test passed")
