"""
Test script to validate the F1 risk math input normalization functions.
"""

def test_to_series_function():
    """Test the _to_series input normalization function."""
    print("\n=== Testing _to_series Input Normalization ===")
    
    from backend.risk.math import _to_series
    import numpy as np
    
    # Test 1: None input
    result = _to_series(None)
    assert result.size == 0
    assert result.dtype == float
    print("✅ Test 1: None input returns empty array")
    
    # Test 2: Single scalar (int)
    result = _to_series(5)
    assert result.size == 1
    assert result[0] == 5.0
    print("✅ Test 2: Integer scalar converted to array")
    
    # Test 3: Single scalar (float)
    result = _to_series(3.14)
    assert result.size == 1
    assert result[0] == 3.14
    print("✅ Test 3: Float scalar converted to array")
    
    # Test 4: List input
    result = _to_series([1, 2, 3, 4])
    assert result.size == 4
    assert np.allclose(result, [1.0, 2.0, 3.0, 4.0])
    print("✅ Test 4: List converted to array")
    
    # Test 5: Numpy array input
    input_array = np.array([1.5, 2.5, 3.5])
    result = _to_series(input_array)
    assert result.size == 3
    assert np.allclose(result, [1.5, 2.5, 3.5])
    print("✅ Test 5: Numpy array handled correctly")
    
    # Test 6: Non-numeric object fallback
    result = _to_series("string")
    # Should return empty array for non-numeric input
    assert result.size == 0
    print("✅ Test 6: Non-numeric input handled gracefully (returns empty array)")


def test_value_at_risk():
    """Test VaR calculation with various inputs."""
    print("\n=== Testing value_at_risk Function ===")
    
    from backend.risk.math import value_at_risk
    import numpy as np
    
    # Test 1: Empty input
    assert value_at_risk(None, 0.95) == 0.0
    assert value_at_risk([], 0.95) == 0.0
    print("✅ Test 1: Empty inputs return 0.0")
    
    # Test 2: Single value
    result = value_at_risk(0.05, 0.95)
    assert result == 0.05
    print("✅ Test 2: Single value handled correctly")
    
    # Test 3: Simple list - known result
    returns = [-0.1, -0.05, 0.02, -0.02, 0.03]
    result = value_at_risk(returns, 0.95) 
    # 95% VaR should be around the 5th percentile
    assert result <= 0  # Should be negative value (loss)
    print(f"✅ Test 3: List VaR = {result:.4f}")
    
    # Test 4: Different alpha levels
    result_90 = value_at_risk(returns, 0.90)
    result_99 = value_at_risk(returns, 0.99)
    assert result_99 <= result_90  # Higher confidence = more conservative
    print(f"✅ Test 4: VaR 90% = {result_90:.4f}, VaR 99% = {result_99:.4f}")


def test_conditional_var():
    """Test CVaR calculation with various inputs."""
    print("\n=== Testing conditional_var Function ===")
    
    from backend.risk.math import conditional_var
    
    # Test 1: Empty input  
    assert conditional_var(None, 0.95) == 0.0
    assert conditional_var([], 0.95) == 0.0
    print("✅ Test 1: Empty inputs return 0.0")
    
    # Test 2: Single value
    result = conditional_var(-0.05, 0.95)
    assert result == -0.05
    print("✅ Test 2: Single value handled correctly")
    
    # Test 3: Known dataset
    returns = [-0.10, -0.08, -0.05, -0.02, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
    result = conditional_var(returns, 0.95)
    # CVaR should be average of worst 5% of returns
    assert result < 0  # Should be negative (expected loss)
    print(f"✅ Test 3: CVaR = {result:.4f}")
    
    # Test 4: CVaR should be more conservative than VaR
    from backend.risk.math import value_at_risk
    var_result = value_at_risk(returns, 0.95)
    cvar_result = conditional_var(returns, 0.95)
    assert cvar_result <= var_result  # CVaR should be worse than VaR
    print(f"✅ Test 4: VaR = {var_result:.4f}, CVaR = {cvar_result:.4f} (CVaR <= VaR)")


def test_parametric_var():
    """Test parametric VaR calculation.""" 
    print("\n=== Testing parametric_var Function ===")
    
    from backend.risk.math import parametric_var
    import numpy as np
    
    # Test 1: Empty input
    assert parametric_var(None, 0.95) == 0.0
    assert parametric_var([], 0.95) == 0.0
    print("✅ Test 1: Empty inputs return 0.0")
    
    # Test 2: With provided mean and std
    result = parametric_var(None, 0.95, mean=0.01, std=0.05)
    assert result < 0.01  # Should be less than mean (loss scenario)
    print(f"✅ Test 2: Parametric VaR with mean=0.01, std=0.05 = {result:.4f}")
    
    # Test 3: Calculate from data
    returns = [0.02, -0.01, 0.03, -0.02, 0.01] * 10  # Repeated for stability
    result = parametric_var(returns, 0.95)
    print(f"✅ Test 3: Parametric VaR from data = {result:.4f}")
    
    # Test 4: Different confidence levels
    result_95 = parametric_var(returns, 0.95)
    result_99 = parametric_var(returns, 0.99)
    assert result_99 <= result_95  # Higher confidence = more conservative  
    print(f"✅ Test 4: 95% VaR = {result_95:.4f}, 99% VaR = {result_99:.4f}")


def test_coherent_risk_measures():
    """Test the comprehensive risk measures function."""
    print("\n=== Testing coherent_risk_measures Function ===")
    
    from backend.risk.math import coherent_risk_measures
    
    # Test comprehensive risk calculation
    returns = [-0.05, -0.03, -0.01, 0.01, 0.02, 0.03, -0.02, 0.04, -0.01, 0.02]
    measures = coherent_risk_measures(returns, 0.95)
    
    # Verify all expected keys are present
    expected_keys = ['var', 'cvar', 'parametric_var', 'mean', 'std', 'observations']
    for key in expected_keys:
        assert key in measures
    print("✅ Test 1: All risk measures calculated")
    
    # Verify relationships
    assert measures['cvar'] <= measures['var']  # CVaR should be more conservative
    assert measures['observations'] == len(returns)
    print(f"✅ Test 2: Risk measures - VaR: {measures['var']:.4f}, CVaR: {measures['cvar']:.4f}")
    print(f"   Mean: {measures['mean']:.4f}, Std: {measures['std']:.4f}, N: {measures['observations']}")


def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n=== Testing Edge Cases ===")
    
    from backend.risk.math import value_at_risk, conditional_var, parametric_var
    import numpy as np
    
    # Test 1: All zeros
    zeros = [0.0] * 10
    var_result = value_at_risk(zeros, 0.95)
    cvar_result = conditional_var(zeros, 0.95)
    assert var_result == 0.0
    assert cvar_result == 0.0
    print("✅ Test 1: All zeros handled correctly")
    
    # Test 2: Single repeated value
    repeated = [0.05] * 10
    var_result = value_at_risk(repeated, 0.95)
    cvar_result = conditional_var(repeated, 0.95)
    assert var_result == 0.05
    assert cvar_result == 0.05
    print("✅ Test 2: Repeated values handled correctly")
    
    # Test 3: Very small dataset
    small = [-0.01, 0.02]
    var_result = value_at_risk(small, 0.95)
    cvar_result = conditional_var(small, 0.95)
    print(f"✅ Test 3: Small dataset - VaR: {var_result:.4f}, CVaR: {cvar_result:.4f}")
    
    # Test 4: Extreme alpha values
    returns = [-0.05, -0.01, 0.01, 0.02, 0.03]
    var_999 = value_at_risk(returns, 0.999)
    var_50 = value_at_risk(returns, 0.50) 
    print(f"✅ Test 4: Extreme alphas - VaR 99.9%: {var_999:.4f}, VaR 50%: {var_50:.4f}")


if __name__ == "__main__":
    try:
        test_to_series_function()
        test_value_at_risk()
        test_conditional_var()
        test_parametric_var()
        test_coherent_risk_measures()
        test_edge_cases()
        
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ _to_series: Robust input normalization working")
        print("✅ value_at_risk: VaR calculation with coerced inputs")
        print("✅ conditional_var: CVaR calculation with coerced inputs")  
        print("✅ parametric_var: Normal distribution VaR")
        print("✅ coherent_risk_measures: Comprehensive risk metrics")
        print("✅ Edge cases: Proper handling of empty/edge inputs")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
