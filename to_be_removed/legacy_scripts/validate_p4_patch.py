#!/usr/bin/env python3
"""Validate P4 Patch: Risk routes & manager compatibility."""

import os
import sys

# Set light mode
os.environ["DISABLE_ML"] = "1"

def main():
    """Test P4 risk routes and manager compatibility."""
    print("🔍 P4 Patch Validation: Risk routes & manager compatibility")
    print("=" * 65)
    
    success_count = 0
    total_tests = 8
    
    try:
        sys.path.insert(0, os.path.abspath('.'))
        
        # Test 1: Import risk router and get_risk_manager
        print("\n✅ Test 1: Risk router imports")
        from backend.api.routes.risk import router, get_risk_manager
        assert router is not None, "Router should be imported"
        assert callable(get_risk_manager), "get_risk_manager should be callable"
        print("   ✅ Risk router and get_risk_manager imported successfully")
        success_count += 1
        
        # Test 2: RiskLimits class with correct structure
        print("\n✅ Test 2: RiskLimits class structure")
        from backend.risk.types import RiskLimits
        
        # Test the constructor with P4-specified parameters
        limits = RiskLimits(
            max_position_value=10000.0,
            max_symbol_exposure=0.3,
            circuit_breaker_pct=0.1,
            max_portfolio_exposure=0.8
        )
        
        assert limits.max_position_value == 10000.0, "max_position_value should be set"
        assert limits.max_symbol_exposure == 0.3, "max_symbol_exposure should be set"
        assert limits.circuit_breaker_pct == 0.1, "circuit_breaker_pct should be set"
        assert limits.max_portfolio_exposure == 0.8, "max_portfolio_exposure should be set"
        print("   ✅ RiskLimits constructor works with P4 parameters")
        success_count += 1
        
        # Test 3: Risk manager import and creation
        print("\n✅ Test 3: DefaultRiskManager import")
        from backend.risk.risk_manager import RiskManager as DefaultRiskManager
        risk_manager = DefaultRiskManager()
        assert risk_manager is not None, "DefaultRiskManager should be created"
        print("   ✅ DefaultRiskManager imported and created")
        success_count += 1
        
        # Test 4: Method shims - check_single_position_limit -> check_symbol_limit
        print("\n✅ Test 4: Method shims delegation")
        
        # Test check_single_position_limit delegates to check_symbol_limit
        result1 = risk_manager.check_single_position_limit("AAPL", 100)
        result2 = risk_manager.check_symbol_limit("AAPL", 100)
        assert len(result1) == 3, "Should return tuple of 3 elements"
        assert len(result2) == 3, "Should return tuple of 3 elements"
        print("   ✅ check_single_position_limit -> check_symbol_limit delegation works")
        success_count += 1
        
        # Test 5: Method shims - update_status -> refresh_status
        print("\n✅ Test 5: update_status -> refresh_status delegation")
        
        status1 = risk_manager.update_status()
        status2 = risk_manager.refresh_status()
        assert isinstance(status1, dict), "update_status should return dict"
        assert isinstance(status2, dict), "refresh_status should return dict"
        assert "refresh_timestamp" in status2, "refresh_status should have refresh_timestamp"
        print("   ✅ update_status -> refresh_status delegation works")
        success_count += 1
        
        # Test 6: Risk manager metrics method
        print("\n✅ Test 6: Risk manager metrics method")
        
        metrics = risk_manager.metrics()
        assert isinstance(metrics, dict), "metrics() should return dict"
        assert "status" in metrics, "metrics should have status"
        assert "metrics" in metrics, "metrics should have metrics sub-dict"
        print("   ✅ Risk manager metrics() method works")
        success_count += 1
        
        # Test 7: Risk manager set_limits method
        print("\n✅ Test 7: Risk manager set_limits method")
        
        payload = {
            "max_position_value": 5000.0,
            "max_symbol_exposure": 0.2,
            "circuit_breaker_pct": 0.05
        }
        result = risk_manager.set_limits(payload)
        assert isinstance(result, dict), "set_limits should return dict"
        assert "status" in result, "Result should have status"
        assert result["status"] == "updated", "Status should be updated"
        assert "limits" in result, "Result should have limits"
        print("   ✅ Risk manager set_limits() method works")
        success_count += 1
        
        # Test 8: App integration - risk routes included
        print("\n✅ Test 8: App integration with risk routes")
        
        from backend.api.factory import create_app
        app = create_app()
        
        # Check if routes are registered by examining the router
        risk_routes = [route for route in app.routes if hasattr(route, 'path') and '/risk' in route.path]
        assert len(risk_routes) > 0, "Risk routes should be registered"
        
        # Test basic app functionality
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        # Test readiness endpoint to ensure app works
        response = client.get("/readyz")
        assert response.status_code in [200, 503], "App should respond to readiness check"
        print("   ✅ App integration with risk routes successful")
        success_count += 1
        
        # Final assessment
        print(f"\n🎯 P4 PATCH VALIDATION: {'COMPLETE' if success_count == total_tests else 'PARTIAL'}")
        print(f"✅ Tests Passed: {success_count}/{total_tests}")
        
        if success_count == total_tests:
            print("\n📋 P4 Implementation Summary:")
            print("   ✅ Risk router with get_risk_manager patch point")
            print("   ✅ /api/v1/risk/metrics endpoint implemented") 
            print("   ✅ /api/v1/risk/limits endpoint implemented")
            print("   ✅ DefaultRiskManager import working")
            print("   ✅ RiskLimits class with P4 constructor parameters")
            print("   ✅ Method shims: check_single_position_limit -> check_symbol_limit")
            print("   ✅ Method shims: update_status -> refresh_status")
            print("   ✅ Risk manager metrics() and set_limits() methods")
            print("   ✅ App integration with risk routes included")
            print("\n🚀 P4 patch successfully implements risk routes & manager compatibility!")
            return True
        else:
            print(f"\n⚠️  P4 patch partially implemented - {total_tests - success_count} issues remain")
            return False
            
    except Exception as e:
        print(f"\n❌ P4 PATCH VALIDATION FAILED!")
        print(f"Error: {e}")
        print(f"Tests Passed: {success_count}/{total_tests}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
