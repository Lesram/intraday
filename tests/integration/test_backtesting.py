"""
Integration tests for backtesting engine.

Tests backtesting with deterministic fills, PnL calculation, performance metrics,
and strategy evaluation over historical data.
"""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest


class MockBacktestEngine:
    """Mock backtesting engine for deterministic testing."""

    def __init__(
        self, initial_capital=100000, commission_rate=0.001, slippage_rate=0.0005
    ):
        self.initial_capital = Decimal(str(initial_capital))
        self.commission_rate = Decimal(str(commission_rate))
        self.slippage_rate = Decimal(str(slippage_rate))

        # Portfolio state
        self.cash = self.initial_capital
        self.positions = {}
        self.portfolio_value = self.initial_capital

        # Performance tracking
        self.trades = []
        self.portfolio_history = []
        self.daily_returns = []

    def process_order(self, order_spec, current_price, timestamp):
        """Process order with deterministic fills."""
        symbol = order_spec["symbol"]
        side = order_spec["side"]
        qty = Decimal(str(order_spec["qty"]))

        # Apply slippage
        if side == "buy":
            fill_price = current_price * (1 + self.slippage_rate)
        else:
            fill_price = current_price * (1 - self.slippage_rate)

        # Calculate costs
        notional = qty * fill_price
        commission = notional * self.commission_rate

        if side == "buy":
            # Check sufficient cash
            total_cost = notional + commission
            if self.cash < total_cost:
                return {"success": False, "reason": "insufficient_cash"}

            # Execute buy
            self.cash -= total_cost

            if symbol in self.positions:
                # Add to existing position (average price)
                existing_qty = self.positions[symbol]["qty"]
                existing_value = existing_qty * self.positions[symbol]["avg_price"]
                new_avg_price = (existing_value + notional) / (existing_qty + qty)

                self.positions[symbol] = {
                    "qty": existing_qty + qty,
                    "avg_price": new_avg_price,
                    "market_value": (existing_qty + qty) * current_price,
                }
            else:
                # New position
                self.positions[symbol] = {
                    "qty": qty,
                    "avg_price": fill_price,
                    "market_value": qty * current_price,
                }

        else:  # sell
            # Check sufficient shares
            if symbol not in self.positions or self.positions[symbol]["qty"] < qty:
                return {"success": False, "reason": "insufficient_shares"}

            # Execute sell
            proceeds = notional - commission
            self.cash += proceeds

            # Update position
            if self.positions[symbol]["qty"] == qty:
                # Close position
                avg_price = self.positions[symbol]["avg_price"]
                pnl = (fill_price - avg_price) * qty - commission
                del self.positions[symbol]
            else:
                # Reduce position
                self.positions[symbol]["qty"] -= qty
                self.positions[symbol]["market_value"] = (
                    self.positions[symbol]["qty"] * current_price
                )
                avg_price = self.positions[symbol]["avg_price"]
                pnl = (fill_price - avg_price) * qty - commission

        # Record trade
        trade = {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": fill_price,
            "commission": commission,
            "pnl": pnl if side == "sell" else None,
        }
        self.trades.append(trade)

        return {"success": True, "fill_price": fill_price, "commission": commission}

    def update_portfolio_value(self, current_prices):
        """Update portfolio value with current market prices."""
        positions_value = Decimal("0")

        for symbol, position in self.positions.items():
            if symbol in current_prices:
                market_price = Decimal(str(current_prices[symbol]))
                position["market_value"] = position["qty"] * market_price
                positions_value += position["market_value"]

        self.portfolio_value = self.cash + positions_value

        # Record portfolio snapshot
        snapshot = {
            "cash": self.cash,
            "positions_value": positions_value,
            "total_value": self.portfolio_value,
        }
        self.portfolio_history.append(snapshot)

        return self.portfolio_value

    def calculate_performance_metrics(self):
        """Calculate comprehensive performance metrics."""
        if len(self.portfolio_history) < 2:
            return {}

        # Calculate returns
        values = [snapshot["total_value"] for snapshot in self.portfolio_history]
        returns = [
            float((values[i] - values[i - 1]) / values[i - 1])
            for i in range(1, len(values))
        ]

        if not returns:
            return {}

        # Performance metrics
        total_return = float(
            (self.portfolio_value - self.initial_capital) / self.initial_capital
        )

        # Annualized return (assuming daily data)
        days = len(returns)
        annualized_return = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0

        # Volatility (annualized)
        volatility = np.std(returns) * np.sqrt(252) if returns else 0

        # Sharpe ratio (assuming 2% risk-free rate)
        risk_free_rate = 0.02
        sharpe_ratio = (
            (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
        )

        # Maximum drawdown
        peak = self.initial_capital
        max_drawdown = 0

        for value in values:
            peak = max(peak, value)
            drawdown = float((peak - value) / peak)
            max_drawdown = max(max_drawdown, drawdown)

        # Win rate
        profitable_trades = [t for t in self.trades if t["pnl"] and t["pnl"] > 0]
        total_closed_trades = [t for t in self.trades if t["pnl"] is not None]
        win_rate = (
            len(profitable_trades) / len(total_closed_trades)
            if total_closed_trades
            else 0
        )

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(total_closed_trades),
            "final_portfolio_value": float(self.portfolio_value),
        }


class TestBacktestingIntegration:
    """Test backtesting engine integration."""

    @pytest.fixture
    def backtest_engine(self):
        """Create backtest engine with test configuration."""
        return MockBacktestEngine(
            initial_capital=100000,
            commission_rate=0.001,  # 0.1%
            slippage_rate=0.0005,  # 0.05%
        )

    @pytest.fixture
    def historical_data(self):
        """Generate historical data for backtesting."""
        from tests.fixtures.market_data import generate_synthetic_ohlcv

        # Generate 6 months of daily data for multiple symbols
        symbols = ["AAPL", "GOOGL", "MSFT"]
        data = {}

        for symbol in symbols:
            symbol_data = generate_synthetic_ohlcv(
                symbol=symbol,
                days=126,  # ~6 months
                freq="1d",
                volatility=0.02,
                trend=0.0003,  # Slight upward trend
            )
            data[symbol] = symbol_data

        return data

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_simple_buy_hold_strategy(self, backtest_engine, historical_data):
        """Test simple buy-and-hold strategy backtesting."""

        symbol = "AAPL"
        data = historical_data[symbol]

        # Buy-and-hold: buy on day 1, hold until end
        first_day = data.iloc[0]
        last_day = data.iloc[-1]

        # Initial purchase
        buy_order = {
            "symbol": symbol,
            "side": "buy",
            "qty": 500,  # $92,500 at ~$185/share
        }

        buy_result = backtest_engine.process_order(
            buy_order, Decimal(str(first_day["close"])), first_day["timestamp"]
        )

        assert buy_result["success"] is True
        assert symbol in backtest_engine.positions
        assert backtest_engine.positions[symbol]["qty"] == 500

        # Update portfolio value daily
        for _, day in data.iterrows():
            current_prices = {symbol: day["close"]}
            backtest_engine.update_portfolio_value(current_prices)

        # Calculate final performance
        metrics = backtest_engine.calculate_performance_metrics()

        # Verify metrics are reasonable
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "final_portfolio_value" in metrics

        # Buy-and-hold should have reasonable performance
        assert metrics["total_trades"] == 0  # No sells = no closed trades
        assert metrics["final_portfolio_value"] > 50000  # Reasonable final value

        print("✓ Buy-and-Hold Backtest Results:")
        print(f"  - Total Return: {metrics['total_return']:.2%}")
        print(f"  - Annualized Return: {metrics['annualized_return']:.2%}")
        print(f"  - Max Drawdown: {metrics['max_drawdown']:.2%}")
        print(f"  - Final Value: ${metrics['final_portfolio_value']:,.2f}")

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_momentum_strategy_backtest(self, backtest_engine, historical_data):
        """Test momentum strategy backtesting."""

        symbol = "AAPL"
        data = historical_data[symbol]

        # Simple momentum strategy: buy when 5-day return > 2%, sell when < -2%
        data["return_5d"] = data["close"].pct_change(5)

        position_size = 100  # Shares per trade

        for i, row in data.iterrows():
            if pd.isna(row["return_5d"]):
                continue

            current_price = Decimal(str(row["close"]))
            timestamp = row["timestamp"]

            # Update portfolio value
            backtest_engine.update_portfolio_value({symbol: float(current_price)})

            # Trading logic
            if row["return_5d"] > 0.02:  # Strong positive momentum
                # Buy signal (if not already long)
                if symbol not in backtest_engine.positions:
                    order = {"symbol": symbol, "side": "buy", "qty": position_size}
                    backtest_engine.process_order(order, current_price, timestamp)

            elif row["return_5d"] < -0.02:  # Strong negative momentum
                # Sell signal (if long)
                if symbol in backtest_engine.positions:
                    current_qty = backtest_engine.positions[symbol]["qty"]
                    order = {"symbol": symbol, "side": "sell", "qty": current_qty}
                    backtest_engine.process_order(order, current_price, timestamp)

        # Final performance
        metrics = backtest_engine.calculate_performance_metrics()

        assert metrics["total_trades"] > 0, "Strategy should have made some trades"
        assert 0 <= metrics["win_rate"] <= 1, "Win rate should be between 0 and 1"

        print("✓ Momentum Strategy Backtest Results:")
        print(f"  - Total Trades: {metrics['total_trades']}")
        print(f"  - Win Rate: {metrics['win_rate']:.2%}")
        print(f"  - Total Return: {metrics['total_return']:.2%}")
        print(f"  - Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_mean_reversion_strategy_backtest(self, backtest_engine, historical_data):
        """Test mean reversion strategy backtesting."""

        symbol = "GOOGL"
        data = historical_data[symbol]

        # Mean reversion: RSI-based strategy
        def calculate_rsi(prices, period=14):
            """Calculate RSI indicator."""
            delta = prices.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            avg_gain = gain.rolling(period).mean()
            avg_loss = loss.rolling(period).mean()

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return rsi

        data["rsi"] = calculate_rsi(data["close"])

        for i, row in data.iterrows():
            if pd.isna(row["rsi"]):
                continue

            current_price = Decimal(str(row["close"]))
            timestamp = row["timestamp"]

            # Update portfolio value
            backtest_engine.update_portfolio_value({symbol: float(current_price)})

            # Mean reversion logic
            if row["rsi"] < 30:  # Oversold - buy
                if symbol not in backtest_engine.positions:
                    order = {
                        "symbol": symbol,
                        "side": "buy",
                        "qty": 50,
                    }  # Smaller size for expensive stock
                    backtest_engine.process_order(order, current_price, timestamp)

            elif row["rsi"] > 70:  # Overbought - sell
                if symbol in backtest_engine.positions:
                    current_qty = backtest_engine.positions[symbol]["qty"]
                    order = {"symbol": symbol, "side": "sell", "qty": current_qty}
                    backtest_engine.process_order(order, current_price, timestamp)

        metrics = backtest_engine.calculate_performance_metrics()

        print("✓ Mean Reversion Strategy Backtest Results:")
        print(f"  - Total Trades: {metrics['total_trades']}")
        print(f"  - Win Rate: {metrics['win_rate']:.2%}")
        print(f"  - Total Return: {metrics['total_return']:.2%}")
        print(f"  - Max Drawdown: {metrics['max_drawdown']:.2%}")

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_multi_asset_portfolio_backtest(self, backtest_engine, historical_data):
        """Test backtesting with multiple assets."""

        symbols = ["AAPL", "GOOGL", "MSFT"]

        # Equal weight rebalancing strategy
        target_weight = 1.0 / len(symbols)  # 33.33% each
        rebalance_frequency = 20  # Every 20 days

        # Get common date range
        min_len = min(len(data) for data in historical_data.values())

        for day_idx in range(min_len):
            current_prices = {}

            # Get current prices for all symbols
            for symbol in symbols:
                row = historical_data[symbol].iloc[day_idx]
                current_prices[symbol] = float(row["close"])

            # Update portfolio value
            backtest_engine.update_portfolio_value(current_prices)

            # Rebalance portfolio periodically
            if day_idx % rebalance_frequency == 0 and day_idx > 0:
                current_value = float(backtest_engine.portfolio_value)
                target_value_per_asset = current_value * target_weight

                for symbol in symbols:
                    current_price = Decimal(str(current_prices[symbol]))
                    target_qty = int(target_value_per_asset / float(current_price))

                    current_qty = backtest_engine.positions.get(symbol, {}).get(
                        "qty", 0
                    )
                    qty_diff = target_qty - current_qty

                    if abs(qty_diff) >= 1:  # Minimum 1 share difference
                        if qty_diff > 0:
                            # Need to buy more
                            order = {"symbol": symbol, "side": "buy", "qty": qty_diff}
                        else:
                            # Need to sell
                            order = {
                                "symbol": symbol,
                                "side": "sell",
                                "qty": abs(qty_diff),
                            }

                        # Get timestamp from first symbol
                        timestamp = historical_data[symbols[0]].iloc[day_idx][
                            "timestamp"
                        ]
                        backtest_engine.process_order(order, current_price, timestamp)

        metrics = backtest_engine.calculate_performance_metrics()

        # Multi-asset portfolio should have better risk-adjusted returns
        assert len(backtest_engine.positions) <= len(symbols)

        print("✓ Multi-Asset Portfolio Backtest Results:")
        print(f"  - Assets Traded: {len(symbols)}")
        print(f"  - Total Trades: {metrics['total_trades']}")
        print(f"  - Total Return: {metrics['total_return']:.2%}")
        print(f"  - Volatility: {metrics['volatility']:.2%}")
        print(f"  - Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_backtest_with_risk_management(self, backtest_engine, historical_data):
        """Test backtesting with risk management rules."""

        symbol = "MSFT"
        data = historical_data[symbol]

        # Risk management parameters
        max_position_size = 0.1  # 10% of portfolio max per position
        stop_loss_pct = 0.05  # 5% stop loss
        max_drawdown_limit = 0.15  # 15% max drawdown

        # Track stop losses
        stop_losses = {}

        for i, row in data.iterrows():
            current_price = Decimal(str(row["close"]))
            timestamp = row["timestamp"]

            # Update portfolio value
            backtest_engine.update_portfolio_value({symbol: float(current_price)})

            # Check drawdown limit
            current_value = float(backtest_engine.portfolio_value)
            drawdown = (100000 - current_value) / 100000  # From initial capital

            if drawdown > max_drawdown_limit:
                # Emergency sell all positions
                if symbol in backtest_engine.positions:
                    qty = backtest_engine.positions[symbol]["qty"]
                    order = {"symbol": symbol, "side": "sell", "qty": qty}
                    backtest_engine.process_order(order, current_price, timestamp)
                    print(f"Emergency sell triggered at {drawdown:.2%} drawdown")
                continue

            # Check stop loss
            if symbol in backtest_engine.positions:
                avg_price = backtest_engine.positions[symbol]["avg_price"]
                loss_pct = float((avg_price - current_price) / avg_price)

                if loss_pct > stop_loss_pct:
                    # Stop loss triggered
                    qty = backtest_engine.positions[symbol]["qty"]
                    order = {"symbol": symbol, "side": "sell", "qty": qty}
                    result = backtest_engine.process_order(
                        order, current_price, timestamp
                    )
                    if result["success"]:
                        stop_losses[timestamp] = {
                            "price": current_price,
                            "loss_pct": loss_pct,
                            "qty": qty,
                        }
                    continue

            # Simple momentum entry (with position sizing)
            if i >= 10:  # Need history for momentum
                recent_return = (row["close"] - data.iloc[i - 10]["close"]) / data.iloc[
                    i - 10
                ]["close"]

                if recent_return > 0.03:  # 3% momentum
                    if symbol not in backtest_engine.positions:
                        # Calculate position size (max 10% of portfolio)
                        portfolio_value = float(backtest_engine.portfolio_value)
                        max_notional = portfolio_value * max_position_size
                        qty = int(max_notional / float(current_price))

                        if qty > 0:
                            order = {"symbol": symbol, "side": "buy", "qty": qty}
                            backtest_engine.process_order(
                                order, current_price, timestamp
                            )

        metrics = backtest_engine.calculate_performance_metrics()

        # With risk management, max drawdown should be controlled
        assert (
            metrics["max_drawdown"] <= max_drawdown_limit + 0.02
        )  # Small tolerance for execution delay

        print("✓ Risk-Managed Backtest Results:")
        print(f"  - Stop Losses Triggered: {len(stop_losses)}")
        print(
            f"  - Max Drawdown: {metrics['max_drawdown']:.2%} (limit: {max_drawdown_limit:.2%})"
        )
        print(f"  - Total Return: {metrics['total_return']:.2%}")
        print(f"  - Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")

    @pytest.mark.integration
    @pytest.mark.backtest
    def test_backtest_performance_comparison(self, historical_data):
        """Compare multiple strategies against buy-and-hold benchmark."""

        symbol = "AAPL"
        data = historical_data[symbol]

        strategies = {}

        # Strategy 1: Buy and Hold
        bnh_engine = MockBacktestEngine()
        buy_order = {"symbol": symbol, "side": "buy", "qty": 500}
        bnh_engine.process_order(
            buy_order, Decimal(str(data.iloc[0]["close"])), data.iloc[0]["timestamp"]
        )

        for _, row in data.iterrows():
            bnh_engine.update_portfolio_value({symbol: row["close"]})

        strategies["buy_and_hold"] = bnh_engine.calculate_performance_metrics()

        # Strategy 2: Simple Moving Average Crossover
        sma_engine = MockBacktestEngine()
        data["sma_10"] = data["close"].rolling(10).mean()
        data["sma_30"] = data["close"].rolling(30).mean()

        for i, row in data.iterrows():
            if pd.isna(row["sma_30"]):
                sma_engine.update_portfolio_value({symbol: row["close"]})
                continue

            current_price = Decimal(str(row["close"]))

            # Golden cross: SMA10 > SMA30 (buy signal)
            # Death cross: SMA10 < SMA30 (sell signal)
            if i > 0:
                prev_row = data.iloc[i - 1]

                # Check for crossover
                if (
                    prev_row["sma_10"] <= prev_row["sma_30"]
                    and row["sma_10"] > row["sma_30"]
                ):  # Golden cross
                    if symbol not in sma_engine.positions:
                        order = {"symbol": symbol, "side": "buy", "qty": 300}
                        sma_engine.process_order(order, current_price, row["timestamp"])

                elif (
                    prev_row["sma_10"] >= prev_row["sma_30"]
                    and row["sma_10"] < row["sma_30"]
                ):  # Death cross
                    if symbol in sma_engine.positions:
                        qty = sma_engine.positions[symbol]["qty"]
                        order = {"symbol": symbol, "side": "sell", "qty": qty}
                        sma_engine.process_order(order, current_price, row["timestamp"])

            sma_engine.update_portfolio_value({symbol: row["close"]})

        strategies["sma_crossover"] = sma_engine.calculate_performance_metrics()

        # Compare strategies
        print("\n✓ Strategy Performance Comparison:")
        print(
            f"{'Strategy':<15} {'Return':<8} {'Sharpe':<7} {'MaxDD':<7} {'Trades':<7}"
        )
        print("-" * 50)

        for name, metrics in strategies.items():
            print(
                f"{name:<15} {metrics['total_return']:>6.2%} "
                f"{metrics['sharpe_ratio']:>6.2f} "
                f"{metrics['max_drawdown']:>6.2%} "
                f"{metrics['total_trades']:>6d}"
            )

        # Verify both strategies completed
        assert all(
            metrics["final_portfolio_value"] > 0 for metrics in strategies.values()
        )

        # At least one strategy should outperform in some metric
        returns = [metrics["total_return"] for metrics in strategies.values()]
        assert max(returns) != min(
            returns
        ), "Strategies should show different performance"
