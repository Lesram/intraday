"""
Full Backtest with Real Historical Data
========================================
Runs a comprehensive backtest using Alpaca historical market data.
"""
import asyncio
import os
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Verify credentials
api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")

if not api_key or not secret_key:
    print("ERROR: Alpaca API credentials not found in .env")
    print(f"  ALPACA_API_KEY_ID: {'SET' if api_key else 'NOT SET'}")
    print(f"  ALPACA_API_SECRET_KEY: {'SET' if secret_key else 'NOT SET'}")
    exit(1)

print(f"✓ Alpaca credentials loaded (Key: {api_key[:8]}...)")


async def run_full_backtest():
    """Run a full backtest with real market data."""
    from backend.data.alpaca_client import AlpacaClient
    from backend.services.backtest_service import BacktestService, PortfolioState
    from backend.models.backtest import Trade, EquityPoint

    # Initialize Alpaca client
    print("\n" + "=" * 70)
    print("FULL BACKTEST WITH REAL MARKET DATA")
    print("=" * 70)

    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)

    # Backtest parameters
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)
    initial_capital = 100_000.0

    print(f"\nBacktest Configuration:")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Period: {start_date} to {end_date}")
    print(f"  Initial Capital: ${initial_capital:,.2f}")
    print(f"  Strategy: Mean Reversion + Momentum Ensemble")

    # Fetch historical data
    print("\nFetching historical data from Alpaca...")
    price_history = {}

    for symbol in symbols:
        try:
            df = client.get_historical_data(
                symbol=symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                timeframe="1Day",
            )
            if not df.empty:
                price_history[symbol] = df["close"].tolist()
                print(f"  ✓ {symbol}: {len(df)} daily bars")
            else:
                print(f"  ⚠ {symbol}: No data returned")
        except Exception as e:
            print(f"  ✗ {symbol}: Error - {e}")

    if not price_history:
        print("\nERROR: No historical data available. Exiting.")
        return

    # Run backtest simulation
    print("\nRunning backtest simulation...")

    # Strategy parameters
    strategy_params = {
        "rsi_buy": 30,
        "rsi_sell": 70,
        "sma_fast": 10,
        "sma_slow": 50,
        "position_size_pct": 0.1,  # 10% of portfolio per position
        "stop_loss_pct": 0.05,  # 5% stop loss
        "take_profit_pct": 0.15,  # 15% take profit
    }

    # Simulate the backtest
    portfolio = PortfolioState(initial_capital)
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []
    positions: dict[str, dict] = {}

    # Get the minimum data length
    min_len = min(len(prices) for prices in price_history.values())
    trading_days = min_len

    print(f"  Trading days: {trading_days}")

    for day_idx in range(strategy_params["sma_slow"], min_len):
        current_date = start_date + timedelta(days=day_idx)

        # Calculate indicators for each symbol
        for symbol in price_history:
            prices = price_history[symbol][:day_idx + 1]

            if len(prices) < strategy_params["sma_slow"]:
                continue

            # Calculate RSI
            rsi = calculate_rsi(prices, 14)

            # Calculate SMAs
            sma_fast = sum(prices[-strategy_params["sma_fast"]:]) / strategy_params["sma_fast"]
            sma_slow = sum(prices[-strategy_params["sma_slow"]:]) / strategy_params["sma_slow"]

            current_price = prices[-1]

            # Check for exit signals on existing positions
            if symbol in positions:
                pos = positions[symbol]
                pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

                # Stop loss or take profit
                if pnl_pct <= -strategy_params["stop_loss_pct"] or pnl_pct >= strategy_params["take_profit_pct"]:
                    # Close position
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    portfolio.cash += current_price * pos["quantity"]

                    trades.append(
                        Trade(
                            symbol=symbol,
                            side="long",
                            quantity=pos["quantity"],
                            entry_date=pos["entry_date"],
                            entry_price=pos["entry_price"],
                            exit_date=current_date,
                            exit_price=current_price,
                            pnl=pnl,
                            pnl_percent=pnl_pct * 100,
                            duration_days=(current_date - pos["entry_date"]).days,
                        )
                    )
                    del positions[symbol]

                # RSI overbought exit
                elif rsi > strategy_params["rsi_sell"]:
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    portfolio.cash += current_price * pos["quantity"]

                    trades.append(
                        Trade(
                            symbol=symbol,
                            side="long",
                            quantity=pos["quantity"],
                            entry_date=pos["entry_date"],
                            entry_price=pos["entry_price"],
                            exit_date=current_date,
                            exit_price=current_price,
                            pnl=pnl,
                            pnl_percent=pnl_pct * 100,
                            duration_days=(current_date - pos["entry_date"]).days,
                        )
                    )
                    del positions[symbol]

            # Check for entry signals
            elif symbol not in positions:
                # Mean reversion: RSI oversold + price below slow SMA
                if rsi < strategy_params["rsi_buy"] and current_price < sma_slow:
                    # Calculate position size
                    position_value = portfolio.cash * strategy_params["position_size_pct"]
                    if position_value > 1000:  # Minimum position size
                        quantity = int(position_value / current_price)
                        if quantity > 0:
                            cost = quantity * current_price
                            portfolio.cash -= cost
                            positions[symbol] = {
                                "entry_date": current_date,
                                "entry_price": current_price,
                                "quantity": quantity,
                            }

                # Momentum: RSI neutral + fast SMA > slow SMA (uptrend)
                elif 40 < rsi < 60 and sma_fast > sma_slow * 1.02:
                    position_value = portfolio.cash * strategy_params["position_size_pct"]
                    if position_value > 1000:
                        quantity = int(position_value / current_price)
                        if quantity > 0:
                            cost = quantity * current_price
                            portfolio.cash -= cost
                            positions[symbol] = {
                                "entry_date": current_date,
                                "entry_price": current_price,
                                "quantity": quantity,
                            }

        # Calculate portfolio value
        positions_value = sum(
            price_history[sym][day_idx] * pos["quantity"]
            for sym, pos in positions.items()
        )
        total_value = portfolio.cash + positions_value

        equity_curve.append(
            EquityPoint(
                date=current_date,
                value=total_value,
                cash=portfolio.cash,
                positions_value=positions_value,
            )
        )

    # Close any remaining positions at end
    for symbol, pos in list(positions.items()):
        current_price = price_history[symbol][-1]
        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

        trades.append(
            Trade(
                symbol=symbol,
                side="long",
                quantity=pos["quantity"],
                entry_date=pos["entry_date"],
                entry_price=pos["entry_price"],
                exit_date=end_date,
                exit_price=current_price,
                pnl=pnl,
                pnl_percent=pnl_pct * 100,
                duration_days=(end_date - pos["entry_date"]).days,
            )
        )
        portfolio.cash += current_price * pos["quantity"]

    # Calculate metrics
    print("\nCalculating performance metrics...")

    class MockSession:
        async def execute(self, q):
            class R:
                def scalar_one_or_none(self):
                    return None

                def scalars(self):
                    class S:
                        def all(self):
                            return []

                    return S()

            return R()

    service = BacktestService(MockSession())
    metrics = service.calculate_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
    )

    # Print results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    print(f"\n📊 Performance Summary:")
    print(f"  Initial Capital:     ${initial_capital:>12,.2f}")
    print(f"  Final Value:         ${equity_curve[-1].value:>12,.2f}")
    print(f"  Total Return:        {metrics.total_return:>12.2f}%")
    print(f"  Annualized Return:   {metrics.annualized_return:>12.2f}%")

    print(f"\n📈 Risk Metrics:")
    print(f"  Sharpe Ratio:        {metrics.sharpe_ratio:>12.2f}")
    print(f"  Sortino Ratio:       {metrics.sortino_ratio:>12.2f}")
    print(f"  Max Drawdown:        {metrics.max_drawdown:>12.2f}%")
    print(f"  Volatility:          {metrics.volatility:>12.2f}%")

    print(f"\n📋 Trading Statistics:")
    print(f"  Total Trades:        {metrics.total_trades:>12}")
    print(f"  Win Rate:            {metrics.win_rate:>12.1f}%")
    print(f"  Profit Factor:       {metrics.profit_factor:>12.2f}")
    print(f"  Avg Trade PnL:       ${metrics.avg_trade_pnl:>11.2f}")
    print(f"  Avg Win:             ${metrics.avg_win:>11.2f}")
    print(f"  Avg Loss:            ${metrics.avg_loss:>11.2f}")

    # Trade breakdown by symbol
    print(f"\n📊 Trades by Symbol:")
    symbol_trades = {}
    for trade in trades:
        if trade.symbol not in symbol_trades:
            symbol_trades[trade.symbol] = {"count": 0, "pnl": 0}
        symbol_trades[trade.symbol]["count"] += 1
        symbol_trades[trade.symbol]["pnl"] += trade.pnl

    for sym, data in sorted(symbol_trades.items(), key=lambda x: x[1]["pnl"], reverse=True):
        print(f"  {sym:6} | Trades: {data['count']:3} | PnL: ${data['pnl']:>10,.2f}")

    print("\n" + "=" * 70)

    # Evaluate results
    if metrics.total_return > 0 and metrics.sharpe_ratio > 0.5:
        print("✅ BACKTEST SUCCESSFUL - Strategy shows positive performance")
    elif metrics.total_return > 0:
        print("⚠️ BACKTEST COMPLETE - Positive returns but low risk-adjusted performance")
    else:
        print("❌ BACKTEST COMPLETE - Strategy needs optimization")

    print("=" * 70)

    # Cleanup (AlpacaClient doesn't require explicit close)
    if hasattr(client, 'close'):
        await client.close()


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI indicator."""
    if len(prices) < period + 1:
        return 50.0

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent_deltas = deltas[-(period):]

    gains = [d for d in recent_deltas if d > 0]
    losses = [-d for d in recent_deltas if d < 0]

    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


if __name__ == "__main__":
    asyncio.run(run_full_backtest())
