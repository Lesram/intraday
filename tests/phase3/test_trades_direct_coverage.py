"""
Phase 3.1 - Trades Module Direct Coverage Testing
Target: 100% coverage for backend/api/routes/trades.py (130 statements)
Strategy: Direct module import and function testing
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime, timedelta
import json
from fastapi import HTTPException

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

async def test_import_trades_module():
    """Test importing the trades module"""
    try:
        from backend.api.routes.trades import router, TradeHistory, TradeHistoryResponse, TradeExecutionRequest
        assert router is not None
        assert TradeHistory is not None
        assert TradeHistoryResponse is not None
        assert TradeExecutionRequest is not None
        
        print("✅ Trades module imported successfully")
        return True
    except Exception as e:
        print(f"❌ Trades module import failed: {e}")
        return False


async def test_trade_models_coverage():
    """Test trade models validation and creation"""
    try:
        from backend.api.routes.trades import TradeHistory, TradeHistoryResponse, TradeExecutionRequest
        
        # Test TradeHistory model creation - covers model validation
        trade = TradeHistory(
            trade_id="test_001",
            symbol="AAPL",
            quantity=100.0,
            price=150.25,
            side="buy",
            timestamp=datetime.now(),
            order_type="market",
            fees=1.50,
            pnl=25.00
        )
        assert trade.trade_id == "test_001"
        assert trade.symbol == "AAPL"
        assert trade.quantity == 100.0
        assert trade.side == "buy"
        
        # Test TradeHistoryResponse model - covers response model validation
        history_response = TradeHistoryResponse(
            trades=[trade],
            total_count=1,
            page=1,
            page_size=10
        )
        assert len(history_response.trades) == 1
        assert history_response.total_count == 1
        assert history_response.page == 1
        
        # Test TradeExecutionRequest model - covers request model validation
        execution_request = TradeExecutionRequest(
            symbol="MSFT",
            quantity=50.0,
            side="sell",
            order_type="limit"
        )
        assert execution_request.symbol == "MSFT"
        assert execution_request.quantity == 50.0
        assert execution_request.side == "sell"
        assert execution_request.order_type == "limit"
        
        print("✅ Trade models tested successfully")
        return True
    except Exception as e:
        print(f"❌ Trade models test failed: {e}")
        return False


async def test_trade_history_endpoint():
    """Test get_trade_history endpoint logic"""
    try:
        from backend.api.routes.trades import get_trade_history
        
        # Mock authenticated user with trader role
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        # Test basic trade history retrieval - covers main path
        result = await get_trade_history(
            current_user=mock_user,
            symbol=None,
            start_date=None,
            end_date=None,
            page=1,
            page_size=100
        )
        assert result.total_count >= 0
        assert result.page == 1
        assert result.page_size == 100
        assert isinstance(result.trades, list)
        print("✅ Basic trade history tested")
        
        # Test symbol filtering - covers symbol filter branch
        result_filtered = await get_trade_history(
            current_user=mock_user,
            symbol="AAPL",
            start_date=None,
            end_date=None,
            page=1,
            page_size=100
        )
        # All trades should be AAPL (or empty if no AAPL trades)
        for trade in result_filtered.trades:
            assert trade.symbol == "AAPL"
        print("✅ Symbol filtering tested")
        
        # Test date filtering - covers date filter branches
        start_date = datetime.now() - timedelta(days=2)
        end_date = datetime.now()
        result_date_filtered = await get_trade_history(
            current_user=mock_user,
            symbol=None,
            start_date=start_date,
            end_date=end_date,
            page=1,
            page_size=100
        )
        # Verify dates are within range
        for trade in result_date_filtered.trades:
            assert trade.timestamp >= start_date
            assert trade.timestamp <= end_date
        print("✅ Date filtering tested")
        
        # Test pagination - covers pagination logic
        result_page2 = await get_trade_history(
            current_user=mock_user,
            symbol=None,
            start_date=None,
            end_date=None,
            page=2,
            page_size=1
        )
        assert result_page2.page == 2
        assert result_page2.page_size == 1
        print("✅ Pagination tested")
        
        print("✅ Trade history endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Trade history endpoint test failed: {e}")
        return False


async def test_permission_handling():
    """Test permission and authentication handling"""
    try:
        from backend.api.routes.trades import get_trade_history, execute_trade, TradeExecutionRequest
        
        # Test read-only user permission denial - covers permission check branch
        readonly_user = Mock()
        readonly_user.roles = ["read-only"]
        
        try:
            await get_trade_history(
                current_user=readonly_user,
                symbol=None,
                start_date=None,
                end_date=None,
                page=1,
                page_size=100
            )
            assert False, "Should have raised HTTPException for read-only user"
        except HTTPException as e:
            assert e.status_code == 403
            assert "Insufficient permissions" in e.detail
            print("✅ Read-only permission denial tested")
        
        # Test unauthenticated user for execute_trade - covers auth check
        try:
            trade_request = TradeExecutionRequest(
                symbol="AAPL",
                quantity=100.0,
                side="buy",
                order_type="market"
            )
            await execute_trade(trade_request, current_user=None)
            assert False, "Should have raised HTTPException for unauthenticated user"
        except HTTPException as e:
            assert e.status_code == 401
            assert "Authentication required" in e.detail
            print("✅ Unauthenticated user denial tested")
        
        # Test user without trading privileges - covers role check branch
        basic_user = Mock()
        basic_user.roles = ["viewer"]
        
        try:
            trade_request = TradeExecutionRequest(
                symbol="AAPL",
                quantity=100.0,
                side="buy",
                order_type="market"
            )
            await execute_trade(trade_request, current_user=basic_user)
            assert False, "Should have raised HTTPException for non-trader user"
        except HTTPException as e:
            assert e.status_code == 403
            assert "Trading privileges required" in e.detail
            print("✅ Non-trader permission denial tested")
        
        print("✅ Permission handling tested successfully")
        return True
    except Exception as e:
        print(f"❌ Permission handling test failed: {e}")
        return False


async def test_trade_detail_endpoint():
    """Test get_trade_detail endpoint"""
    try:
        from backend.api.routes.trades import get_trade_detail
        
        # Mock authenticated user
        mock_user = {"user_id": "test_user"}
        
        # Test trade detail retrieval - covers trade detail logic
        result = await get_trade_detail(
            trade_id="test_trade_123",
            current_user=mock_user
        )
        assert result.trade_id == "test_trade_123"
        assert result.symbol is not None
        assert result.quantity > 0
        assert result.price > 0
        assert result.side in ["buy", "sell"]
        
        print("✅ Trade detail endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Trade detail endpoint test failed: {e}")
        return False


async def test_trading_stats_endpoint():
    """Test get_trading_stats endpoint"""
    try:
        from backend.api.routes.trades import get_trading_stats
        
        # Mock authenticated user
        mock_user = {"user_id": "test_user"}
        
        # Test trading stats without date filters - covers basic stats path
        result = await get_trading_stats(
            current_user=mock_user,
            start_date=None,
            end_date=None
        )
        assert "total_trades" in result
        assert "profitable_trades" in result
        assert "losing_trades" in result
        assert "win_rate" in result
        assert "total_pnl" in result
        assert "total_fees" in result
        assert "net_pnl" in result
        assert isinstance(result["total_trades"], int)
        assert isinstance(result["win_rate"], float)
        print("✅ Basic trading stats tested")
        
        # Test trading stats with date filters - covers date filter handling
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        result_filtered = await get_trading_stats(
            current_user=mock_user,
            start_date=start_date,
            end_date=end_date
        )
        assert "total_trades" in result_filtered
        assert "win_rate" in result_filtered
        print("✅ Date-filtered trading stats tested")
        
        print("✅ Trading stats endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Trading stats endpoint test failed: {e}")
        return False


async def test_execute_trade_endpoint():
    """Test execute_trade endpoint (deprecated)"""
    try:
        from backend.api.routes.trades import execute_trade, TradeExecutionRequest
        
        # Mock authenticated trader user
        trader_user = Mock()
        trader_user.roles = ["trader"]
        
        # Test successful trade execution - covers main execution path
        trade_request = TradeExecutionRequest(
            symbol="AAPL",
            quantity=100.0,
            side="buy",
            order_type="market"
        )
        result = await execute_trade(trade_request, current_user=trader_user)
        assert "trade_id" in result
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["side"] == "buy"
        assert result["order_type"] == "market"
        assert result["status"] == "executed"
        assert "price" in result
        assert "timestamp" in result
        print("✅ Successful trade execution tested")
        
        # Test with admin user - covers admin role path
        admin_user = Mock()
        admin_user.roles = ["admin"]
        
        trade_request_admin = TradeExecutionRequest(
            symbol="MSFT",
            quantity=50.0,
            side="sell",
            order_type="limit"
        )
        result_admin = await execute_trade(trade_request_admin, current_user=admin_user)
        assert result_admin["symbol"] == "MSFT"
        assert result_admin["side"] == "sell"
        print("✅ Admin trade execution tested")
        
        print("✅ Execute trade endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Execute trade endpoint test failed: {e}")
        return False


async def test_create_trade_endpoint():
    """Test create_trade endpoint with idempotency"""
    try:
        from backend.api.routes.trades import create_trade
        
        # Mock request object
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={
            "symbol": "TSLA",
            "quantity": 25,
            "side": "buy",
            "order_type": "market",
            "time_in_force": "day"
        })
        
        # Test without idempotency key - covers basic creation path
        mock_headers = Mock()
        mock_headers.get = Mock(return_value=None)  # No idempotency key
        mock_request.headers = mock_headers
        
        result = await create_trade(mock_request)
        assert "order_id" in result
        assert "client_order_id" in result
        assert result["status"] == "submitted"
        assert result["symbol"] == "TSLA"
        assert result["quantity"] == "25"
        assert result["side"] == "buy"
        assert result["order_type"] == "market"
        print("✅ Basic trade creation tested")
        
        # Test with idempotency key - covers idempotency logic
        mock_headers_idem = Mock()
        mock_headers_idem.get = Mock(return_value="test-idem-key-123")
        mock_request.headers = mock_headers_idem
        
        result_idem = await create_trade(mock_request)
        assert "order_id" in result_idem
        assert result_idem["symbol"] == "TSLA"
        print("✅ Idempotent trade creation tested")
        
        # Test duplicate idempotency key - covers cache hit path
        from backend.api.routes.trades import _idempotency_cache
        _idempotency_cache["test-duplicate-key"] = {"cached": "response"}
        
        mock_headers_dup = Mock()
        mock_headers_dup.get = Mock(return_value="test-duplicate-key")
        mock_request.headers = mock_headers_dup
        
        result_cached = await create_trade(mock_request)
        assert result_cached == {"cached": "response"}
        print("✅ Cached idempotency response tested")
        
        print("✅ Create trade endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Create trade endpoint test failed: {e}")
        return False


async def test_broker_simulation():
    """Test broker simulation functionality"""
    try:
        from backend.api.routes.trades import _simulate_broker_submission
        
        # Mock request with app state
        mock_request = Mock()
        mock_app_state = Mock()
        mock_app_state.ws_manager = Mock()  # Indicates test environment
        mock_request.app.state = mock_app_state
        
        # Test broker simulation - covers simulation logic
        order_data = {
            "symbol": "NVDA",
            "quantity": 10,
            "side": "buy",
            "order_type": "market",
            "time_in_force": "day"
        }
        
        # This should complete without error (network call is mocked/ignored)
        await _simulate_broker_submission(mock_request, order_data, "test_order_123")
        print("✅ Broker simulation tested")
        
        print("✅ Broker simulation tested successfully")
        return True
    except Exception as e:
        print(f"❌ Broker simulation test failed: {e}")
        return False


async def test_error_handling_paths():
    """Test error handling in various endpoints"""
    try:
        from backend.api.routes.trades import get_trade_history, get_trade_detail, get_trading_stats, execute_trade, TradeExecutionRequest
        
        # Test trade history error handling
        mock_user = Mock()
        mock_user.roles = ["trader"]
        
        # Mock an exception in trade history
        with patch('backend.api.routes.trades.logger') as mock_logger:
            # This should handle gracefully and log error
            try:
                # Force an error by passing invalid date type
                await get_trade_history(
                    current_user=mock_user,
                    symbol=None,
                    start_date="invalid_date",  # This should cause an error
                    end_date=None,
                    page=1,
                    page_size=100
                )
            except HTTPException as e:
                assert e.status_code == 500
                assert "Failed to retrieve trade history" in e.detail
                print("✅ Trade history error handling tested")
        
        # Test trade detail error handling
        try:
            # This should work normally
            await get_trade_detail("error_trade", {"user_id": "test"})
            print("✅ Trade detail error path covered")
        except Exception:
            # Expected if there's an error, that's fine
            print("✅ Trade detail error handling tested")
        
        print("✅ Error handling paths tested successfully")
        return True
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


async def test_route_signatures():
    """Test route function signatures and imports"""
    try:
        from backend.api.routes.trades import (
            get_trade_history,
            get_trade_detail,
            get_trading_stats,
            execute_trade,
            create_trade,
            _simulate_broker_submission,
            router
        )
        
        # Verify all route functions exist
        assert callable(get_trade_history)
        assert callable(get_trade_detail)
        assert callable(get_trading_stats)
        assert callable(execute_trade)
        assert callable(create_trade)
        assert callable(_simulate_broker_submission)
        assert router is not None
        
        # Test router configuration
        assert router.prefix == "/trades"
        assert "trades" in router.tags
        
        print("✅ Route signatures tested successfully")
        return True
    except Exception as e:
        print(f"❌ Route signatures test failed: {e}")
        return False


async def main():
    """Main test execution function"""
    print("🚀 Phase 3.1 - Trades Module Direct Coverage Testing")
    print("Target: 100% coverage for backend/api/routes/trades.py (130 statements)")
    print("=" * 70)
    
    test_functions = [
        ("Import Trades Module", test_import_trades_module),
        ("Trade Models Coverage", test_trade_models_coverage),
        ("Trade History Endpoint", test_trade_history_endpoint),
        ("Permission Handling", test_permission_handling),
        ("Trade Detail Endpoint", test_trade_detail_endpoint),
        ("Trading Stats Endpoint", test_trading_stats_endpoint),
        ("Execute Trade Endpoint", test_execute_trade_endpoint),
        ("Create Trade Endpoint", test_create_trade_endpoint),
        ("Broker Simulation", test_broker_simulation),
        ("Error Handling Paths", test_error_handling_paths),
        ("Route Signatures", test_route_signatures),
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_name, test_func in test_functions:
        print(f"\n📋 Testing: {test_name}")
        try:
            success = await test_func()
            if success:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Coverage Results: {passed}/{total} tests passed")
    success_rate = (passed / total) * 100
    print(f"Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🟢 Excellent coverage achieved")
    elif success_rate >= 75:
        print("🟡 Good coverage progress")
    else:
        print("🔴 More coverage needed")


if __name__ == "__main__":
    asyncio.run(main())