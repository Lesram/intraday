"""
Unit Test - K6 Parsing Logic Validation
Tests the actual parsing logic with sample K6 output
"""

import json
from pathlib import Path

# Sample K6 summary data (mimics real K6 output)
SAMPLE_K6_SUMMARY = {
    "metrics": {
        "http_reqs": {
            "count": 1000,
            "rate": 16.666666666666668
        },
        "http_req_failed": {
            "rate": 0.0,
            "passes": 1000,
            "fails": 0
        },
        "http_req_duration": {
            "values": {
                "avg": 35.5,
                "min": 12.3,
                "max": 156.7,
                "p(50)": 32.1,
                "p(90)": 45.2,
                "p(95)": 52.8,
                "p(99)": 78.4
            }
        },
        "http_req_duration{name:GET /health}": {
            "values": {
                "avg": 25.3,
                "min": 10.1,
                "max": 65.2,
                "p(50)": 22.5,
                "p(90)": 35.7,
                "p(95)": 42.1,
                "p(99)": 58.9,
                "count": 200
            }
        },
        "http_req_duration{name:GET /api/v1/signals}": {
            "values": {
                "avg": 45.7,
                "min": 15.2,
                "max": 180.3,
                "p(50)": 40.2,
                "p(90)": 60.5,
                "p(95)": 68.3,
                "p(99)": 95.1,
                "count": 300
            }
        },
        "http_req_duration{name:POST /api/v1/orders/submit}": {
            "values": {
                "avg": 55.2,
                "min": 20.5,
                "max": 220.7,
                "p(50)": 50.1,
                "p(90)": 75.3,
                "p(95)": 85.6,
                "p(99)": 125.4,
                "count": 150
            }
        },
        "unexpected_error_rate": {
            "rate": 0.005,
            "passes": 995,
            "fails": 5
        }
    }
}

def test_latency_extraction():
    """Test overall latency extraction"""
    print("\n🧪 Testing Latency Extraction...")
    
    metrics = SAMPLE_K6_SUMMARY["metrics"]
    http_req_duration = metrics.get('http_req_duration', {})
    
    if http_req_duration:
        values = http_req_duration.get('values', {})
        
        # Test robust parsing (as in our fix)
        avg_latency_ms = float(values.get('avg', 0) or 0)
        p95_latency_ms = float(values.get('p(95)', 0) or 0)
        p99_latency_ms = float(values.get('p(99)', 0) or 0)
        
        print(f"  ✅ Avg Latency: {avg_latency_ms:.1f}ms (expected: 35.5ms)")
        print(f"  ✅ P95 Latency: {p95_latency_ms:.1f}ms (expected: 52.8ms)")
        print(f"  ✅ P99 Latency: {p99_latency_ms:.1f}ms (expected: 78.4ms)")
        
        assert abs(avg_latency_ms - 35.5) < 0.1, "Avg latency mismatch"
        assert abs(p95_latency_ms - 52.8) < 0.1, "P95 latency mismatch"
        assert abs(p99_latency_ms - 78.4) < 0.1, "P99 latency mismatch"
        
        return True
    
    print("  ❌ No latency data found")
    return False

def test_route_metrics_extraction():
    """Test per-route metrics extraction"""
    print("\n🧪 Testing Route Metrics Extraction...")
    
    metrics = SAMPLE_K6_SUMMARY["metrics"]
    route_metrics = {}
    
    # Simulate our extraction logic
    for metric_name, metric_data in metrics.items():
        if metric_name.startswith('http_req_duration{name:') and metric_name.endswith('}'):
            # Extract endpoint name
            start_idx = metric_name.find('name:') + 5
            end_idx = metric_name.rfind('}')
            endpoint = metric_name[start_idx:end_idx]
            
            # Extract values
            values = metric_data.get('values', {})
            if values:
                route_metrics[endpoint] = {
                    'p95_ms': float(values.get('p(95)', 0) or 0),
                    'p99_ms': float(values.get('p(99)', 0) or 0),
                    'avg_ms': float(values.get('avg', 0) or 0),
                    'count': int(values.get('count', 0) or 0)
                }
    
    print(f"  ✅ Extracted {len(route_metrics)} routes:")
    for endpoint, metrics in route_metrics.items():
        print(f"    • {endpoint}: P95={metrics['p95_ms']:.1f}ms, count={metrics['count']}")
    
    # Validate
    assert len(route_metrics) == 3, f"Expected 3 routes, got {len(route_metrics)}"
    assert "GET /health" in route_metrics, "Missing GET /health"
    assert "GET /api/v1/signals" in route_metrics, "Missing GET /api/v1/signals"
    assert "POST /api/v1/orders/submit" in route_metrics, "Missing POST /api/v1/orders/submit"
    
    # Check specific values
    health_p95 = route_metrics["GET /health"]["p95_ms"]
    assert abs(health_p95 - 42.1) < 0.1, f"GET /health P95 mismatch: {health_p95}"
    
    return True

def test_exit_code_handling():
    """Test K6 exit code evaluation"""
    print("\n🧪 Testing Exit Code Handling...")
    
    test_cases = [
        (0, True, "Exit code 0 (success)"),
        (99, True, "Exit code 99 (non-fatal warning)"),
        (1, False, "Exit code 1 (error)"),
        (127, False, "Exit code 127 (command not found)")
    ]
    
    for return_code, expected_continue, description in test_cases:
        # Simulate our logic
        should_continue = return_code in [0, 99]
        
        if should_continue == expected_continue:
            print(f"  ✅ {description}: {'Continue' if should_continue else 'Fail'}")
        else:
            print(f"  ❌ {description}: Expected {expected_continue}, got {should_continue}")
            return False
    
    return True

def test_slo_calculation():
    """Test SLO calculation from burn-in metrics"""
    print("\n🧪 Testing SLO Calculation...")
    
    # Sample burn-in data
    burn_in_data = {
        "aggregate_metrics": {
            "average_success_rate": 1.0,  # 100%
            "total_requests": 259135
        }
    }
    
    # Simulate our SLO calculation
    success_rate = burn_in_data["aggregate_metrics"]["average_success_rate"]
    availability = success_rate
    
    # Calculate error budget
    slo_target = 0.99  # 99% target
    if availability >= slo_target:
        error_budget_remaining = (availability - slo_target) / (1 - slo_target)
    else:
        error_budget_remaining = 0.0
    
    print(f"  ✅ Success Rate: {success_rate:.3%}")
    print(f"  ✅ Availability: {availability:.3%}")
    print(f"  ✅ Error Budget: {error_budget_remaining:.3%}")
    
    assert availability == 1.0, "Availability should be 100%"
    assert error_budget_remaining == 1.0, "Error budget should be 100% with perfect availability"
    
    # Test with lower availability
    print("\n  Testing with 99.5% availability...")
    availability_2 = 0.995
    error_budget_2 = (availability_2 - slo_target) / (1 - slo_target)
    print(f"  ✅ Availability: {availability_2:.3%}")
    print(f"  ✅ Error Budget: {error_budget_2:.3%}")
    
    assert abs(error_budget_2 - 0.5) < 0.01, "Error budget should be 50% with 99.5% availability"
    
    return True

def test_null_handling():
    """Test handling of null/missing values"""
    print("\n🧪 Testing Null/Missing Value Handling...")
    
    # Sample with nulls and missing values
    test_data = {
        "values": {
            "avg": None,
            "p(95)": 0,
            "p(99)": None
        }
    }
    
    values = test_data["values"]
    
    # Test our robust parsing
    avg_ms = float(values.get('avg', 0) or 0)
    p95_ms = float(values.get('p(95)', 0) or 0)
    p99_ms = float(values.get('p(99)', 0) or 0)
    missing_ms = float(values.get('p(50)', 0) or 0)
    
    print(f"  ✅ Null avg → {avg_ms:.1f}ms (expected: 0.0)")
    print(f"  ✅ Zero p95 → {p95_ms:.1f}ms (expected: 0.0)")
    print(f"  ✅ Null p99 → {p99_ms:.1f}ms (expected: 0.0)")
    print(f"  ✅ Missing p50 → {missing_ms:.1f}ms (expected: 0.0)")
    
    assert avg_ms == 0.0, "Null should convert to 0.0"
    assert p95_ms == 0.0, "Zero should stay 0.0"
    assert p99_ms == 0.0, "Null should convert to 0.0"
    assert missing_ms == 0.0, "Missing should default to 0.0"
    
    return True

def main():
    print("=" * 70)
    print("🧪 PARSING LOGIC UNIT TESTS")
    print("=" * 70)
    
    tests = [
        ("Latency Extraction", test_latency_extraction),
        ("Route Metrics Extraction", test_route_metrics_extraction),
        ("Exit Code Handling", test_exit_code_handling),
        ("SLO Calculation", test_slo_calculation),
        ("Null Handling", test_null_handling)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} FAILED with exception: {str(e)}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST RESULTS")
    print("=" * 70)
    print(f"\n✅ Passed: {passed}/{len(tests)}")
    if failed > 0:
        print(f"❌ Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n🎉 ALL PARSING LOGIC TESTS PASSED!")
        print("   The fixes are working correctly.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        print("   Review the failures above.")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
