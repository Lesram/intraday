"""
Final validation test for light mode functionality.
This test validates that our light mode system is working correctly.
"""
import sys
import os

# Ensure light mode is activated FIRST
import conftest_light_mode

def test_light_mode_validation():
    """Test that light mode is properly activated"""
    print(f"\n🔍 Validating Light Mode:")
    
    # Check environment variables
    env_vars = ['DISABLE_ML', 'DISABLE_TORCH', 'DISABLE_TRANSFORMERS', 'PYTEST_RUNNING']
    for var in env_vars:
        print(f"   {var}: {os.environ.get(var, 'NOT SET')}")
    
    # Test torch import
    import torch
    print(f"   torch type: {type(torch)}")
    print(f"   torch.__file__: {getattr(torch, '__file__', 'NO FILE ATTR')}")
    
    # Test transformers import 
    import transformers
    print(f"   transformers type: {type(transformers)}")
    print(f"   transformers.__file__: {getattr(transformers, '__file__', 'NO FILE ATTR')}")
    
    # Validate they are mocked
    assert "<mocked:" in str(torch), f"torch should be mocked, got {torch}"
    assert "<mocked:" in str(transformers), f"transformers should be mocked, got {transformers}"
    
    print("✅ Light Mode Validation PASSED!")
    
    return True

if __name__ == "__main__":
    test_light_mode_validation()
