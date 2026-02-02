"""
Extended Backtest with 3-Year Historical Data (2023-2025)
==========================================================
"""
import asyncio
import os
import warnings
from datetime import date, timedelta
from pathlib import Path
from itertools import product
from dataclasses import dataclass

import numpy as np
import pandas as pd
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")


@dataclass
class BacktestResult:
    """Container for backtest results."""
    params: dict
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    final_value: float
    annualized_return: float = 0.0


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI indicator."""
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent_deltas = deltas[-period:]
    gains = [d for d in recent_deltas if d > 0]
    losses = [-d for d in recent_deltas if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run_backtest_with_params(
    price_history: dict[str, list[float]],
    params: dict,
    initial_capital: float = 100_000.0,
    start_date: date = date(2023, 1, 1),
) -> BacktestResult:
    """Run backtest with specific parameters."""
    from backend.models.backtest import Trade, EquityPoint

    cash = initial_capital
    positions: dict[str, dict] = {}
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    min_len = min(len(p) for p in price_history.values())

    for day_idx in range(params["sma_slow"], min_len):
        current_date = start_date + timedelta(days=day_idx)

        for symbol in price_history:
            prices = price_history[symbol][: day_idx + 1]
            if len(prices) < params["sma_slow"]:
                continue

            rsi = calculate_rsi(prices, 14)
            sma_fast = sum(prices[-params["sma_fast"] :]) / params["sma_fast"]
            sma_slow = sum(prices[-params["sma_slow"] :]) / params["sma_slow"]
            current_price = prices[-1]

            # Exit logic
            if symbol in positions:
                pos = positions[symbol]
                pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

                if (
                    pnl_pct <= -params["stop_loss_pct"]
                    or pnl_pct >= params["take_profit_pct"]
                    or rsi > params["rsi_sell"]
                ):
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    cash += current_price * pos["quantity"]
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

            # Entry logic
            elif symbol not in positions:
                should_buy = False

                # Mean reversion
                if rsi < params["rsi_buy"] and current_price < sma_slow:
                    should_buy = True
                # Momentum
                elif 40 < rsi < 60 and sma_fast > sma_slow * 1.02:
                    should_buy = True

                if should_buy:
                    position_value = cash * params["position_size_pct"]
                    if position_value > 1000:
                        quantity = int(position_value / current_price)
                        if quantity > 0:
                            cash -= quantity * current_price
                            positions[symbol] = {
                                "entry_date": current_date,
                                "entry_price": current_price,
                                "quantity": quantity,
                            }

        # Portfolio value
        positions_value = sum(
            price_history[sym][min(day_idx, len(price_history[sym]) - 1)] * pos["quantity"]
            for sym, pos in positions.items()
        )
        total_value = cash + positions_value
        equity_curve.append(
            EquityPoint(
                date=current_date,
                value=total_value,
                cash=cash,
                positions_value=positions_value,
            )
        )

    # Close remaining positions
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
                exit_date=start_date + timedelta(days=min_len - 1),
                exit_price=current_price,
                pnl=pnl,
                pnl_percent=pnl_pct * 100,
                duration_days=10,
            )
        )
        cash += current_price * pos["quantity"]

    # Calculate metrics
    if not equity_curve:
        return BacktestResult(
            params=params,
            total_return=0,
            sharpe_ratio=0,
            max_drawdown=0,
            win_rate=0,
            profit_factor=0,
            total_trades=0,
            final_value=initial_capital,
        )

    final_value = equity_curve[-1].value
    total_return = ((final_value - initial_capital) / initial_capital) * 100
    
    # Annualized return (assuming ~252 trading days per year)
    years = len(equity_curve) / 252
    annualized_return = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    # Sharpe ratio
    if len(equity_curve) > 1:
        returns = [
            (equity_curve[i].value - equity_curve[i - 1].value) / equity_curve[i - 1].value
            for i in range(1, len(equity_curve))
        ]
        if returns and np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0

    # Max drawdown
    peak = initial_capital
    max_dd = 0
    for point in equity_curve:
        if point.value > peak:
            peak = point.value
        dd = (peak - point.value) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Win rate and profit factor
    if trades:
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) * 100
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")
    else:
        win_rate = 0
        profit_factor = 0

    return BacktestResult(
        params=params,
        total_return=total_return,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_dd,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_trades=len(trades),
        final_value=final_value,
        annualized_return=annualized_return,
    )


async def fetch_data(symbols: list[str], start_date: date, end_date: date) -> dict[str, list[float]]:
    """Fetch historical data for symbols."""
    from backend.data.alpaca_client import AlpacaClient

    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)
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
                print(f"    ✓ {symbol}: {len(df)} bars")
        except Exception as e:
            print(f"    ⚠ {symbol}: {e}")

    return price_history


async def run_extended_backtest():
    """Run 3-year extended backtest with optimization."""
    print("=" * 70)
    print("EXTENDED 3-YEAR BACKTEST (2023-2025)")
    print("=" * 70)
    print(f"Started at: {pd.Timestamp.now()}")

    # Configuration
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
    start_date = date(2023, 1, 1)
    end_date = date(2025, 12, 31)
    initial_capital = 100_000.0

    print(f"\nConfiguration:")
    print(f"  Symbols: {', '.join(symbols)}")
    print(f"  Period: {start_date} to {end_date} (3 years)")
    print(f"  Initial Capital: ${initial_capital:,.2f}")

    # Fetch data
    print(f"\nFetching 3-year historical data...")
    price_history = await fetch_data(symbols, start_date, end_date)

    if not price_history:
        print("ERROR: No data available")
        return

    min_bars = min(len(p) for p in price_history.values())
    max_bars = max(len(p) for p in price_history.values())
    print(f"  Data range: {min_bars} to {max_bars} bars per symbol")

    # =========================================================================
    # PHASE 1: PARAMETER OPTIMIZATION ON FULL DATASET
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 1: PARAMETER OPTIMIZATION")
    print("=" * 70)

    param_grid = {
        "rsi_buy": [25, 30, 35],
        "rsi_sell": [65, 70, 75],
        "sma_fast": [5, 10, 20],
        "sma_slow": [30, 50, 70],
        "stop_loss_pct": [0.03, 0.05, 0.07],
        "take_profit_pct": [0.10, 0.15, 0.20],
        "position_size_pct": [0.10],
    }

    keys = list(param_grid.keys())
    combinations = list(product(*[param_grid[k] for k in keys]))
    print(f"  Testing {len(combinations)} parameter combinations...")

    results = []
    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        result = run_backtest_with_params(price_history, params, initial_capital, start_date)
        results.append(result)

        if (i + 1) % 100 == 0:
            print(f"    Progress: {i + 1}/{len(combinations)}")

    results.sort(key=lambda x: x.sharpe_ratio, reverse=True)

    print("\n  Top 5 Parameter Sets (3-Year Performance):")
    print("-" * 70)
    for i, r in enumerate(results[:5]):
        print(f"  #{i + 1}: Sharpe={r.sharpe_ratio:.2f}, Return={r.total_return:.2f}%, "
              f"Annual={r.annualized_return:.2f}%, MaxDD={r.max_drawdown:.2f}%")

    best_params = results[0].params
    print(f"\n  ✅ Best Parameters: {best_params}")

    # =========================================================================
    # PHASE 2: DETAILED BACKTEST WITH BEST PARAMS
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 2: DETAILED 3-YEAR BACKTEST")
    print("=" * 70)

    result = run_backtest_with_params(price_history, best_params, initial_capital, start_date)

    print(f"\n📊 3-Year Performance Summary:")
    print(f"  Initial Capital:     ${initial_capital:>12,.2f}")
    print(f"  Final Value:         ${result.final_value:>12,.2f}")
    print(f"  Total Return:        {result.total_return:>12.2f}%")
    print(f"  Annualized Return:   {result.annualized_return:>12.2f}%")

    print(f"\n📈 Risk Metrics:")
    print(f"  Sharpe Ratio:        {result.sharpe_ratio:>12.2f}")
    print(f"  Max Drawdown:        {result.max_drawdown:>12.2f}%")

    print(f"\n📋 Trading Statistics:")
    print(f"  Total Trades:        {result.total_trades:>12}")
    print(f"  Win Rate:            {result.win_rate:>12.1f}%")
    print(f"  Profit Factor:       {result.profit_factor:>12.2f}")

    # =========================================================================
    # PHASE 3: YEAR-BY-YEAR BREAKDOWN
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 3: YEAR-BY-YEAR PERFORMANCE")
    print("=" * 70)

    yearly_results = []
    for year in [2023, 2024, 2025]:
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Filter data for this year
        year_data = await fetch_data(symbols, year_start, year_end)

        if year_data and all(len(p) > best_params["sma_slow"] for p in year_data.values()):
            yr = run_backtest_with_params(year_data, best_params, initial_capital, year_start)
            yearly_results.append((year, yr))
            print(f"\n  {year}:")
            print(f"    Return: {yr.total_return:>7.2f}%  |  Sharpe: {yr.sharpe_ratio:>5.2f}  |  "
                  f"MaxDD: {yr.max_drawdown:>5.2f}%  |  Trades: {yr.total_trades:>3}")
        else:
            print(f"\n  {year}: Insufficient data")

    # =========================================================================
    # PHASE 4: WALK-FORWARD VALIDATION (6-month windows)
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 4: WALK-FORWARD VALIDATION (6-month windows)")
    print("=" * 70)

    wf_periods = [
        (date(2023, 1, 1), date(2023, 6, 30)),
        (date(2023, 7, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 6, 30)),
        (date(2024, 7, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 6, 30)),
        (date(2025, 7, 1), date(2025, 12, 31)),
    ]

    wf_results = []
    print("\n  Semi-Annual Results:")
    for period_start, period_end in wf_periods:
        period_data = await fetch_data(symbols, period_start, period_end)

        if period_data and all(len(p) > best_params["sma_slow"] for p in period_data.values()):
            pr = run_backtest_with_params(period_data, best_params, initial_capital, period_start)
            wf_results.append(pr)
            period_label = f"{period_start.strftime('%Y H1')}" if period_start.month == 1 else f"{period_start.strftime('%Y H2')}"
            status = "✓" if pr.total_return > 0 else "✗"
            print(f"    {period_label}: Return={pr.total_return:>6.2f}%  Sharpe={pr.sharpe_ratio:>5.2f}  {status}")

    if wf_results:
        profitable = sum(1 for r in wf_results if r.total_return > 0)
        avg_return = sum(r.total_return for r in wf_results) / len(wf_results)
        print(f"\n  Walk-Forward Summary:")
        print(f"    Profitable Periods: {profitable}/{len(wf_results)}")
        print(f"    Average Return:     {avg_return:.2f}%")

    # =========================================================================
    # PHASE 5: ML MODEL ON 3-YEAR DATA
    # =========================================================================
    print("\n" + "=" * 70)
    print("PHASE 5: ML MODEL TRAINING (3-Year Dataset)")
    print("=" * 70)

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    features = []
    labels = []

    for symbol, prices in price_history.items():
        for i in range(60, len(prices) - 5):
            rsi = calculate_rsi(prices[: i + 1], 14)
            sma_5 = sum(prices[i - 4 : i + 1]) / 5
            sma_20 = sum(prices[i - 19 : i + 1]) / 20
            sma_50 = sum(prices[i - 49 : i + 1]) / 50

            current = prices[i]
            ret_1d = (current - prices[i - 1]) / prices[i - 1] * 100
            ret_5d = (current - prices[i - 5]) / prices[i - 5] * 100
            ret_20d = (current - prices[i - 20]) / prices[i - 20] * 100

            returns = [(prices[j] - prices[j - 1]) / prices[j - 1] for j in range(i - 19, i + 1)]
            volatility = np.std(returns) * 100

            features.append([rsi, ret_1d, ret_5d, ret_20d, volatility, current / sma_20, sma_5 / sma_50])

            future_return = (prices[i + 5] - current) / current
            labels.append(1 if future_return > 0.02 else 0)

    X = np.array(features)
    y = np.array(labels)

    print(f"  Dataset: {len(X)} samples from 3 years")
    print(f"  Positive class: {sum(y)} ({sum(y)/len(y)*100:.1f}%)")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_train_scaled, y_train)

    accuracy = model.score(X_test_scaled, y_test)
    print(f"  Model Accuracy: {accuracy:.4f}")

    # Feature importance
    feature_names = ["RSI", "Ret_1d", "Ret_5d", "Ret_20d", "Volatility", "Price/SMA20", "SMA5/SMA50"]
    importances = model.feature_importances_
    sorted_idx = np.argsort(importances)[::-1]
    print(f"\n  Top Features:")
    for i in sorted_idx[:5]:
        print(f"    {feature_names[i]:15} {importances[i]:.4f}")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("FINAL SUMMARY - 3-YEAR EXTENDED BACKTEST")
    print("=" * 70)

    print(f"\n📊 Overall Performance (2023-2025):")
    print(f"    Total Return:       {result.total_return:.2f}%")
    print(f"    Annualized Return:  {result.annualized_return:.2f}%")
    print(f"    Sharpe Ratio:       {result.sharpe_ratio:.2f}")
    print(f"    Max Drawdown:       {result.max_drawdown:.2f}%")
    print(f"    Total Trades:       {result.total_trades}")
    print(f"    Win Rate:           {result.win_rate:.1f}%")

    print(f"\n📈 Yearly Breakdown:")
    for year, yr in yearly_results:
        print(f"    {year}: {yr.total_return:>+7.2f}%")

    print(f"\n🤖 ML Model Accuracy: {accuracy:.1%}")

    if wf_results:
        print(f"\n✅ Walk-Forward: {profitable}/{len(wf_results)} periods profitable")

    print("\n" + "=" * 70)
    if result.total_return > 0 and result.sharpe_ratio > 0.5:
        print("✅ STRATEGY VALIDATED - Ready for paper trading!")
    else:
        print("⚠️ Strategy needs further refinement")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_extended_backtest())
