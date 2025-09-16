"""
Test OrderSpec validation to ensure __post_init__ is working.
"""

from backend.risk.types import OrderSpec, Side
from decimal import Decimal

try:
    # This should raise ValueError
    spec = OrderSpec(
        symbol="AAPL",
        side=Side.BUY,
        qty=Decimal("-100")  # Negative quantity should fail
    )
    print("❌ FAILED: Expected ValueError for negative qty")
except ValueError as e:
    print(f"✅ SUCCESS: Validation working - {e}")
except Exception as e:
    print(f"❌ UNEXPECTED ERROR: {e}")
