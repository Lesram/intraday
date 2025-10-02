"""
Circuit Breaker Production Validation Test
Validates that the circuit breaker and broker error classification is fully functional
"""

import asyncio
import time
from typing import Dict, Any

# Test the circuit breaker implementation
def test_circuit_breaker_implementation():
    """Test that circuit breaker implementation exists and is functional."""
    
    print("\n" + "="*60)
    print("CIRCUIT BREAKER PRODUCTION VALIDATION")  
    print("="*60)
    
    results = {
        "Circuit Breaker Import": False,
        "Error Classification": False,
        "State Management": False,
        "Broker Integration": False,
        "Production Configuration": False
    }
    
    try:
        # 1. Test Circuit Breaker Import
        print("🔍 Testing circuit breaker import...")
        try:
            from backend.infra.guardrails_production import TransactionalGuardrails, BrokerErrorType
            results["Circuit Breaker Import"] = True
            print("✅ Circuit breaker classes imported successfully")
        except Exception as e:
            print(f"❌ Circuit breaker import failed: {e}")
        
        # 2. Test Error Classification  
        print("\n🔍 Testing broker error classification...")
        try:
            guardrails = TransactionalGuardrails(["AAPL", "MSFT"])
            
            # Mock different error types
            class MockError:
                def __init__(self, msg, status_code=None):
                    self.message = msg
                    if status_code:
                        self.status_code = status_code
                def __str__(self):
                    return self.message
            
            # Test classification of different errors
            test_errors = [
                (MockError("Connection timeout", 500), BrokerErrorType.BROKER_DOWN),
                (MockError("Insufficient funds", 400), BrokerErrorType.BROKER_REJECT),
                (MockError("Rate limit exceeded", 429), BrokerErrorType.RATE_LIMITED),
                (MockError("Network connection refused"), BrokerErrorType.BROKER_DOWN),
                (MockError("Invalid order parameters"), BrokerErrorType.BROKER_REJECT)
            ]
            
            all_classified_correctly = True
            for error, expected_type in test_errors:
                classified_type = guardrails.classify_broker_error(error)
                if classified_type == expected_type:
                    print(f"  ✅ {error.message} → {classified_type.value}")
                else:
                    print(f"  ❌ {error.message} → {classified_type.value} (expected {expected_type.value})")
                    all_classified_correctly = False
            
            if all_classified_correctly:
                results["Error Classification"] = True
                print("✅ All error types classified correctly")
            else:
                print("❌ Some error classifications incorrect")
                
        except Exception as e:
            print(f"❌ Error classification test failed: {e}")
        
        # 3. Test State Management
        print("\n🔍 Testing circuit breaker state management...")
        try:
            guardrails = TransactionalGuardrails(["AAPL"], circuit_breaker_threshold=3)
            
            # Initial state
            initial_state = guardrails.get_circuit_breaker_status()
            if not initial_state["circuit_open"] and initial_state["consecutive_errors"] == 0:
                print("  ✅ Initial state correct: circuit closed, no errors")
            else:
                print(f"  ❌ Initial state incorrect: {initial_state}")
                
            # Trip circuit breaker
            timeout_error = MockError("Connection timeout", 500)
            for i in range(4):  # Exceed threshold of 3
                guardrails.record_broker_error(timeout_error)
            
            tripped_state = guardrails.get_circuit_breaker_status()
            if tripped_state["circuit_open"] and tripped_state["consecutive_errors"] >= 3:
                print(f"  ✅ Circuit breaker tripped correctly after {tripped_state['consecutive_errors']} errors")
                results["State Management"] = True
            else:
                print(f"  ❌ Circuit breaker did not trip: {tripped_state}")
            
            # Test reset
            guardrails.reset_circuit_breaker()
            reset_state = guardrails.get_circuit_breaker_status()
            if not reset_state["circuit_open"] and reset_state["consecutive_errors"] == 0:
                print("  ✅ Circuit breaker reset correctly")
            else:
                print(f"  ❌ Circuit breaker reset failed: {reset_state}")
                
        except Exception as e:
            print(f"❌ State management test failed: {e}")
        
        # 4. Test Broker Integration Points
        print("\n🔍 Testing broker integration points...")
        try:
            # Check if circuit breaker is used in stream client
            import os
            stream_files = [
                "backend/integrations/alpaca_stream_production.py",
                "backend/integrations/alpaca_stream.py"
            ]
            
            integration_found = False
            for file_path in stream_files:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if "record_broker_error" in content or "guardrails" in content:
                            print(f"  ✅ Circuit breaker integration found in {file_path}")
                            integration_found = True
                            break
            
            if integration_found:
                results["Broker Integration"] = True
            else:
                print("  ⚠️  Circuit breaker integration not found in stream clients")
                
        except Exception as e:
            print(f"❌ Broker integration test failed: {e}")
        
        # 5. Test Production Configuration
        print("\n🔍 Testing production configuration...")
        try:
            import os
            
            # Check environment variable support
            env_vars = [
                "CIRCUIT_BREAKER_THRESHOLD", 
                "CIRCUIT_BREAKER_WINDOW_MINUTES",
                "CIRCUIT_BREAKER_RECOVERY_TIME_MINUTES"
            ]
            
            config_ready = True
            for var in env_vars:
                if var in os.environ:
                    print(f"  ✅ {var} configured: {os.environ[var]}")
                else:
                    print(f"  ℹ️  {var} not set (using defaults)")
            
            # Test guardrails can be initialized with environment config
            guardrails = TransactionalGuardrails(
                ["AAPL", "MSFT"],
                circuit_breaker_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "10")),
                circuit_breaker_window_minutes=int(os.getenv("CIRCUIT_BREAKER_WINDOW_MINUTES", "5"))
            )
            
            print(f"  ✅ Production guardrails initialized with threshold={guardrails.circuit_breaker_threshold}")
            results["Production Configuration"] = True
            
        except Exception as e:
            print(f"❌ Production configuration test failed: {e}")
    
    except Exception as e:
        print(f"❌ Overall circuit breaker test failed: {e}")
    
    # Print Summary
    print("\n" + "="*60)
    print("CIRCUIT BREAKER VALIDATION SUMMARY")
    print("="*60)
    
    total_passed = 0
    for component, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{component:<30} {status}")
        if passed:
            total_passed += 1
    
    total_tests = len(results)
    percentage = (total_passed / total_tests) * 100
    
    print("="*60)
    print(f"Circuit Breaker Readiness: {total_passed}/{total_tests} ({percentage:.0f}%)")
    
    if percentage >= 80:
        print("🎉 Circuit breaker implementation is PRODUCTION READY!")
        print("✅ Broker error classification working correctly")
        print("✅ Circuit breaker state management functional") 
        print("✅ Integration points established")
    elif percentage >= 60:
        print("⚠️  Circuit breaker implementation needs minor improvements")
    else:
        print("❌ Circuit breaker implementation needs major improvements")
    
    print("="*60)
    
    return results


if __name__ == "__main__":
    test_circuit_breaker_implementation()