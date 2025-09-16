"""
Tests for backend/services/signal_service.py - Trading signal service
Tests the SignalService class and related functions using direct import.
"""

import os
import sys
import pytest
import asyncio
import importlib.util
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, Mock, AsyncMock


class TestSignalServiceDirect:
    """Test suite for signal service using direct import."""
    
    def setup_method(self):
        """Set up direct module import."""
        backend_path = Path(__file__).parent.parent.parent / "backend"
        self.backend_path = str(backend_path.resolve())
        
        # Import the signal service module using importlib
        signal_service_path = os.path.join(self.backend_path, 'services', 'signal_service.py')
        spec = importlib.util.spec_from_file_location("signal_service_module", signal_service_path)
        self.signal_service = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.signal_service)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.signal_service = None

    def test_signal_service_initialization(self):
        """Test SignalService class initialization."""
        service = self.signal_service.SignalService()
        
        assert service is not None
        assert isinstance(service, self.signal_service.SignalService)
        assert service.signals == {}

    @pytest.mark.asyncio
    async def test_get_signals_with_symbol(self):
        """Test get_signals method with specific symbol."""
        service = self.signal_service.SignalService()
        
        signals = await service.get_signals("TSLA")
        
        assert isinstance(signals, list)
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal["symbol"] == "TSLA"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert "timestamp" in signal
        
        # Verify timestamp format
        datetime.fromisoformat(signal["timestamp"].replace('Z', '+00:00'))

    @pytest.mark.asyncio
    async def test_get_signals_without_symbol(self):
        """Test get_signals method without symbol (default behavior)."""
        service = self.signal_service.SignalService()
        
        signals = await service.get_signals()
        
        assert isinstance(signals, list)
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal["symbol"] == "AAPL"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.8
        assert "timestamp" in signal
        
        # Verify timestamp format
        datetime.fromisoformat(signal["timestamp"].replace('Z', '+00:00'))

    @pytest.mark.asyncio
    async def test_get_signals_with_none_symbol(self):
        """Test get_signals method with None symbol."""
        service = self.signal_service.SignalService()
        
        signals = await service.get_signals(None)
        
        assert isinstance(signals, list)
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_signals_with_empty_string_symbol(self):
        """Test get_signals method with empty string symbol."""
        service = self.signal_service.SignalService()
        
        signals = await service.get_signals("")
        
        # Empty string is falsy, should return default AAPL signal
        assert isinstance(signals, list)
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_generate_signal_with_data(self):
        """Test generate_signal method with trading data."""
        service = self.signal_service.SignalService()
        
        test_data = {
            "price": 150.0,
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 2.3
        }
        
        signal = await service.generate_signal("NVDA", test_data)
        
        assert isinstance(signal, dict)
        assert signal["symbol"] == "NVDA"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert signal["data"] == test_data
        assert "timestamp" in signal
        
        # Verify timestamp format
        datetime.fromisoformat(signal["timestamp"].replace('Z', '+00:00'))

    @pytest.mark.asyncio
    async def test_generate_signal_with_empty_data(self):
        """Test generate_signal method with empty data."""
        service = self.signal_service.SignalService()
        
        signal = await service.generate_signal("GOOG", {})
        
        assert signal["symbol"] == "GOOG"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert signal["data"] == {}

    @pytest.mark.asyncio
    async def test_generate_signal_with_complex_data(self):
        """Test generate_signal method with complex nested data."""
        service = self.signal_service.SignalService()
        
        complex_data = {
            "technical": {
                "sma_20": 145.0,
                "sma_50": 140.0,
                "bollinger_bands": {"upper": 155.0, "lower": 135.0}
            },
            "fundamental": {
                "pe_ratio": 25.5,
                "market_cap": 2000000000
            },
            "sentiment": ["positive", "bullish", "growth"]
        }
        
        signal = await service.generate_signal("AMZN", complex_data)
        
        assert signal["symbol"] == "AMZN"
        assert signal["data"] == complex_data
        assert signal["data"]["technical"]["bollinger_bands"]["upper"] == 155.0

    def test_signals_attribute_persistence(self):
        """Test that signals attribute maintains state."""
        service = self.signal_service.SignalService()
        
        # Initially empty
        assert service.signals == {}
        
        # Modify signals
        service.signals["AAPL"] = {"signal": "BUY", "confidence": 0.9}
        
        # Should persist
        assert "AAPL" in service.signals
        assert service.signals["AAPL"]["confidence"] == 0.9

    def test_global_signal_service_instance(self):
        """Test the global signal_service instance."""
        global_instance = self.signal_service.signal_service
        
        assert global_instance is not None
        assert isinstance(global_instance, self.signal_service.SignalService)

    @pytest.mark.asyncio
    async def test_get_signal_service_function(self):
        """Test get_signal_service factory function."""
        service = await self.signal_service.get_signal_service()
        
        assert service is not None
        assert isinstance(service, self.signal_service.SignalService)
        
        # Should return the same global instance
        assert service is self.signal_service.signal_service

    def test_get_signals_shim_function(self):
        """Test the standalone get_signals shim function."""
        # Test default behavior
        result = self.signal_service.get_signals()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        signal = result[0]
        assert "symbol" in signal
        assert "signal_type" in signal
        assert "confidence" in signal
        assert "target_price" in signal
        assert "position_size" in signal
        assert "timestamp" in signal
        
        # Verify default values
        assert signal["symbol"] == "AAPL"
        assert signal["signal_type"] == "BUY"
        assert signal["confidence"] == 0.8
        assert signal["target_price"] == 150.0
        assert signal["position_size"] == 100.0
        assert signal["timestamp"] == "2024-01-01T12:00:00Z"

    def test_get_signals_shim_function_with_args(self):
        """Test get_signals shim function accepts arbitrary arguments."""
        result = self.signal_service.get_signals("TSLA", period="1d", indicators=["RSI", "MACD"])
        
        # Should still return default mock response regardless of args
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_get_signals_calls(self):
        """Test concurrent calls to get_signals method."""
        service = self.signal_service.SignalService()
        
        # Create multiple concurrent calls
        tasks = [
            service.get_signals("AAPL"),
            service.get_signals("TSLA"),
            service.get_signals("GOOG")
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        
        # Each should return appropriate signal
        assert results[0][0]["symbol"] == "AAPL"
        assert results[1][0]["symbol"] == "TSLA"
        assert results[2][0]["symbol"] == "GOOG"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_generate_signal_calls(self):
        """Test concurrent calls to generate_signal method."""
        service = self.signal_service.SignalService()
        
        # Create multiple concurrent calls
        tasks = [
            service.generate_signal("AAPL", {"price": 150}),
            service.generate_signal("TSLA", {"price": 800}),
            service.generate_signal("GOOG", {"price": 2500})
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        
        # Each should return appropriate signal with data
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["data"]["price"] == 150
        assert results[1]["symbol"] == "TSLA"
        assert results[1]["data"]["price"] == 800
        assert results[2]["symbol"] == "GOOG"
        assert results[2]["data"]["price"] == 2500

    @pytest.mark.asyncio
    async def test_timestamp_consistency(self):
        """Test that timestamps are generated consistently across methods."""
        service = self.signal_service.SignalService()
        
        # Get signals from both methods within a short time window
        signal1 = await service.get_signals("TEST1")
        signal2 = await service.generate_signal("TEST2", {"data": "test"})
        
        # Parse timestamps
        ts1 = datetime.fromisoformat(signal1[0]["timestamp"].replace('Z', '+00:00'))
        ts2 = datetime.fromisoformat(signal2["timestamp"].replace('Z', '+00:00'))
        
        # Should be generated within a small time window (less than 1 second apart)
        time_diff = abs((ts2 - ts1).total_seconds())
        assert time_diff < 1.0  # Both should be generated within 1 second

    @pytest.mark.asyncio
    async def test_service_state_isolation(self):
        """Test that different service instances maintain separate state."""
        service1 = self.signal_service.SignalService()
        service2 = self.signal_service.SignalService()
        
        # Modify state in service1
        service1.signals["AAPL"] = {"test": "value1"}
        
        # service2 should have clean state
        assert service2.signals == {}
        
        # service1 should maintain its state
        assert service1.signals["AAPL"]["test"] == "value1"

    def test_type_annotations_exist(self):
        """Test that proper type annotations are present in the module."""
        # Check that required imports exist
        assert hasattr(self.signal_service, 'Dict')
        assert hasattr(self.signal_service, 'List')
        assert hasattr(self.signal_service, 'Any')
        assert hasattr(self.signal_service, 'datetime')
        assert hasattr(self.signal_service, 'asyncio')

    @pytest.mark.asyncio
    async def test_signal_format_consistency(self):
        """Test that all signal formats are consistent across methods."""
        service = self.signal_service.SignalService()
        
        # Get signals from both methods
        signals_list = await service.get_signals("TEST")
        generated_signal = await service.generate_signal("TEST", {"test": "data"})
        
        # Both should have common fields
        common_fields = ["symbol", "signal", "confidence", "timestamp"]
        
        for field in common_fields:
            assert field in signals_list[0]
            assert field in generated_signal
        
        # Values should be consistent for same symbol
        assert signals_list[0]["symbol"] == "TEST"
        assert generated_signal["symbol"] == "TEST"
        assert signals_list[0]["confidence"] == 0.75
        assert generated_signal["confidence"] == 0.75
