"""
Optimize Parameters for All 5 Trading Strategies
=================================================
Grid search to find optimal parameters for each strategy.
"""
import asyncio
import os
import warnings
from datetime import date, timedelta
from pathlib import Path
from dataclasses import dataclass
from itertools import product

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
class StrategyResult:
    """Container for strategy backtest results."""
    name: str
    params: dict
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_pnl: float
    final_value: float


def calculate_rsi(prices: list[float], period: int = 14) -> float:
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


def calculate_sma(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def calculate_ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_macd(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 26:
        return 0, 0
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    macd = ema_12 - ema_26
    signal = macd * 0.9
    return macd, signal


def calculate_bollinger_bands(prices: list[float], period: int = 20) -> tuple[float, float, float]:
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1]
    recent = prices[-period:]
    middle = sum(recent) / period
    std = np.std(recent)
    upper = middle + 2 * std
    lower = middle - 2 * std
    return upper, middle, lower


def calculate_z_score(prices: list[float], period: int = 60) -> float:
    if len(prices) < period:
        return 0
    recent = prices[-period:]
    mean = sum(recent) / len(recent)
    std = np.std(recent)
    if std == 0:
        return 0
    return (prices[-1] - mean) / std


# =============================================================================
# STRATEGY SIGNAL FUNCTIONS
# =============================================================================

def mean_reversion_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    if len(prices) < 20:
        return "hold", 0
    rsi = calculate_rsi(prices, 14)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(prices, 20)
    current_price = prices[-1]
    oversold = params.get("oversold_threshold", 30)
    overbought = params.get("overbought_threshold", 70)
    band_tol = params.get("band_tolerance", 0.01)

    if current_price < bb_lower * (1 + band_tol) and rsi < oversold:
        return "buy", min(0.9, (oversold - rsi) / 20)
    if current_price > bb_upper * (1 - band_tol) and rsi > overbought:
        return "sell", min(0.9, (rsi - overbought) / 20)
    return "hold", 0


def momentum_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    if len(prices) < 50:
        return "hold", 0
    current_price = prices[-1]
    macd, macd_signal = calculate_macd(prices)
    sma_fast = calculate_sma(prices, params.get("sma_fast", 20))
    sma_slow = calculate_sma(prices, params.get("sma_slow", 50))

    if macd > macd_signal and current_price > sma_fast > sma_slow:
        return "buy", min(0.85, abs(macd - macd_signal) * 10)
    if macd < macd_signal and current_price < sma_fast < sma_slow:
        return "sell", min(0.85, abs(macd - macd_signal) * 10)
    return "hold", 0


def stat_arb_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    lookback = params.get("lookback_period", 60)
    entry_threshold = params.get("entry_threshold", 2.0)
    if len(prices) < lookback:
        return "hold", 0
    z_score = calculate_z_score(prices, lookback)
    confidence = min(0.9, abs(z_score) / 5.0)
    if z_score < -entry_threshold:
        return "buy", confidence
    if z_score > entry_threshold:
        return "sell", confidence
    return "hold", 0


def rebalancing_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    target_weight = params.get("target_weights", {}).get(symbol, 0.15)
    if symbol not in positions and target_weight > 0:
        return "buy", 0.6
    return "hold", 0


def ensemble_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    if len(prices) < 50:
        return "hold", 0
    current_price = prices[-1]
    rsi = calculate_rsi(prices, 14)
    macd, macd_signal = calculate_macd(prices)
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(prices, 20)

    rsi_buy = params.get("rsi_buy", 35)
    rsi_sell = params.get("rsi_sell", 65)
    confidence_threshold = params.get("confidence_threshold", 0.6)

    buy_votes = sell_votes = 0
    if rsi < rsi_buy:
        buy_votes += 0.25
    elif rsi > rsi_sell:
        sell_votes += 0.25
    if macd > macd_signal:
        buy_votes += 0.25
    else:
        sell_votes += 0.25
    if current_price > sma_20 > sma_50:
        buy_votes += 0.25
    elif current_price < sma_20 < sma_50:
        sell_votes += 0.25
    if current_price < bb_lower * 1.02:
        buy_votes += 0.25
    elif current_price > bb_upper * 0.98:
        sell_votes += 0.25

    if buy_votes >= confidence_threshold:
        return "buy", buy_votes
    if sell_votes >= confidence_threshold:
        return "sell", sell_votes
    return "hold", 0


def run_backtest(signal_func, price_history, start_date, params, initial_capital=100_000.0):
    """Run backtest with given parameters."""
    from backend.models.backtest import Trade, EquityPoint

    cash = initial_capital
    positions = {}
    trades = []
    equity_curve = []
    min_len = min(len(p) for p in price_history.values())
    warmup = params.get("warmup", 60)

    for day_idx in range(warmup, min_len):
        current_date = start_date + timedelta(days=day_idx)
        for symbol in price_history:
            prices = price_history[symbol][:day_idx + 1]
            current_price = prices[-1]
            signal, confidence = signal_func(symbol, prices, positions, params)

            if symbol in positions:
                pos = positions[symbol]
                pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
                should_exit = (
                    pnl_pct <= -params.get("stop_loss_pct", 0.05)
                    or pnl_pct >= params.get("take_profit_pct", 0.15)
                    or signal == "sell"
                )
                if should_exit:
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    cash += current_price * pos["quantity"]
                    trades.append(Trade(
                        symbol=symbol, side="long", quantity=pos["quantity"],
                        entry_date=pos["entry_date"], entry_price=pos["entry_price"],
                        exit_date=current_date, exit_price=current_price,
                        pnl=pnl, pnl_percent=pnl_pct * 100,
                        duration_days=(current_date - pos["entry_date"]).days,
                    ))
                    del positions[symbol]

            elif signal == "buy" and confidence > 0.3:
                position_value = cash * params.get("position_size_pct", 0.1)
                if position_value > 1000:
                    quantity = int(position_value / current_price)
                    if quantity > 0:
                        cash -= quantity * current_price
                        positions[symbol] = {
                            "entry_date": current_date,
                            "entry_price": current_price,
                            "quantity": quantity,
                        }

        positions_value = sum(
            price_history[sym][min(day_idx, len(price_history[sym]) - 1)] * pos["quantity"]
            for sym, pos in positions.items()
        )
        equity_curve.append(EquityPoint(
            date=current_date, value=cash + positions_value,
            cash=cash, positions_value=positions_value,
        ))

    # Close remaining
    for symbol, pos in list(positions.items()):
        current_price = price_history[symbol][-1]
        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
        trades.append(Trade(
            symbol=symbol, side="long", quantity=pos["quantity"],
            entry_date=pos["entry_date"], entry_price=pos["entry_price"],
            exit_date=start_date + timedelta(days=min_len - 1), exit_price=current_price,
            pnl=pnl, pnl_percent=pnl_pct * 100, duration_days=10,
        ))
        cash += current_price * pos["quantity"]

    # Metrics
    if not equity_curve:
        return 0, 0, 0, 0, 0, 0, initial_capital

    final_value = equity_curve[-1].value
    total_return = ((final_value - initial_capital) / initial_capital) * 100
    years = len(equity_curve) / 252
    ann_return = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    if len(equity_curve) > 1:
        returns = [(equity_curve[i].value - equity_curve[i-1].value) / equity_curve[i-1].value
                   for i in range(1, len(equity_curve))]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    peak = initial_capital
    max_dd = 0
    for pt in equity_curve:
        if pt.value > peak:
            peak = pt.value
        dd = (peak - pt.value) / peak * 100
        if dd > max_dd:
            max_dd = dd

    if trades:
        wins = [t for t in trades if t.pnl > 0]
        win_rate = len(wins) / len(trades) * 100
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in trades if t.pnl <= 0))
        pf = total_wins / total_losses if total_losses > 0 else 999
    else:
        win_rate = pf = 0

    return total_return, ann_return, sharpe, max_dd, win_rate, len(trades), final_value


async def fetch_data(symbols, start_date, end_date):
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
        except:
            pass
    return price_history


def optimize_strategy(name, signal_func, param_grid, price_history, start_date):
    """Grid search for optimal parameters."""
    keys = list(param_grid.keys())
    combinations = list(product(*[param_grid[k] for k in keys]))
    
    best_result = None
    best_sharpe = -999
    
    for combo in combinations:
        params = dict(zip(keys, combo))
        params["warmup"] = 60
        params["position_size_pct"] = 0.10
        
        ret, ann, sharpe, dd, wr, trades, fv = run_backtest(
            signal_func, price_history, start_date, params
        )
        
        if sharpe > best_sharpe and trades >= 10:  # Min 10 trades
            best_sharpe = sharpe
            best_result = StrategyResult(
                name=name, params=params.copy(),
                total_return=ret, annualized_return=ann, sharpe_ratio=sharpe,
                max_drawdown=dd, win_rate=wr, profit_factor=0, total_trades=trades,
                avg_trade_pnl=0, final_value=fv
            )
    
    return best_result


async def run_optimization():
    """Optimize all 5 strategies."""
    print("=" * 80)
    print("PARAMETER OPTIMIZATION FOR ALL 5 STRATEGIES")
    print("=" * 80)
    print(f"Started at: {pd.Timestamp.now()}")

    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
    start_date = date(2023, 1, 1)
    end_date = date(2025, 12, 31)

    print(f"\nFetching 3-year data for {len(symbols)} symbols...")
    price_history = await fetch_data(symbols, start_date, end_date)
    print(f"  ✓ Loaded {len(price_history)} symbols")

    # Define parameter grids for each strategy
    strategies = {
        "1. MeanReversionStrategy": {
            "signal_func": mean_reversion_signal,
            "param_grid": {
                "oversold_threshold": [20, 25, 30, 35],
                "overbought_threshold": [65, 70, 75, 80],
                "band_tolerance": [0.005, 0.01, 0.02],
                "stop_loss_pct": [0.03, 0.05, 0.07],
                "take_profit_pct": [0.10, 0.15, 0.20],
            },
        },
        "2. MomentumStrategy": {
            "signal_func": momentum_signal,
            "param_grid": {
                "sma_fast": [10, 15, 20, 25],
                "sma_slow": [40, 50, 60],
                "stop_loss_pct": [0.02, 0.03, 0.05],
                "take_profit_pct": [0.08, 0.10, 0.15],
            },
        },
        "3. StatisticalArbitrageStrategy": {
            "signal_func": stat_arb_signal,
            "param_grid": {
                "lookback_period": [30, 45, 60, 90],
                "entry_threshold": [1.5, 2.0, 2.5, 3.0],
                "stop_loss_pct": [0.03, 0.05, 0.07],
                "take_profit_pct": [0.10, 0.15, 0.20],
            },
        },
        "4. RebalancingStrategy": {
            "signal_func": rebalancing_signal,
            "param_grid": {
                "stop_loss_pct": [0.05, 0.10, 0.15],
                "take_profit_pct": [0.15, 0.20, 0.30],
                "target_weights": [{s: 1/len(symbols) for s in symbols}],  # Fixed
            },
        },
        "5. EnsembleStrategy": {
            "signal_func": ensemble_signal,
            "param_grid": {
                "rsi_buy": [25, 30, 35, 40],
                "rsi_sell": [60, 65, 70, 75],
                "confidence_threshold": [0.5, 0.6, 0.75],
                "stop_loss_pct": [0.03, 0.05, 0.07],
                "take_profit_pct": [0.10, 0.15, 0.20, 0.25],
            },
        },
    }

    results = []

    print("\n" + "=" * 80)
    print("OPTIMIZING EACH STRATEGY")
    print("=" * 80)

    for name, config in strategies.items():
        grid = config["param_grid"]
        total_combos = 1
        for v in grid.values():
            total_combos *= len(v)
        
        print(f"\n  {name}: Testing {total_combos} combinations...")
        
        result = optimize_strategy(
            name,
            config["signal_func"],
            config["param_grid"],
            price_history,
            start_date,
        )
        
        if result:
            results.append(result)
            print(f"    ✓ Best Sharpe: {result.sharpe_ratio:.2f}, Return: {result.total_return:+.2f}%")
        else:
            print(f"    ⚠ No valid configuration found")

    # Sort by Sharpe
    results.sort(key=lambda x: x.sharpe_ratio, reverse=True)

    # Display results
    print("\n" + "=" * 80)
    print("OPTIMIZED STRATEGY COMPARISON (Ranked by Sharpe)")
    print("=" * 80)

    print(f"\n{'Rank':<5} {'Strategy':<30} {'Return':>10} {'Annual':>10} {'Sharpe':>8} "
          f"{'MaxDD':>8} {'WinRate':>8} {'Trades':>7}")
    print("-" * 96)

    for i, r in enumerate(results):
        print(f"{i+1:<5} {r.name:<30} {r.total_return:>+9.2f}% {r.annualized_return:>+9.2f}% "
              f"{r.sharpe_ratio:>8.2f} {r.max_drawdown:>7.2f}% {r.win_rate:>7.1f}% {r.total_trades:>7}")

    # Show optimal parameters for each
    print("\n" + "=" * 80)
    print("OPTIMAL PARAMETERS FOR EACH STRATEGY")
    print("=" * 80)

    for r in results:
        print(f"\n🎯 {r.name}")
        print(f"   Performance: Return={r.total_return:+.2f}%, Sharpe={r.sharpe_ratio:.2f}")
        print(f"   Optimal Parameters:")
        for k, v in r.params.items():
            if k not in ["warmup", "position_size_pct", "target_weights"]:
                if isinstance(v, float):
                    print(f"      {k}: {v:.2f}" if v < 1 else f"      {k}: {v}")
                else:
                    print(f"      {k}: {v}")

    # Final recommendation
    print("\n" + "=" * 80)
    print("FINAL RECOMMENDATION")
    print("=" * 80)

    best = results[0]
    print(f"\n🏆 BEST OPTIMIZED STRATEGY: {best.name}")
    print(f"   Sharpe Ratio:     {best.sharpe_ratio:.2f}")
    print(f"   Total Return:     {best.total_return:+.2f}%")
    print(f"   Annualized:       {best.annualized_return:+.2f}%")
    print(f"   Max Drawdown:     {best.max_drawdown:.2f}%")
    print(f"   Win Rate:         {best.win_rate:.1f}%")
    print(f"   Total Trades:     {best.total_trades}")

    print(f"\n   📋 Optimal Parameters to Use:")
    for k, v in best.params.items():
        if k not in ["warmup", "position_size_pct", "target_weights"]:
            if isinstance(v, float):
                print(f"      {k}: {v:.2f}" if v < 1 else f"      {k}: {v}")
            else:
                print(f"      {k}: {v}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(run_optimization())
