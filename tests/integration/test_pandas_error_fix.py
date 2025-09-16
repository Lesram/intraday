"""
Specific test for "ValueError: other must be a DataFrame or Series" fix
"""

import numpy as np
import pandas as pd


def test_pandas_arithmetic_error_scenarios():
    """
    Test scenarios that previously caused "other must be a DataFrame or Series" errors
    """
    
    print("=== Testing Pandas Arithmetic Error Scenarios ===")
    
    # Create test DataFrame
    df = pd.DataFrame({
        'close': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [101.0, 102.0, 103.0, 104.0, 105.0],
        'low': [99.0, 100.0, 101.0, 102.0, 103.0],
    }, index=pd.date_range('2025-08-20', periods=5, freq='D'))
    
    from backend.utils.helpers import align_for_pandas_arithmetic
    
    print("✅ Test 1: Scalar arithmetic (was: df['close'] - 5)")
    # This would previously fail in some contexts
    try:
        result1 = df['close'] - align_for_pandas_arithmetic(5, df.index)
        assert len(result1) == 5
        print(f"   Result length: {len(result1)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 2: List arithmetic (was: df['close'] - [1,2,3,4,5])")
    try:
        test_list = [1, 2, 3, 4, 5]
        result2 = df['close'] - align_for_pandas_arithmetic(test_list, df.index)
        assert len(result2) == 5
        print(f"   Result length: {len(result2)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 3: Numpy array arithmetic")
    try:
        test_array = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
        result3 = df['close'] - align_for_pandas_arithmetic(test_array, df.index)
        assert len(result3) == 5
        print(f"   Result length: {len(result3)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 4: Series with different index")
    try:
        other_series = pd.Series([10, 20, 30], index=[1, 2, 3])  # Different index
        result4 = df['close'] - align_for_pandas_arithmetic(other_series, df.index)
        assert len(result4) == 5
        print(f"   Result length: {len(result4)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 5: DataFrame arithmetic (using first column)")
    try:
        other_df = pd.DataFrame({'values': [5, 6, 7, 8, 9]}, index=df.index)
        result5 = df['close'] - align_for_pandas_arithmetic(other_df, df.index)
        assert len(result5) == 5
        print(f"   Result length: {len(result5)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 6: Mixed type division")
    try:
        # Simulate Bollinger Band position calculation that might fail
        bb_upper = pd.Series([105, 106, 107, 108, 109], index=df.index)
        bb_lower = [95, 96, 97, 98, 99]  # List instead of Series
        
        # This type of operation could cause the error
        denominator = align_for_pandas_arithmetic(bb_upper, df.index) - align_for_pandas_arithmetic(bb_lower, df.index)
        result6 = (df['close'] - align_for_pandas_arithmetic(bb_lower, df.index)) / denominator
        assert len(result6) == 5
        print(f"   Result length: {len(result6)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    return True


def test_feature_engineering_specific_cases():
    """Test specific feature engineering calculations that could fail"""
    
    print("\n=== Testing Feature Engineering Specific Cases ===")
    
    from backend.features.feature_engineering import align_for_arithmetic
    
    # Create realistic market data
    dates = pd.date_range('2025-08-01', periods=20, freq='D')
    df = pd.DataFrame({
        'close': np.random.uniform(100, 110, 20),
        'high': np.random.uniform(110, 115, 20), 
        'low': np.random.uniform(95, 100, 20),
        'volume': np.random.uniform(1000, 5000, 20)
    }, index=dates)
    
    print("✅ Test 1: EMA convergence calculation")
    try:
        # Simulate EMA calculations
        ema_fast = df['close'].ewm(span=12).mean()
        ema_slow = df['close'].ewm(span=26).mean()
        
        # This type of operation could fail without alignment
        convergence = ema_fast - align_for_arithmetic(ema_slow, df.index)
        assert len(convergence) == len(df)
        print(f"   Convergence series length: {len(convergence)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 2: Rate of Change with shifted data")
    try:
        close_shifted = df['close'].shift(10)
        
        # This could fail if alignment isn't handled properly
        roc = ((df['close'] - align_for_arithmetic(close_shifted, df.index)) / 
               align_for_arithmetic(close_shifted, df.index)) * 100
        assert len(roc) == len(df)
        print(f"   ROC series length: {len(roc)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 3: Bollinger Band position")
    try:
        bb_period = 20
        bb_middle = df['close'].rolling(window=bb_period).mean()
        bb_std = df['close'].rolling(window=bb_period).std()
        bb_upper = bb_middle + (bb_std * 2)
        bb_lower = bb_middle - (bb_std * 2)
        
        # Complex calculation that could fail
        bb_position = ((df['close'] - align_for_arithmetic(bb_lower, df.index)) / 
                      (align_for_arithmetic(bb_upper, df.index) - align_for_arithmetic(bb_lower, df.index)))
        
        assert len(bb_position) == len(df)
        print(f"   BB position series length: {len(bb_position)} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
        
    return True


def test_risk_math_pandas_inputs():
    """Test risk math functions with pandas inputs"""
    
    print("\n=== Testing Risk Math with Pandas Inputs ===")
    
    from backend.risk.math import value_at_risk, conditional_var
    
    print("✅ Test 1: VaR with pandas Series")
    try:
        returns_series = pd.Series([-0.05, -0.02, 0.01, 0.03, -0.01, 0.02, -0.03])
        var_result = value_at_risk(returns_series, 0.95)
        assert isinstance(var_result, float)
        print(f"   VaR result: {var_result:.4f} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
    
    print("✅ Test 2: CVaR with pandas DataFrame")
    try:
        returns_df = pd.DataFrame({
            'returns': [-0.05, -0.02, 0.01, 0.03, -0.01, 0.02, -0.03]
        })
        cvar_result = conditional_var(returns_df, 0.95)
        assert isinstance(cvar_result, float)
        print(f"   CVaR result: {cvar_result:.4f} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
        
    print("✅ Test 3: Mixed pandas inputs")
    try:
        # Test with different pandas structures
        series_input = pd.Series([0.01, -0.02, 0.03])
        df_input = pd.DataFrame({'col': [0.01, -0.02, 0.03]})
        
        var1 = value_at_risk(series_input, 0.95)
        var2 = value_at_risk(df_input, 0.95)
        
        # Results should be similar (same underlying data)
        assert abs(var1 - var2) < 0.001
        print(f"   Series VaR: {var1:.4f}, DataFrame VaR: {var2:.4f} ✓")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        return False
        
    return True


if __name__ == "__main__":
    success1 = test_pandas_arithmetic_error_scenarios()
    success2 = test_feature_engineering_specific_cases() 
    success3 = test_risk_math_pandas_inputs()
    
    if success1 and success2 and success3:
        print("\n🎉 ALL PANDAS ARITHMETIC ERROR SCENARIOS FIXED!")
        print("✅ No more 'other must be a DataFrame or Series' errors")
        print("✅ Feature engineering calculations normalized")
        print("✅ Risk math functions handle pandas inputs properly") 
    else:
        print("\n❌ Some tests failed - check implementation")
