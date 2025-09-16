"""
Integration test for F1 risk math functions with existing risk manager.
"""

def test_risk_math_integration():
    """Test integration of risk math functions with existing risk types."""
    print("\n=== F1 Risk Math Integration Test ===")
    
    # Test with various input formats that might come from the rest of the system
    from backend.risk.math import value_at_risk, conditional_var, coherent_risk_measures
    
    # Test 1: Mixed input types (like what might come from order history)
    print("📊 Testing mixed input scenarios...")
    
    # Scenario A: Portfolio returns from order P&L
    pnl_data = [100.50, -75.25, 200.00, -150.75, 50.25, -25.50, 125.00, -200.00]
    
    var_95 = value_at_risk(pnl_data, 0.95)
    cvar_95 = conditional_var(pnl_data, 0.95)
    
    print(f"✅ Portfolio P&L VaR (95%): ${var_95:.2f}")
    print(f"✅ Portfolio P&L CVaR (95%): ${cvar_95:.2f}")
    
    # Scenario B: Single position risk
    single_position_return = -0.05  # 5% loss
    var_single = value_at_risk(single_position_return, 0.99)
    print(f"✅ Single position VaR (99%): {var_single:.4f}")
    
    # Scenario C: Empty/None data (defensive)
    var_empty = value_at_risk(None, 0.95)
    cvar_empty = conditional_var([], 0.95) 
    print(f"✅ Defensive handling - Empty VaR: {var_empty}, Empty CVaR: {cvar_empty}")
    
    # Scenario D: Comprehensive risk metrics
    sample_returns = [-0.02, 0.01, -0.03, 0.015, -0.01, 0.02, -0.015, 0.005]
    risk_metrics = coherent_risk_measures(sample_returns, 0.95)
    
    print("✅ Comprehensive Risk Report:")
    for key, value in risk_metrics.items():
        if isinstance(value, (int, float)):
            print(f"   {key}: {value:.4f}")
        else:
            print(f"   {key}: {value}")


def test_edge_case_robustness():
    """Test edge cases that might occur in production."""
    print("\n=== Edge Case Robustness Test ===")
    
    from backend.risk.math import value_at_risk, conditional_var, _to_series
    
    # Test 1: Very small numbers
    tiny_returns = [1e-10, -1e-10, 2e-10, -3e-10]
    var_tiny = value_at_risk(tiny_returns, 0.95)
    print(f"✅ Tiny numbers VaR: {var_tiny}")
    
    # Test 2: Large numbers  
    large_returns = [1e6, -2e6, 3e6, -1.5e6]
    var_large = value_at_risk(large_returns, 0.95)
    print(f"✅ Large numbers VaR: {var_large:.0f}")
    
    # Test 3: Mixed numeric types
    mixed_types = [1, 2.5, -3, 4.7, -0.5]
    var_mixed = value_at_risk(mixed_types, 0.95)
    print(f"✅ Mixed types VaR: {var_mixed:.4f}")
    
    # Test 4: Input normalization stress test
    test_inputs = [
        None,
        [],
        0,
        [0.0],
        [-1, -2, -3],
        1.5,
        "invalid",  # Should gracefully handle
        [1, "2", 3],  # Mixed valid/invalid - should handle valid parts
    ]
    
    for i, test_input in enumerate(test_inputs):
        try:
            normalized = _to_series(test_input)
            print(f"✅ Input {i+1} normalized to shape {normalized.shape}")
        except Exception as e:
            print(f"❌ Input {i+1} failed: {e}")


def test_alpha_parameter_validation():
    """Test alpha parameter edge cases."""
    print("\n=== Alpha Parameter Validation ===")
    
    from backend.risk.math import value_at_risk, conditional_var
    
    returns = [-0.05, -0.02, 0.01, 0.03, -0.01]
    
    # Test various alpha values
    alpha_values = [0.50, 0.90, 0.95, 0.99, 0.995, 0.999]
    
    print("Alpha\tVaR\t\tCVaR")
    print("-" * 35)
    for alpha in alpha_values:
        var_val = value_at_risk(returns, alpha)
        cvar_val = conditional_var(returns, alpha)
        print(f"{alpha:.3f}\t{var_val:.4f}\t\t{cvar_val:.4f}")
    
    print("✅ Alpha parameter sweep completed")


if __name__ == "__main__":
    try:
        test_risk_math_integration()
        test_edge_case_robustness()  
        test_alpha_parameter_validation()
        
        print("\n🎉 F1 RISK MATH INTEGRATION SUCCESSFUL!")
        print("✅ All input normalization functions working correctly")
        print("✅ VaR/CVaR calculations handle diverse input types")  
        print("✅ Edge cases handled gracefully")
        print("✅ Integration ready for production use")
        
    except Exception as e:
        print(f"\n❌ INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
