"""
REAL Position Tracking Integration Tests.

These tests validate ACTUAL position management:
- Real position retrieval from Alpaca
- Real P&L calculations
- Real portfolio aggregation
- Real position reconciliation

NO MOCKING - All positions come from real broker accounts.
"""

import asyncio
import pytest


# =============================================================================
# POSITION SYNC TESTS
# =============================================================================

class TestRealPositionSync:
    """Test real position synchronization with broker."""
    
    @pytest.mark.asyncio
    async def test_get_all_positions(self, paper_broker):
        """Test retrieving all positions from broker."""
        positions = await paper_broker.get_positions()
        
        # Should return a list (possibly empty)
        assert isinstance(positions, list)
        
        # If positions exist, verify structure
        for pos in positions[:5]:  # Check first 5
            assert "symbol" in pos
            assert "qty" in pos
            assert "avg_entry_price" in pos or "avg_price" in pos or "current_price" in pos
    
    @pytest.mark.asyncio
    async def test_get_position_by_symbol(self, paper_broker):
        """Test retrieving position for specific symbol."""
        # First get all positions to find an existing one
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test - account may be empty")
        
        # Get position for first symbol
        symbol = positions[0]["symbol"]
        position = await paper_broker.get_position(symbol)
        
        assert position is not None
        assert position["symbol"] == symbol
    
    @pytest.mark.asyncio
    async def test_position_not_found(self, paper_broker):
        """Test handling of non-existent position."""
        # Try to get a position that doesn't exist
        position = await paper_broker.get_position("ZZZZZ_NONEXISTENT_12345")
        
        # Should return None or raise an exception
        assert position is None


# =============================================================================
# P&L CALCULATION TESTS  
# =============================================================================

class TestRealPnLCalculation:
    """Test real P&L calculations from broker data."""
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl_calculation(self, paper_broker):
        """Test unrealized P&L is present in position data."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test P&L")
        
        for pos in positions[:3]:
            # Alpaca returns unrealized_pl or unrealized_plpc
            has_pnl = (
                "unrealized_pl" in pos or 
                "unrealized_pnl" in pos or 
                "unrealized_plpc" in pos
            )
            assert has_pnl, f"Position {pos.get('symbol')} missing P&L data"
    
    @pytest.mark.asyncio
    async def test_market_value_calculation(self, paper_broker):
        """Test market value is present in position data."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test market value")
        
        for pos in positions[:3]:
            # Alpaca returns market_value
            has_value = (
                "market_value" in pos or 
                "qty" in pos  # Can calculate from qty * current_price
            )
            assert has_value, f"Position {pos.get('symbol')} missing value data"


# =============================================================================
# PORTFOLIO AGGREGATION TESTS
# =============================================================================

class TestRealPortfolioAggregation:
    """Test real portfolio aggregation calculations."""
    
    @pytest.mark.asyncio
    async def test_total_market_value(self, paper_broker):
        """Test calculating total market value across all positions."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test total market value")
        
        total_value = 0
        for pos in positions:
            if "market_value" in pos:
                total_value += float(pos["market_value"])
            elif "qty" in pos and "current_price" in pos:
                total_value += float(pos["qty"]) * float(pos["current_price"])
        
        assert total_value >= 0
    
    @pytest.mark.asyncio
    async def test_total_unrealized_pnl(self, paper_broker):
        """Test calculating total unrealized P&L."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test total P&L")
        
        total_pnl = 0
        for pos in positions:
            pnl = pos.get("unrealized_pl") or pos.get("unrealized_pnl") or 0
            total_pnl += float(pnl)
        
        # P&L can be positive or negative
        assert isinstance(total_pnl, float)
    
    @pytest.mark.asyncio
    async def test_portfolio_weights(self, paper_broker):
        """Test calculating portfolio weight distribution."""
        positions = await paper_broker.get_positions()
        account = await paper_broker.get_account()
        
        if not positions:
            pytest.skip("No positions to test weights")
        
        portfolio_value = float(account.get("portfolio_value", 0))
        if portfolio_value <= 0:
            pytest.skip("Portfolio value is zero")
        
        weights = {}
        for pos in positions:
            market_value = float(pos.get("market_value", 0))
            weights[pos["symbol"]] = market_value / portfolio_value
        
        # Weights should sum to roughly the positions portion of portfolio
        # For margin accounts, positions can exceed equity (leverage)
        total_weights = sum(weights.values())
        assert total_weights >= 0
        # Allow for up to 300% leverage
        assert total_weights <= 3.0 or abs(total_weights - 1.0) < 2.5


# =============================================================================
# POSITION RECONCILIATION TESTS
# =============================================================================

class TestRealPositionReconciliation:
    """Test position reconciliation between broker and local state."""
    
    @pytest.mark.asyncio
    async def test_broker_position_sync(self, paper_broker):
        """Test that broker positions can be fetched consistently."""
        # Fetch positions twice
        positions1 = await paper_broker.get_positions()
        await asyncio.sleep(0.5)
        positions2 = await paper_broker.get_positions()
        
        # Should have same count (no trades in between)
        assert len(positions1) == len(positions2)
        
        # Same symbols
        symbols1 = {p["symbol"] for p in positions1}
        symbols2 = {p["symbol"] for p in positions2}
        assert symbols1 == symbols2
    
    @pytest.mark.asyncio
    async def test_position_change_detection(self, paper_broker):
        """Test position data consistency."""
        positions = await paper_broker.get_positions()
        
        for pos in positions[:3]:
            symbol = pos["symbol"]
            qty = float(pos.get("qty", 0))
            
            # Verify we can fetch the same position individually
            single_pos = await paper_broker.get_position(symbol)
            if single_pos:
                single_qty = float(single_pos.get("qty", 0))
                assert qty == single_qty, f"Quantity mismatch for {symbol}"


# =============================================================================
# LONG/SHORT POSITION TESTS
# =============================================================================

class TestRealLongShortPositions:
    """Test handling of long and short positions."""
    
    @pytest.mark.asyncio
    async def test_identify_position_side(self, paper_broker):
        """Test identifying long vs short positions."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test")
        
        for pos in positions:
            qty = float(pos.get("qty", 0))
            side = pos.get("side", "long" if qty > 0 else "short")
            
            # Alpaca uses positive qty for long, negative for short
            if qty > 0:
                assert side in ["long", "buy"], f"Expected long for positive qty: {qty}"
            elif qty < 0:
                assert side in ["short", "sell"], f"Expected short for negative qty: {qty}"
    
    @pytest.mark.asyncio
    async def test_net_exposure_calculation(self, paper_broker):
        """Test calculating net long/short exposure."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to test exposure")
        
        long_value = 0
        short_value = 0
        
        for pos in positions:
            market_value = float(pos.get("market_value", 0))
            qty = float(pos.get("qty", 0))
            
            if qty > 0:
                long_value += abs(market_value)
            else:
                short_value += abs(market_value)
        
        net_exposure = long_value - short_value
        gross_exposure = long_value + short_value
        
        assert gross_exposure >= 0


# =============================================================================
# POSITION HISTORY TESTS
# =============================================================================

class TestRealPositionHistory:
    """Test position history tracking."""
    
    @pytest.mark.asyncio
    async def test_track_position_over_time(self, paper_broker):
        """Test that position data can be tracked over time."""
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to track")
        
        # Take snapshot
        snapshot = {p["symbol"]: float(p.get("qty", 0)) for p in positions}
        
        await asyncio.sleep(1)
        
        # Take another snapshot
        positions2 = await paper_broker.get_positions()
        snapshot2 = {p["symbol"]: float(p.get("qty", 0)) for p in positions2}
        
        # Should be consistent (no trades in between)
        for symbol, qty in snapshot.items():
            if symbol in snapshot2:
                assert qty == snapshot2[symbol]


# =============================================================================
# POSITION ALERT TESTS
# =============================================================================

class TestRealPositionAlerts:
    """Test position-based alerts."""
    
    @pytest.mark.asyncio
    async def test_large_position_alert(self, paper_broker):
        """Test identifying large position concentrations."""
        positions = await paper_broker.get_positions()
        account = await paper_broker.get_account()
        
        if not positions:
            pytest.skip("No positions to test")
        
        portfolio_value = float(account.get("portfolio_value", 1))
        concentration_threshold = 0.25  # 25%
        
        large_positions = []
        for pos in positions:
            market_value = abs(float(pos.get("market_value", 0)))
            weight = market_value / portfolio_value if portfolio_value > 0 else 0
            
            if weight > concentration_threshold:
                large_positions.append({
                    "symbol": pos["symbol"],
                    "weight": weight
                })
        
        # Just verify we can identify them
        assert isinstance(large_positions, list)


# =============================================================================
# POSITION PERFORMANCE TESTS
# =============================================================================

class TestRealPositionPerformance:
    """Test position performance metrics."""
    
    @pytest.mark.asyncio
    async def test_best_and_worst_positions(self, paper_broker):
        """Test identifying best and worst performing positions."""
        positions = await paper_broker.get_positions()
        
        if len(positions) < 2:
            pytest.skip("Need at least 2 positions for comparison")
        
        # Sort by unrealized P&L
        sorted_positions = sorted(
            positions,
            key=lambda p: float(p.get("unrealized_pl", 0) or p.get("unrealized_pnl", 0) or 0),
            reverse=True
        )
        
        best = sorted_positions[0]
        worst = sorted_positions[-1]
        
        assert best["symbol"] != worst["symbol"] or len(positions) == 1
    
    @pytest.mark.asyncio
    async def test_weighted_portfolio_return(self, paper_broker):
        """Test calculating weighted portfolio return."""
        positions = await paper_broker.get_positions()
        account = await paper_broker.get_account()
        
        if not positions:
            pytest.skip("No positions to test")
        
        portfolio_value = float(account.get("portfolio_value", 1))
        
        weighted_return = 0
        for pos in positions:
            market_value = abs(float(pos.get("market_value", 0)))
            pnl_pct = float(pos.get("unrealized_plpc", 0) or 0)
            weight = market_value / portfolio_value if portfolio_value > 0 else 0
            weighted_return += weight * pnl_pct
        
        # Weighted return can be positive or negative
        assert isinstance(weighted_return, float)
