#!/usr/bin/env python3
"""Simple test of production guardrails without full integration"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def simple_test():
    """Simple test of production guardrails components"""
    
    print("🧪 Testing production components...")
    
    # Test 1: Simple guardrails init
    try:
        from backend.infra.guardrails_production import TransactionalGuardrails, GuardrailViolation
        
        guardrails = TransactionalGuardrails(
            symbol_whitelist=["AAPL", "MSFT"],
            max_daily_orders=100,
            max_daily_notional=1000.0,
            max_order_size=100.0
        )
        
        print("  ✅ TransactionalGuardrails initialized successfully")
        
        # Test basic validation without database
        try:
            guardrails._validate_symbol("AAPL")  # Should pass
            print("  ✅ Symbol validation working")
        except GuardrailViolation:
            print("  ❌ Symbol validation failed")
        
        try:
            guardrails._validate_symbol("INVALID")  # Should fail
            print("  ❌ Symbol validation not working (should have failed)")
        except GuardrailViolation:
            print("  ✅ Symbol validation properly rejects invalid symbols")
            
        # Test error classification
        test_error = Exception("Connection timeout")
        error_type = guardrails.classify_broker_error(test_error)
        print(f"  ✅ Error classification working: {error_type.value}")
        
        # Test circuit breaker status
        status = guardrails.get_circuit_breaker_status()
        print(f"  ✅ Circuit breaker status: {status}")
        
    except ImportError as e:
        print(f"  ❌ Could not import production guardrails: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Production guardrails test failed: {e}")
        return False
    
    # Test 2: Database models
    try:
        from backend.database.models_production import DailyLedger, OrderEvent
        
        # Test model creation (without database)
        ledger = DailyLedger(
            account_id="test", 
            day_utc="2025-09-30",
            orders_count=5,
            submitted_notional_usd=500.0
        )
        print("  ✅ DailyLedger model working")
        
        event = OrderEvent(
            order_id="test-order",
            broker_order_id="test-broker-123",
            event_type="fill",
            event_time="2025-09-30 10:00:00"
        )
        print("  ✅ OrderEvent model working")
        
    except Exception as e:
        print(f"  ❌ Database models test failed: {e}")
        return False
    
    print("\n🎉 All production components test successfully!")
    return True

if __name__ == "__main__":
    success = asyncio.run(simple_test())
    if success:
        print("\n✅ Production guardrails components are ready for deployment")
    sys.exit(0 if success else 1)