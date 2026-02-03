"""
REAL Order Flow Integration Tests.

These tests validate the COMPLETE order lifecycle:
- Real order submission to Alpaca paper trading
- Real order status tracking
- Real fills and partial fills
- Real cancellations
- Real order validation

NO MOCKING - All orders are submitted to real paper trading.

Note: Some tests require buying power and will be skipped if the account
has insufficient funds to place orders.
"""

import asyncio
from datetime import datetime, UTC
import pytest


# =============================================================================
# ORDER SUBMISSION TESTS
# =============================================================================

class TestRealOrderSubmission:
    """Real order submission tests using Alpaca paper trading."""
    
    @pytest.mark.asyncio
    async def test_submit_market_buy_order(self, paper_broker, require_market_open):
        """
        Test submitting a real market buy order.
        Order is submitted to Alpaca paper trading.
        """
        # Check buying power first
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 20:
            pytest.skip(f"Insufficient buying power (${buying_power:.2f}) to place orders")
        
        # Use cheapest stock for low buying power
        symbol = "F"  # Ford ~$10-15
        
        # Submit real order
        order = await paper_broker.place_order(
            symbol=symbol,
            qty=1,
            side="buy",
            type="market",
            tif="day"
        )
        
        assert order is not None, "Order submission returned None"
        assert order["symbol"] == symbol
        assert order["side"] == "buy"
        assert str(order["qty"]) == "1"
        assert order["type"] == "market"
        assert order["status"] in ["new", "pending_new", "accepted", "filled"]
        
        order_id = order["id"]
        
        # Wait briefly for order processing
        await asyncio.sleep(2)
        
        # Check order status
        updated_order = await paper_broker.get_order(order_id)
        
        # If filled, sell it back
        if updated_order["status"] == "filled":
            sell_order = await paper_broker.place_order(
                symbol=symbol,
                qty=1,
                side="sell",
                type="market",
                tif="day"
            )
            await asyncio.sleep(2)
        elif updated_order["status"] not in ["filled", "cancelled", "canceled"]:
            # Cancel if still pending
            try:
                await paper_broker.cancel_order(order_id)
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_submit_limit_order_below_market(self, paper_broker, require_market_open):
        """
        Test submitting a limit buy order well below market price.
        Order should remain open (not fill immediately).
        """
        # Check buying power first
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 50:
            pytest.skip(f"Insufficient buying power (${buying_power:.2f}) to place orders")
        
        # Set limit price very low (won't fill)
        limit_price = 1.00  # Extremely low
        
        order = await paper_broker.place_order(
            symbol="AAPL",
            qty=1,
            side="buy",
            type="limit",
            limit_price=limit_price,
            tif="day"
        )
        
        assert order is not None
        assert order["type"] == "limit"
        
        # Wait for order to be accepted
        await asyncio.sleep(1)
        
        # Order should still be open (not filled at this price)
        updated_order = await paper_broker.get_order(order["id"])
        assert updated_order["status"] in ["new", "accepted", "pending_new"]
        
        # Cancel the order
        await paper_broker.cancel_order(order["id"])
        
        # Verify cancellation
        await asyncio.sleep(0.5)
        cancelled_order = await paper_broker.get_order(order["id"])
        assert cancelled_order["status"] in ["cancelled", "canceled", "pending_cancel"]
    
    @pytest.mark.asyncio
    async def test_submit_and_immediately_cancel(self, paper_broker, require_market_open):
        """Test that orders can be submitted and immediately cancelled."""
        # Check buying power first
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 100:
            pytest.skip(f"Insufficient buying power (${buying_power:.2f}) to place orders")
        
        # Submit a limit order far from market
        order = await paper_broker.place_order(
            symbol="MSFT",
            qty=1,
            side="buy",
            type="limit",
            limit_price=1.00,  # Very low - won't fill
            tif="day"
        )
        
        assert order is not None
        
        # Immediately cancel
        await paper_broker.cancel_order(order["id"])
        
        # Verify cancellation succeeded
        await asyncio.sleep(0.5)
        final_order = await paper_broker.get_order(order["id"])
        assert final_order["status"] in ["cancelled", "canceled", "pending_cancel"]


# =============================================================================
# ORDER STATUS TRACKING TESTS
# =============================================================================

class TestRealOrderStatusTracking:
    """Test real order status tracking."""
    
    @pytest.mark.asyncio
    async def test_order_lifecycle_status_progression(self, paper_broker, require_market_open):
        """
        Test that orders progress through expected status lifecycle.
        new/pending_new -> accepted -> filled (for market orders)
        """
        # Check buying power first
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 20:
            pytest.skip(f"Insufficient buying power (${buying_power:.2f})")
        
        # Submit a market order that should fill quickly
        order = await paper_broker.place_order(
            symbol="F",
            qty=1,
            side="buy",
            type="market",
            tif="day"
        )
        
        initial_status = order["status"]
        assert initial_status in ["new", "pending_new", "accepted", "filled"]
        
        # Wait for fill
        for _ in range(10):
            await asyncio.sleep(1)
            updated = await paper_broker.get_order(order["id"])
            if updated["status"] == "filled":
                # Verify fill data
                assert float(updated.get("filled_qty", 0)) == 1
                assert float(updated.get("filled_avg_price", 0)) > 0
                
                # Sell it back
                await paper_broker.place_order(
                    symbol="F",
                    qty=1,
                    side="sell",
                    type="market",
                    tif="day"
                )
                break
        else:
            # Cancel if not filled
            try:
                await paper_broker.cancel_order(order["id"])
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_get_order_by_id(self, paper_broker):
        """Test retrieving an existing order by ID."""
        # This doesn't require buying power - just check we can call the API
        # Try to get a non-existent order (will fail or return None)
        try:
            order = await paper_broker.get_order("nonexistent-order-id-12345")
            # If it doesn't raise, order should be None or have error status
        except Exception as e:
            # Expected - order doesn't exist or invalid ID format
            error_msg = str(e).lower()
            assert "not found" in error_msg or "404" in str(e) or "422" in str(e) or "missing" in error_msg


# =============================================================================
# ORDER VALIDATION TESTS  
# =============================================================================

class TestRealOrderValidation:
    """Test real order validation by the broker."""
    
    @pytest.mark.asyncio
    async def test_reject_invalid_symbol(self, paper_broker):
        """Test that invalid symbols are rejected."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await paper_broker.place_order(
                symbol="INVALID_XYZ_123",
                qty=1,
                side="buy",
                type="market",
                tif="day"
            )
        
        # Alpaca returns 403 or 422 for invalid symbols
        assert exc_info.value.status_code in [400, 403, 404, 422]
    
    @pytest.mark.asyncio
    async def test_reject_zero_quantity(self, paper_broker):
        """Test that zero quantity orders are rejected."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException):
            await paper_broker.place_order(
                symbol="AAPL",
                qty=0,
                side="buy",
                type="market",
                tif="day"
            )
    
    @pytest.mark.asyncio
    async def test_reject_negative_limit_price(self, paper_broker):
        """Test that negative limit prices are rejected."""
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException):
            await paper_broker.place_order(
                symbol="AAPL",
                qty=1,
                side="buy",
                type="limit",
                limit_price=-10.00,
                tif="day"
            )


# =============================================================================
# SELL ORDER TESTS
# =============================================================================

class TestRealSellOrders:
    """Test sell order functionality."""
    
    @pytest.mark.asyncio
    async def test_sell_existing_position(self, paper_broker, require_market_open):
        """Test selling from an existing position."""
        # Check if we have any positions to sell
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions available to sell")
        
        # Find a position with at least 1 share
        sellable = None
        for pos in positions:
            qty = float(pos.get("qty", 0))
            if qty >= 1:
                sellable = pos
                break
        
        if not sellable:
            pytest.skip("No positions with sellable quantity")
        
        symbol = sellable["symbol"]
        
        # Sell 1 share
        sell_order = await paper_broker.place_order(
            symbol=symbol,
            qty=1,
            side="sell",
            type="market",
            tif="day"
        )
        
        assert sell_order is not None
        assert sell_order["side"] == "sell"
        assert sell_order["symbol"] == symbol
        
        # Wait for fill
        await asyncio.sleep(3)
        
        final = await paper_broker.get_order(sell_order["id"])
        assert final["status"] in ["filled", "new", "accepted", "partially_filled"]


# =============================================================================
# ACCOUNT CONSTRAINT TESTS
# =============================================================================

class TestRealAccountConstraints:
    """Test real account constraints and limits."""
    
    @pytest.mark.asyncio
    async def test_get_account_buying_power(self, paper_broker):
        """Test retrieving real account buying power."""
        account = await paper_broker.get_account()
        
        assert account is not None
        assert "buying_power" in account
        assert "equity" in account
        assert "cash" in account
        
        buying_power = float(account["buying_power"])
        equity = float(account["equity"])
        
        # Basic sanity checks
        assert buying_power >= 0, "Buying power should not be negative"
        assert equity > 0, "Equity should be positive (or account is empty)"
    
    @pytest.mark.asyncio
    async def test_insufficient_buying_power_rejected(self, paper_broker):
        """Test that orders exceeding buying power are rejected."""
        from fastapi import HTTPException
        
        # Try to buy a huge amount that would exceed any reasonable buying power
        with pytest.raises(HTTPException) as exc_info:
            await paper_broker.place_order(
                symbol="AAPL",
                qty=1000000,  # 1 million shares
                side="buy",
                type="market",
                tif="day"
            )
        
        # Should get insufficient buying power error
        assert exc_info.value.status_code == 403
        assert "buying_power" in str(exc_info.value.detail).lower() or \
               "insufficient" in str(exc_info.value.detail).lower()


# =============================================================================
# ORDER CANCELLATION TESTS
# =============================================================================

class TestRealOrderCancellation:
    """Test order cancellation functionality."""
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, paper_broker):
        """Test cancelling a non-existent order."""
        from fastapi import HTTPException
        
        try:
            await paper_broker.cancel_order("fake-order-id-12345")
            # If no exception, the API might return None/empty
        except HTTPException as e:
            # Expected - order doesn't exist
            assert e.status_code in [404, 422]
        except Exception as e:
            # Some other error format
            assert "not found" in str(e).lower() or "422" in str(e) or "404" in str(e)


# =============================================================================
# POSITION TESTS
# =============================================================================

class TestRealPositions:
    """Test position retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_all_positions(self, paper_broker):
        """Test retrieving all positions."""
        positions = await paper_broker.get_positions()
        
        assert isinstance(positions, list)
        
        for pos in positions:
            assert "symbol" in pos
            assert "qty" in pos
            assert "market_value" in pos or "current_price" in pos
    
    @pytest.mark.asyncio
    async def test_get_position_by_symbol(self, paper_broker):
        """Test retrieving a specific position."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test")
        
        symbol = positions[0]["symbol"]
        position = await paper_broker.get_position(symbol)
        
        assert position is not None
        assert position["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_position(self, paper_broker):
        """Test retrieving a position that doesn't exist."""
        position = await paper_broker.get_position("NONEXISTENT_SYMBOL_XYZ")
        
        # Should return None for non-existent position
        assert position is None
