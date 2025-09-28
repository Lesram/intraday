"""
Comprehensive test suite for Module 20: backend.data.market_data
Tests market data processing with resilience to malformed inputs.
"""

import pytest
import math
import pandas as pd
import numpy as np
import json
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# Import the module under test
from backend.data.market_data import MarketDataProcessor, MarketDataPoint


class TestModule20BackendDataMarketData:
    """Comprehensive test suite for market data module functionality."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.processor = MarketDataProcessor()
        self.config_processor = MarketDataProcessor({"max_items": 50, "validate_prices": True})

    def test_market_data_point_creation(self):
        """Test MarketDataPoint dataclass creation."""
        point = MarketDataPoint(
            timestamp="2025-09-20T10:00:00Z",
            open=100.0,
            high=105.0,
            low=95.0,
            close=103.0,
            volume=1000
        )
        
        assert point.timestamp == "2025-09-20T10:00:00Z"
        assert point.open == 100.0
        assert point.high == 105.0
        assert point.low == 95.0
        assert point.close == 103.0
        assert point.volume == 1000

    def test_market_data_processor_initialization_default(self):
        """Test MarketDataProcessor initialization with default config."""
        processor = MarketDataProcessor()
        
        assert processor.config == {}
        assert processor.processed_count == 0
        assert processor.error_count == 0

    def test_market_data_processor_initialization_with_config(self):
        """Test MarketDataProcessor initialization with custom config."""
        config = {"max_items": 100, "strict_validation": True}
        processor = MarketDataProcessor(config)
        
        assert processor.config == config
        assert processor.processed_count == 0
        assert processor.error_count == 0

    def test_process_tick_alias_functionality(self):
        """Test process_tick method as alias for process_raw_data."""
        test_data = {"symbol": "AAPL", "price": 150.0, "volume": 1000}
        
        tick_result = self.processor.process_tick(test_data)
        raw_result = self.processor.process_raw_data(test_data)
        
        assert tick_result == raw_result
        assert tick_result["status"] == "processed"

    def test_process_raw_data_none_input(self):
        """Test processing None input."""
        result = self.processor.process_raw_data(None)
        
        assert result["status"] == "rejected"
        assert result["error"] == "null_data"

    def test_process_raw_data_valid_dict_price(self):
        """Test processing valid dictionary with price."""
        data = {"symbol": "AAPL", "price": 150.0, "volume": 1000}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["fields_processed"] >= 1
        assert result["format"] == "dict"
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.0

    def test_process_raw_data_invalid_price_string(self):
        """Test processing invalid price string."""
        data = {"price": "invalid_price"}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_format"

    def test_process_raw_data_nan_price(self):
        """Test processing NaN price value."""
        data = {"price": float('nan')}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_value"

    def test_process_raw_data_infinite_price(self):
        """Test processing infinite price value."""
        data = {"price": float('inf')}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_value"

    def test_process_raw_data_negative_price(self):
        """Test processing negative price value."""
        data = {"price": -50.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_value"

    def test_process_raw_data_extremely_high_price(self):
        """Test processing extremely high price value."""
        data = {"price": 2000000.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "price_too_high"

    def test_process_raw_data_price_conversion_failure(self):
        """Test processing price that fails conversion."""
        data = {"price": {"nested": "object"}}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "price_conversion_failed"

    def test_process_raw_data_invalid_symbol_empty(self):
        """Test processing invalid empty symbol."""
        data = {"symbol": "", "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_symbol"

    def test_process_raw_data_invalid_symbol_too_long(self):
        """Test processing invalid symbol that's too long."""
        data = {"symbol": "VERY_LONG_SYMBOL_NAME", "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_symbol"

    def test_process_raw_data_invalid_symbol_non_string(self):
        """Test processing invalid non-string symbol."""
        data = {"symbol": 12345, "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_symbol"

    def test_process_raw_data_invalid_volume_string(self):
        """Test processing invalid volume string."""
        data = {"volume": "invalid_volume", "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_volume_format"

    def test_process_raw_data_negative_volume(self):
        """Test processing negative volume."""
        data = {"volume": -100, "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_volume_value"

    def test_process_raw_data_nan_volume(self):
        """Test processing NaN volume."""
        data = {"volume": float('nan'), "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_volume_value"

    def test_process_string_data_empty_string(self):
        """Test processing empty string data."""
        result = self.processor.process_raw_data("")
        
        assert result["status"] == "error"
        assert result["error"] == "empty_string"

    def test_process_string_data_whitespace_only(self):
        """Test processing whitespace-only string."""
        result = self.processor.process_raw_data("   \n\t   ")
        
        assert result["status"] == "error"
        assert result["error"] == "empty_string"

    def test_process_string_data_json_object(self):
        """Test processing JSON object string."""
        json_data = '{"symbol": "AAPL", "price": 150.0}'
        result = self.processor.process_raw_data(json_data)
        
        assert result["status"] == "processed"
        assert result["format"] == "dict"

    def test_process_string_data_json_array(self):
        """Test processing JSON array string."""
        json_data = '[{"symbol": "AAPL", "price": 150.0}]'
        result = self.processor.process_raw_data(json_data)
        
        assert result["status"] == "processed"
        assert result["format"] == "list"

    def test_process_string_data_invalid_json(self):
        """Test processing invalid JSON string."""
        invalid_json = '{"symbol": "AAPL", price: 150.0}'  # Missing quotes
        result = self.processor.process_raw_data(invalid_json)
        
        assert result["status"] == "error"
        assert "string_parsing" in result["error"]

    def test_process_string_data_csv_like(self):
        """Test processing CSV-like string data."""
        csv_data = "symbol,price,volume\nAAPL,150.0,1000\nGOOG,2800.0,500"
        result = self.processor.process_raw_data(csv_data)
        
        assert result["status"] == "processed"
        assert result["format"] == "csv_like"
        assert result["rows"] == 3

    def test_process_string_data_simple_string(self):
        """Test processing simple string data."""
        simple_string = "AAPL market data"
        result = self.processor.process_raw_data(simple_string)
        
        assert result["status"] == "processed"
        assert result["format"] == "string"
        assert result["length"] == len(simple_string)

    def test_process_dict_data_comprehensive_fields(self):
        """Test processing dictionary with comprehensive market data fields."""
        data = {
            "symbol": "AAPL",
            "open": 145.0,
            "high": 155.0,
            "low": 140.0,
            "close": 150.0,
            "volume": 1000000,
            "timestamp": "2025-09-20T10:00:00Z"
        }
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["fields_processed"] >= 5  # All main fields processed
        assert result["format"] == "dict"
        assert result["symbol"] == "AAPL"

    def test_process_dict_data_alternative_field_names(self):
        """Test processing dictionary with alternative field names."""
        data = {
            "vol": 1000,
            "quantity": 500,
            "time": "10:00:00",
            "date": "2025-09-20"
        }
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["fields_processed"] >= 2
        assert result["format"] == "dict"

    def test_process_dict_data_error_handling(self):
        """Test dictionary processing error handling."""
        # Mock _validate_numeric_field to raise an exception
        with patch.object(self.processor, '_validate_numeric_field', side_effect=Exception("Validation error")):
            data = {"price": 100.0}
            result = self.processor.process_raw_data(data)
            
            assert result["status"] == "error"
            assert "dict_processing" in result["error"]

    def test_process_list_data_empty_list(self):
        """Test processing empty list."""
        result = self.processor.process_raw_data([])
        
        assert result["status"] == "error"
        assert result["error"] == "empty_list"

    def test_process_list_data_dict_items(self):
        """Test processing list with dictionary items."""
        data = [
            {"symbol": "AAPL", "price": 150.0},
            {"symbol": "GOOGL", "price": 2800.0},
            {"symbol": "MSFT", "price": 300.0}
        ]
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["items_processed"] >= 1
        assert result["total_items"] == 3
        assert result["format"] == "list"

    def test_process_list_data_numeric_items(self):
        """Test processing list with numeric items."""
        data = [100.0, 105.0, 98.0, 103.0]
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["items_processed"] >= 1
        assert result["total_items"] == 4
        assert result["format"] == "list"

    def test_process_list_data_large_list_limit(self):
        """Test processing large list with processing limit."""
        # Create a list with more than 100 items
        data = [{"price": i} for i in range(150)]
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["total_items"] == 150
        # Processing is limited to 100 items

    def test_process_list_data_error_handling(self):
        """Test list processing error handling."""
        # Mock _process_dict_data to raise an exception
        with patch.object(self.processor, '_process_dict_data', side_effect=Exception("Processing error")):
            data = [{"price": 100.0}]
            result = self.processor.process_raw_data(data)
            
            assert result["status"] == "error"
            assert "list_processing" in result["error"]

    def test_process_iterable_data_tuple(self):
        """Test processing tuple as iterable data."""
        data = (100.0, 105.0, 98.0)
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["format"] == "list"

    def test_process_iterable_data_generator(self):
        """Test processing generator as iterable data."""
        def data_generator():
            for i in range(5):
                yield {"price": 100.0 + i}
        
        result = self.processor.process_raw_data(data_generator())
        
        assert result["status"] == "processed"
        assert result["format"] == "list"

    def test_process_iterable_data_error_handling(self):
        """Test iterable processing error handling."""
        # Create an iterable that fails when converted to list
        class FailingIterable:
            def __iter__(self):
                raise Exception("Iteration failed")
        
        result = self.processor.process_raw_data(FailingIterable())
        
        assert result["status"] == "error"
        assert "iterable_processing" in result["error"]

    def test_process_raw_data_unsupported_type(self):
        """Test processing unsupported data type."""
        class UnsupportedType:
            pass
        
        result = self.processor.process_raw_data(UnsupportedType())
        
        assert result["status"] == "rejected"
        assert result["error"] == "unsupported_type"

    def test_process_raw_data_exception_handling(self):
        """Test general exception handling in process_raw_data."""
        # Mock _process_dict_data to raise an exception
        with patch.object(self.processor, '_process_dict_data', side_effect=Exception("Unexpected error")):
            data = {"price": 100.0}
            result = self.processor.process_raw_data(data)
            
            assert result["status"] == "error"
            assert "Unexpected error" in result["error"]
            assert self.processor.error_count > 0

    def test_validate_numeric_field_none_value(self):
        """Test numeric field validation with None value."""
        result = self.processor._validate_numeric_field(None, "price")
        assert result is False

    def test_validate_numeric_field_string_conversion(self):
        """Test numeric field validation with string conversion."""
        result = self.processor._validate_numeric_field("100.5", "price")
        assert result is True

    def test_validate_numeric_field_integer_conversion(self):
        """Test numeric field validation with integer conversion."""
        result = self.processor._validate_numeric_field(100, "volume")
        assert result is True

    def test_validate_numeric_field_float_conversion(self):
        """Test numeric field validation with float conversion."""
        result = self.processor._validate_numeric_field(100.5, "price")
        assert result is True

    def test_validate_numeric_field_invalid_type(self):
        """Test numeric field validation with invalid type."""
        result = self.processor._validate_numeric_field({"nested": "object"}, "price")
        assert result is False

    def test_validate_numeric_field_nan_value(self):
        """Test numeric field validation with NaN value."""
        result = self.processor._validate_numeric_field(float('nan'), "price")
        assert result is False

    def test_validate_numeric_field_infinite_value(self):
        """Test numeric field validation with infinite value."""
        result = self.processor._validate_numeric_field(float('inf'), "price")
        assert result is False

    def test_validate_numeric_field_price_range_valid(self):
        """Test price field validation within valid range."""
        result = self.processor._validate_numeric_field(150.0, "price")
        assert result is True

    def test_validate_numeric_field_price_range_invalid_low(self):
        """Test price field validation below valid range."""
        result = self.processor._validate_numeric_field(0, "price")
        assert result is False

    def test_validate_numeric_field_price_range_invalid_high(self):
        """Test price field validation above valid range."""
        result = self.processor._validate_numeric_field(2000000, "price")
        assert result is False

    def test_validate_numeric_field_volume_valid(self):
        """Test volume field validation with valid value."""
        result = self.processor._validate_numeric_field(1000, "volume")
        assert result is True

    def test_validate_numeric_field_volume_zero(self):
        """Test volume field validation with zero value."""
        result = self.processor._validate_numeric_field(0, "volume")
        assert result is True

    def test_validate_numeric_field_volume_negative(self):
        """Test volume field validation with negative value."""
        result = self.processor._validate_numeric_field(-100, "volume")
        assert result is False

    def test_validate_numeric_field_conversion_error(self):
        """Test numeric field validation with conversion error."""
        result = self.processor._validate_numeric_field("not_a_number", "price")
        assert result is False

    def test_validate_numeric_field_overflow_error(self):
        """Test numeric field validation with overflow error."""
        # Create a value that causes overflow
        with patch('builtins.float', side_effect=OverflowError("Overflow")):
            result = self.processor._validate_numeric_field("1e400", "price")
            assert result is False

    def test_get_processing_stats_initial(self):
        """Test processing statistics with initial values."""
        stats = self.processor.get_processing_stats()
        
        assert stats["processed_count"] == 0
        assert stats["error_count"] == 0
        assert stats["success_rate"] == 0

    def test_get_processing_stats_after_processing(self):
        """Test processing statistics after processing data."""
        # Process some data to update counters
        self.processor.process_raw_data({"symbol": "AAPL", "price": 150.0})
        self.processor.process_raw_data({"symbol": "GOOGL", "price": 2800.0})
        self.processor.process_raw_data(None)  # This should increment error_count
        
        stats = self.processor.get_processing_stats()
        
        assert stats["processed_count"] == 2
        assert stats["error_count"] == 0  # None input returns rejected, not error
        assert stats["success_rate"] == 1.0

    def test_get_processing_stats_with_errors(self):
        """Test processing statistics with errors."""
        # Mock to cause an exception
        with patch.object(self.processor, '_process_dict_data', side_effect=Exception("Error")):
            self.processor.process_raw_data({"price": 100.0})
        
        stats = self.processor.get_processing_stats()
        
        assert stats["error_count"] > 0
        assert stats["success_rate"] < 1.0

    def test_processor_state_persistence(self):
        """Test that processor maintains state across multiple calls."""
        initial_processed = self.processor.processed_count
        initial_errors = self.processor.error_count
        
        # Process multiple items
        self.processor.process_raw_data({"symbol": "AAPL", "price": 150.0})
        self.processor.process_raw_data({"symbol": "GOOGL", "price": 2800.0})
        
        assert self.processor.processed_count == initial_processed + 2
        assert self.processor.error_count == initial_errors

    def test_config_usage(self):
        """Test that processor uses configuration correctly."""
        config = {"custom_setting": "test_value"}
        processor = MarketDataProcessor(config)
        
        assert processor.config["custom_setting"] == "test_value"

    @patch('backend.data.market_data.logger')
    def test_logging_on_error(self, mock_logger):
        """Test that errors are properly logged."""
        # Mock to cause an exception
        with patch.object(self.processor, '_process_dict_data', side_effect=Exception("Test error")):
            self.processor.process_raw_data({"price": 100.0})
        
        mock_logger.warning.assert_called_once()
        assert "Market data processing error" in str(mock_logger.warning.call_args)

    def test_edge_case_zero_string_price(self):
        """Test edge case with zero string price."""
        data = {"price": "0"}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_value"

    def test_edge_case_zero_float_price(self):
        """Test edge case with zero float price."""
        data = {"price": 0.0}
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "invalid_price_value"

    def test_edge_case_zero_string_volume(self):
        """Test edge case with zero string volume."""
        data = {"volume": "0", "price": 100.0}
        result = self.processor.process_raw_data(data)
        
        # Zero volume should be allowed and processed
        assert result["status"] == "processed"

    def test_comprehensive_field_coverage(self):
        """Test comprehensive coverage of all field types."""
        data = {
            "symbol": "TEST",
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 103.0,
            "price": 103.0,
            "volume": 1000,
            "vol": 500,
            "quantity": 750,
            "timestamp": "2025-09-20T10:00:00Z",
            "time": "10:00:00",
            "date": "2025-09-20",
            "datetime": "2025-09-20T10:00:00Z"
        }
        
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "processed"
        assert result["fields_processed"] >= 8  # Should process most fields
        assert result["format"] == "dict"
        assert result["symbol"] == "TEST"
        assert result["price"] == 103.0

    def test_module_level_imports(self):
        """Test that all required modules are properly imported."""
        import backend.data.market_data as module
        
        assert hasattr(module, 'MarketDataProcessor')
        assert hasattr(module, 'MarketDataPoint')
        assert hasattr(module, 'math')
        assert hasattr(module, 'pd')
        assert hasattr(module, 'np')
        assert hasattr(module, 'logging')

    def test_module_level_logger(self):
        """Test module-level logger configuration."""
        import backend.data.market_data as module
        
        assert hasattr(module, 'logger')
        assert module.logger.name == 'backend.data.market_data'

    def test_dataclass_field_types(self):
        """Test MarketDataPoint field types."""
        point = MarketDataPoint(
            timestamp="2025-09-20T10:00:00Z",
            open=100.0,
            high=105.0,
            low=95.0,
            close=103.0,
            volume=1000
        )
        
        assert isinstance(point.timestamp, str)
        assert isinstance(point.open, float)
        assert isinstance(point.high, float)
        assert isinstance(point.low, float)
        assert isinstance(point.close, float)
        assert isinstance(point.volume, int)

    def test_processor_method_coverage(self):
        """Test that all processor methods are accessible."""
        processor = MarketDataProcessor()
        
        assert hasattr(processor, 'process_tick')
        assert hasattr(processor, 'process_raw_data')
        assert hasattr(processor, '_process_string_data')
        assert hasattr(processor, '_process_dict_data')
        assert hasattr(processor, '_process_list_data')
        assert hasattr(processor, '_process_iterable_data')
        assert hasattr(processor, '_validate_numeric_field')
        assert hasattr(processor, 'get_processing_stats')

    def test_realistic_market_data_scenario(self):
        """Test realistic market data processing scenario."""
        # Simulate real market data feed
        market_feed = [
            {"symbol": "AAPL", "price": 175.50, "volume": 45000, "timestamp": "2025-09-20T09:30:00Z"},
            {"symbol": "GOOGL", "price": 2750.25, "volume": 12000, "timestamp": "2025-09-20T09:30:01Z"},
            {"symbol": "MSFT", "price": 325.75, "volume": 38000, "timestamp": "2025-09-20T09:30:02Z"},
            None,  # Bad data
            {"symbol": "TSLA", "price": "bad_price", "volume": 25000},  # Invalid price
            {"symbol": "AMZN", "price": 3250.00, "volume": 15000, "timestamp": "2025-09-20T09:30:03Z"}
        ]
        
        results = []
        for data in market_feed:
            result = self.processor.process_raw_data(data)
            results.append(result)
        
        # Check results
        assert results[0]["status"] == "processed"  # AAPL
        assert results[1]["status"] == "processed"  # GOOGL
        assert results[2]["status"] == "processed"  # MSFT
        assert results[3]["status"] == "rejected"   # None
        assert results[4]["status"] == "rejected"   # Bad price
        assert results[5]["status"] == "processed"  # AMZN
        
        # Check statistics
        stats = self.processor.get_processing_stats()
        assert stats["processed_count"] == 4
        assert stats["success_rate"] > 0.6

    def test_volume_conversion_error_coverage(self):
        """Test volume conversion error coverage for lines 82-83."""
        # Create a class that raises TypeError when converted to float
        class BadVolume:
            def __float__(self):
                raise TypeError("Cannot convert to float")
        
        # Test data with problematic volume that will trigger lines 82-83
        data = {
            "symbol": "TEST",
            "price": 100.0,
            "volume": BadVolume()
        }
        
        result = self.processor.process_raw_data(data)
        
        assert result["status"] == "rejected"
        assert result["error"] == "volume_conversion_failed"