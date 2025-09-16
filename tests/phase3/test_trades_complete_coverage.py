#!/usr/bin/env python3
"""
Complete Trades.py Coverage Test - targeting 100% coverage
Focus on missing lines: 147-149, 176-178, 228-230, 295-298, 334-339
Fix failing tests and achieve perfect coverage
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

# Add the backend directory to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, backend_path)

@pytest.mark.asyncio
async def test_get_trade_detail_exception_lines_147_149():
    """Test lines 147-149: Exception handling in get_trade_detail"""
    from backend.api.routes.trades import get_trade_detail
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # The function will have issues getting trade data, so let's simulate that
    # Since it's currently using mock data, we need to force an exception
    with patch('backend.api.routes.trades.logger') as mock_logger:
        # Patch the trade building logic to raise an exception
        with patch.dict('backend.api.routes.trades._submitted_orders', {'trade_123': True}):
            # Mock trade data that will cause processing error
            with patch('backend.api.routes.trades.TradeHistory') as MockTradeHistory:
                MockTradeHistory.side_effect = Exception("Trade processing error")
                
                try:
                    await get_trade_detail(
                        trade_id="trade_123", 
                        current_user=mock_user
                    )
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 500
                    assert "Failed to retrieve trade detail" in e.detail
                    print("✅ Lines 147-149: get_trade_detail exception handling tested")

@pytest.mark.asyncio
async def test_get_trading_stats_exception_lines_176_178():
    """Test lines 176-178: Exception handling in get_trading_stats"""
    from backend.api.routes.trades import get_trading_stats
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Force an exception in the stats computation
    with patch('backend.api.routes.trades.logger') as mock_logger:
        # Patch datetime to raise an exception during processing
        with patch('backend.api.routes.trades.datetime') as mock_datetime:
            mock_datetime.now.side_effect = Exception("Stats computation error")
            
            try:
                await get_trading_stats(
                    current_user=mock_user,
                    start_date=datetime.now() - timedelta(days=30),
                    end_date=datetime.now()
                )
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 500
                assert "Failed to retrieve trading statistics" in e.detail
                print("✅ Lines 176-178: get_trading_stats exception handling tested")

@pytest.mark.asyncio
async def test_execute_trade_exception_lines_228_230():
    """Test lines 228-230: Exception handling in execute_trade"""
    from backend.api.routes.trades import execute_trade, TradeExecutionRequest
    from fastapi import HTTPException
    
    # Create user with trading privileges
    mock_user = Mock()
    mock_user.roles = ["trader"]
    
    trade_request = TradeExecutionRequest(
        symbol="AAPL",
        quantity=100,
        side="buy",
        order_type="market"
    )
    
    # Force an exception in the trade execution logic
    with patch('backend.api.routes.trades.logger') as mock_logger:
        # Patch uuid to raise an exception
        with patch('backend.api.routes.trades.uuid') as mock_uuid:
            mock_uuid.uuid4.side_effect = Exception("Trade execution error")
            
            try:
                await execute_trade(
                    trade_request=trade_request,
                    current_user=mock_user
                )
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 500
                assert "Trade execution failed" in e.detail
                print("✅ Lines 228-230: execute_trade exception handling tested")

@pytest.mark.asyncio 
async def test_prometheus_metrics_exception_lines_295_298():
    """Test lines 295-298: Prometheus metrics ValueError exception handling"""
    from backend.api.routes.trades import create_trade
    from fastapi import Request
    
    # Create a mock request
    mock_request = Mock(spec=Request)
    mock_request.json = AsyncMock(return_value={
        "symbol": "AAPL",
        "quantity": 100,
        "side": "buy",
        "order_type": "market"
    })
    mock_request.headers = {"idempotency-key": "test_key_123"}
    
    # Mock prometheus_client to trigger ValueError and then recovery path
    with patch('backend.api.routes.trades.prometheus_client') as mock_prom:
        # Create a mock registry that raises ValueError on first inc() call
        mock_reg = Mock()
        mock_counter = Mock()
        mock_counter.inc.side_effect = [ValueError("Collector already exists"), None]
        mock_prom.CollectorRegistry.return_value = mock_reg
        mock_prom.Counter.return_value = mock_counter
        
        # Mock the _names_to_collectors dict to return a collector for recovery
        mock_recovery_counter = Mock()
        mock_reg._names_to_collectors = {"outbox_dispatched_total": mock_recovery_counter}
        
        result = await create_trade(mock_request)
        
        # Should have handled the ValueError and used recovery path
        assert "order_id" in result
        mock_recovery_counter.inc.assert_called_once()
        print("✅ Lines 295-298: Prometheus ValueError exception handling tested")

@pytest.mark.asyncio
async def test_broker_simulation_exception_lines_334_339():
    """Test lines 334-339: Broker simulation exception handling"""
    from backend.api.routes.trades import _simulate_broker_submission
    from fastapi import Request
    
    mock_request = Mock(spec=Request)
    order_data = {
        "symbol": "AAPL",
        "quantity": 100,
        "side": "buy",
        "order_type": "market"
    }
    order_id = "test_order_123"
    
    # Mock httpx to raise an exception during broker communication
    with patch('backend.api.routes.trades.httpx') as mock_httpx:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Network error")
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
        
        # This should handle the exception gracefully and not raise
        try:
            await _simulate_broker_submission(mock_request, order_data, order_id)
            print("✅ Lines 334-339: Broker simulation exception handling tested")
        except Exception as e:
            assert False, f"Should have handled exception gracefully, but got: {e}"

@pytest.mark.asyncio
async def test_execute_trade_user_without_roles():
    """Test execute_trade with user that has no roles attribute"""
    from backend.api.routes.trades import execute_trade, TradeExecutionRequest
    from fastapi import HTTPException
    
    # Create user without roles attribute
    mock_user = {"user_id": "test"}  # Dict without roles
    
    trade_request = TradeExecutionRequest(
        symbol="AAPL",
        quantity=100,
        side="buy"
    )
    
    try:
        await execute_trade(
            trade_request=trade_request,
            current_user=mock_user
        )
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 403
        assert "Trading privileges required" in e.detail
        print("✅ execute_trade user without roles tested")

async def main():
    """Run complete trades coverage tests"""
    print("🎯 Complete Trades.py Coverage Test - Targeting 100%")
    print("Missing lines: 147-149, 176-178, 228-230, 295-298, 334-339")
    print("=" * 70)
    
    test_functions = [
        ("Trade Detail Exception (147-149)", test_get_trade_detail_exception_lines_147_149),
        ("Trading Stats Exception (176-178)", test_get_trading_stats_exception_lines_176_178),
        ("Execute Trade Exception (228-230)", test_execute_trade_exception_lines_228_230),
        ("Prometheus Metrics Exception (295-298)", test_prometheus_metrics_exception_lines_295_298),
        ("Broker Simulation Exception (334-339)", test_broker_simulation_exception_lines_334_339),
        ("Execute Trade No Roles", test_execute_trade_user_without_roles),
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
    
    print(f"\n📊 Complete Coverage Results: {passed}/{total} tests passed")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎯 Perfect! All missing lines covered!")
    else:
        print(f"🔶 {total - passed} tests still need work")
    
    return passed == total

if __name__ == "__main__":
    # Run the complete coverage tests
    result = asyncio.run(main())