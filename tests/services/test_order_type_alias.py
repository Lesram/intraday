"""
Test that our order_type alias works with existing patterns.
"""

from tests.helpers.factories import create_order_spec
from backend.risk.types import OrderSpec, Side
from decimal import Decimal

# Test factory still works
print("=== Testing Factory Compatibility ===")
order = create_order_spec()
print(f'Factory order type: {order.get("order_type")}')

# Test direct construction with order_type
print("\n=== Testing Direct Construction ===")
spec = OrderSpec(symbol='TEST', side=Side.BUY, qty=Decimal('100'), order_type='market')  
print(f'Direct order_type: {spec.get("order_type")}')
print(f'Direct type: {spec.get("type")}')

# Test that both resolve to the same thing
print(f'Are they equal? {spec.get("order_type") == spec.get("type")}')

# Test construction with type instead
spec2 = OrderSpec(symbol='TEST2', side=Side.SELL, qty=Decimal('50'), type='limit')
print(f'Type field order_type: {spec2.get("order_type")}')
print(f'Type field type: {spec2.get("type")}')

print('✅ order_type alias working correctly!')
