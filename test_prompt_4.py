"""
Test Prompt 4 implementation: Order constructor/contract shims
"""

from decimal import Decimal

def test_prompt_4a():
    """Test Prompt 4A: Legacy args tolerance in order services"""
    
    # Test OrderService with legacy positional args
    from backend.services.order_service import OrderService
    
    # Test with positional args
    service = OrderService("orders_repo", "broker", "outbox_repo", db_session="test_session")
    assert service.orders_repo == "orders_repo"
    assert service.broker == "broker" 
    assert service.outbox_repo == "outbox_repo"
    assert service.db_session == "test_session"
    
    # Test update_status stub method exists
    assert hasattr(service, "update_status")
    result = service.update_status("arg1", "arg2", kwarg="test")
    assert result is None
    
    # Test OrderIntegrityService
    from backend.services.order_integrity_service import OrderIntegrityService
    
    integrity_service = OrderIntegrityService("arg1", "arg2", db_session="test_db")
    assert integrity_service.db_session == "test_db"
    assert integrity_service.validate({"test": "order"}) is True
    
    # Test OrderStateMachine
    from backend.services.order_fsm import OrderStateMachine
    
    audit_calls = []
    def test_audit(*args, **kwargs):
        audit_calls.append((args, kwargs))
    
    fsm = OrderStateMachine("arg1", "arg2", audit_logger=test_audit)
    assert fsm.audit_logger == test_audit
    
    order = fsm.create_order({"symbol": "AAPL", "side": "buy"})
    assert order["id"] == "test-order"
    assert order["status"] == "new"
    assert len(audit_calls) == 1
    assert audit_calls[0][0] == ("create_order", {"symbol": "AAPL", "side": "buy"})
    
    print("✅ Prompt 4A tests passed!")


def test_prompt_4b():
    """Test Prompt 4B: OrderSpec aliases for order_type and quantity"""
    
    from backend.risk.types import OrderSpec
    from backend.strategies.types import Side
    
    # Test order_type alias
    spec1 = OrderSpec(
        symbol="AAPL",
        side=Side.BUY,
        qty=Decimal("100"),
        order_type="market"  # Using alias
    )
    assert spec1.type == "market"
    assert spec1.get("type") == "market"
    assert spec1.get("order_type") == "market"  # Alias should work in get() too
    
    # Test quantity alias
    spec2 = OrderSpec(
        symbol="AAPL", 
        side=Side.BUY,
        quantity=Decimal("200"),  # Using alias
        type="limit"
    )
    assert spec2.qty == Decimal("200")
    assert spec2.get("qty") == Decimal("200")
    assert spec2.get("quantity") == Decimal("200")  # Alias should work in get() too
    
    # Test both aliases together
    spec3 = OrderSpec(
        symbol="GOOGL",
        side=Side.SELL,
        quantity=Decimal("50"),  # quantity alias
        order_type="stop"        # order_type alias
    )
    assert spec3.qty == Decimal("50")
    assert spec3.type == "stop"
    assert spec3.get("quantity") == Decimal("50")
    assert spec3.get("order_type") == "stop"
    
    print("✅ Prompt 4B tests passed!")


if __name__ == "__main__":
    test_prompt_4a()
    test_prompt_4b()
    print("🎉 All Prompt 4 tests passed!")
