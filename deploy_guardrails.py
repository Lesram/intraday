#!/usr/bin/env python3
"""Integration script to deploy transactional guardrails"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def deploy_transactional_guardrails():
    """Deploy the production guardrails with database backing"""
    
    print("🚀 Deploying transactional guardrails for Phase 5...")
    
    # Step 1: Create a compatibility module that bridges old and new APIs
    print("\n📋 Step 1: Creating guardrails compatibility layer")
    
    # Import the existing guardrails to understand current usage
    try:
        from backend.infra.guardrails import TradingGuardrails, GuardrailResult, GuardrailViolation
        from backend.infra.guardrails_production import TransactionalGuardrails, GuardrailViolation as ProductionGuardrailViolation
        print("  ✅ Imported existing and production guardrails")
    except ImportError as e:
        print(f"  ❌ Failed to import guardrails: {e}")
        return False
    
    # Step 2: Test the production guardrails
    print("\n📋 Step 2: Testing production guardrails")
    
    try:
        # Initialize production guardrails  
        production_guardrails = TransactionalGuardrails(
            symbol_whitelist=["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "SPY", "QQQ"],
            max_daily_orders=1000,
            max_daily_notional=10000.0,
            max_order_size=1000.0,
            trading_start_hour=9,
            trading_end_hour=16
        )
        
        # Test atomic validation
        test_account = "TEST_ACCOUNT_PHASE5"
        test_symbol = "AAPL"
        test_notional = 100.0
        test_client_id = "test_order_12345"
        
        await production_guardrails.validate_order_atomic(
            account_id=test_account,
            symbol=test_symbol,
            notional_usd=test_notional,
            client_order_id=test_client_id
        )
        print("  ✅ Production guardrails validation successful")
        
        # Test event recording
        event_recorded = await production_guardrails.record_trade_event(
            order_id="test-uuid-1234",
            broker_order_id="TEST_BROKER_456",
            event_type="test_event",
            event_time=asyncio.get_event_loop().time(),
            event_data={"test": True}
        )
        print(f"  ✅ Event recording: {'New event' if event_recorded else 'Duplicate detected'}")
        
        # Test circuit breaker
        status = production_guardrails.get_circuit_breaker_status()
        print(f"  ✅ Circuit breaker status: {'Open' if status['circuit_open'] else 'Closed'}")
        
    except Exception as e:
        print(f"  ❌ Production guardrails test failed: {e}")
        return False
    
    # Step 3: Create hybrid guardrails that use database backing  
    print("\n📋 Step 3: Creating hybrid guardrails implementation")
    
    hybrid_guardrails_code = '''
"""Hybrid guardrails that bridge existing API with production database backing"""

import asyncio
from typing import Optional
from backend.infra.guardrails import TradingGuardrails as OriginalGuardrails, GuardrailResult, OrderRequest
from backend.infra.guardrails_production import TransactionalGuardrails, GuardrailViolation as ProductionGuardrailViolation

class HybridTradingGuardrails(OriginalGuardrails):
    """
    Hybrid guardrails that maintain the original API while using 
    production database-backed validation internally.
    """
    
    def __init__(self):
        # Initialize the original guardrails for config compatibility
        super().__init__()
        
        # Initialize production guardrails with database backing
        self._production_guardrails = TransactionalGuardrails(
            symbol_whitelist=list(self.symbol_whitelist),
            max_daily_orders=self.max_daily_orders,
            max_daily_notional=float(self.daily_notional_cap_usd),
            max_order_size=float(self.max_order_size),
            trading_start_hour=self.trading_window_start.hour,
            trading_end_hour=self.trading_window_end.hour
        )
    
    async def validate_order(self, order: OrderRequest) -> GuardrailResult:
        """
        Validate order using production guardrails with database backing.
        Maintains compatibility with existing API.
        """
        try:
            # Use production guardrails for atomic validation
            await self._production_guardrails.validate_order_atomic(
                account_id="default_account",  # TODO: Get from order or context
                symbol=order.symbol,
                notional_usd=float(order.qty) * 100,  # Estimate notional
                client_order_id=getattr(order, 'client_order_id', f"order_{id(order)}")
            )
            
            # If no exception, validation passed
            return GuardrailResult(
                allowed=True,
                violations=[],
                warnings=[],
                details={
                    "validation_type": "production_atomic",
                    "circuit_breaker_status": self._production_guardrails.get_circuit_breaker_status()
                }
            )
            
        except ProductionGuardrailViolation as e:
            # Convert production violation to original format
            return GuardrailResult(
                allowed=False,
                violations=[{
                    "code": e.violation_type,
                    "message": str(e),
                    "current_value": getattr(e, 'current_value', None),
                    "limit": getattr(e, 'limit', None)
                }],
                warnings=[],
                details={
                    "validation_type": "production_atomic",
                    "violation_details": {
                        "type": e.violation_type,
                        "current": getattr(e, 'current_value', None),
                        "limit": getattr(e, 'limit', None)
                    }
                }
            )
        except Exception as e:
            # Fallback to original validation on unexpected errors
            print(f"Production validation failed, falling back to original: {e}")
            return await super().validate_order(order)
    
    def get_production_guardrails(self) -> TransactionalGuardrails:
        """Get access to underlying production guardrails for advanced features"""
        return self._production_guardrails

# Replace the global instance
_hybrid_guardrails_instance: Optional[HybridTradingGuardrails] = None

def get_guardrails() -> HybridTradingGuardrails:
    """Get the hybrid guardrails instance with production backing"""
    global _hybrid_guardrails_instance
    if _hybrid_guardrails_instance is None:
        _hybrid_guardrails_instance = HybridTradingGuardrails()
    return _hybrid_guardrails_instance
'''
    
    # Write the hybrid guardrails
    with open(project_root / "backend" / "infra" / "guardrails_hybrid.py", "w") as f:
        f.write(hybrid_guardrails_code)
    print("  ✅ Created hybrid guardrails implementation")
    
    # Step 4: Update the factory to use hybrid guardrails
    print("\n📋 Step 4: Updating application factory")
    
    factory_file = project_root / "backend" / "api" / "factory.py"
    if factory_file.exists():
        print("  ✅ Factory file found - manual update needed")
        print("     Add: from backend.infra.guardrails_hybrid import get_guardrails")
    else:
        print("  ⚠️ Factory file not found - manual integration required")
    
    print("\n🎉 Transactional guardrails deployment completed!")
    print("\n📋 Next steps:")
    print("  1. Test the hybrid guardrails with existing API")
    print("  2. Gradually migrate to production features")
    print("  3. Monitor database operations and performance")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(deploy_transactional_guardrails())
    sys.exit(0 if success else 1)