"""
Organism Replay Simulator — feed historical bars through the real live_tick() pipeline.

Provides:
    - SimulatedBroker: mock broker that tracks fills, positions, and equity
    - HistoricalBarProvider: feeds bars one-at-a-time from historical data
    - ReplayEngine: orchestrates replay through OrganismLiveEngine.live_tick()
    - ReplayResult: structured output with trades, equity curve, metrics

Usage:
    python -m backend.organism.replay_simulator \\
        --symbols AAPL,MSFT,SPY --start 2026-02-01 --end 2026-02-25
"""

from __future__ import annotations

import asyncio
import math
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.utils.logger import get_logger

logger = get_logger(__name__)


# ═════════════════════════════════════════════════════════════════════════
#  SIMULATED BROKER
# ═════════════════════════════════════════════════════════════════════════

class SimulatedBroker:
    """Mock that implements PositionsService + OrderService interfaces.

    Tracks fills, positions, cash, and equity — usable by both the
    integration smoke tests and the replay simulator.
    """

    def __init__(
        self,
        initial_cash: float = 100_000,
        slippage_bps: float = 0,
        delay_fill: bool = False,
    ) -> None:
        self.cash: float = initial_cash
        self.initial_cash: float = initial_cash
        self.slippage_bps: float = slippage_bps
        # delay_fill: when True, orders observe the current bar's close
        # but fill at the NEXT bar's open. More realistic than instant
        # same-bar fill at observed close. Default False for backward-compat.
        self.delay_fill: bool = delay_fill

        # symbol → {qty, avg_entry_price, side, market_value, cost_basis, ...}
        self._positions: dict[str, dict[str, Any]] = {}
        # Manually-set prices for test control
        self._prices: dict[str, float] = {}
        # Bar provider for live price lookups (optional)
        self._bar_provider: HistoricalBarProvider | None = None

        self.filled_orders: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self._equity_curve: list[float] = [initial_cash]

    def set_price(self, symbol: str, price: float) -> None:
        """Test helper — set current price for a symbol."""
        self._prices[symbol] = price

    def set_prices(self, prices: dict[str, float]) -> None:
        """Test helper — set prices for multiple symbols."""
        self._prices.update(prices)

    def set_bar_provider(self, provider: HistoricalBarProvider) -> None:
        """Link to a bar provider for live price lookups."""
        self._bar_provider = provider

    def _current_price(self, symbol: str) -> float:
        """Get current price — manual price > bar provider > 0."""
        if symbol in self._prices:
            return self._prices[symbol]
        if self._bar_provider is not None:
            return self._bar_provider.current_price(symbol)
        return 0.0

    def _fill_price(self, symbol: str) -> float:
        """Get fill price. With delay_fill=True, returns NEXT bar's open
        (more realistic than same-bar close). Otherwise returns current price.
        """
        if not self.delay_fill or self._bar_provider is None:
            return self._current_price(symbol)
        # Look up next bar's open via bar provider
        return self._bar_provider.next_bar_open(symbol)

    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage in basis points."""
        if self.slippage_bps <= 0:
            return price
        slip = price * (self.slippage_bps / 10_000)
        return price + slip if side == "buy" else price - slip

    def add_position(
        self,
        symbol: str,
        qty: float,
        avg_entry_price: float,
        side: str = "long",
    ) -> None:
        """Test helper — manually add a position."""
        self._positions[symbol] = {
            "symbol": symbol,
            "qty": abs(qty),
            "side": side,
            "avg_entry_price": avg_entry_price,
            "cost_basis": abs(qty) * avg_entry_price,
            "market_value": abs(qty) * self._current_price(symbol) or abs(qty) * avg_entry_price,
            "unrealized_pl": 0.0,
            "current_price": self._current_price(symbol) or avg_entry_price,
        }

    def remove_position(self, symbol: str) -> None:
        """Test helper — manually remove a position."""
        self._positions.pop(symbol, None)

    # ── PositionsService interface ──────────────────────────────────

    async def get_all_positions(self) -> dict[str, dict[str, Any]]:
        # Update market values before returning
        for sym, pos in self._positions.items():
            price = self._current_price(sym)
            if price > 0:
                pos["current_price"] = price
                pos["market_value"] = abs(pos["qty"]) * price
                entry = pos["avg_entry_price"]
                direction = 1.0 if pos["side"] == "long" else -1.0
                pos["unrealized_pl"] = (price - entry) * abs(pos["qty"]) * direction
        return dict(self._positions)

    async def get_total_portfolio_value(self) -> float:
        positions = await self.get_all_positions()
        pos_value = sum(p["market_value"] for p in positions.values())
        return self.cash + pos_value

    async def get_buying_power(self) -> float:
        return self.cash

    # ── OrderService interface ──────────────────────────────────────

    async def submit_symbol_order(self, **kwargs: Any) -> dict[str, Any]:
        symbol = kwargs["symbol"]
        side = kwargs["side"]
        qty = int(float(kwargs["qty"]))
        # With delay_fill, orders observe the current bar's close but fill
        # at next bar's open (more realistic). Without it, fill at current.
        price = self._fill_price(symbol)

        if price <= 0:
            return {"id": str(uuid.uuid4()), "status": "rejected", "reason": "no_price"}

        fill_price = self._apply_slippage(price, side)

        if side == "buy":
            cost = fill_price * qty
            if cost > self.cash:
                # Partial fill — buy what we can afford
                qty = int(self.cash / fill_price) if fill_price > 0 else 0
                if qty <= 0:
                    return {"id": str(uuid.uuid4()), "status": "rejected", "reason": "insufficient_cash"}
                cost = fill_price * qty

            self.cash -= cost

            if symbol in self._positions:
                pos = self._positions[symbol]
                old_qty = pos["qty"]
                old_cost = pos["cost_basis"]
                new_qty = old_qty + qty
                new_cost = old_cost + cost
                pos["qty"] = new_qty
                pos["cost_basis"] = new_cost
                pos["avg_entry_price"] = new_cost / new_qty if new_qty > 0 else 0
                pos["market_value"] = new_qty * fill_price
            else:
                self._positions[symbol] = {
                    "symbol": symbol,
                    "qty": qty,
                    "side": "long",
                    "avg_entry_price": fill_price,
                    "cost_basis": cost,
                    "market_value": qty * fill_price,
                    "unrealized_pl": 0.0,
                    "current_price": fill_price,
                }

        elif side == "sell":
            pos = self._positions.get(symbol)
            if pos is None or pos["qty"] <= 0:
                return {"id": str(uuid.uuid4()), "status": "rejected", "reason": "no_position"}

            sell_qty = min(qty, int(pos["qty"]))
            proceeds = fill_price * sell_qty
            self.cash += proceeds

            entry_price = pos["avg_entry_price"]
            pnl = (fill_price - entry_price) * sell_qty
            self.trade_log.append({
                "symbol": symbol,
                "side": "sell",
                "qty": sell_qty,
                "entry_price": entry_price,
                "exit_price": fill_price,
                "pnl": pnl,
            })

            remaining = pos["qty"] - sell_qty
            if remaining <= 0:
                del self._positions[symbol]
            else:
                pos["qty"] = remaining
                pos["market_value"] = remaining * fill_price
                pos["cost_basis"] = remaining * pos["avg_entry_price"]

        order_id = str(uuid.uuid4())
        order_record = {
            "id": order_id,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "filled_qty": str(qty),
            "status": "filled",
            "avg_fill_price": str(fill_price),
            "idempotency_key": kwargs.get("idempotency_key", ""),
        }
        self.filled_orders.append(order_record)

        # Record equity snapshot
        total = await self.get_total_portfolio_value()
        self._equity_curve.append(total)

        return order_record

    # ── Extra service methods the engine may call ───────────────────

    async def plan_and_submit(self, signals: Any, **kwargs: Any) -> list[dict]:
        return [{"id": "mock", "status": "accepted"}]

    @property
    def equity_curve(self) -> list[float]:
        return list(self._equity_curve)


# ═════════════════════════════════════════════════════════════════════════
#  HISTORICAL BAR PROVIDER
# ═════════════════════════════════════════════════════════════════════════

class HistoricalBarProvider:
    """Feeds bars from historical data, advancing one bar per tick.

    Implements the data_client interface expected by OrganismLiveEngine:
    - get_historical_data(symbol, timeframe, limit)
    """

    def __init__(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
        lookback: int = 500,
    ) -> None:
        self._bars = bars_by_symbol
        self._max_idx = min(len(df) for df in bars_by_symbol.values()) if bars_by_symbol else 0
        # Need enough warmup bars for feature computation (MIN_BARS default 200),
        # but also leave room to actually replay. Use min of requested lookback
        # vs 75% of available bars (always leave 25% for replay).
        max_lookback = max(0, int(self._max_idx * 0.75))
        self._lookback = min(lookback, max_lookback)
        self._current_idx: int = self._lookback  # Start after enough history

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 500,
    ) -> pd.DataFrame | None:
        """Return lookback window of bars up to current cursor."""
        df = self._bars.get(symbol)
        if df is None:
            return None
        end = min(self._current_idx, len(df))
        start = max(0, end - limit)
        if start >= end:
            return None
        return df.iloc[start:end].copy().reset_index(drop=True)

    def advance(self) -> bool:
        """Move cursor forward 1 bar. Returns False when exhausted."""
        if self._current_idx >= self._max_idx:
            return False
        self._current_idx += 1
        return True

    def current_price(self, symbol: str) -> float:
        """Get the close price at current cursor for a symbol."""
        df = self._bars.get(symbol)
        if df is None or self._current_idx <= 0:
            return 0.0
        idx = min(self._current_idx - 1, len(df) - 1)
        return float(df["close"].iloc[idx])

    def next_bar_open(self, symbol: str) -> float:
        """Get the OPEN of the bar AFTER the current cursor — the price an
        order submitted at the current bar's close would actually fill at.
        Falls back to current_price if at last bar.
        """
        df = self._bars.get(symbol)
        if df is None or self._current_idx <= 0:
            return 0.0
        # current_idx points to the bar we just observed; next bar's open
        # is at df.iloc[current_idx]['open'] (if it exists).
        if self._current_idx < len(df) and "open" in df.columns:
            return float(df["open"].iloc[self._current_idx])
        return self.current_price(symbol)

    @property
    def current_time(self) -> datetime | None:
        """Timestamp at current cursor position."""
        for df in self._bars.values():
            if df.index.dtype.kind == "M" and self._current_idx > 0:
                idx = min(self._current_idx - 1, len(df) - 1)
                return pd.Timestamp(df.index[idx]).to_pydatetime()
            break
        return None

    @property
    def bars_remaining(self) -> int:
        return max(0, self._max_idx - self._current_idx)

    @property
    def current_simulated_time(self) -> float:
        """Return epoch seconds for current bar position.

        Tries bar timestamps first, falls back to synthetic 1-minute spacing.
        """
        for df in self._bars.values():
            if hasattr(df, 'index') and df.index.dtype.kind == 'M':
                idx = min(self._current_idx - 1, len(df) - 1)
                return pd.Timestamp(df.index[idx]).timestamp()
            if 'timestamp' in df.columns:
                idx = min(self._current_idx - 1, len(df) - 1)
                return pd.Timestamp(df['timestamp'].iloc[idx]).timestamp()
            break
        # Synthetic fallback: 1-minute spacing from a base time
        base = datetime(2026, 1, 2, 9, 30).timestamp()  # market open
        return base + (self._current_idx * 60)

    @property
    def current_simulated_datetime(self) -> datetime:
        """Return timezone-aware datetime for current bar position."""
        return datetime.fromtimestamp(self.current_simulated_time, tz=UTC)


# ═════════════════════════════════════════════════════════════════════════
#  REPLAY RESULT
# ═════════════════════════════════════════════════════════════════════════

@dataclass
class ReplayResult:
    """Structured output from a replay run."""

    ticks: int = 0
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    regime_history: list[str] = field(default_factory=list)
    signals_log: list[dict] = field(default_factory=list)
    tick_results: list[dict] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(t.get("pnl", 0) for t in self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        return wins / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                dd = (peak - eq) / peak
                max_dd = max(max_dd, dd)
        return max_dd

    @property
    def sharpe(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev = self.equity_curve[i - 1]
            if prev > 0:
                returns.append((self.equity_curve[i] - prev) / prev)
        if not returns:
            return 0.0
        mean_r = np.mean(returns)
        std_r = np.std(returns)
        if std_r == 0:
            return 0.0
        return float(mean_r / std_r * math.sqrt(252))

    def summary(self) -> str:
        """Printable summary table."""
        lines = [
            "=" * 50,
            "  REPLAY SUMMARY",
            "=" * 50,
            f"  Ticks:          {self.ticks}",
            f"  Trades:         {len(self.trades)}",
            f"  Total PnL:      ${self.total_pnl:,.2f}",
            f"  Win Rate:       {self.win_rate:.1%}",
            f"  Max Drawdown:   {self.max_drawdown:.2%}",
            f"  Sharpe Ratio:   {self.sharpe:.2f}",
        ]
        if self.equity_curve:
            lines.append(f"  Final Equity:   ${self.equity_curve[-1]:,.2f}")
        if self.regime_history:
            from collections import Counter
            regime_counts = Counter(self.regime_history)
            top3 = regime_counts.most_common(3)
            lines.append(f"  Top Regimes:    {', '.join(f'{r}({c})' for r, c in top3)}")
        lines.append("=" * 50)
        return "\n".join(lines)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert tick results to DataFrame for analysis."""
        if not self.tick_results:
            return pd.DataFrame()
        return pd.DataFrame(self.tick_results)


# ═════════════════════════════════════════════════════════════════════════
#  REPLAY ENGINE
# ═════════════════════════════════════════════════════════════════════════

class ReplayEngine:
    """Feeds historical bars through the real OrganismLiveEngine.live_tick() pipeline."""

    def __init__(
        self,
        bars_by_symbol: dict[str, pd.DataFrame],
        initial_cash: float = 100_000,
        slippage_bps: float = 5,
        universe: list[str] | None = None,
        brain_dir: str | None = None,
        max_entries_per_hour: int = 20,
        timeframe: str = "1Day",
        lookback: int | None = None,
        delay_fill: bool = False,
    ) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.initial_cash = initial_cash
        self.slippage_bps = slippage_bps
        self.universe = universe or list(bars_by_symbol.keys())
        self.brain_dir = brain_dir
        self.max_entries_per_hour = max_entries_per_hour
        self.timeframe = timeframe
        self.delay_fill = delay_fill

        if lookback is not None:
            self.lookback = lookback
        else:
            is_intraday = timeframe in ("1Min", "5Min", "15Min", "1Hour")
            self.lookback = 500 if is_intraday else 200

    async def run(self, max_ticks: int | None = None) -> ReplayResult:
        """Run replay: create engine, loop through bars, collect results."""
        from backend.organism.live_engine import OrganismLiveEngine

        # Create components
        bar_provider = HistoricalBarProvider(self.bars_by_symbol, lookback=self.lookback)
        broker = SimulatedBroker(
            initial_cash=self.initial_cash,
            slippage_bps=self.slippage_bps,
            delay_fill=self.delay_fill,
        )
        broker.set_bar_provider(bar_provider)

        brain_dir = self.brain_dir or tempfile.mkdtemp(prefix="replay_brain_")

        engine = OrganismLiveEngine(
            data_client=bar_provider,
            order_service=broker,
            positions_service=broker,
            brain_dir=brain_dir,
            universe=self.universe,
            timeframe=self.timeframe,
        )
        await engine.initialize()

        # Override clock to use bar time instead of wall time.
        # V5 Wave-17b (2026-05-03): extend the override to the auxiliary
        # components that also hold their own clocks. V4 R-F-4 / V5
        # U-RF4 + Track U found that injecting only into the engine
        # left RegimeDetector, GovernanceController, etc. reading wall
        # clock — the replay's `regime_state.timestamp` came back with
        # the year of the deploy, not the replay window. The engine
        # owns these collaborators, so monkey-patch their `_now_fn`
        # post-init.
        _replay_now = lambda: bar_provider.current_simulated_datetime
        _replay_time = lambda: bar_provider.current_simulated_time
        engine._time_fn = _replay_time
        engine._now_fn = _replay_now
        # V5 Wave-19 (2026-05-03): extend clock injection to remaining
        # auxiliary components.
        for _attr in (
            "regime_detector",
            "governance",
            "promotion_controller",
            "learner",
        ):
            _comp = getattr(engine, _attr, None)
            if _comp is not None and hasattr(_comp, "_now_fn"):
                _comp._now_fn = _replay_now

        # Disable MarketScanner — don't hit real APIs during replay
        engine.market_scanner = None

        # Relax entry throttle for learning (production default is 3)
        engine._MAX_ENTRIES_PER_HOUR = self.max_entries_per_hour

        result = ReplayResult()
        tick_count = 0

        while bar_provider.advance():
            if max_ticks is not None and tick_count >= max_ticks:
                break

            # Update broker prices from bar provider
            for sym in self.universe:
                price = bar_provider.current_price(sym)
                if price > 0:
                    broker.set_price(sym, price)

            try:
                tick_result = await engine.live_tick()
                result.tick_results.append(tick_result.to_dict())
                result.regime_history.append(tick_result.regime)
                result.signals_log.append({
                    "tick": tick_count,
                    "signals": tick_result.signals_generated,
                    "orders": tick_result.orders_submitted,
                    "exits": tick_result.trades_closed,
                })
            except Exception as e:
                logger.warning("Tick %d failed: %s", tick_count, e)
                result.tick_results.append({"tick": tick_count, "error": str(e)})

            # Record equity
            equity = await broker.get_total_portfolio_value()
            result.equity_curve.append(equity)

            tick_count += 1

        await engine.shutdown()

        result.ticks = tick_count
        result.trades = list(broker.trade_log)

        return result

    @classmethod
    async def from_alpaca(
        cls,
        symbols: list[str],
        start: str,
        end: str,
        timeframe: str = "1Min",
        initial_cash: float = 100_000,
        slippage_bps: float = 5,
        lookback: int | None = None,
    ) -> ReplayEngine:
        """Fetch bars from Alpaca API and create a replay engine."""
        from backend.data.alpaca_client import AlpacaClient

        api_key = os.environ.get("ALPACA_API_KEY_ID", "") or os.environ.get("ALPACA_API_KEY", "")
        secret_key = os.environ.get("ALPACA_API_SECRET_KEY", "") or os.environ.get("ALPACA_SECRET_KEY", "")
        if not api_key or not secret_key:
            raise ValueError(
                "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY must be set in environment"
            )
        client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)
        bars_by_symbol: dict[str, pd.DataFrame] = {}

        for sym in symbols:
            try:
                df = client.get_historical_data(
                    sym, timeframe=timeframe, start=start, end=end,
                    limit=10_000,
                )
                if df is not None and not df.empty:
                    # Normalize columns
                    col_map = {"Open": "open", "High": "high", "Low": "low",
                               "Close": "close", "Volume": "volume"}
                    df = df.rename(columns=col_map)
                    bars_by_symbol[sym] = df
                    logger.info("Loaded %d bars for %s", len(df), sym)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", sym, e)

        if not bars_by_symbol:
            raise ValueError("No bars loaded for any symbol")

        return cls(
            bars_by_symbol=bars_by_symbol,
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            universe=symbols,
            timeframe=timeframe,
            lookback=lookback,
        )

    @classmethod
    def from_csv(cls, path: str, **kwargs: Any) -> ReplayEngine:
        """Load bars from CSV files in a directory.

        Expects files named {SYMBOL}.csv with columns: open, high, low, close, volume.
        """
        bars_by_symbol: dict[str, pd.DataFrame] = {}
        csv_dir = Path(path)

        for csv_file in csv_dir.glob("*.csv"):
            symbol = csv_file.stem.upper()
            df = pd.read_csv(csv_file)
            # Normalize columns
            col_map = {"Open": "open", "High": "high", "Low": "low",
                        "Close": "close", "Volume": "volume"}
            df = df.rename(columns=col_map)
            bars_by_symbol[symbol] = df
            logger.info("Loaded %d bars for %s from CSV", len(df), symbol)

        if not bars_by_symbol:
            raise ValueError(f"No CSV files found in {path}")

        return cls(bars_by_symbol=bars_by_symbol, **kwargs)


# ═════════════════════════════════════════════════════════════════════════
#  HELPERS — Synthetic data generators (for tests)
# ═════════════════════════════════════════════════════════════════════════

def make_price_df(
    n: int = 300,
    base: float = 100.0,
    seed: int = 42,
    trend: str = "up",
) -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame with controllable trend.

    Args:
        n: Number of bars
        base: Starting price
        seed: Random seed
        trend: One of "up", "down", "chop", "crash"
    """
    rng = np.random.default_rng(seed)

    if trend == "up":
        drift = 0.001
        vol = 0.015
    elif trend == "down":
        drift = -0.001
        vol = 0.015
    elif trend == "chop":
        drift = 0.0
        vol = 0.02
    elif trend == "crash":
        drift = -0.005
        vol = 0.04
    else:
        drift = 0.0005
        vol = 0.02

    returns = rng.normal(drift, vol, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 10_000_000, n).astype(float)

    return pd.DataFrame({
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def make_features_dict(
    symbols: list[str],
    n: int = 300,
    base: float = 100.0,
    seed: int = 42,
    trend: str = "up",
) -> dict[str, pd.DataFrame]:
    """Build {symbol: DataFrame} for a universe of symbols."""
    result = {}
    for i, sym in enumerate(symbols):
        result[sym] = make_price_df(
            n=n,
            base=base + i * 10,
            seed=seed + i,
            trend=trend,
        )
    return result


# ═════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Organism Replay Simulator")
    parser.add_argument("--symbols", default="AAPL,MSFT,SPY,NVDA,GOOGL")
    parser.add_argument("--start", default="2026-02-01")
    parser.add_argument("--end", default="2026-02-25")
    parser.add_argument("--timeframe", default="1Min")
    parser.add_argument("--cash", type=float, default=100_000)
    parser.add_argument("--lookback", type=int, default=None,
                        help="Lookback bars for warmup (default: 200 daily, 500 intraday)")
    parser.add_argument("--max-ticks", type=int, default=None)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    async def main() -> None:
        engine = await ReplayEngine.from_alpaca(
            symbols=symbols,
            start=args.start,
            end=args.end,
            timeframe=args.timeframe,
            initial_cash=args.cash,
            slippage_bps=5,
            lookback=args.lookback,
        )
        result = await engine.run(max_ticks=args.max_ticks)
        print(result.summary())

    asyncio.run(main())
