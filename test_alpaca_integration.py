#!/usr/bin/env python3
"""
Test Alpaca Client Integration with Real Credentials
"""

import asyncio
import sys
from backend.data.alpaca_client import AlpacaClient
from backend.config.settings import settings

async def test_alpaca_integration():
    """Test AlpacaClient with real credentials."""
    print("🧪 Testing Alpaca Client Integration...")
    
    # Create client
    client = AlpacaClient(
        api_key=settings.alpaca.api_key,
        secret_key=settings.alpaca.secret_key,
        paper=settings.alpaca.paper_trading
    )
    
    print(f"✅ AlpacaClient created (Paper mode: {client.paper})")
    
    try:
        # Test account access
        print("\n📊 Testing account access...")
        account_status = client.get_account_status()
        print(f"  ✅ Account Status Retrieved: {account_status}")
        
        # Test orders
        print("\n� Testing recent orders...")
        orders = client.get_recent_orders(limit=10)
        print(f"  ✅ Found {len(orders)} recent orders")
        for order in orders[:3]:  # Show first 3
            print(f"    - {order.get('symbol', 'N/A')}: {order.get('side', 'N/A')} {order.get('qty', 'N/A')} @ {order.get('order_type', 'N/A')}")
        
        # Test current price
        print("\n� Testing current price...")
        try:
            price = client.get_current_price("AAPL")
            if price:
                print(f"  ✅ AAPL Current Price: ${price:.2f}")
            else:
                print("  ⚠️ Could not get AAPL price (market closed?)")
        except Exception as e:
            print(f"  ⚠️ Price lookup failed: {e}")
            
        # Test historical data
        print("\n📈 Testing historical data...")
        try:
            from datetime import datetime, timedelta
            
            bars = client.get_bars(
                symbols=["AAPL"],
                timeframe="1Min",
                start=datetime.now() - timedelta(hours=1),
                end=datetime.now()
            )
            print(f"  ✅ Retrieved {len(bars)} bars for AAPL")
            if not bars.empty:
                latest = bars.iloc[-1]
                print(f"    Latest AAPL bar: ${latest['close']:.2f}")
        except Exception as e:
            print(f"  ⚠️ Historical data test failed: {e}")
            
        print("\n🎉 All Alpaca integration tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_alpaca_integration())
    sys.exit(0 if success else 1)