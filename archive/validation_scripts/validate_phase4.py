#!/usr/bin/env python3
"""
Phase 4 Validation Script
Tests all regression fixes implemented
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the backend to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_signal_response_compatibility():
    """Test 1: SignalResponse compatibility - signal_strength field"""
    print("🔧 Test 1: Signal Response Compatibility")
    
    try:
        from backend.api.schemas.signals import SignalResponse
        from backend.strategies.basic import BasicStrategy
        import pandas as pd
        import numpy as np
        
        # Create test data
        closes = pd.Series([100, 101, 102, 99, 98])
        
        # Test BasicStrategy with both parameter formats
        strategy = BasicStrategy()
        
        # Test with 'closes' parameter (new format)
        decision1 = strategy.decide(closes=closes)
        print(f"✓ BasicStrategy.decide(closes=...) works: {decision1}")
        
        # Test with 'close_prices' parameter (legacy format)  
        decision2 = strategy.decide(close_prices=closes)
        print(f"✓ BasicStrategy.decide(close_prices=...) works: {decision2}")
        
        # Test SignalResponse creation
        signal = SignalResponse.from_decision(decision1, symbol="AAPL")
        
        # Check both fields exist and mirror each other
        assert hasattr(signal, 'confidence'), "Missing confidence field"
        assert hasattr(signal, 'signal_strength'), "Missing signal_strength field"
        assert signal.confidence == signal.signal_strength, "Fields don't mirror"
        
        print(f"✓ SignalResponse has both fields: confidence={signal.confidence}, signal_strength={signal.signal_strength}")
        print("✅ Test 1 PASSED: Signal compatibility works")
        return True
        
    except Exception as e:
        print(f"❌ Test 1 FAILED: {e}")
        return False

async def test_position_limits_compatibility():
    """Test 2: PositionLimits constructor compatibility"""
    print("\n🔧 Test 2: PositionLimits Compatibility")
    
    try:
        from backend.risk.position_limits import PositionLimits
        
        # Test with circuit_breaker_pct (new parameter)
        limits1 = PositionLimits(
            max_position_pct=0.25,
            circuit_breaker_pct=0.15,
        )
        print(f"✓ PositionLimits with circuit_breaker_pct: {limits1.circuit_breaker_pct}")
        
        # Test with circuit_breaker (legacy parameter)
        limits2 = PositionLimits(
            circuit_breaker=0.20,
        )
        print(f"✓ PositionLimits with circuit_breaker: {limits2.circuit_breaker_pct}")
        
        # Test percentage normalization
        limits3 = PositionLimits(
            max_position_pct=25,  # Should normalize to 0.25
            circuit_breaker_pct=15,  # Should normalize to 0.15
        )
        print(f"✓ Percentage normalization: {limits3.max_position_pct}, {limits3.circuit_breaker_pct}")
        
        assert limits3.max_position_pct == 0.25, "Max position normalization failed"
        assert limits3.circuit_breaker_pct == 0.15, "Circuit breaker normalization failed"
        
        print("✅ Test 2 PASSED: PositionLimits compatibility works")
        return True
        
    except Exception as e:
        print(f"❌ Test 2 FAILED: {e}")
        return False

async def test_imports_and_basic_functionality():
    """Test 3: Basic imports and functionality after lint cleanup"""
    print("\n🔧 Test 3: Import and Basic Functionality")
    
    try:
        # Test key imports
        from backend.api.factory import create_app
        from backend.services.order_service import OrderService
        from backend.risk.risk_manager import RiskManager
        
        print("✓ Core imports successful")
        
        # Test app creation
        app = create_app()
        print("✓ FastAPI app creation successful")
        
        print("✅ Test 3 PASSED: Imports and basic functionality work")
        return True
        
    except Exception as e:
        print(f"❌ Test 3 FAILED: {e}")
        return False

async def main():
    """Run all validation tests"""
    print("🚀 Phase 4 Validation - Regression Fix Testing")
    print("=" * 50)
    
    tests = [
        test_signal_response_compatibility(),
        test_position_limits_compatibility(),
        test_imports_and_basic_functionality(),
    ]
    
    results = await asyncio.gather(*tests)
    
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"Test {i}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Phase 4 regression fixes verified!")
        return 0
    else:
        print("⚠️  Some tests failed - regression fixes need attention")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)