"""
Mock classes and utilities for testing.
"""

import asyncio
from unittest.mock import Mock, AsyncMock
from typing import Any, Dict


class MockMetrics:
    """Mock metrics class with all expected methods"""
    
    def __init__(self):
        self.counters = {}
        self.histograms = {}
        self.gauges = {}
        self.calls = []
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric"""
        self.calls.append(('increment_counter', name, value, labels))
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value
    
    def inc_counter(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Alias for increment_counter"""
        return self.increment_counter(name, value, labels)
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a histogram metric"""
        self.calls.append(('observe_histogram', name, value, labels))
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric"""
        self.calls.append(('set_gauge', name, value, labels))
        self.gauges[name] = value
    
    def update_status(self, status: str):
        """Mock status update"""
        self.calls.append(('update_status', status))


class MockOrderService:
    """Mock order service with async methods"""
    
    def __init__(self):
        self.orders = {}
        self.call_count = 0
        self.should_fail = False
        
    async def create_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock async create_order method"""
        self.call_count += 1
        
        if self.should_fail and self.call_count <= 2:
            if self.call_count == 1:
                raise Exception("Connection timeout")
            else:
                raise Exception("Rate limited")
        
        order_id = f"order_{self.call_count}"
        order = {
            "id": order_id,
            "status": "PENDING",
            "symbol": order_data.get("symbol", "AAPL"),
            "quantity": order_data.get("quantity", 100),
            "side": order_data.get("side", "BUY"),
            **order_data
        }
        self.orders[order_id] = order
        return order
    
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Mock async get_order method"""
        return self.orders.get(order_id, {"id": order_id, "status": "NOT_FOUND"})
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Mock async cancel_order method"""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
            return self.orders[order_id]
        return {"id": order_id, "status": "NOT_FOUND"}


class MockAsyncResult:
    """Mock for async function results that should act like dictionaries"""
    
    def __init__(self, data: Dict[str, Any]):
        self._data = data
        
    def __getitem__(self, key):
        return self._data[key]
    
    def __setitem__(self, key, value):
        self._data[key] = value
    
    def __contains__(self, key):
        return key in self._data
    
    def get(self, key, default=None):
        return self._data.get(key, default)
    
    def keys(self):
        return self._data.keys()
    
    def values(self):
        return self._data.values()
    
    def items(self):
        return self._data.items()


def create_async_mock_result(data: Dict[str, Any]):
    """Create a mock result that can be used in async/await context"""
    async def mock_coro():
        return MockAsyncResult(data)
    
    return mock_coro()


def patch_order_service_tests():
    """Patch common order service test issues"""
    import sys
    
    # Mock modules that cause import issues
    mock_modules = [
        'backend.services.signal_service',
        'backend.risk.risk_calculator'
    ]
    
    for module_name in mock_modules:
        if module_name not in sys.modules:
            mock_module = Mock()
            sys.modules[module_name] = mock_module
