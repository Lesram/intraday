"""
Test script to validate the E1 and E2 constructor improvements.
"""

def test_order_service_constructor():
    """Test OrderService constructor with legacy args."""
    print("\n=== Testing OrderService Constructor ===")
    
    from backend.services.order_service import OrderService
    
    # Test 1: Keyword arguments (new style)
    print("✅ Test 1: Keyword arguments")
    service1 = OrderService(db_session="mock_db", orders_repo="mock_orders", broker="mock_broker")
    assert service1.db_session == "mock_db"
    assert service1.orders_repo == "mock_orders"
    assert service1.broker == "mock_broker"
    print("   ✅ Keyword arguments work")
    
    # Test 2: Positional arguments (legacy style)
    print("✅ Test 2: Legacy positional arguments")
    service2 = OrderService("mock_orders", "mock_broker", "mock_outbox")
    assert service2.orders_repo == "mock_orders"
    assert service2.broker == "mock_broker" 
    assert service2.outbox_repo == "mock_outbox"
    print("   ✅ Legacy positional arguments work")
    
    # Test 3: Mixed arguments
    print("✅ Test 3: Mixed arguments")
    service3 = OrderService("mock_orders", db_session="mock_db", strategy_engine="mock_strategy")
    assert service3.orders_repo == "mock_orders"
    assert service3.db_session == "mock_db"
    assert service3.strategy_engine == "mock_strategy"
    print("   ✅ Mixed arguments work")


def test_order_integrity_service_constructor():
    """Test OrderIntegrityService constructor."""
    print("\n=== Testing OrderIntegrityService Constructor ===")
    
    from backend.models.order_integrity import OrderIntegrityService
    
    # Test with args and kwargs
    print("✅ Test 1: Args and kwargs tolerance")
    service1 = OrderIntegrityService("arg1", "arg2", db_session="mock_db", extra="test")
    assert service1.db_session == "mock_db"
    print("   ✅ OrderIntegrityService tolerates args and kwargs")


def test_order_state_machine_constructor():
    """Test OrderStateMachine constructor."""
    print("\n=== Testing OrderStateMachine Constructor ===")
    
    from backend.models.order_integrity import OrderStateMachine
    
    # Test with args and kwargs
    print("✅ Test 1: Args and kwargs tolerance")
    fsm1 = OrderStateMachine("arg1", audit_logger=lambda: None, extra="test")
    assert fsm1.audit_logger is not None
    print("   ✅ OrderStateMachine tolerates args and kwargs")


def test_order_spec_constructor():
    """Test OrderSpec constructor with order_type alias.""" 
    print("\n=== Testing OrderSpec Constructor ===")
    
    from backend.risk.types import OrderSpec, Side
    from decimal import Decimal
    
    # Test 1: Using type field
    print("✅ Test 1: Using 'type' field")
    spec1 = OrderSpec(
        symbol="AAPL",
        side=Side.BUY,
        qty=Decimal("100"),
        type="market"
    )
    assert spec1.type == "market"
    assert spec1.get("type") == "market"
    assert spec1.get("order_type") == "market"  # Should work as alias
    print("   ✅ 'type' field works")
    
    # Test 2: Using order_type alias  
    print("✅ Test 2: Using 'order_type' alias")
    spec2 = OrderSpec(
        symbol="TSLA", 
        side=Side.SELL,
        qty=Decimal("50"),
        order_type="limit"
    )
    assert spec2.type == "limit"
    assert spec2.get("type") == "limit"
    assert spec2.get("order_type") == "limit"
    print("   ✅ 'order_type' alias works")
    
    # Test 3: Defaults when neither provided
    print("✅ Test 3: Default behavior")
    spec3 = OrderSpec(
        symbol="MSFT",
        side=Side.BUY,
        qty=Decimal("10")
    )
    assert spec3.type is None
    assert spec3.get("type") is None
    assert spec3.get("order_type") is None
    print("   ✅ Default behavior works")


if __name__ == "__main__":
    try:
        test_order_service_constructor()
        test_order_integrity_service_constructor()
        test_order_state_machine_constructor()
        test_order_spec_constructor()
        
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ OrderService: Legacy positional args supported")
        print("✅ OrderIntegrityService: Args/kwargs tolerant")
        print("✅ OrderStateMachine: Args/kwargs tolerant")
        print("✅ OrderSpec: order_type alias supported")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
