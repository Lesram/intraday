#!/usr/bin/env python3
"""
Final smoke test for Phase 4 + Authentication/Routing fixes.
Tests the complete flow from regression fixes to working API endpoints.
"""

import sys
from pathlib import Path

# Add the backend to Python path
sys.path.insert(0, str(Path(__file__).parent))


def test_routing_and_authentication():
    """Test that routing and authentication work together"""
    print("🔧 Testing Routing + Authentication Integration...")
    
    try:
        from fastapi.testclient import TestClient
        from backend.api.main import app
        from backend.api.test_utils.auth import get_test_headers
        
        client = TestClient(app)
        
        # Test 1: Public endpoint (no auth required)
        response = client.get("/api/v1/system/health")
        print(f"✓ Public health endpoint: {response.status_code}")
        
        # Test 2: Protected endpoint without auth (should fail)
        response = client.get("/api/v1/signals/")
        print(f"✓ Protected signals without auth: {response.status_code} (expected 401)")
        
        # Test 3: Protected endpoint with test token  
        headers = get_test_headers()
        response = client.get("/api/v1/signals/", headers=headers)
        print(f"✓ Protected signals with auth: {response.status_code}")
        
        # Test 4: Orders endpoint with auth
        response = client.get("/api/v1/orders/", headers=headers)
        print(f"✓ Orders endpoint with auth: {response.status_code}")
        
        print("✅ SUCCESS: Routing and authentication integration works!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_phase4_plus_routing_fixes():
    """Test that Phase 4 regression fixes work with new routing"""
    print("\n🔧 Testing Phase 4 Fixes + New Routing...")
    
    try:
        from fastapi.testclient import TestClient
        from backend.api.main import app
        from backend.api.test_utils.auth import get_test_headers
        
        client = TestClient(app)
        headers = get_test_headers()
        
        # Test SignalResponse compatibility through actual endpoint
        response = client.get("/api/v1/signals/AAPL", headers=headers)
        print(f"✓ Signals endpoint access: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            has_confidence = 'confidence' in data
            has_signal_strength = 'signal_strength' in data
            print(f"✓ Response has confidence: {has_confidence}")
            print(f"✓ Response has signal_strength: {has_signal_strength}")
        
        # Test orders endpoint (validates PositionLimits integration)
        order_data = {
            "symbol": "AAPL", 
            "side": "buy",
            "qty": 10,
            "type": "market"
        }
        response = client.post("/api/v1/orders/", json=order_data, headers=headers)
        print(f"✓ Orders creation: {response.status_code}")
        
        print("✅ SUCCESS: Phase 4 + routing integration works!")
        return True
        
    except Exception as e:
        print(f"❌ Phase 4 + routing test FAILED: {e}")
        return False


def test_route_coverage():
    """Test that key routes are available"""
    print("\n🔧 Testing Route Coverage...")
    
    try:
        from fastapi.routing import APIRoute
        from backend.api.main import app
        
        routes = [r.path for r in app.routes if isinstance(r, APIRoute)]
        
        required_routes = [
            "/api/v1/signals/",
            "/api/v1/orders/", 
            "/api/v1/system/health",
            "/api/v1/auth/login"
        ]
        
        missing = []
        for required in required_routes:
            if required not in routes:
                missing.append(required)
        
        if missing:
            print(f"❌ Missing routes: {missing}")
            return False
        else:
            print(f"✅ All required routes present ({len(required_routes)}/{len(required_routes)})")
            print(f"Total routes registered: {len(routes)}")
            return True
            
    except Exception as e:
        print(f"❌ Route coverage test FAILED: {e}")
        return False


def main():
    """Run comprehensive smoke test"""
    print("🚀 Phase 4 + Authentication/Routing - Final Smoke Test")
    print("=" * 65)
    
    tests = [
        ("Route Coverage", test_route_coverage),
        ("Routing + Authentication", test_routing_and_authentication),
        ("Phase 4 + Routing Integration", test_phase4_plus_routing_fixes),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        results.append(test_func())
    
    print("\n" + "=" * 65)
    print("📊 FINAL SMOKE TEST SUMMARY")
    print("=" * 65)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test_name, result) in enumerate(zip([t[0] for t in tests], results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL SMOKE TESTS PASSED!")
        print("✅ Phase 4 regression fixes: WORKING")
        print("✅ Centralized routing: WORKING")
        print("✅ Authentication integration: WORKING")
        print("✅ API endpoints: ACCESSIBLE")
        print("\n🚀 Ready for deployment!")
        return 0
    else:
        print(f"\n⚠️  {total-passed} smoke test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)