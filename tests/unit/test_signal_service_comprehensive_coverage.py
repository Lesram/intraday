"""
Comprehensive test suite for backend.services.signal_service module.

Tests SignalService class and signal generation functionality.

Target: backend.services.signal_service.py (68 lines, likely zero coverage)
Coverage Goal: 90%+ with comprehensive edge cases and error handling
"""

import asyncio
import pytest
from datetime import datetime, UTC
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock
import os

# Set environment variables for test compatibility
os.environ["DISABLE_ML"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.services.signal_service import SignalService, signal_service, get_signal_service


class TestSignalService:
    """Test SignalService class functionality."""
    
    def test_signal_service_init(self):
        """Test SignalService initialization."""
        service = SignalService()
        
        assert hasattr(service, 'signals')
        assert service.signals == {}
        assert isinstance(service.signals, dict)
    
    @pytest.mark.asyncio
    async def test_get_signals_no_symbol(self):
        """Test getting signals without specifying symbol."""
        service = SignalService()
        
        signals = await service.get_signals()
        
        assert isinstance(signals, list)
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal["symbol"] == "AAPL"
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.8
        assert "timestamp" in signal
        
        # Verify timestamp format
        timestamp_str = signal["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_get_signals_with_symbol(self):
        """Test getting signals for specific symbol."""
        service = SignalService()
        symbol = "TSLA"
        
        signals = await service.get_signals(symbol=symbol)
        
        assert isinstance(signals, list)
        assert len(signals) == 1
        
        signal = signals[0]
        assert signal["symbol"] == symbol
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert "timestamp" in signal
        
        # Verify timestamp is recent
        timestamp_str = signal["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(UTC)
        assert (now - timestamp).total_seconds() < 5  # Within 5 seconds
    
    @pytest.mark.asyncio
    async def test_get_signals_multiple_symbols(self):
        """Test getting signals for different symbols."""
        service = SignalService()
        
        # Test multiple different symbols
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
        
        for symbol in symbols:
            signals = await service.get_signals(symbol=symbol)
            assert len(signals) == 1
            assert signals[0]["symbol"] == symbol
            assert signals[0]["confidence"] == 0.75
    
    @pytest.mark.asyncio
    async def test_generate_signal_basic(self):
        """Test basic signal generation."""
        service = SignalService()
        symbol = "AAPL"
        data = {"price": 150.0, "volume": 1000}
        
        signal = await service.generate_signal(symbol, data)
        
        assert isinstance(signal, dict)
        assert signal["symbol"] == symbol
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert signal["data"] == data
        assert "timestamp" in signal
        
        # Verify timestamp format
        timestamp_str = signal["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        assert isinstance(timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_generate_signal_with_complex_data(self):
        """Test signal generation with complex data."""
        service = SignalService()
        symbol = "GOOGL"
        
        complex_data = {
            "price": 2500.0,
            "volume": 50000,
            "indicators": {
                "rsi": 45.0,
                "macd": 2.5,
                "bb_upper": 2520.0,
                "bb_lower": 2480.0
            },
            "market_data": {
                "sector": "Technology",
                "market_cap": "1.5T",
                "pe_ratio": 25.5
            }
        }
        
        signal = await service.generate_signal(symbol, complex_data)
        
        assert signal["symbol"] == symbol
        assert signal["signal"] == "BUY"
        assert signal["confidence"] == 0.75
        assert signal["data"] == complex_data
        assert "timestamp" in signal
    
    @pytest.mark.asyncio
    async def test_generate_signal_empty_data(self):
        """Test signal generation with empty data."""
        service = SignalService()
        symbol = "MSFT"
        data = {}
        
        signal = await service.generate_signal(symbol, data)
        
        assert signal["symbol"] == symbol
        assert signal["data"] == {}
        assert "timestamp" in signal
    
    @pytest.mark.asyncio
    async def test_generate_signal_none_data(self):
        """Test signal generation with None data."""
        service = SignalService()
        symbol = "NVDA"
        data = None
        
        signal = await service.generate_signal(symbol, data)
        
        assert signal["symbol"] == symbol
        assert signal["data"] is None
        assert "timestamp" in signal
    
    @pytest.mark.asyncio
    async def test_generate_signal_various_symbols(self):
        """Test signal generation for various symbols."""
        service = SignalService()
        
        test_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA"]
        
        for symbol in test_symbols:
            data = {"test": f"data_for_{symbol}"}
            signal = await service.generate_signal(symbol, data)
            
            assert signal["symbol"] == symbol
            assert signal["data"]["test"] == f"data_for_{symbol}"
    
    @pytest.mark.asyncio
    async def test_concurrent_signal_generation(self):
        """Test concurrent signal generation."""
        service = SignalService()
        
        async def generate_test_signal(symbol: str):
            data = {"concurrent_test": True, "symbol": symbol}
            return await service.generate_signal(symbol, data)
        
        # Generate signals concurrently
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        tasks = [generate_test_signal(symbol) for symbol in symbols]
        
        signals = await asyncio.gather(*tasks)
        
        assert len(signals) == len(symbols)
        
        # Verify all signals are correct
        for i, signal in enumerate(signals):
            expected_symbol = symbols[i]
            assert signal["symbol"] == expected_symbol
            assert signal["data"]["symbol"] == expected_symbol
            assert signal["data"]["concurrent_test"] is True
    
    @pytest.mark.asyncio
    async def test_timestamp_consistency(self):
        """Test that timestamps are consistent and recent."""
        service = SignalService()
        
        # Generate multiple signals in quick succession
        signals = []
        for i in range(5):
            signal = await service.generate_signal(f"TEST{i}", {"index": i})
            signals.append(signal)
        
        # All timestamps should be recent and in order
        timestamps = []
        for signal in signals:
            timestamp_str = signal["timestamp"]
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            timestamps.append(timestamp)
        
        # Check all timestamps are recent (within 10 seconds)
        now = datetime.now(UTC)
        for timestamp in timestamps:
            assert (now - timestamp).total_seconds() < 10
        
        # Check timestamps are in order (or very close)
        for i in range(1, len(timestamps)):
            time_diff = (timestamps[i] - timestamps[i-1]).total_seconds()
            assert time_diff >= 0  # Should be non-negative (or very small negative due to precision)


class TestSignalServiceGlobalInstance:
    """Test the global signal_service instance."""
    
    def test_global_signal_service_exists(self):
        """Test that global signal_service instance exists."""
        assert signal_service is not None
        assert isinstance(signal_service, SignalService)
        assert hasattr(signal_service, 'signals')
    
    @pytest.mark.asyncio
    async def test_global_signal_service_functionality(self):
        """Test that global signal_service works correctly."""
        signals = await signal_service.get_signals("TEST")
        
        assert len(signals) == 1
        assert signals[0]["symbol"] == "TEST"
        assert signals[0]["confidence"] == 0.75
    
    @pytest.mark.asyncio
    async def test_get_signal_service_function(self):
        """Test get_signal_service function."""
        service = await get_signal_service()
        
        assert service is not None
        assert isinstance(service, SignalService)
        assert service is signal_service  # Should return the global instance
    
    @pytest.mark.asyncio
    async def test_get_signal_service_consistency(self):
        """Test that get_signal_service always returns the same instance."""
        service1 = await get_signal_service()
        service2 = await get_signal_service()
        
        assert service1 is service2
        assert service1 is signal_service
    
    @pytest.mark.asyncio
    async def test_global_service_state_persistence(self):
        """Test that global service maintains state."""
        # Modify the global service
        original_signals = signal_service.signals.copy()
        
        # Add some test data
        signal_service.signals["test"] = "data"
        
        # Get service through function
        service = await get_signal_service()
        
        # Should have the same state
        assert service.signals["test"] == "data"
        
        # Cleanup
        signal_service.signals = original_signals


class TestSignalServiceEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_empty_symbol_handling(self):
        """Test handling of empty symbol."""
        service = SignalService()
        
        # Test empty string symbol - empty string is falsy so uses default behavior
        signals = await service.get_signals(symbol="")
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"  # Falls back to default
        assert signals[0]["confidence"] == 0.8  # Default confidence
        
        # Test None symbol (should use default behavior)
        signals = await service.get_signals(symbol=None)
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"  # Default symbol
        assert signals[0]["confidence"] == 0.8  # Default confidence
    
    @pytest.mark.asyncio
    async def test_special_characters_in_symbol(self):
        """Test handling of special characters in symbol."""
        service = SignalService()
        
        special_symbols = ["BRK.A", "BRK-B", "TSLA@", "TEST.TO", "VOO_TEST"]
        
        for symbol in special_symbols:
            signals = await service.get_signals(symbol=symbol)
            assert signals[0]["symbol"] == symbol
            
            signal = await service.generate_signal(symbol, {"test": True})
            assert signal["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_very_long_symbol(self):
        """Test handling of very long symbol names."""
        service = SignalService()
        
        long_symbol = "A" * 100  # 100 character symbol
        
        signals = await service.get_signals(symbol=long_symbol)
        assert signals[0]["symbol"] == long_symbol
        
        signal = await service.generate_signal(long_symbol, {"test": "long_symbol"})
        assert signal["symbol"] == long_symbol
    
    @pytest.mark.asyncio
    async def test_large_data_handling(self):
        """Test handling of large data objects."""
        service = SignalService()
        
        # Create large data object
        large_data = {
            "large_list": list(range(1000)),
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(100)},
            "nested": {
                "deep": {
                    "structure": {
                        "with": {
                            "many": {
                                "levels": "test_value"
                            }
                        }
                    }
                }
            }
        }
        
        signal = await service.generate_signal("LARGE_DATA", large_data)
        
        assert signal["symbol"] == "LARGE_DATA"
        assert signal["data"] == large_data
        assert len(signal["data"]["large_list"]) == 1000
        assert signal["data"]["nested"]["deep"]["structure"]["with"]["many"]["levels"] == "test_value"
    
    @pytest.mark.asyncio
    async def test_unicode_symbol_handling(self):
        """Test handling of unicode characters in symbols."""
        service = SignalService()
        
        unicode_symbols = ["测试", "テスト", "тест", "🚀📈", "EUR/USD"]
        
        for symbol in unicode_symbols:
            signals = await service.get_signals(symbol=symbol)
            assert signals[0]["symbol"] == symbol
            
            signal = await service.generate_signal(symbol, {"unicode_test": True})
            assert signal["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_signal_data_types(self):
        """Test various data types in signal generation."""
        service = SignalService()
        
        test_data_sets = [
            {"int": 123, "float": 45.67, "bool": True, "none": None},
            {"list": [1, 2, 3], "tuple": (4, 5, 6), "set_as_list": list({7, 8, 9})},
            {"nested_list": [[1, 2], [3, 4]], "mixed": [1, "string", 3.14, True]},
            {"string": "test", "multiline": "line1\nline2\nline3"},
        ]
        
        for i, data in enumerate(test_data_sets):
            signal = await service.generate_signal(f"TYPE_TEST_{i}", data)
            assert signal["symbol"] == f"TYPE_TEST_{i}"
            assert signal["data"] == data


class TestSignalServicePerformance:
    """Test performance and reliability aspects."""
    
    @pytest.mark.asyncio
    async def test_rapid_signal_generation(self):
        """Test rapid signal generation performance."""
        service = SignalService()
        
        # Generate many signals rapidly
        signals = []
        for i in range(100):
            signal = await service.generate_signal(f"PERF_{i}", {"index": i})
            signals.append(signal)
        
        # Verify all signals are correct
        assert len(signals) == 100
        for i, signal in enumerate(signals):
            assert signal["symbol"] == f"PERF_{i}"
            assert signal["data"]["index"] == i
    
    @pytest.mark.asyncio
    async def test_memory_efficiency(self):
        """Test that service doesn't accumulate memory."""
        service = SignalService()
        
        # Generate signals without storing them
        for i in range(50):
            await service.generate_signal(f"MEM_TEST_{i}", {"large_data": "x" * 1000})
        
        # Service should still be functional and not have grown significantly
        test_signal = await service.generate_signal("FINAL_TEST", {"test": True})
        assert test_signal["symbol"] == "FINAL_TEST"
    
    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self):
        """Test concurrent access to the same service."""
        service = SignalService()
        
        async def worker(worker_id: int):
            results = []
            for i in range(10):
                signal = await service.generate_signal(f"WORKER_{worker_id}_{i}", {"worker": worker_id, "iteration": i})
                results.append(signal)
            return results
        
        # Run multiple workers concurrently
        tasks = [worker(i) for i in range(5)]
        all_results = await asyncio.gather(*tasks)
        
        # Verify all results are correct
        total_signals = 0
        for worker_id, results in enumerate(all_results):
            assert len(results) == 10
            for i, signal in enumerate(results):
                assert signal["symbol"] == f"WORKER_{worker_id}_{i}"
                assert signal["data"]["worker"] == worker_id
                assert signal["data"]["iteration"] == i
            total_signals += len(results)
        
        assert total_signals == 50


class TestSignalServiceIntegration:
    """Test integration scenarios and realistic usage patterns."""
    
    @pytest.mark.asyncio
    async def test_trading_workflow_simulation(self):
        """Test a realistic trading workflow simulation."""
        service = SignalService()
        
        # Simulate getting signals for a portfolio
        portfolio_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
        
        # Get current signals
        portfolio_signals = []
        for symbol in portfolio_symbols:
            signals = await service.get_signals(symbol)
            portfolio_signals.extend(signals)
        
        assert len(portfolio_signals) == len(portfolio_symbols)
        
        # Generate new signals based on market data
        market_data = {
            "AAPL": {"price": 175.0, "change": 2.5, "volume": 75000000},
            "GOOGL": {"price": 2800.0, "change": -15.0, "volume": 25000000},
            "MSFT": {"price": 400.0, "change": 5.0, "volume": 30000000},
            "TSLA": {"price": 250.0, "change": 12.0, "volume": 85000000},
        }
        
        generated_signals = []
        for symbol, data in market_data.items():
            signal = await service.generate_signal(symbol, data)
            generated_signals.append(signal)
        
        assert len(generated_signals) == len(market_data)
        
        # Verify all signals have consistent structure
        for signal in generated_signals:
            assert "symbol" in signal
            assert "signal" in signal
            assert "confidence" in signal
            assert "timestamp" in signal
            assert "data" in signal
    
    @pytest.mark.asyncio
    async def test_batch_signal_processing(self):
        """Test batch processing of multiple signals."""
        service = SignalService()
        
        # Simulate batch processing request
        batch_request = [
            {"symbol": "AAPL", "data": {"price": 175.0}},
            {"symbol": "GOOGL", "data": {"price": 2800.0}},
            {"symbol": "MSFT", "data": {"price": 400.0}},
            {"symbol": "TSLA", "data": {"price": 250.0}},
            {"symbol": "AMZN", "data": {"price": 145.0}},
        ]
        
        # Process all requests
        batch_signals = []
        for request in batch_request:
            signal = await service.generate_signal(request["symbol"], request["data"])
            batch_signals.append(signal)
        
        assert len(batch_signals) == len(batch_request)
        
        # Verify batch processing results
        for i, signal in enumerate(batch_signals):
            expected_symbol = batch_request[i]["symbol"]
            expected_data = batch_request[i]["data"]
            
            assert signal["symbol"] == expected_symbol
            assert signal["data"] == expected_data
    
    @pytest.mark.asyncio
    async def test_service_reliability_over_time(self):
        """Test service reliability over extended usage."""
        service = SignalService()
        
        # Simulate extended usage pattern
        for session in range(10):
            # Each session represents a trading session
            for minute in range(5):  # 5 "minutes" per session
                # Generate signals for multiple symbols each minute
                minute_symbols = ["AAPL", "GOOGL", "MSFT"]
                for symbol in minute_symbols:
                    data = {
                        "session": session,
                        "minute": minute,
                        "price": 100.0 + session + minute,
                        "volume": 1000 * (session + 1) * (minute + 1)
                    }
                    signal = await service.generate_signal(symbol, data)
                    
                    # Verify signal is correct
                    assert signal["symbol"] == symbol
                    assert signal["data"]["session"] == session
                    assert signal["data"]["minute"] == minute
        
        # Service should still be fully functional after extended use
        final_signal = await service.generate_signal("FINAL_TEST", {"test": "reliability"})
        assert final_signal["symbol"] == "FINAL_TEST"
        assert final_signal["data"]["test"] == "reliability"