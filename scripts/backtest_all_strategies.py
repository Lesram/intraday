"""
Backtest All 5 Trading Strategies
==================================
Compare performance of all existing strategies on the same dataset.
"""
import asyncio
import os
import warnings
from datetime import date, timedelta
from pathlib import Path
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
class StrategyResult:
    """Container for strategy backtest results."""
    name: str
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


def calculate_sma(prices: list[float], period: int) -> float:
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def calculate_ema(prices: list[float], period: int) -> float:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # Start with SMA
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_macd(prices: list[float]) -> tuple[float, float]:
    """Calculate MACD and Signal line."""
    if len(prices) < 26:
        return 0, 0
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    macd = ema_12 - ema_26
    # Signal line (9-period EMA of MACD) - simplified
    signal = macd * 0.9  # Approximation
    return macd, signal


def calculate_bollinger_bands(prices: list[float], period: int = 20) -> tuple[float, float, float]:
    """Calculate Bollinger Bands."""
    if len(prices) < period:
        return prices[-1], prices[-1], prices[-1]
    recent = prices[-period:]
    middle = sum(recent) / period
    std = np.std(recent)
    upper = middle + 2 * std
    lower = middle - 2 * std
    return upper, middle, lower


def calculate_z_score(prices: list[float], period: int = 60) -> float:
    """Calculate Z-score for mean reversion."""
    if len(prices) < period:
        return 0
    recent = prices[-period:]
    mean = sum(recent) / len(recent)
    std = np.std(recent)
    if std == 0:
        return 0
    return (prices[-1] - mean) / std


class BacktestEngine:
    """Generic backtest engine for testing strategies."""

    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital

    def run_backtest(
        self,
        strategy_name: str,
        signal_func,
        price_history: dict[str, list[float]],
        start_date: date,
        params: dict,
    ) -> StrategyResult:
        """Run backtest with a given signal function."""
        from backend.models.backtest import Trade, EquityPoint

        cash = self.initial_capital
        positions: dict[str, dict] = {}
        trades: list[Trade] = []
        equity_curve: list[EquityPoint] = []

        min_len = min(len(p) for p in price_history.values())
        warmup = params.get("warmup", 60)

        for day_idx in range(warmup, min_len):
            current_date = start_date + timedelta(days=day_idx)

            for symbol in price_history:
                prices = price_history[symbol][: day_idx + 1]
                current_price = prices[-1]

                # Get signal from strategy
                signal, confidence = signal_func(symbol, prices, positions, params)

                # Exit logic for existing positions
                if symbol in positions:
                    pos = positions[symbol]
                    pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

                    should_exit = False
                    exit_reason = ""

                    # Stop loss
                    if pnl_pct <= -params.get("stop_loss_pct", 0.05):
                        should_exit = True
                        exit_reason = "stop_loss"
                    # Take profit
                    elif pnl_pct >= params.get("take_profit_pct", 0.15):
                        should_exit = True
                        exit_reason = "take_profit"
                    # Strategy exit signal
                    elif signal == "sell":
                        should_exit = True
                        exit_reason = "signal"

                    if should_exit:
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
                elif symbol not in positions and signal == "buy" and confidence > 0.3:
                    position_size_pct = params.get("position_size_pct", 0.1)
                    position_value = cash * position_size_pct
                    if position_value > 1000:
                        quantity = int(position_value / current_price)
                        if quantity > 0:
                            cash -= quantity * current_price
                            positions[symbol] = {
                                "entry_date": current_date,
                                "entry_price": current_price,
                                "quantity": quantity,
                            }

            # Calculate portfolio value
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
        return self._calculate_metrics(strategy_name, trades, equity_curve)

    def _calculate_metrics(self, name: str, trades, equity_curve) -> StrategyResult:
        """Calculate performance metrics."""
        if not equity_curve:
            return StrategyResult(
                name=name, total_return=0, annualized_return=0, sharpe_ratio=0,
                max_drawdown=0, win_rate=0, profit_factor=0, total_trades=0,
                avg_trade_pnl=0, final_value=self.initial_capital
            )

        final_value = equity_curve[-1].value
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100
        years = len(equity_curve) / 252
        annualized_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

        # Sharpe ratio
        if len(equity_curve) > 1:
            returns = [
                (equity_curve[i].value - equity_curve[i - 1].value) / equity_curve[i - 1].value
                for i in range(1, len(equity_curve))
            ]
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe_ratio = 0

        # Max drawdown
        peak = self.initial_capital
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
            avg_trade_pnl = sum(t.pnl for t in trades) / len(trades)
        else:
            win_rate = 0
            profit_factor = 0
            avg_trade_pnl = 0

        return StrategyResult(
            name=name,
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            avg_trade_pnl=avg_trade_pnl,
            final_value=final_value,
        )


# =============================================================================
# STRATEGY SIGNAL FUNCTIONS (matching the actual strategy logic)
# =============================================================================

def mean_reversion_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    """
    MeanReversionStrategy: Bollinger Bands + RSI
    Buy when price near lower band + RSI oversold
    Sell when price near upper band + RSI overbought
    """
    if len(prices) < 20:
        return "hold", 0

    rsi = calculate_rsi(prices, 14)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(prices, 20)
    current_price = prices[-1]

    oversold_threshold = params.get("oversold_threshold", 30)
    overbought_threshold = params.get("overbought_threshold", 70)
    band_tolerance = params.get("band_tolerance", 0.01)

    # Buy: price near lower band + RSI oversold
    if current_price < bb_lower * (1 + band_tolerance) and rsi < oversold_threshold:
        confidence = min(0.9, (oversold_threshold - rsi) / 20)
        return "buy", confidence

    # Sell: price near upper band + RSI overbought
    if current_price > bb_upper * (1 - band_tolerance) and rsi > overbought_threshold:
        confidence = min(0.9, (rsi - overbought_threshold) / 20)
        return "sell", confidence

    return "hold", 0


def momentum_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    """
    MomentumStrategy: MACD + Moving Average trends
    Buy when MACD > signal + price > SMA20 > SMA50
    Sell when MACD < signal + price < SMA20 < SMA50
    """
    if len(prices) < 50:
        return "hold", 0

    current_price = prices[-1]
    macd, macd_signal = calculate_macd(prices)
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)

    # Bullish momentum
    if macd > macd_signal and current_price > sma_20 > sma_50:
        confidence = min(0.85, abs(macd - macd_signal) * 10)
        return "buy", confidence

    # Bearish momentum
    if macd < macd_signal and current_price < sma_20 < sma_50:
        confidence = min(0.85, abs(macd - macd_signal) * 10)
        return "sell", confidence

    return "hold", 0


def stat_arb_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    """
    StatisticalArbitrageStrategy: Z-score mean reversion
    Buy when z-score < -entry_threshold (price too low)
    Sell when z-score > entry_threshold (price too high)
    """
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
    """
    RebalancingStrategy: Maintain target portfolio weights
    Simplified version - buy when underweight, sell when overweight
    """
    target_weight = params.get("target_weights", {}).get(symbol, 0.15)
    rebalance_threshold = params.get("rebalance_threshold", 0.05)

    # Check if we have a position
    has_position = symbol in positions

    if not has_position and target_weight > 0:
        # No position but should have one
        return "buy", 0.6

    if has_position:
        # Simplified: hold until significant deviation
        # In real implementation, would check actual weights
        return "hold", 0

    return "hold", 0


def ensemble_signal(symbol: str, prices: list[float], positions: dict, params: dict) -> tuple[str, float]:
    """
    EnsembleStrategy: Combine multiple indicators
    Uses weighted voting from RSI, MACD, SMA, and Bollinger Bands
    """
    if len(prices) < 50:
        return "hold", 0

    current_price = prices[-1]
    rsi = calculate_rsi(prices, 14)
    macd, macd_signal = calculate_macd(prices)
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(prices, 20)

    # Vote counting
    buy_votes = 0
    sell_votes = 0
    total_weight = 0

    # RSI vote (weight: 0.25)
    if rsi < 35:
        buy_votes += 0.25
    elif rsi > 65:
        sell_votes += 0.25
    total_weight += 0.25

    # MACD vote (weight: 0.25)
    if macd > macd_signal:
        buy_votes += 0.25
    else:
        sell_votes += 0.25
    total_weight += 0.25

    # SMA trend vote (weight: 0.25)
    if current_price > sma_20 > sma_50:
        buy_votes += 0.25
    elif current_price < sma_20 < sma_50:
        sell_votes += 0.25
    total_weight += 0.25

    # Bollinger vote (weight: 0.25)
    if current_price < bb_lower * 1.02:
        buy_votes += 0.25
    elif current_price > bb_upper * 0.98:
        sell_votes += 0.25
    total_weight += 0.25

    # Determine signal
    confidence_threshold = params.get("confidence_threshold", 0.6)

    if buy_votes >= confidence_threshold:
        return "buy", buy_votes

    if sell_votes >= confidence_threshold:
        return "sell", sell_votes

    return "hold", 0


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
        except Exception as e:
            print(f"    ⚠ {symbol}: {e}")

    return price_history


async def run_strategy_comparison():
    """Compare all 5 trading strategies."""
    print("=" * 80)
    print("BACKTEST COMPARISON: ALL 5 TRADING STRATEGIES")
    print("=" * 80)
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
    print(f"\nFetching historical data...")
    price_history = await fetch_data(symbols, start_date, end_date)
    print(f"  ✓ Loaded {len(price_history)} symbols, {min(len(p) for p in price_history.values())} bars each")

    # Initialize backtest engine
    engine = BacktestEngine(initial_capital)

    # Define strategies with their parameters
    strategies = [
        {
            "name": "1. MeanReversionStrategy",
            "signal_func": mean_reversion_signal,
            "params": {
                "warmup": 60,
                "oversold_threshold": 30,
                "overbought_threshold": 70,
                "band_tolerance": 0.01,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.15,
                "position_size_pct": 0.10,
            },
        },
        {
            "name": "2. MomentumStrategy",
            "signal_func": momentum_signal,
            "params": {
                "warmup": 60,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.10,
                "position_size_pct": 0.10,
            },
        },
        {
            "name": "3. StatisticalArbitrageStrategy",
            "signal_func": stat_arb_signal,
            "params": {
                "warmup": 60,
                "lookback_period": 60,
                "entry_threshold": 2.0,
                "exit_threshold": 0.5,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.15,
                "position_size_pct": 0.10,
            },
        },
        {
            "name": "4. RebalancingStrategy",
            "signal_func": rebalancing_signal,
            "params": {
                "warmup": 30,
                "target_weights": {s: 1.0 / len(symbols) for s in symbols},
                "rebalance_threshold": 0.05,
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.25,
                "position_size_pct": 0.10,
            },
        },
        {
            "name": "5. EnsembleStrategy",
            "signal_func": ensemble_signal,
            "params": {
                "warmup": 60,
                "confidence_threshold": 0.6,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.20,
                "position_size_pct": 0.10,
            },
        },
    ]

    # Run backtests
    print("\n" + "=" * 80)
    print("RUNNING BACKTESTS")
    print("=" * 80)

    results: list[StrategyResult] = []

    for strategy in strategies:
        print(f"\n  Testing {strategy['name']}...")
        result = engine.run_backtest(
            strategy_name=strategy["name"],
            signal_func=strategy["signal_func"],
            price_history=price_history,
            start_date=start_date,
            params=strategy["params"],
        )
        results.append(result)
        print(f"    Return: {result.total_return:+.2f}%  |  Sharpe: {result.sharpe_ratio:.2f}  |  "
              f"Trades: {result.total_trades}")

    # Sort by Sharpe ratio
    results.sort(key=lambda x: x.sharpe_ratio, reverse=True)

    # Display results
    print("\n" + "=" * 80)
    print("STRATEGY COMPARISON RESULTS (Ranked by Sharpe Ratio)")
    print("=" * 80)

    print(f"\n{'Rank':<5} {'Strategy':<30} {'Return':>10} {'Annual':>10} {'Sharpe':>8} "
          f"{'MaxDD':>8} {'WinRate':>8} {'Trades':>7}")
    print("-" * 96)

    for i, r in enumerate(results):
        print(f"{i+1:<5} {r.name:<30} {r.total_return:>+9.2f}% {r.annualized_return:>+9.2f}% "
              f"{r.sharpe_ratio:>8.2f} {r.max_drawdown:>7.2f}% {r.win_rate:>7.1f}% {r.total_trades:>7}")

    # Detailed breakdown
    print("\n" + "=" * 80)
    print("DETAILED METRICS")
    print("=" * 80)

    for r in results:
        print(f"\n📊 {r.name}")
        print(f"   Final Value:     ${r.final_value:>12,.2f}")
        print(f"   Total Return:    {r.total_return:>+12.2f}%")
        print(f"   Annualized:      {r.annualized_return:>+12.2f}%")
        print(f"   Sharpe Ratio:    {r.sharpe_ratio:>12.2f}")
        print(f"   Max Drawdown:    {r.max_drawdown:>12.2f}%")
        print(f"   Win Rate:        {r.win_rate:>12.1f}%")
        print(f"   Profit Factor:   {r.profit_factor:>12.2f}")
        print(f"   Total Trades:    {r.total_trades:>12}")
        print(f"   Avg Trade PnL:   ${r.avg_trade_pnl:>11.2f}")

    # Summary and recommendation
    print("\n" + "=" * 80)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 80)

    best = results[0]
    print(f"\n🏆 BEST STRATEGY: {best.name}")
    print(f"   - Highest Sharpe Ratio: {best.sharpe_ratio:.2f}")
    print(f"   - Total Return: {best.total_return:+.2f}%")
    print(f"   - Win Rate: {best.win_rate:.1f}%")

    # Find best by other metrics
    best_return = max(results, key=lambda x: x.total_return)
    best_winrate = max(results, key=lambda x: x.win_rate)
    lowest_dd = min(results, key=lambda x: x.max_drawdown)

    print(f"\n📈 Highest Return: {best_return.name} ({best_return.total_return:+.2f}%)")
    print(f"🎯 Best Win Rate: {best_winrate.name} ({best_winrate.win_rate:.1f}%)")
    print(f"🛡️ Lowest Drawdown: {lowest_dd.name} ({lowest_dd.max_drawdown:.2f}%)")

    # Profitability check
    profitable = [r for r in results if r.total_return > 0]
    print(f"\n✅ Profitable Strategies: {len(profitable)}/5")
    for r in profitable:
        print(f"   - {r.name}: {r.total_return:+.2f}%")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(run_strategy_comparison())
