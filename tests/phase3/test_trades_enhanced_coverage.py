#!/usr/bin/env python3
"""
Enhanced trades coverage test - targeting 100% coverage
Focus on missing lines: 147-149, 176-178, 228-230, 246, 250-251, 285-298, 305, 334-339
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import Request

# Add the backend directory to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, backend_path)

@pytest.mark.asyncio
async def test_get_trade_detail_exception():
    """Test lines 147-149: Exception handling in get_trade_detail"""
    from backend.api.routes.trades import get_trade_detail
    from fastapi import HTTPException
    
    # Mock get_current_user dependency
    mock_user = {"user_id": "test"}
    
    with patch('backend.api.routes.trades.logger') as mock_logger:
        try:
            # This should trigger the exception handling
            await get_trade_detail(
                trade_id="non_existent_trade",
                current_user=mock_user
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 500
            assert "Failed to retrieve trade detail" in e.detail
            mock_logger.error.assert_called()
            print("✅ Lines 147-149: Trade detail exception handled")

@pytest.mark.asyncio
async def test_get_trading_stats_exception():
    """Test lines 176-178: Exception handling in get_trading_stats"""
    from backend.api.routes.trades import get_trading_stats
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    with patch('backend.api.routes.trades.logger') as mock_logger:
        try:
            # This should trigger the exception by passing invalid dates
            await get_trading_stats(
                current_user=mock_user,
                start_date="invalid_date",  # This will cause an error
                end_date="invalid_date"
            )
            assert False, "Should have raised HTTPException"
        except (HTTPException, TypeError, ValueError):
            # Could be HTTPException or type error from invalid date
            print("✅ Lines 176-178: Trading stats exception handled")

@pytest.mark.asyncio 
async def test_execute_trade_exception():
    """Test lines 228-230: Exception handling in execute_trade"""
    from backend.api.routes.trades import execute_trade, TradeExecutionRequest
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    trade_request = TradeExecutionRequest(
        symbol="INVALID",
        quantity=-1,  # Invalid quantity
        side="invalid_side"  # Invalid side
    )
    
    with patch('backend.api.routes.trades.logger') as mock_logger:
        try:
            await execute_trade(
                trade_request=trade_request,
                current_user=mock_user
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 500
            assert "Trade execution failed" in e.detail
            mock_logger.error.assert_called()
            print("✅ Lines 228-230: Trade execution exception handled")

@pytest.mark.asyncio
async def test_create_trade_idempotency_cache_hit():
    """Test line 246: Idempotency cache hit"""
    from backend.api.routes.trades import create_trade, _idempotency_cache
    
    # Create a mock request with idempotency key
    mock_request = Mock(spec=Request)
    mock_request.json = AsyncMock(return_value={"symbol": "AAPL", "quantity": 100})
    mock_request.headers = {"X-Idempotency-Key": "test_key_123"}
    
    # Pre-populate cache
    cached_response = {"order_id": "cached_order", "client_order_id": "cached_client"}
    _idempotency_cache["test_key_123"] = cached_response
    
    try:
        result = await create_trade(mock_request)
        assert result == cached_response
        print("✅ Line 246: Idempotency cache hit tested")
    finally:
        # Clean up cache
        _idempotency_cache.clear()

@pytest.mark.asyncio
async def test_create_trade_no_idempotency_key():
    """Test lines 250-251: No idempotency key path"""
    from backend.api.routes.trades import create_trade
    
    # Create a mock request without idempotency key
    mock_request = Mock(spec=Request)
    mock_request.json = AsyncMock(return_value={"symbol": "AAPL", "quantity": 100})
    mock_request.headers = {}  # No idempotency key
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.outbox_dispatcher = None
    
    result = await create_trade(mock_request)
    
    assert "order_id" in result
    assert "client_order_id" in result
    assert result["order_id"].startswith("mock_")
    assert result["client_order_id"].startswith("client_")
    print("✅ Lines 250-251: No idempotency key path tested")

@pytest.mark.asyncio
async def test_outbox_dispatcher_with_prometheus():
    """Test lines 285-298: Outbox dispatcher and Prometheus metrics"""
    from backend.api.routes.trades import create_trade
    
    # Mock outbox dispatcher
    mock_dispatcher = Mock()
    mock_dispatcher.poll_and_dispatch = AsyncMock()
    
    # Mock metrics registry
    mock_registry = Mock()
    mock_counter = Mock()
    mock_counter.inc = Mock()
    
    # Create mock request with all required attributes
    mock_request = Mock(spec=Request)
    mock_request.json = AsyncMock(return_value={"symbol": "AAPL", "quantity": 100})
    mock_request.headers = {"X-Idempotency-Key": "test_prometheus"}
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.outbox_dispatcher = mock_dispatcher
    mock_request.app.state.metrics_registry = mock_registry
    
    with patch('prometheus_client.Counter') as mock_counter_class:
        mock_counter_class.return_value = mock_counter
        
        result = await create_trade(mock_request)
        
        # Verify outbox dispatcher was called
        mock_dispatcher.poll_and_dispatch.assert_called_once()
        
        # Verify counter was incremented
        mock_counter.inc.assert_called_once()
        
        assert "order_id" in result
        print("✅ Lines 285-298: Outbox dispatcher and Prometheus metrics tested")

@pytest.mark.asyncio
async def test_outbox_dispatcher_exception_handling():
    """Test line 305: Exception handling in outbox dispatch"""
    from backend.api.routes.trades import create_trade
    
    # Mock outbox dispatcher that raises exception
    mock_dispatcher = Mock()
    mock_dispatcher.poll_and_dispatch = AsyncMock(side_effect=Exception("Outbox error"))
    
    # Create mock request
    mock_request = Mock(spec=Request)
    mock_request.json = AsyncMock(return_value={"symbol": "AAPL", "quantity": 100})
    mock_request.headers = {"X-Idempotency-Key": "test_exception"}
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.outbox_dispatcher = mock_dispatcher
    mock_request.app.state.metrics_registry = None
    
    # Should not raise exception even if outbox dispatch fails
    result = await create_trade(mock_request)
    
    assert "order_id" in result
    print("✅ Line 305: Outbox dispatcher exception handling tested")

@pytest.mark.asyncio
async def test_simulate_broker_submission_exception():
    """Test lines 334-339: Exception handling in broker simulation"""
    from backend.api.routes.trades import _simulate_broker_submission
    
    # Create mock request
    mock_request = Mock(spec=Request)
    
    # Test with invalid order data that should cause exception
    invalid_order_data = {"invalid": "data"}
    
    # Should not raise exception even if broker simulation fails
    try:
        await _simulate_broker_submission(mock_request, invalid_order_data, "test_order_123")
        print("✅ Lines 334-339: Broker simulation exception handling tested")
    except Exception:
        # Should not reach here - function should handle all exceptions
        assert False, "Broker simulation should handle all exceptions internally"

@pytest.mark.asyncio
async def test_simulate_broker_submission_with_session():
    """Test broker simulation with actual session calls"""
    from backend.api.routes.trades import _simulate_broker_submission
    
    # Create mock request
    mock_request = Mock(spec=Request)
    
    order_data = {
        "symbol": "AAPL",
        "qty": 100,
        "side": "buy",
        "type": "market"
    }
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = Mock()
        mock_session.post = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session
        
        # Should handle the request without raising
        await _simulate_broker_submission(mock_request, order_data, "test_order_456")
        
        print("✅ Broker simulation with session tested")

async def main():
    """Run enhanced trades coverage tests"""
    print("🎯 Enhanced Trades Coverage Test - Targeting 100%")
    print("Missing lines: 147-149, 176-178, 228-230, 246, 250-251, 285-298, 305, 334-339")
    print("=" * 75)
    
    test_functions = [
        ("Trade Detail Exception (147-149)", test_get_trade_detail_exception),
        ("Trading Stats Exception (176-178)", test_get_trading_stats_exception),
        ("Execute Trade Exception (228-230)", test_execute_trade_exception),
        ("Idempotency Cache Hit (246)", test_create_trade_idempotency_cache_hit),
        ("No Idempotency Key (250-251)", test_create_trade_no_idempotency_key),
        ("Outbox Dispatcher + Prometheus (285-298)", test_outbox_dispatcher_with_prometheus),
        ("Outbox Exception Handling (305)", test_outbox_dispatcher_exception_handling),
        ("Broker Simulation Exception (334-339)", test_simulate_broker_submission_exception),
        ("Broker Simulation with Session", test_simulate_broker_submission_with_session),
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_name, test_func in test_functions:
        print(f"\n📋 Testing: {test_name}")
        try:
            await test_func()
            passed += 1
            print(f"✅ {test_name} passed")
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
    
    print(f"\n📊 Enhanced Coverage Results: {passed}/{total} tests passed")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎯 Perfect! All missing lines covered!")
    elif passed >= total * 0.8:
        print("🟢 Excellent coverage improvement!")
    else:
        print(f"🔶 {total - passed} tests still need work")
    
    return passed >= total * 0.8

if __name__ == "__main__":
    # Run the enhanced coverage tests
    result = asyncio.run(main())