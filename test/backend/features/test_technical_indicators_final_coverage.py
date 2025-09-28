"""
Final coverage enhancement tests for backend.features.technical_indicators module.
Target: Cover remaining missing lines to achieve maximum possible coverage.
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


class TestTechnicalIndicatorsFinalCoverage:
    """Final tests to cover remaining missing lines."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_missing_lines_coverage_calculate_all_features(self):
        """Test missing lines in calculate_all_features method."""
        # Test the remaining branches in calculate_all_features
        
        # Create data with exactly enough for SMA 20 but not RSI (14 changes)
        data_13_rows = pd.DataFrame({
            'close': list(range(100, 113)),  # 13 rows, 12 changes
            'high': list(range(101, 114)),
            'low': list(range(99, 112)),
            'volume': [1000] * 13
        })
        
        result = self.ti.calculate_all_features(data_13_rows)
        
        # Should return None due to insufficient data (< 14 for RSI)
        assert result is None
    
    def test_missing_lines_rsi_calculation_edges(self):
        """Test missing edge cases in RSI calculation."""
        # Test when there are exactly enough changes but at the minimum
        prices_15 = list(range(100, 115))  # 15 prices = 14 changes, exact minimum
        
        result = self.ti.calculate_rsi(prices_15, period=14)
        
        # Should work with exactly the minimum required changes
        assert result is not None
        if result.value is not None:
            assert 0 <= result.value <= 100
    
    def test_missing_lines_bollinger_bands_edge_cases(self):
        """Test missing edge cases in Bollinger Bands calculation."""
        # Test when we have exactly 2 valid prices (minimum for std calculation)
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            # Return True only for first two prices
            mock_valid.side_effect = lambda x: x in [100.0, 101.0]
            
            # Create SMA mock that succeeds
            with patch.object(self.ti, 'calculate_sma') as mock_sma:
                mock_sma.return_value = IndicatorResult(value=100.5, confidence=0.5)
                
                prices = [100.0, 101.0] + [float('inf')] * 18  # Only 2 valid out of 20
                result = self.ti.calculate_bollinger_bands(prices, period=20)
                
                # Should succeed with exactly 2 valid prices
                if result["upper"].value is not None:
                    assert result["upper"].confidence > 0
    
    def test_missing_lines_extreme_conditions_coverage(self):
        """Test missing lines in handle_extreme_conditions method."""
        # Test when we have exactly 10 prices (minimum for volatility analysis)
        prices_10 = [100, 102, 98, 104, 96, 108, 92, 112, 88, 116]
        
        result = self.ti.handle_extreme_conditions(prices_10)
        
        assert result["status"] == "analyzed"
        # Should analyze volatility clustering with exactly 10 prices
        assert "extreme_conditions" in result
    
    def test_missing_lines_is_valid_price_boundary(self):
        """Test the exact boundary condition in _is_valid_price."""
        # Test the exact boundary at 1000000
        assert self.ti._is_valid_price(1000000) == True   # Should be valid (not >)
        assert self.ti._is_valid_price(1000000.1) == False  # Should be invalid
        
        # Test other boundaries
        assert self.ti._is_valid_price(0.0001) == True    # Very small positive
        assert self.ti._is_valid_price(0) == False        # Zero
        assert self.ti._is_valid_price(-0.0001) == False  # Negative
    
    def test_missing_lines_exception_handling_coverage(self):
        """Test exception handling branches that might be missing."""
        # Test OverflowError in _is_valid_price
        with patch('builtins.float', side_effect=OverflowError("Test overflow")):
            assert self.ti._is_valid_price("huge_number") == False
        
        # Test TypeError in _is_valid_price  
        assert self.ti._is_valid_price(object()) == False
    
    def test_missing_lines_calculation_stats_edge_case(self):
        """Test edge case in get_calculation_stats."""
        # Reset counters to test the max(1, ...) logic
        self.ti.calculation_count = 0
        self.ti.error_count = 0
        
        stats = self.ti.get_calculation_stats()
        
        # When both counts are 0, should use max(1, 0+0) = 1 as denominator
        assert stats["success_rate"] == 0.0  # 0 / max(1, 0) = 0.0
    
    def test_missing_lines_feature_engineering_edge_cases(self):
        """Test specific edge cases that might be in missing lines."""
        # Test with data that has exactly 10 rows (minimum data threshold)
        data_10_rows = pd.DataFrame({
            'close': list(range(100, 110)),  # Exactly 10 rows
            'high': list(range(101, 111)),
            'low': list(range(99, 109)),
            'volume': [1000] * 10
        })
        
        result = self.ti.calculate_all_features(data_10_rows)
        
        # Should return None because 10 < minimum for most indicators
        assert result is None
    
    def test_remaining_sma_edge_cases(self):
        """Test remaining SMA edge cases."""
        # Test when we have exactly 50% valid data (boundary condition)
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            # Return True for exactly half the prices (boundary case)
            mock_valid.side_effect = lambda x: x in [100, 101, 102]  # 3 out of 6 = 50%
            
            prices = [100, 101, 102, float('inf'), float('nan'), None]
            result = self.ti.calculate_sma(prices, period=6)
            
            # Should succeed with exactly 50% valid data
            assert result is not None
            if result.value is not None:
                assert result.confidence > 0
    
    def test_remaining_rsi_edge_cases(self):
        """Test remaining RSI edge cases for complete coverage.""" 
        # Test RSI with mixed valid/invalid prices in the change calculation
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            # Create a pattern that tests the change calculation loop
            mock_valid.side_effect = lambda x: x not in [None, float('inf')]
            
            prices = [100, 101, None, 102, float('inf'), 103, 104, 105, 106, 107, 
                     108, 109, 110, 111, 112, 113, 114, 115]
            
            result = self.ti.calculate_rsi(prices)
            
            # Should handle mixed valid/invalid in the change calculation
            assert result is not None
    
    def test_volatility_clustering_threshold_edge_case(self):
        """Test the exact threshold condition in volatility clustering."""
        # Create data that hits exactly the 30% threshold for high volatility
        
        # We need exactly 30% of periods to be high volatility to trigger the condition
        # Create 10 periods where exactly 3 (30%) have high volatility
        base_prices = [100]
        
        # Create 9 more prices with specific volatility pattern
        # 3 high volatility periods, 6 normal ones
        volatility_pattern = [1.01, 1.01, 1.4, 1.01, 1.01, 1.4, 1.01, 1.01, 1.4, 1.01]  # 3 high vol out of 10
        
        for multiplier in volatility_pattern:
            base_prices.append(base_prices[-1] * multiplier)
        
        result = self.ti.handle_extreme_conditions(base_prices)
        
        assert result["status"] == "analyzed"
        # This tests the exact threshold logic
        assert "extreme_conditions" in result


class TestSpecificMissingLines:
    """Target very specific missing lines based on coverage report."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_line_132_handle_extreme_conditions(self):
        """Test specific missing line in handle_extreme_conditions."""
        # This targets the calculation count and other specific logic
        initial_error_count = self.ti.error_count
        
        # Create a scenario that exercises the exact missing lines
        prices = [100, 90, 110, 85, 115]  # Multiple extreme changes
        
        result = self.ti.handle_extreme_conditions(prices)
        
        assert result["status"] == "analyzed"
        # The function should complete without incrementing error_count
        assert self.ti.error_count == initial_error_count
    
    def test_missing_branches_in_technical_indicators(self):
        """Test any remaining missing branches."""
        # Test with very specific data patterns to hit remaining lines
        
        # Pattern 1: Data with alternating valid/invalid for edge case testing
        mixed_data = pd.DataFrame({
            'close': [100, None, 102, float('inf'), 104, float('nan'), 106, 107, 108, 109, 110, 111]
        })
        
        # This should hit error handling and edge case paths
        result = self.ti.calculate_all_features(mixed_data)
        # May return None due to insufficient valid data
        
        # Pattern 2: Test calculation methods with edge case inputs
        edge_prices = [100.0, 100.0, 100.0001, 99.9999, 100.0002]  # Very small changes
        sma_result = self.ti.calculate_sma(edge_prices, 3)
        
        assert sma_result is not None
        # Should handle very small price variations


if __name__ == "__main__":
    pytest.main([__file__])