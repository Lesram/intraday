#!/usr/bin/env python3
"""
WebSocket Real-Time Update Test Script

This script tests the WebSocket real-time portfolio update functionality
by broadcasting updates to connected clients.

Usage:
    python test_websocket_updates.py
"""

import asyncio
import sys
import json
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, '.')

from backend.api.socketio_server import broadcast_portfolio_update


async def test_portfolio_broadcast():
    """Test broadcasting portfolio updates via WebSocket."""
    
    print("=" * 80)
    print("WEBSOCKET REAL-TIME UPDATE TEST")
    print("=" * 80)
    print()
    print("⚠️  INSTRUCTIONS:")
    print("1. Make sure backend is running (python main.py)")
    print("2. Open dashboard in browser (http://localhost:5173)")
    print("3. Watch the dashboard while this script runs")
    print("4. Values should update WITHOUT page refresh")
    print()
    input("Press ENTER when ready to start test...")
    print()
    
    # Test user ID (use actual logged-in user)
    user_id = "admin@example.com"
    
    print(f"📊 Broadcasting updates to user: {user_id}")
    print()
    
    # Test 1: Initial portfolio state
    print("Test 1: Broadcasting initial portfolio state...")
    portfolio_1 = {
        'totalEquity': 100000.0,
        'cash': 100000.0,
        'buyingPower': 100000.0,
        'marginUsed': 0.0,
        'maintenanceMargin': 0.0,
        'totalPnL': 0.0,
        'totalPnLPercent': 0.0,
        'dayPnL': 0.0,
        'dayPnLPercent': 0.0,
        'positions': [],
        'userId': user_id,
        'lastUpdate': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        await broadcast_portfolio_update(user_id, portfolio_1)
        print("✅ Sent: Total Equity = $100,000.00")
        print(json.dumps(portfolio_1, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    print("⏳ Wait 5 seconds...")
    await asyncio.sleep(5)
    print()
    
    # Test 2: Simulate a profitable trade
    print("Test 2: Broadcasting portfolio with $5,000 profit...")
    portfolio_2 = {
        'totalEquity': 105000.0,  # +$5,000
        'cash': 95000.0,          # Used $10,000 for position
        'buyingPower': 95000.0,
        'marginUsed': 0.0,
        'maintenanceMargin': 0.0,
        'totalPnL': 5000.0,       # +$5,000 profit
        'totalPnLPercent': 5.0,   # +5%
        'dayPnL': 5000.0,
        'dayPnLPercent': 5.0,
        'positions': [
            {
                'symbol': 'AAPL',
                'quantity': 50,
                'avgPrice': 180.0,
                'currentPrice': 200.0,
                'marketValue': 10000.0,
                'unrealizedPnL': 1000.0,
                'unrealizedPnLPercent': 11.11,
                'side': 'long',
                'exchange': 'NASDAQ'
            }
        ],
        'userId': user_id,
        'lastUpdate': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        await broadcast_portfolio_update(user_id, portfolio_2)
        print("✅ Sent: Total Equity = $105,000.00 (+$5,000)")
        print("✅ Sent: Total P&L = $5,000.00 (+5.0%)")
        print("✅ Sent: 1 position (AAPL)")
        print(json.dumps(portfolio_2, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    print("⏳ Wait 5 seconds...")
    await asyncio.sleep(5)
    print()
    
    # Test 3: Simulate a loss
    print("Test 3: Broadcasting portfolio with $2,000 loss from peak...")
    portfolio_3 = {
        'totalEquity': 103000.0,  # Down from $105k
        'cash': 95000.0,
        'buyingPower': 95000.0,
        'marginUsed': 0.0,
        'maintenanceMargin': 0.0,
        'totalPnL': 3000.0,       # +$3,000 total (down from +$5k)
        'totalPnLPercent': 3.0,
        'dayPnL': -2000.0,        # -$2,000 today
        'dayPnLPercent': -1.9,
        'positions': [
            {
                'symbol': 'AAPL',
                'quantity': 50,
                'avgPrice': 180.0,
                'currentPrice': 188.0,  # Down from $200
                'marketValue': 9400.0,
                'unrealizedPnL': 400.0,
                'unrealizedPnLPercent': 4.44,
                'side': 'long',
                'exchange': 'NASDAQ'
            }
        ],
        'userId': user_id,
        'lastUpdate': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        await broadcast_portfolio_update(user_id, portfolio_3)
        print("✅ Sent: Total Equity = $103,000.00")
        print("✅ Sent: Day P&L = -$2,000.00 (-1.9%)")
        print("✅ Sent: Position updated (AAPL price changed)")
        print(json.dumps(portfolio_3, indent=2))
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    print("⏳ Wait 5 seconds...")
    await asyncio.sleep(5)
    print()
    
    # Test 4: Reset to original
    print("Test 4: Resetting to original portfolio state...")
    try:
        await broadcast_portfolio_update(user_id, portfolio_1)
        print("✅ Sent: Back to Total Equity = $100,000.00")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print()
    print("=" * 80)
    print("✅ TEST COMPLETE")
    print("=" * 80)
    print()
    print("📋 Expected Results:")
    print("  ✅ Dashboard updated 4 times without page refresh")
    print("  ✅ Portfolio Equity changed: $100k → $105k → $103k → $100k")
    print("  ✅ P&L values changed and showed correct colors")
    print("  ✅ Position appeared and disappeared smoothly")
    print()
    print("Did the dashboard update correctly? (Check the browser)")
    print()


def main():
    """Main entry point."""
    try:
        asyncio.run(test_portfolio_broadcast())
    except KeyboardInterrupt:
        print("\n❌ Test cancelled by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
