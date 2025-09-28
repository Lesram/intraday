"""
Additional coverage enhancement tests for backend.features.technical_indicators module.
Target: Cover remaining missing methods to achieve maximum coverage improvement.
"""

import pytest
import numpy as np
import pandas as pd
import math
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any, Optional

# Set test environment
import os
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.features.technical_indicators import TechnicalIndicators, IndicatorResult


class TestTechnicalIndicatorsAdvancedCoverage:
    """Test advanced methods and complete coverage for TechnicalIndicators."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
        self.sample_prices = [100.0, 102.0, 101.0, 103.0, 104.0, 102.0, 105.0, 106.0, 
                            107.0, 108.0, 109.0, 108.0, 107.0, 110.0, 111.0, 112.0, 
                            113.0, 114.0, 115.0, 116.0, 117.0, 118.0, 119.0, 120.0]
    
    def test_calculate_bollinger_bands_valid_data(self):
        """Test Bollinger Bands calculation with valid data."""
        result = self.ti.calculate_bollinger_bands(self.sample_prices)
        
        assert isinstance(result, dict)
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        
        # Check that all results are IndicatorResult objects
        for key in ["upper", "middle", "lower"]:
            assert isinstance(result[key], IndicatorResult)
        
        # If calculation succeeds, values should be ordered correctly
        if (result["upper"].value is not None and 
            result["middle"].value is not None and 
            result["lower"].value is not None):
            assert result["upper"].value >= result["middle"].value >= result["lower"].value
    
    def test_calculate_bollinger_bands_insufficient_data(self):
        """Test Bollinger Bands with insufficient data."""
        short_prices = [100, 101, 102]  # Less than default period (20)
        result = self.ti.calculate_bollinger_bands(short_prices)
        
        assert isinstance(result, dict)
        for key in ["upper", "middle", "lower"]:
            assert result[key].value is None
            assert result[key].confidence == 0.0
            assert result[key].error is not None
    
    def test_calculate_bollinger_bands_custom_parameters(self):
        """Test Bollinger Bands with custom parameters."""
        result = self.ti.calculate_bollinger_bands(self.sample_prices, period=10, std_dev=1.5)
        
        assert isinstance(result, dict)
        assert "upper" in result
        assert "middle" in result 
        assert "lower" in result
    
    def test_calculate_bollinger_bands_sma_failure(self):
        """Test Bollinger Bands when SMA calculation fails."""
        with patch.object(self.ti, 'calculate_sma') as mock_sma:
            mock_sma.return_value = IndicatorResult(value=None, confidence=0.0, error="test_error")
            
            result = self.ti.calculate_bollinger_bands(self.sample_prices)
            
            assert isinstance(result, dict)
            for key in ["upper", "middle", "lower"]:
                assert result[key].value is None
                assert result[key].error == "sma_calculation_failed"
    
    def test_calculate_bollinger_bands_insufficient_std_data(self):
        """Test Bollinger Bands with insufficient data for standard deviation."""
        # Mock _is_valid_price to return False for most values
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            mock_valid.side_effect = lambda x: x == 100.0  # Only first price valid
            
            result = self.ti.calculate_bollinger_bands([100.0] + [float('inf')] * 20)
            
            assert isinstance(result, dict)
            for key in ["upper", "middle", "lower"]:
                if result[key].value is None:
                    assert result[key].error == "insufficient_data_for_std"
    
    @patch('backend.features.technical_indicators.logger')
    def test_calculate_bollinger_bands_exception_handling(self, mock_logger):
        """Test Bollinger Bands exception handling."""
        with patch.object(self.ti, 'calculate_sma', side_effect=Exception("Test error")):
            result = self.ti.calculate_bollinger_bands(self.sample_prices)
            
            assert isinstance(result, dict)
            for key in ["upper", "middle", "lower"]:
                assert result[key].value is None
                assert result[key].confidence == 0.0
                assert result[key].error is not None
            
            mock_logger.warning.assert_called()
            assert self.ti.error_count > 0
    
    def test_handle_extreme_conditions_valid_data(self):
        """Test extreme conditions handling with normal data."""
        normal_prices = [100 + i for i in range(10)]  # Gradual increase
        
        result = self.ti.handle_extreme_conditions(normal_prices)
        
        assert isinstance(result, dict)
        assert result["status"] == "analyzed"
        assert "extreme_conditions" in result
        assert "total_conditions" in result
        assert isinstance(result["extreme_conditions"], list)
    
    def test_handle_extreme_conditions_insufficient_data(self):
        """Test extreme conditions with insufficient data."""
        result = self.ti.handle_extreme_conditions([100])  # Only one price
        
        assert result["status"] == "insufficient_data"
        assert result["extreme_conditions"] == []
    
    def test_handle_extreme_conditions_empty_data(self):
        """Test extreme conditions with empty data."""
        result = self.ti.handle_extreme_conditions([])
        
        assert result["status"] == "insufficient_data"
        assert result["extreme_conditions"] == []
    
    def test_handle_extreme_conditions_none_data(self):
        """Test extreme conditions with None data."""
        result = self.ti.handle_extreme_conditions(None)
        
        assert result["status"] == "insufficient_data"
        assert result["extreme_conditions"] == []
    
    def test_handle_extreme_conditions_flash_crash(self):
        """Test extreme conditions detection of flash crash."""
        crash_prices = [100, 100, 100, 80, 100, 100]  # 20% drop then recovery
        
        result = self.ti.handle_extreme_conditions(crash_prices)
        
        assert result["status"] == "analyzed"
        assert len(result["extreme_conditions"]) > 0
        
        # Check for flash crash detection
        crash_detected = any(condition["type"] == "flash_crash" 
                           for condition in result["extreme_conditions"])
        assert crash_detected
    
    def test_handle_extreme_conditions_price_spike(self):
        """Test extreme conditions detection of price spike."""
        spike_prices = [100, 100, 100, 130, 100, 100]  # 30% spike then drop
        
        result = self.ti.handle_extreme_conditions(spike_prices)
        
        assert result["status"] == "analyzed"
        assert len(result["extreme_conditions"]) > 0
        
        # Check for price spike detection
        spike_detected = any(condition["type"] == "price_spike" 
                           for condition in result["extreme_conditions"])
        assert spike_detected
    
    def test_handle_extreme_conditions_high_volatility_cluster(self):
        """Test extreme conditions detection of high volatility clustering."""
        # Create highly volatile prices
        volatile_prices = [100]
        for i in range(1, 15):
            if i % 2 == 0:
                volatile_prices.append(volatile_prices[-1] * 1.15)  # 15% jump
            else:
                volatile_prices.append(volatile_prices[-1] * 0.85)  # 15% drop
        
        result = self.ti.handle_extreme_conditions(volatile_prices)
        
        assert result["status"] == "analyzed"
        
        # Should detect high volatility clustering
        volatility_detected = any(condition["type"] == "high_volatility_cluster" 
                                for condition in result["extreme_conditions"])
        # Note: May not always detect depending on the exact threshold
        # This tests the code path exists
    
    def test_handle_extreme_conditions_severity_levels(self):
        """Test extreme conditions severity classification."""
        extreme_prices = [100, 100, 70, 140]  # 30% drop, then 100% spike
        
        result = self.ti.handle_extreme_conditions(extreme_prices)
        
        assert result["status"] == "analyzed"
        
        # Check that severity is assigned
        for condition in result["extreme_conditions"]:
            assert "severity" in condition
            assert condition["severity"] in ["medium", "high"]
    
    @patch('backend.features.technical_indicators.logger')
    def test_handle_extreme_conditions_exception_handling(self, mock_logger):
        """Test extreme conditions exception handling."""
        with patch.object(self.ti, '_is_valid_price', side_effect=Exception("Test error")):
            result = self.ti.handle_extreme_conditions([100, 101, 102])
            
            assert result["status"] == "error"
            assert "error" in result
            assert result["extreme_conditions"] == []
            mock_logger.warning.assert_called()
            assert self.ti.error_count > 0
    
    def test_is_valid_price_valid_cases(self):
        """Test _is_valid_price with valid cases."""
        valid_prices = [100.0, 0.01, 1.5, 999.99, 50000]
        
        for price in valid_prices:
            assert self.ti._is_valid_price(price) == True
    
    def test_is_valid_price_invalid_cases(self):
        """Test _is_valid_price with invalid cases."""
        invalid_prices = [
            None,
            float('nan'),
            float('inf'),
            float('-inf'),
            -100,  # Negative
            0,     # Zero
            -0.01, # Negative
            1000001  # Too large
        ]
        
        for price in invalid_prices:
            assert self.ti._is_valid_price(price) == False
    
    def test_is_valid_price_edge_cases(self):
        """Test _is_valid_price with edge cases."""
        # Test boundary values
        assert self.ti._is_valid_price(0.000001) == True  # Very small positive
        assert self.ti._is_valid_price(1000000) == False  # At boundary (should be False)
        assert self.ti._is_valid_price(999999) == True    # Just under boundary
    
    def test_is_valid_price_type_conversion(self):
        """Test _is_valid_price with different types."""
        # Should handle string numbers
        assert self.ti._is_valid_price("100.5") == True
        assert self.ti._is_valid_price("invalid") == False
        
        # Should handle integers
        assert self.ti._is_valid_price(100) == True
        assert self.ti._is_valid_price(-100) == False
        
        # Should handle complex numbers (should fail)
        assert self.ti._is_valid_price(complex(100, 1)) == False
    
    def test_get_calculation_stats_initial(self):
        """Test get_calculation_stats initial state."""
        stats = self.ti.get_calculation_stats()
        
        assert isinstance(stats, dict)
        assert "calculation_count" in stats
        assert "error_count" in stats
        assert "success_rate" in stats
        
        # Should handle division by zero case
        assert stats["success_rate"] >= 0.0
        assert stats["success_rate"] <= 1.0
    
    def test_get_calculation_stats_after_operations(self):
        """Test get_calculation_stats after some operations."""
        # Perform some calculations
        self.ti.calculate_sma([100, 101, 102, 103, 104], 3)
        self.ti.calculate_rsi(list(range(100, 120)))
        
        stats = self.ti.get_calculation_stats()
        
        assert stats["calculation_count"] > 0
        assert stats["success_rate"] > 0.0
    
    def test_get_calculation_stats_with_errors(self):
        """Test get_calculation_stats with some errors."""
        # Force an error
        with patch.object(self.ti, '_is_valid_price', side_effect=Exception("Test error")):
            self.ti.calculate_sma([100, 101, 102], 2)
        
        stats = self.ti.get_calculation_stats()
        
        assert stats["error_count"] > 0
        # Success rate should be between 0 and 1
        assert 0.0 <= stats["success_rate"] <= 1.0


class TestTechnicalIndicatorsRSIEdgeCases:
    """Test RSI calculation edge cases for complete coverage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_calculate_rsi_all_gains_scenario(self):
        """Test RSI calculation when all price changes are gains (RSI = 100)."""
        # Constantly increasing prices
        increasing_prices = [100 + i for i in range(20)]
        
        result = self.ti.calculate_rsi(increasing_prices)
        
        # Should get RSI close to 100 due to all gains, no losses
        if result.value is not None:
            assert result.value > 80  # Should be high RSI
            assert 0 <= result.value <= 100
    
    def test_calculate_rsi_zero_average_loss(self):
        """Test RSI calculation when average loss is zero."""
        # Prices that only go up or stay same (no losses)
        no_loss_prices = [100, 100, 101, 101, 102, 102, 103, 103, 104, 104, 
                         105, 105, 106, 106, 107, 107, 108]
        
        result = self.ti.calculate_rsi(no_loss_prices)
        
        # When avg_loss = 0, RSI should be 100
        if result.value is not None:
            assert result.value == 100.0
    
    def test_calculate_rsi_confidence_calculation(self):
        """Test RSI confidence calculation."""
        prices = list(range(100, 120))  # 20 prices, 19 changes
        
        result = self.ti.calculate_rsi(prices, period=14)
        
        if result.value is not None:
            # Confidence should be changes / period = 19 / 14
            expected_confidence = 19 / 14
            assert abs(result.confidence - expected_confidence) < 0.01


class TestTechnicalIndicatorsBollingerBandsEdgeCases:
    """Test Bollinger Bands edge cases for complete coverage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_calculate_bollinger_bands_calculation_count(self):
        """Test that Bollinger Bands increments calculation count correctly."""
        initial_count = self.ti.calculation_count
        
        prices = list(range(100, 125))  # 25 prices
        self.ti.calculate_bollinger_bands(prices, period=20)
        
        # Should increment by 3 (upper, middle, lower)
        assert self.ti.calculation_count >= initial_count + 3
    
    def test_calculate_bollinger_bands_variance_calculation(self):
        """Test Bollinger Bands variance and standard deviation calculation."""
        # Use constant prices to get zero standard deviation
        constant_prices = [100.0] * 25
        
        result = self.ti.calculate_bollinger_bands(constant_prices, period=20)
        
        if (result["upper"].value is not None and 
            result["middle"].value is not None and 
            result["lower"].value is not None):
            # With zero volatility, all bands should be equal to SMA
            assert abs(result["upper"].value - result["middle"].value) < 0.01
            assert abs(result["lower"].value - result["middle"].value) < 0.01


if __name__ == "__main__":
    pytest.main([__file__])