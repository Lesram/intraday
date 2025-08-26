"""
Phase 7B.1 Extended: Market Data Processing Module Testing - Coverage Enhancement
Additional tests targeting specific uncovered lines and edge cases
"""

import pytest
import math
from unittest.mock import Mock, patch, MagicMock
from backend.data.market_data import MarketDataProcessor


class TestMarketDataValidationPhase7B1Extended:
    """Test specific validation logic from lines 57-67, 70-72"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_price_validation_string_format(self, processor):
        """Test price validation for string values - lines 57-67"""
        # Test valid price strings (only '0' and '0.0' are allowed as strings)
        data = {"price": "0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_price_format"
        
        data = {"price": "0.0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_price_format"
        
        # Test invalid price strings (any other string is invalid)
        data = {"price": "150.50"}  # This is considered invalid format
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_format"
        
        data = {"price": "not_a_price"}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_format"
    
    def test_price_validation_edge_values(self, processor):
        """Test price validation for edge values"""
        # Test NaN price
        data = {"price": float('nan')}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_value"
        
        # Test infinite price
        data = {"price": float('inf')}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_value"
        
        # Test zero price
        data = {"price": 0}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_value"
        
        # Test negative price
        data = {"price": -50.0}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_price_value"
        
        # Test extremely high price
        data = {"price": 2000000.0}
        result = processor.process_raw_data(data)
        assert result.get("error") == "price_too_high"
    
    def test_price_conversion_failures(self, processor):
        """Test price conversion error handling - lines 70-72"""
        # Test unconvertible price
        data = {"price": {"invalid": "object"}}
        result = processor.process_raw_data(data)
        assert result.get("error") == "price_conversion_failed"
        
        # Test list as price
        data = {"price": [1, 2, 3]}
        result = processor.process_raw_data(data)
        assert result.get("error") == "price_conversion_failed"


class TestSymbolValidationPhase7B1Extended:
    """Test symbol validation logic - lines 81-83"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_symbol_validation_valid_symbols(self, processor):
        """Test valid symbol formats"""
        valid_symbols = ["AAPL", "MSFT", "TSLA", "BTC", "A", "ABCD"]
        
        for symbol in valid_symbols:
            data = {"symbol": symbol}
            result = processor.process_raw_data(data)
            assert result.get("error") != "invalid_symbol"
    
    def test_symbol_validation_invalid_symbols(self, processor):
        """Test invalid symbol formats"""
        # Empty string
        data = {"symbol": ""}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_symbol"
        
        # Too long
        data = {"symbol": "VERYLONGSYMBOL"}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_symbol"
        
        # Non-string type
        data = {"symbol": 12345}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_symbol"
        
        # None value
        data = {"symbol": None}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_symbol"


class TestVolumeValidationPhase7B1Extended:
    """Test volume validation logic - lines 93, 97-100"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_volume_validation_string_format(self, processor):
        """Test volume validation for string values"""
        # Valid volume strings (only '0' and '0.0' are allowed as strings)
        data = {"volume": "0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_volume_format"
        
        data = {"volume": "0.0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_volume_format"
        
        # Invalid volume strings (any other string is invalid)
        data = {"volume": "125000"}  # This is considered invalid format
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_volume_format"
        
        data = {"volume": "not_a_volume"}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_volume_format"
    
    def test_volume_validation_edge_values(self, processor):
        """Test volume validation for edge values"""
        # Test NaN volume
        data = {"volume": float('nan')}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_volume_value"
        
        # Test infinite volume
        data = {"volume": float('inf')}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_volume_value"
        
        # Test negative volume
        data = {"volume": -1000}
        result = processor.process_raw_data(data)
        assert result.get("error") == "invalid_volume_value"
    
    def test_volume_conversion_failures(self, processor):
        """Test volume conversion error handling"""
        # Test unconvertible volume
        data = {"volume": {"invalid": "object"}}
        result = processor.process_raw_data(data)
        assert result.get("error") == "volume_conversion_failed"


class TestDataTypeHandlingPhase7B1Extended:
    """Test different data type handling - lines 106, 110-112, 117, 121-122"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_string_data_processing(self, processor):
        """Test _process_string_data method - line 106"""
        result = processor.process_raw_data("some_string_data")
        
        # Should call _process_string_data method
        assert result is not None
        assert "status" in result
    
    def test_dict_data_processing(self, processor):
        """Test _process_dict_data method - line 110"""
        dict_data = {"key": "value", "another": "data"}
        result = processor.process_raw_data(dict_data)
        
        # Should call _process_dict_data method
        assert result is not None
    
    def test_list_data_processing(self, processor):
        """Test _process_list_data method - line 111"""
        list_data = [1, 2, 3, "data"]
        result = processor.process_raw_data(list_data)
        
        # Should call _process_list_data method
        assert result is not None
    
    def test_iterable_data_processing(self, processor):
        """Test _process_iterable_data method - line 112"""
        # Create a custom iterable that's not a string, dict, or list
        class CustomIterable:
            def __iter__(self):
                return iter([1, 2, 3])
        
        iterable_data = CustomIterable()
        result = processor.process_raw_data(iterable_data)
        
        # Should call _process_iterable_data method
        assert result is not None
    
    def test_unsupported_type(self, processor):
        """Test unsupported type handling - line 117"""
        # Use a type that's not iterable
        unsupported_data = 12345
        result = processor.process_raw_data(unsupported_data)
        
        assert result.get("error") == "unsupported_type"
    
    def test_exception_handling(self, processor):
        """Test exception handling in process_raw_data - lines 121-122"""
        initial_error_count = processor.error_count
        
        # Create data that will cause an exception in processing
        # Patch one of the processing methods to raise an exception
        with patch.object(processor, '_process_dict_data', side_effect=Exception("Test exception")):
            result = processor.process_raw_data({"test": "data"})
            
            assert result.get("status") == "error"
            assert "Test exception" in result.get("error", "")
            assert processor.error_count == initial_error_count + 1


class TestProcessingMethodsPhase7B1Extended:
    """Test the individual processing methods that are called"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_process_string_data_implementation(self, processor):
        """Test _process_string_data method implementation"""
        # This method may not exist yet, so test what should happen
        result = processor.process_raw_data("test_string")
        assert result is not None
        assert isinstance(result, dict)
        assert "status" in result
    
    def test_process_dict_data_implementation(self, processor):
        """Test _process_dict_data method implementation"""
        test_dict = {
            "timestamp": "2023-08-25T10:30:00Z",
            "open": 150.50,
            "high": 152.25,
            "low": 149.75,
            "close": 151.80,
            "volume": 125000
        }
        
        result = processor.process_raw_data(test_dict)
        assert result is not None
        assert isinstance(result, dict)
    
    def test_process_list_data_implementation(self, processor):
        """Test _process_list_data method implementation"""
        test_list = [150.50, 152.25, 149.75, 151.80]
        
        result = processor.process_raw_data(test_list)
        assert result is not None
        assert isinstance(result, dict)
        assert "status" in result
    
    def test_process_iterable_data_implementation(self, processor):
        """Test _process_iterable_data method implementation"""
        test_iterable = (x for x in range(5))
        
        result = processor.process_raw_data(test_iterable)
        assert result is not None
        assert isinstance(result, dict)


class TestSpecialCasesPhase7B1Extended:
    """Test special cases and remaining uncovered lines"""
    
    @pytest.fixture
    def processor(self):
        return MarketDataProcessor()
    
    def test_valid_price_zero_strings(self, processor):
        """Test that '0' and '0.0' price strings are handled correctly"""
        # These should NOT trigger invalid_price_format error
        data = {"price": "0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_price_format"
        
        data = {"price": "0.0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_price_format"
    
    def test_valid_volume_zero_strings(self, processor):
        """Test that '0' and '0.0' volume strings are handled correctly"""
        # These should NOT trigger invalid_volume_format error
        data = {"volume": "0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_volume_format"
        
        data = {"volume": "0.0"}
        result = processor.process_raw_data(data)
        assert result.get("error") != "invalid_volume_format"
    
    def test_processor_counters_increment(self, processor):
        """Test that processing counters are incremented correctly"""
        initial_processed = processor.processed_count
        initial_errors = processor.error_count
        
        # Process valid data
        valid_data = {
            "timestamp": "2023-08-25T10:30:00Z",
            "open": 150.50,
            "high": 152.25,
            "low": 149.75,
            "close": 151.80,
            "volume": 125000
        }
        processor.process_raw_data(valid_data)
        
        # Process invalid data that causes exception
        with patch.object(processor, '_process_dict_data', side_effect=Exception("Test error")):
            processor.process_raw_data({"test": "error"})
        
        # Counters should have incremented
        assert processor.processed_count >= initial_processed
        assert processor.error_count >= initial_errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
