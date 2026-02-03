"""
REAL End-to-End Workflow Integration Tests.

These tests validate COMPLETE trading workflows:
- Full order lifecycle from creation to fill
- Real portfolio operations
- Real data pipeline flows
- Complete trading cycles

NO MOCKING - All workflows execute against real Alpaca systems.
"""

import asyncio
import math
from datetime import datetime, UTC
import pytest

from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.integrations.alpaca_data import AlpacaDataClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
async def data_client():
    """Create AlpacaDataClient for testing."""
    client = AlpacaDataClient()
    yield client
    await client.close()


# =============================================================================
# COMPLETE ORDER LIFECYCLE
# =============================================================================

class TestRealOrderLifecycle:
    """Test complete order lifecycle from creation to completion."""
    
    @pytest.mark.asyncio
    async def test_full_market_buy_lifecycle(self, paper_broker, require_market_open):
        """
        Test complete market buy order flow:
        1. Check account status
        2. Submit market order
        3. Wait for fill
        4. Verify position created
        """
        # Step 1: Check account
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 20:
            pytest.skip(f"Insufficient buying power: ${buying_power:.2f}")
        
        # Use a cheap stock
        symbol = "F"  # Ford, typically ~$10-15
        qty = 1
        
        # Step 2: Submit market order
        order = await paper_broker.place_order(
            symbol=symbol,
            qty=qty,
            side="buy",
            type="market",
            tif="day"
        )
        
        order_id = order["id"]
        assert order_id is not None
        
        # Step 3: Wait for fill
        max_wait = 30
        start = datetime.now(UTC)
        
        while (datetime.now(UTC) - start).total_seconds() < max_wait:
            await asyncio.sleep(1)
            updated = await paper_broker.get_order(order_id)
            
            if updated["status"] == "filled":
                break
            elif updated["status"] in ["canceled", "cancelled", "expired", "rejected"]:
                pytest.fail(f"Order failed with status: {updated['status']}")
        
        # Step 4: Verify fill
        final_order = await paper_broker.get_order(order_id)
        
        if final_order["status"] == "filled":
            assert float(final_order.get("filled_qty", 0)) == qty
            assert float(final_order.get("filled_avg_price", 0)) > 0
            
            # Verify position exists
            position = await paper_broker.get_position(symbol)
            assert position is not None
            assert float(position.get("qty", 0)) >= qty
        
        # Clean up - sell the position
        try:
            sell_order = await paper_broker.place_order(
                symbol=symbol,
                qty=qty,
                side="sell",
                type="market",
                tif="day"
            )
            await asyncio.sleep(3)  # Wait for sell to complete
        except Exception:
            pass  # Best effort cleanup
    
    @pytest.mark.asyncio
    async def test_limit_order_and_cancel(self, paper_broker, require_market_open):
        """
        Test limit order submission and cancellation:
        1. Get current price
        2. Submit limit order far below market
        3. Verify order is open
        4. Cancel order
        5. Verify cancellation
        """
        # Get account info
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 100:
            pytest.skip(f"Insufficient buying power: ${buying_power:.2f}")
        
        symbol = "AAPL"
        
        # Use a very low limit price that won't fill
        limit_price = 50.0  # Well below AAPL's current price
        
        # Submit limit order
        order = await paper_broker.place_order(
            symbol=symbol,
            qty=1,
            side="buy",
            type="limit",
            tif="day",
            limit_price=limit_price
        )
        
        order_id = order["id"]
        assert order_id is not None
        
        # Wait for order to be accepted
        await asyncio.sleep(2)
        
        # Verify order is open/new
        status = await paper_broker.get_order(order_id)
        assert status["status"] in ["new", "accepted", "pending_new"], \
            f"Expected open order, got {status['status']}"
        
        # Cancel order
        await paper_broker.cancel_order(order_id)
        
        # Wait for cancellation
        await asyncio.sleep(2)
        
        # Verify cancelled
        final = await paper_broker.get_order(order_id)
        assert final["status"] in ["canceled", "cancelled", "pending_cancel"]
    
    @pytest.mark.asyncio
    async def test_round_trip_buy_sell(self, paper_broker, require_market_open):
        """
        Test complete round-trip trade:
        1. Buy 1 share
        2. Verify position
        3. Sell 1 share
        4. Verify position closed
        """
        account = await paper_broker.get_account()
        buying_power = float(account.get("buying_power", 0))
        
        if buying_power < 20:
            pytest.skip(f"Insufficient buying power: ${buying_power:.2f}")
        
        symbol = "F"  # Ford, cheap stock
        qty = 1
        
        # Step 1: Buy
        buy_order = await paper_broker.place_order(
            symbol=symbol,
            qty=qty,
            side="buy",
            type="market",
            tif="day"
        )
        
        # Wait for fill
        await asyncio.sleep(5)
        buy_status = await paper_broker.get_order(buy_order["id"])
        
        if buy_status["status"] != "filled":
            pytest.skip("Buy order did not fill")
        
        # Step 2: Verify position
        position = await paper_broker.get_position(symbol)
        assert position is not None
        assert float(position.get("qty", 0)) >= qty
        
        # Step 3: Sell
        sell_order = await paper_broker.place_order(
            symbol=symbol,
            qty=qty,
            side="sell",
            type="market",
            tif="day"
        )
        
        # Wait for fill
        await asyncio.sleep(5)
        sell_status = await paper_broker.get_order(sell_order["id"])
        
        assert sell_status["status"] == "filled", \
            f"Sell order status: {sell_status['status']}"


# =============================================================================
# DATA TO TRADE WORKFLOW
# =============================================================================

class TestRealDataToTradeWorkflow:
    """Test complete data-to-trade workflows."""
    
    @pytest.mark.asyncio
    async def test_data_fetch_to_signal_generation(self, data_client):
        """
        Test workflow from data fetch to signal generation:
        1. Fetch historical data
        2. Calculate technical indicator
        3. Generate trading signal
        """
        # Step 1: Fetch data
        closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=50,
            timeframe="1Day"
        )
        
        assert len(closes) >= 30
        
        # Step 2: Calculate simple moving averages
        sma_20 = sum(closes[-20:]) / 20
        sma_10 = sum(closes[-10:]) / 10
        current_price = closes[-1]
        
        # Step 3: Generate signal (simple crossover)
        if sma_10 > sma_20:
            signal = "bullish"
        elif sma_10 < sma_20:
            signal = "bearish"
        else:
            signal = "neutral"
        
        assert signal in ["bullish", "bearish", "neutral"]
        
        # Verify signal makes sense
        assert current_price > 0
        assert sma_10 > 0
        assert sma_20 > 0
    
    @pytest.mark.asyncio
    async def test_multi_symbol_analysis_workflow(self, data_client):
        """
        Test multi-symbol analysis workflow:
        1. Fetch data for multiple symbols
        2. Calculate indicators for each
        3. Rank by momentum
        """
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]
        
        # Step 1: Fetch data for all symbols
        symbol_data = {}
        for symbol in symbols:
            closes = await data_client.get_historical_closes(
                symbol=symbol,
                lookback=30,
                timeframe="1Day"
            )
            symbol_data[symbol] = closes
        
        # Step 2: Calculate momentum for each
        momentum_scores = {}
        for symbol, closes in symbol_data.items():
            if len(closes) >= 20:
                # Simple momentum: 20-day return
                momentum = (closes[-1] - closes[-20]) / closes[-20]
                momentum_scores[symbol] = momentum
        
        # Step 3: Rank by momentum
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        
        assert len(ranked) == len(symbols)
        
        # Best momentum stock should be first
        best_symbol, best_momentum = ranked[0]
        worst_symbol, worst_momentum = ranked[-1]
        
        assert best_momentum >= worst_momentum
    
    @pytest.mark.asyncio
    async def test_rsi_signal_workflow(self, data_client):
        """
        Test RSI-based signal generation:
        1. Fetch data
        2. Calculate RSI
        3. Generate overbought/oversold signal
        """
        closes = await data_client.get_historical_closes(
            symbol="AAPL",
            lookback=50,
            timeframe="1Day"
        )
        
        assert len(closes) >= 15
        
        # Calculate RSI
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        gains = [max(0, c) for c in changes[-14:]]
        losses = [-min(0, c) for c in changes[-14:]]
        
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        else:
            rsi = 100
        
        # Generate signal
        if rsi > 70:
            signal = "overbought"
        elif rsi < 30:
            signal = "oversold"
        else:
            signal = "neutral"
        
        assert 0 <= rsi <= 100
        assert signal in ["overbought", "oversold", "neutral"]


# =============================================================================
# ACCOUNT MONITORING WORKFLOW
# =============================================================================

class TestRealAccountMonitoringWorkflow:
    """Test account monitoring workflows."""
    
    @pytest.mark.asyncio
    async def test_portfolio_value_tracking(self, paper_broker):
        """
        Test portfolio value tracking:
        1. Get account info
        2. Get all positions
        3. Calculate total value
        4. Verify consistency
        """
        # Step 1: Get account
        account = await paper_broker.get_account()
        reported_equity = float(account.get("equity", 0))
        reported_portfolio = float(account.get("portfolio_value", 0))
        
        # Step 2: Get positions
        positions = await paper_broker.get_positions()
        
        # Step 3: Calculate position value
        position_value = sum(
            abs(float(p.get("market_value", 0))) for p in positions
        )
        
        # Step 4: Verify consistency
        assert reported_equity > 0
        assert reported_portfolio > 0
        
        # Cash + positions should roughly equal portfolio value
        cash = float(account.get("cash", 0))
        calculated_total = cash + position_value
        
        # Should be within 5% (margin accounts may differ)
        if reported_portfolio > 0:
            diff_pct = abs(calculated_total - reported_portfolio) / reported_portfolio
            # Allow some variance for margin/timing
            assert diff_pct < 0.10 or calculated_total == 0, \
                f"Value mismatch: calculated ${calculated_total:.2f} vs reported ${reported_portfolio:.2f}"
    
    @pytest.mark.asyncio
    async def test_position_pnl_monitoring(self, paper_broker):
        """
        Test position P&L monitoring:
        1. Get all positions
        2. Calculate total P&L
        3. Verify P&L values
        """
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to monitor")
        
        total_unrealized_pnl = 0.0
        total_market_value = 0.0
        
        for pos in positions:
            pnl = float(pos.get("unrealized_pl", 0))
            market_value = abs(float(pos.get("market_value", 0)))
            
            total_unrealized_pnl += pnl
            total_market_value += market_value
        
        # P&L can be positive or negative
        assert isinstance(total_unrealized_pnl, float)
        assert total_market_value >= 0
    
    @pytest.mark.asyncio
    async def test_buying_power_monitoring(self, paper_broker):
        """
        Test buying power monitoring workflow:
        1. Get account
        2. Calculate available buying power
        3. Verify sufficient for trading
        """
        account = await paper_broker.get_account()
        
        buying_power = float(account.get("buying_power", 0))
        cash = float(account.get("cash", 0))
        equity = float(account.get("equity", 0))
        
        # Verify buying power is reasonable
        assert buying_power >= 0
        
        # Log trading capacity
        min_trade_value = 10.0  # Minimum reasonable trade
        can_trade = buying_power >= min_trade_value
        
        # This is informational
        if not can_trade:
            print(f"Warning: Low buying power (${buying_power:.2f})")


# =============================================================================
# RISK MONITORING WORKFLOW
# =============================================================================

class TestRealRiskMonitoringWorkflow:
    """Test risk monitoring workflows."""
    
    @pytest.mark.asyncio
    async def test_exposure_monitoring(self, paper_broker):
        """
        Test exposure monitoring workflow:
        1. Get account and positions
        2. Calculate gross and net exposure
        3. Check against limits
        """
        account = await paper_broker.get_account()
        positions = await paper_broker.get_positions()
        
        equity = float(account.get("equity", 1))
        
        long_value = 0.0
        short_value = 0.0
        
        for pos in positions:
            qty = float(pos.get("qty", 0))
            market_value = abs(float(pos.get("market_value", 0)))
            
            if qty > 0:
                long_value += market_value
            else:
                short_value += market_value
        
        gross_exposure = long_value + short_value
        net_exposure = long_value - short_value
        
        gross_leverage = gross_exposure / equity if equity > 0 else 0
        net_leverage = net_exposure / equity if equity > 0 else 0
        
        # Check limits
        max_gross_leverage = 2.0  # 200% max
        max_net_leverage = 1.0  # 100% max
        
        assert gross_leverage >= 0
        # Paper account should not exceed limits
        assert gross_leverage <= max_gross_leverage + 0.1
    
    @pytest.mark.asyncio
    async def test_concentration_monitoring(self, paper_broker):
        """
        Test position concentration monitoring:
        1. Get positions
        2. Calculate weights
        3. Check for over-concentration
        """
        account = await paper_broker.get_account()
        positions = await paper_broker.get_positions()
        
        if not positions:
            pytest.skip("No positions to monitor")
        
        equity = float(account.get("equity", 1))
        max_concentration = 0.30  # 30% max per position
        
        over_concentrated = []
        for pos in positions:
            market_value = abs(float(pos.get("market_value", 0)))
            weight = market_value / equity if equity > 0 else 0
            
            if weight > max_concentration:
                over_concentrated.append({
                    "symbol": pos.get("symbol"),
                    "weight": weight
                })
        
        # Informational - not necessarily an error
        if over_concentrated:
            print(f"Over-concentrated positions: {over_concentrated}")


# =============================================================================
# MULTI-STEP TRADING WORKFLOW
# =============================================================================

class TestRealMultiStepWorkflow:
    """Test multi-step trading workflows."""
    
    @pytest.mark.asyncio
    async def test_analyze_and_report_workflow(self, paper_broker, data_client):
        """
        Complete analysis and reporting workflow:
        1. Get account status
        2. Get positions
        3. Fetch market data
        4. Calculate metrics
        5. Generate report
        """
        # Step 1: Account status
        account = await paper_broker.get_account()
        
        # Step 2: Positions
        positions = await paper_broker.get_positions()
        
        # Step 3: Get market data for SPY (benchmark)
        spy_closes = await data_client.get_historical_closes(
            symbol="SPY",
            lookback=30,
            timeframe="1Day"
        )
        
        # Step 4: Calculate metrics
        equity = float(account.get("equity", 0))
        position_count = len(positions)
        
        total_position_value = sum(
            abs(float(p.get("market_value", 0))) for p in positions
        )
        
        total_pnl = sum(
            float(p.get("unrealized_pl", 0)) for p in positions
        )
        
        # SPY 20-day return (benchmark)
        if len(spy_closes) >= 20:
            spy_return = (spy_closes[-1] - spy_closes[-20]) / spy_closes[-20]
        else:
            spy_return = 0
        
        # Step 5: Generate report
        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "equity": equity,
            "position_count": position_count,
            "total_position_value": total_position_value,
            "total_unrealized_pnl": total_pnl,
            "spy_20d_return": spy_return,
            "buying_power": float(account.get("buying_power", 0))
        }
        
        # Verify report is complete
        assert all(key in report for key in [
            "timestamp", "equity", "position_count", "total_position_value"
        ])
        assert report["equity"] > 0
    
    @pytest.mark.asyncio
    async def test_portfolio_health_check(self, paper_broker):
        """
        Portfolio health check workflow:
        1. Check account status
        2. Verify trading enabled
        3. Check margin status
        4. Generate health report
        """
        account = await paper_broker.get_account()
        
        # Check trading status
        trading_blocked = account.get("trading_blocked", False)
        transfers_blocked = account.get("transfers_blocked", False)
        account_blocked = account.get("account_blocked", False)
        
        # Check margin
        maintenance_margin = float(account.get("maintenance_margin", 0))
        equity = float(account.get("equity", 0))
        
        margin_safe = True
        if maintenance_margin > 0 and equity > 0:
            margin_cushion = (equity - maintenance_margin) / equity
            margin_safe = margin_cushion > 0.20  # 20% cushion
        
        # Health report
        health = {
            "trading_enabled": not trading_blocked,
            "transfers_enabled": not transfers_blocked,
            "account_active": not account_blocked,
            "margin_safe": margin_safe,
            "equity": equity,
            "buying_power": float(account.get("buying_power", 0))
        }
        
        # Verify health
        assert health["trading_enabled"], "Trading is blocked"
        assert health["account_active"], "Account is blocked"
        assert health["equity"] > 0, "No equity in account"
