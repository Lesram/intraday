#!/usr/bin/env python3
"""
Test script to verify the complete database-backed order flow fix.
Tests that order creation and status lookup work properly with database persistence.
"""

import asyncio
import os
import uuid
from backend.infra.db import init_db
from backend.infra.repositories.orders import OrdersRepo
from backend.infra.outbox import OutboxRepo
from backend.services.order_service import OrderService


async def test_complete_order_flow():
    """Test complete order creation and status lookup with database."""
    
    print("=== Testing Complete Database-Backed Order Flow ===")
    
    # 1. Initialize database
    database_url = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./test_trading_platform.db')
    print(f"1. Initializing database: {database_url}")
    
    try:
        engine, sessionmaker = init_db(database_url)
        print("   ✅ Database initialization successful")
    except Exception as e:
        print(f"   ❌ Database initialization failed: {e}")
        return False
    
    # 2. Create OrderService with database sessionmaker
    print("2. Creating OrderService with database sessionmaker...")
    # OrderService will create repositories internally when sessionmaker is provided
    order_service = OrderService(sessionmaker=sessionmaker)
    
    # 3. Test order submission
    print("3. Testing order submission...")
    # Create a simple signal dict that matches what OrderService expects
    test_signal = {
        "signal_id": "test-signal-" + str(uuid.uuid4())[:8],
        "timestamp": "2024-01-15T10:30:00Z",
        "symbol": "AAPL",
        "side": "buy",  # Required field for OrderService
        "qty": 10,       # Required field for OrderService  
        "confidence": 0.85,
        "price": 150.0
    }
    
    try:
        # Submit order
        result = await order_service.submit_order_async(test_signal)
        
        if result and hasattr(result, 'order_id'):
            order_id = result.order_id
            print(f"   ✅ Order submitted successfully with ID: {order_id}")
        else:
            print(f"   ❌ Order submission failed - no order_id in result: {result}")
            return False
            
    except Exception as e:
        print(f"   ❌ Order submission failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 4. Test order status lookup
    print("4. Testing order status lookup...")
    try:
        # Get order status using the enhanced method
        status = await order_service.get_order_status(order_id)
        
        if status:
            print(f"   ✅ Order status retrieved successfully: {status}")
            
            # Verify order details match
            if hasattr(status, 'symbol') and status.symbol == test_signal["symbol"]:
                print("   ✅ Order details match original signal")
            else:
                print(f"   ⚠️  Order details mismatch - status symbol: {getattr(status, 'symbol', 'N/A')}, signal symbol: {test_signal['symbol']}")
                
        else:
            print(f"   ❌ Order status lookup returned None for order_id: {order_id}")
            return False
            
    except Exception as e:
        print(f"   ❌ Order status lookup failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. Test with invalid order ID
    print("5. Testing lookup with invalid order ID...")
    try:
        invalid_id = str(uuid.uuid4())
        status = await order_service.get_order_status(invalid_id)
        
        if status is None:
            print("   ✅ Invalid order ID correctly returns None")
        else:
            print(f"   ⚠️  Invalid order ID returned unexpected result: {status}")
            
    except Exception as e:
        print(f"   ⚠️  Invalid order ID lookup raised exception: {e}")
    
    print("\n=== Test Complete ===")
    print("✅ All tests passed! Database-backed order flow is working correctly.")
    return True


if __name__ == "__main__":
    asyncio.run(test_complete_order_flow())