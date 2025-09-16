"""
Test Prompt 5 implementation: Risk & features normalization
"""

import numpy as np
import pandas as pd
from decimal import Decimal


def test_alignment_functions():
    """Test that alignment functions prevent DataFrame/Series arithmetic errors"""
    
    # Test the alignment function from utils.helpers
    from backend.utils.helpers import align_for_pandas_arithmetic
    
    # Create test DataFrame
    df = pd.DataFrame({
        'close': [100, 101, 102, 103, 104],
        'high': [101, 102, 103, 104, 105],  
        'low': [99, 100, 101, 102, 103]
    }, index=[0, 1, 2, 3, 4])
    
    # Test scalar alignment
    aligned_scalar = align_for_pandas_arithmetic(5, df.index)
    result = df['close'] - aligned_scalar
    assert len(result) == len(df)
    assert all(result == df['close'] - 5)
    
    # Test list alignment
    test_list = [1, 2, 3, 4, 5]
    aligned_list = align_for_pandas_arithmetic(test_list, df.index)
    result = df['close'] - aligned_list  
    expected = df['close'] - pd.Series(test_list, index=df.index)
    pd.testing.assert_series_equal(result, expected)
    
    # Test Series alignment with different index
    other_series = pd.Series([10, 20, 30], index=[1, 2, 3])
    aligned_series = align_for_pandas_arithmetic(other_series, df.index)
    result = df['close'] - aligned_series
    assert len(result) == len(df)
    
    # Test DataFrame alignment
    other_df = pd.DataFrame({'value': [5, 6, 7, 8, 9]}, index=df.index)
    aligned_df = align_for_pandas_arithmetic(other_df, df.index)
    result = df['close'] - aligned_df
    assert len(result) == len(df)
    
    print("✅ Alignment functions test passed!")


def test_feature_engineering_arithmetic():
    """Test feature engineering operations don't fail with ValueError"""
    
    from backend.features.feature_engineering import align_for_arithmetic
    
    # Create test data
    df = pd.DataFrame({
        'close': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [101.0, 102.0, 103.0, 104.0, 105.0],
        'low': [99.0, 100.0, 101.0, 102.0, 103.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }, index=pd.date_range('2025-08-20', periods=5, freq='D'))
    
    # Test operations that previously might have failed
    
    # Bollinger band-style operations
    bb_upper = pd.Series([105, 106, 107, 108, 109], index=df.index)
    bb_lower = pd.Series([95, 96, 97, 98, 99], index=df.index)
    bb_middle = pd.Series([100, 101, 102, 103, 104], index=df.index)
    
    # These should not raise "other must be DataFrame or Series" errors
    bb_position = (df["close"] - align_for_arithmetic(bb_lower, df.index)) / (
        align_for_arithmetic(bb_upper, df.index) - align_for_arithmetic(bb_lower, df.index)
    )
    assert len(bb_position) == len(df)
    
    bb_width = (align_for_arithmetic(bb_upper, df.index) - align_for_arithmetic(bb_lower, df.index)) / align_for_arithmetic(bb_middle, df.index)
    assert len(bb_width) == len(df)
    
    # MACD-style operations
    macd = pd.Series([1.5, 1.2, 0.8, 0.5, 0.2], index=df.index)
    macd_signal = pd.Series([1.3, 1.1, 0.9, 0.6, 0.3], index=df.index)
    
    macd_histogram = macd - align_for_arithmetic(macd_signal, df.index)
    assert len(macd_histogram) == len(df)
    
    # Rate of change operations
    close_shifted = df["close"].shift(1)
    roc = (df["close"] - align_for_arithmetic(close_shifted, df.index)) / align_for_arithmetic(close_shifted, df.index)
    assert len(roc) == len(df)
    
    print("✅ Feature engineering arithmetic test passed!")


def test_edge_cases():
    """Test edge cases for alignment functions"""
    
    from backend.utils.helpers import align_for_pandas_arithmetic
    
    # Empty index
    empty_index = pd.Index([])
    result = align_for_pandas_arithmetic(5, empty_index)
    assert len(result) == 0
    
    # Single element index
    single_index = pd.Index([0])
    result = align_for_pandas_arithmetic([1, 2, 3], single_index)  # More data than index
    assert len(result) == 1
    assert result.iloc[0] == 1
    
    # Index longer than data
    long_index = pd.Index([0, 1, 2, 3, 4])
    result = align_for_pandas_arithmetic([1, 2], long_index)  # Less data than index
    assert len(result) == 5
    assert result.iloc[0] == 1
    assert result.iloc[1] == 2
    assert result.iloc[2] == 2  # Padded with last value
    
    # Weird input types
    result = align_for_pandas_arithmetic("test", long_index)
    assert len(result) == 5
    
    # None input
    result = align_for_pandas_arithmetic(None, long_index)
    assert len(result) == 5
    
    print("✅ Edge cases test passed!")


def test_risk_math_integration():
    """Test risk math integration with pandas"""
    
    # Test that risk math works with pandas data
    from backend.risk.math import value_at_risk, conditional_var
    
    # Create pandas Series returns
    returns_series = pd.Series([-0.05, -0.02, 0.01, 0.03, -0.01, 0.02, -0.03])
    
    # These should work without DataFrame/Series errors
    var = value_at_risk(returns_series, 0.95)
    assert isinstance(var, float)
    
    cvar = conditional_var(returns_series, 0.95)
    assert isinstance(cvar, float)
    
    # Test with DataFrame input (should extract values)
    returns_df = pd.DataFrame({'returns': returns_series})
    var_df = value_at_risk(returns_df, 0.95)
    assert isinstance(var_df, float)
    
    print("✅ Risk math integration test passed!")


if __name__ == "__main__":
    test_alignment_functions()
    test_feature_engineering_arithmetic() 
    test_edge_cases()
    test_risk_math_integration()
    print("🎉 All Prompt 5 tests passed!")
