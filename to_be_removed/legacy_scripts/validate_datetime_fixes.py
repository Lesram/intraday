#!/usr/bin/env python3
"""
Validate that datetime.utcnow() fixes work correctly in Python 3.12.
Tests the core modules we fixed for Python 3.12 compatibility.
"""

import traceback
from datetime import datetime, UTC

def test_datetime_compatibility():
    """Test that datetime.now(UTC) works correctly"""
    print("🔍 Testing datetime.now(UTC) compatibility...")
    try:
        now_utc = datetime.now(UTC)
        print(f"✅ datetime.now(UTC) works: {now_utc}")
        return True
    except Exception as e:
        print(f"❌ datetime.now(UTC) failed: {e}")
        return False

def test_outbox_module():
    """Test that outbox module imports without datetime errors"""
    print("\n🔍 Testing outbox module import...")
    try:
        from backend.infra.outbox import OutboxService, ExponentialBackoffStrategy
        print("✅ Outbox module imported successfully")
        
        # Test instantiation
        strategy = ExponentialBackoffStrategy()
        now = strategy.next_attempt_time(1)
        print(f"✅ Backoff strategy works: next attempt at {now}")
        return True
    except Exception as e:
        print(f"❌ Outbox module failed: {e}")
        traceback.print_exc()
        return False

def test_factory_module():
    """Test that factory module imports without datetime errors"""
    print("\n🔍 Testing factory module import...")
    try:
        from backend.api.factory import create_application
        print("✅ Factory module imported successfully")
        return True
    except Exception as e:
        print(f"❌ Factory module failed: {e}")
        traceback.print_exc()
        return False

def test_repositories():
    """Test that repository modules import without datetime errors"""
    print("\n🔍 Testing repository modules...")
    modules_to_test = [
        "backend.infra.repositories.orders",
        "backend.infra.repositories.models", 
        "backend.infra.repositories.signals",
        "backend.infra.repositories.positions",
        "backend.infra.repositories.executions",
        "backend.infra.repositories.audits"
    ]
    
    success_count = 0
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {module_name} imported successfully")
            success_count += 1
        except Exception as e:
            print(f"❌ {module_name} failed: {e}")
    
    print(f"📊 Repository modules: {success_count}/{len(modules_to_test)} successful")
    return success_count == len(modules_to_test)

def test_risk_types():
    """Test that risk types module imports without datetime errors"""
    print("\n🔍 Testing risk types module...")
    try:
        from backend.risk.types import RiskDecision
        # Test creating a risk decision (should use datetime.now(UTC))
        decision = RiskDecision.allow("Test decision")
        print(f"✅ Risk decision created: {decision.timestamp}")
        return True
    except Exception as e:
        print(f"❌ Risk types failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all validation tests"""
    print("🚀 Validating datetime.utcnow() → datetime.now(UTC) fixes for Python 3.12")
    print("=" * 80)
    
    tests = [
        test_datetime_compatibility,
        test_outbox_module,
        test_factory_module, 
        test_repositories,
        test_risk_types
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 80)
    print(f"📊 VALIDATION SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 SUCCESS: All datetime compatibility fixes working!")
        print("✨ Python 3.12 AttributeError issues should be resolved")
        return True
    else:
        print("⚠️  Some modules still have datetime compatibility issues")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
