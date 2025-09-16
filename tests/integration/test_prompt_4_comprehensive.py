"""
Comprehensive test to validate Prompt 4 implementation with integration.
"""

from decimal import Decimal

def test_integration():
    """Integration test combining all Prompt 4 features"""
    
    # Test OrderService with mixed args
    from backend.services.order_service import OrderService
    
    service = OrderService(
        "mock_orders_repo", 
        broker="mock_broker",  # mixed positional and keyword 
        db_session="test_session"
    )
    
    assert service.orders_repo == "mock_orders_repo"
    assert service.broker == "mock_broker"
    assert service.db_session == "test_session"
    
    # Test that update_status stub works
    result = service.update_status("order_1", "filled", timestamp="2025-08-24")
    assert result is None
    
    # Test OrderSpec with legacy aliases
    from backend.risk.types import OrderSpec
    from backend.strategies.types import Side
    
    # Create spec using aliases
    spec = OrderSpec(
        symbol="AAPL",
        side=Side.BUY,
        quantity=Decimal("150"),  # quantity alias instead of qty
        order_type="limit",       # order_type alias instead of type
        price=Decimal("175.50")
    )
    
    # Verify canonical fields are set
    assert spec.qty == Decimal("150")
    assert spec.type == "limit"
    assert spec.symbol == "AAPL"
    assert spec.side == Side.BUY
    
    # Verify get() method works with aliases
    assert spec.get("quantity") == Decimal("150")
    assert spec.get("order_type") == "limit"
    assert spec.get("qty") == Decimal("150") 
    assert spec.get("type") == "limit"
    
    # Test FSM with audit logging
    from backend.services.order_fsm import OrderStateMachine
    
    audit_log = []
    def audit_fn(*args, **kwargs):
        audit_log.append({"args": args, "kwargs": kwargs})
    
    fsm = OrderStateMachine(audit_logger=audit_fn)
    order = fsm.create_order({"symbol": spec.symbol, "qty": float(spec.qty)})
    
    assert order["id"] == "test-order"
    assert order["status"] == "new"
    assert len(audit_log) == 1
    assert audit_log[0]["args"][0] == "create_order"
    
    # Test OrderIntegrityService
    from backend.services.order_integrity_service import OrderIntegrityService
    
    integrity = OrderIntegrityService(db_session="test_db")
    is_valid = integrity.validate(order)
    assert is_valid is True
    
    print("✅ Integration test passed - all Prompt 4 features working together!")


def test_edge_cases():
    """Test edge cases and error conditions"""
    
    from backend.risk.types import OrderSpec
    from backend.strategies.types import Side
    
    # Test with both canonical and alias names (canonical should win precedence)
    spec = OrderSpec(
        symbol="MSFT",
        side=Side.SELL,
        qty=Decimal("100"),        # canonical
        quantity=Decimal("200"),   # alias - should be ignored since qty is present
        type="market",             # canonical  
        order_type="limit"         # alias - should be ignored since type is present
    )
    
    assert spec.qty == Decimal("100")  # canonical won
    assert spec.type == "market"       # canonical won
    
    # Test with aliases only
    spec2 = OrderSpec(
        symbol="GOOGL",
        side=Side.BUY,
        quantity=Decimal("300"),   # alias only
        order_type="stop"          # alias only
    )
    
    assert spec2.qty == Decimal("300")  # alias used when canonical absent
    assert spec2.type == "stop"         # alias used when canonical absent
    
    # Test OrderService with no args (should use defaults/mocks)
    from backend.services.order_service import OrderService
    
    service = OrderService()
    assert service.orders_repo is not None  # Should be AsyncMock
    assert service.broker is not None       # Should be AsyncMock
    assert service.outbox_repo is not None  # Should be AsyncMock
    
    print("✅ Edge cases test passed!")


if __name__ == "__main__":
    test_integration()
    test_edge_cases()
    print("🎉 All comprehensive tests passed!")
