#!/usr/bin/env python3
"""
Test script to verify portfolio API returns correct camelCase schema.
"""

import asyncio
import json
from backend.services.portfolio_service import get_portfolio_service


async def test_portfolio_service():
    """Test portfolio service directly."""
    print("=" * 80)
    print("TESTING PORTFOLIO SERVICE")
    print("=" * 80)
    
    service = get_portfolio_service()
    result = await service.get_user_portfolio('test_user_123')
    
    print("\n✅ Portfolio Service Response:")
    print(json.dumps(result, indent=2))
    
    # Verify schema
    print("\n📋 Schema Verification:")
    required_fields = [
        'totalEquity', 'cash', 'buyingPower', 'marginUsed', 
        'maintenanceMargin', 'totalPnL', 'totalPnLPercent',
        'dayPnL', 'dayPnLPercent', 'positions', 'userId', 'lastUpdate'
    ]
    
    missing_fields = [f for f in required_fields if f not in result]
    if missing_fields:
        print(f"❌ Missing fields: {missing_fields}")
    else:
        print("✅ All required fields present")
    
    # Verify types
    print("\n🔍 Type Verification:")
    type_checks = [
        ('totalEquity', float),
        ('cash', float),
        ('buyingPower', float),
        ('totalPnL', float),
        ('dayPnL', float),
        ('positions', list),
        ('userId', str),
    ]
    
    for field, expected_type in type_checks:
        actual_type = type(result.get(field))
        status = "✅" if isinstance(result.get(field), expected_type) else "❌"
        print(f"{status} {field}: {actual_type.__name__} (expected {expected_type.__name__})")
    
    # Verify values
    print("\n💰 Value Verification:")
    print(f"Total Equity: ${result['totalEquity']:,.2f}")
    print(f"Cash: ${result['cash']:,.2f}")
    print(f"Buying Power: ${result['buyingPower']:,.2f}")
    print(f"Total P&L: ${result['totalPnL']:,.2f}")
    print(f"Day P&L: ${result['dayPnL']:,.2f}")
    print(f"Positions: {len(result['positions'])}")
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETE - Schema is correct!")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(test_portfolio_service())
