#!/usr/bin/env python3
"""
Module 4E: Technical Indicators - Direct method coverage tests
Target: backend/features/technical_indicators.py
"""

import os
import sys
import importlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def _import_module(name: str):
    try:
        return importlib.import_module(name), None
    except Exception as e:
        return None, e


def test_technical_indicators_importable():
    mod, err = _import_module("backend.features.technical_indicators")
    if mod is None:
        pytest.skip(f"backend.features.technical_indicators not importable in this env: {err}")
    assert hasattr(mod, "__name__")


def test_technical_indicators_has_candidate_exports():
    mod, err = _import_module("backend.features.technical_indicators")
    if mod is None:
        pytest.skip("backend.features.technical_indicators not importable")
    # Loosely check for common patterns
    attrs = ["TechnicalIndicators", "IndicatorResult"]
    assert any(hasattr(mod, a) for a in attrs)


def test_technical_indicators_direct_methods():
    """Test TechnicalIndicators methods directly to increase coverage."""
    # Create stubs for numpy and pandas if not available
    if "numpy" not in sys.modules:
        import types
        np = types.ModuleType("numpy")
        
        def mean(arr):
            return sum(arr) / len(arr) if arr else 0
        
        def std(arr):
            if not arr or len(arr) < 2:
                return 0
            m = mean(arr)
            return (sum((x - m) ** 2 for x in arr) / len(arr)) ** 0.5
        
        def array_max(arr):
            return __builtins__['max'](arr) if arr else 0
        
        def array_min(arr):
            return __builtins__['min'](arr) if arr else 0
        
        np.mean = mean
        np.std = std
        np.max = array_max
        np.min = array_min
        np.nan = float('nan')
        np.inf = float('inf')
        sys.modules["numpy"] = np
    
    if "pandas" not in sys.modules:
        import types
        pd = types.ModuleType("pandas")
        
        class DataFrame:
            def __init__(self, data=None):
                if data is None:
                    data = {}
                self.data = data
                self._empty = len(data) == 0
            
            @property
            def empty(self):
                return self._empty
            
            @property
            def columns(self):
                return list(self.data.keys()) if self.data else []
            
            def __getitem__(self, key):
                if key in self.data:
                    class Series:
                        def __init__(self, values):
                            self._values = values if isinstance(values, list) else [values]
                        
                        @property
                        def values(self):
                            return self
                        
                        def tolist(self):
                            return self._values
                    return Series(self.data[key])
                raise KeyError(key)
        
        pd.DataFrame = DataFrame
        sys.modules["pandas"] = pd
    
    mod, err = _import_module("backend.features.technical_indicators")
    if mod is None:
        pytest.skip(f"backend.features.technical_indicators not importable: {err}")
    
    # Create instance
    ti = mod.TechnicalIndicators()
    assert ti is not None
    
    # Test with normal price data
    normal_prices = [100.0, 101.0, 102.0, 101.5, 103.0, 104.0, 103.5, 105.0, 106.0, 105.5,
                     107.0, 108.0, 107.5, 109.0, 110.0, 109.5, 111.0, 112.0, 111.5, 113.0]
    
    # Test SMA calculation
    sma_result = ti.calculate_sma(normal_prices, 10)
    assert sma_result.value is not None
    assert sma_result.confidence > 0
    
    # Test RSI calculation
    rsi_result = ti.calculate_rsi(normal_prices)
    assert rsi_result.value is not None
    assert 0 <= rsi_result.value <= 100
    
    # Test Bollinger Bands
    bb_result = ti.calculate_bollinger_bands(normal_prices)
    assert "upper" in bb_result
    assert "middle" in bb_result
    assert "lower" in bb_result
    assert bb_result["middle"].value is not None
    
    # Test extreme conditions
    extreme_result = ti.handle_extreme_conditions(normal_prices)
    assert extreme_result["status"] == "analyzed"
    
    # Test edge cases - insufficient data
    short_prices = [100.0, 101.0]
    sma_short = ti.calculate_sma(short_prices, 10)
    assert sma_short.value is None
    assert sma_short.error == "insufficient_data"
    
    # Test edge cases - invalid prices
    invalid_prices = [100.0, None, float('inf'), -50.0, 0]
    sma_invalid = ti.calculate_sma(invalid_prices, 3)
    assert sma_invalid.error == "too_many_invalid_prices"
    
    # Test _is_valid_price method with all edge cases
    assert ti._is_valid_price(100.0) == True
    assert ti._is_valid_price(None) == False
    assert ti._is_valid_price(float('inf')) == False
    assert ti._is_valid_price(float('-inf')) == False
    assert ti._is_valid_price(float('nan')) == False
    assert ti._is_valid_price(-10.0) == False
    assert ti._is_valid_price(0) == False
    assert ti._is_valid_price(2000000) == False
    assert ti._is_valid_price("invalid") == False
    assert ti._is_valid_price([]) == False
    
    # Test additional edge cases for calculation methods
    # RSI with insufficient data
    rsi_short = ti.calculate_rsi([100, 101])
    assert rsi_short.value is None
    
    # RSI with all zeros for loss (100% RSI)
    rising_prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
    rsi_rising = ti.calculate_rsi(rising_prices)
    assert rsi_rising.value == 100.0
    
    # Bollinger Bands with insufficient data for std dev
    bb_short = ti.calculate_bollinger_bands([100, 101])
    assert bb_short["upper"].value is None
    
    # Test configuration parameter
    ti_with_config = mod.TechnicalIndicators(config={"test": "value"})
    assert ti_with_config.config == {"test": "value"}
    
    # Test calculation stats
    stats = ti.get_calculation_stats()
    assert "calculation_count" in stats
    assert "error_count" in stats
    assert "success_rate" in stats
    
    # Test extreme conditions with crash data
    crash_prices = [100.0, 95.0, 85.0, 92.0, 88.0]  # Flash crash scenario
    extreme_crash = ti.handle_extreme_conditions(crash_prices)
    assert len(extreme_crash["extreme_conditions"]) > 0
    
    # Test with spike data
    spike_prices = [100.0, 115.0, 105.0, 110.0]  # Price spike
    extreme_spike = ti.handle_extreme_conditions(spike_prices)
    assert extreme_spike["status"] == "analyzed"


def test_calculate_all_features():
    """Test calculate_all_features with DataFrame input."""
    mod, err = _import_module("backend.features.technical_indicators")
    if mod is None:
        pytest.skip("backend.features.technical_indicators not importable")
    
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas not available")
    
    ti = mod.TechnicalIndicators()
    
    # Test with valid DataFrame
    prices = [100.0 + i for i in range(30)]  # 30 data points
    df = pd.DataFrame({"close": prices})
    
    features = ti.calculate_all_features(df)
    assert features is not None
    assert "sma_20" in features
    assert "rsi" in features
    assert "price_mean" in features
    
    # Test with empty DataFrame
    empty_df = pd.DataFrame()
    features_empty = ti.calculate_all_features(empty_df)
    assert features_empty is None
    
    # Test with None input
    features_none = ti.calculate_all_features(None)
    assert features_none is None
    
    # Test with DataFrame missing close column
    bad_df = pd.DataFrame({"open": [100, 101, 102]})
    features_bad = ti.calculate_all_features(bad_df)
    assert features_bad is None