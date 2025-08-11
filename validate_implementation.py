#!/usr/bin/env python3
"""
Quick validation script for observability contracts and security hardening.
Runs basic tests to ensure functionality works correctly.
"""

import sys
import os

# Add the backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_observability_contracts():
    """Test observability contracts functionality."""
    print("Testing Observability Contracts...")
    
    try:
        from backend.infra.observability_contracts import (
            get_histogram_buckets,
            validate_route_template,
            HISTOGRAM_BUCKETS,
            ObservabilityContract
        )
        from prometheus_client import CollectorRegistry
        
        # Test histogram buckets
        print("✓ Testing histogram buckets...")
        buckets = get_histogram_buckets("http_request_duration_seconds")
        assert buckets[-1] == float('inf'), "Buckets should end with infinity"
        assert len(buckets) >= 5, "Should have reasonable number of buckets"
        print(f"  HTTP buckets: {buckets}")
        
        # Test route templates
        print("✓ Testing route templates...")
        route_templates = {
            "/api/v1/orders/{order_id}": "/api/v1/orders/{id}",
            "/health": "/health"
        }
        
        result = validate_route_template("/api/v1/orders/12345", route_templates)
        assert result == "/api/v1/orders/{id}", f"Expected '/api/v1/orders/{{id}}', got '{result}'"
        
        result = validate_route_template("/health", route_templates)
        assert result == "/health", f"Expected '/health', got '{result}'"
        
        # Test ObservabilityContract
        print("✓ Testing ObservabilityContract...")
        registry = CollectorRegistry()
        contract = ObservabilityContract(registry)
        
        duplicates = contract.check_for_duplicate_metrics()
        assert isinstance(duplicates, list), "Should return list of duplicates"
        
        summary = contract.get_validation_summary()
        assert "duplicate_metrics" in summary, "Summary should include duplicate metrics"
        assert "histogram_contracts" in summary, "Summary should include histogram contracts"
        
        print("✓ All observability contract tests passed!")
        
    except Exception as e:
        print(f"✗ Observability contracts test failed: {e}")
        return False
    
    return True

def test_security_hardening():
    """Test security hardening functionality."""
    print("\nTesting Security Hardening...")
    
    try:
        from backend.infra.security_hardening import (
            SecuritySettings,
            SimpleRateLimiter,
            JWTValidator
        )
        
        # Test security settings validation
        print("✓ Testing SecuritySettings validation...")
        try:
            # This should fail - empty CORS origins
            SecuritySettings()
            print("✗ SecuritySettings should require CORS origins")
            return False
        except Exception:
            print("  ✓ Correctly rejected empty CORS origins")
        
        # Valid settings
        settings = SecuritySettings(
            cors_allow_origins=["https://example.com"],
            rate_limit_requests_per_minute=60,
            trusted_hosts=["example.com"]
        )
        assert settings.cors_allow_origins == ["https://example.com"]
        print("  ✓ Valid settings accepted")
        
        # Test rate limiter
        print("✓ Testing SimpleRateLimiter...")
        limiter = SimpleRateLimiter(requests_per_minute=5, burst_size=2)
        
        # Should allow first requests
        allowed, info = limiter.is_allowed("127.0.0.1")
        assert allowed is True, "First request should be allowed"
        assert info["requests_made"] == 1, f"Expected 1 request, got {info['requests_made']}"
        
        allowed, info = limiter.is_allowed("127.0.0.1")
        assert allowed is True, "Second request should be allowed"
        assert info["requests_made"] == 2, f"Expected 2 requests, got {info['requests_made']}"
        
        print("  ✓ Rate limiter working correctly")
        
        # Test JWT validator
        print("✓ Testing JWTValidator...")
        validator = JWTValidator(settings)
        options = validator.get_enhanced_jwt_verification_options()
        
        assert options["verify_signature"] is True, "Should verify signature"
        assert options["verify_exp"] is True, "Should verify expiration"
        
        print("  ✓ JWT validator configured correctly")
        
        print("✓ All security hardening tests passed!")
        
    except Exception as e:
        print(f"✗ Security hardening test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_metrics_integration():
    """Test metrics integration with observability contracts."""
    print("\nTesting Metrics Integration...")
    
    try:
        from backend.infra.metrics import MetricsRegistry
        from prometheus_client import CollectorRegistry
        
        print("✓ Testing MetricsRegistry with observability contracts...")
        registry = CollectorRegistry()
        metrics_registry = MetricsRegistry(registry=registry)
        
        # Should have observability contract
        assert metrics_registry.observability_contract is not None, "Should have observability contract"
        
        # Test route validation
        normalized_route = metrics_registry.validate_route_template("/health")
        assert normalized_route == "/health", f"Expected '/health', got '{normalized_route}'"
        
        # Test duplicate detection
        duplicates = metrics_registry.check_duplicate_metrics()
        assert isinstance(duplicates, list), "Should return list of duplicates"
        
        # Test histogram with standardized buckets
        histogram = metrics_registry.histogram(
            "http_request_duration_seconds",
            labels={"route": "/test", "method": "GET"}
        )
        assert histogram is not None, "Should create histogram"
        
        print("✓ Metrics integration tests passed!")
        
    except Exception as e:
        print(f"✗ Metrics integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Run all validation tests."""
    print("=" * 60)
    print("VALIDATION TESTS - Observability & Security Hardening")
    print("=" * 60)
    
    all_passed = True
    
    # Run tests
    all_passed &= test_observability_contracts()
    all_passed &= test_security_hardening()
    all_passed &= test_metrics_integration()
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Implementation is working correctly.")
        return 0
    else:
        print("❌ SOME TESTS FAILED! Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
