"""
Living Organism Backtest Runner
================================
Runs all 5 core trading strategies through a backtest with the Living Organism
system active, demonstrating:

  1. Multi-strategy signal generation (momentum, mean_reversion, stat_arb,
     rebalancing, ensemble)
  2. Regime detection (trending / choppy / volatile)
  3. Living Policy adaptive weight mixing
  4. Regime-conditioned ensemble blending
  5. Governance kill-switch & drawdown protection
  6. Confidence calibration bucket tracking
  7. Signal conflict resolution (conviction-weighted)

Uses REAL Alpaca historical data (paper-trading keys).
"""
from __future__ import annotations

import asyncio
import os
import sys
import warnings
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

# ── project root on sys.path ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
warnings.filterwarnings("ignore")

# ── platform imports ──────────────────────────────────────────────────────
from backend.organism.governance import GovernanceController
from backend.organism.regime import (
    DriftDetector,
    RegimeConditionedEnsemble,
    RegimeDetector,
)
from backend.organism.runner import OrganismRunner
from backend.strategies.living_policy import LivingPolicyEngine

# ---------------------------------------------------------------------------
# Technical indicator helpers (standalone — no DB / broker needed)
# ---------------------------------------------------------------------------

def _rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    ag = sum(gains) / period if gains else 0
    al = sum(losses) / period if losses else 1e-10
    return 100 - 100 / (1 + ag / al)


def _sma(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def _ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p - ema) * k + ema
    return ema


def _macd(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 26:
        return 0, 0
    return _ema(prices, 12) - _ema(prices, 26), 0  # simplified signal


def _bb(prices: list[float], period: int = 20) -> tuple[float, float, float]:
    if len(prices) < period:
        p = prices[-1] if prices else 0
        return p, p, p
    r = prices[-period:]
    mid = sum(r) / period
    std = float(np.std(r))
    return mid + 2 * std, mid, mid - 2 * std


def _zscore(prices: list[float], period: int = 60) -> float:
    if len(prices) < period:
        return 0
    r = prices[-period:]
    m = sum(r) / len(r)
    s = float(np.std(r))
    return (prices[-1] - m) / s if s else 0


def _atr(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> float:
    """Average True Range."""
    if len(closes) < period + 1:
        return 0
    trs: list[float] = []
    for i in range(1, len(closes)):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period if trs else 0


# ---------------------------------------------------------------------------
# Strategy signal functions
# ---------------------------------------------------------------------------

def mean_reversion_signal(prices, params):
    if len(prices) < 20:
        return "hold", 0.0
    rsi = _rsi(prices, 14)
    upper, _, lower = _bb(prices, 20)
    cur = prices[-1]
    if cur < lower * 1.01 and rsi < params.get("oversold", 30):
        return "buy", min(0.9, (30 - rsi) / 20)
    if cur > upper * 0.99 and rsi > params.get("overbought", 70):
        return "sell", min(0.9, (rsi - 70) / 20)
    return "hold", 0.0


def momentum_signal(prices, params):
    if len(prices) < 50:
        return "hold", 0.0
    cur = prices[-1]
    macd_val, _ = _macd(prices)
    s20, s50 = _sma(prices, 20), _sma(prices, 50)
    if macd_val > 0 and cur > s20 > s50:
        return "buy", min(0.85, abs(macd_val) * 10)
    if macd_val < 0 and cur < s20 < s50:
        return "sell", min(0.85, abs(macd_val) * 10)
    return "hold", 0.0


def stat_arb_signal(prices, params):
    lb = params.get("lookback", 60)
    entry = params.get("entry_threshold", 2.0)
    if len(prices) < lb:
        return "hold", 0.0
    z = _zscore(prices, lb)
    conf = min(0.9, abs(z) / 5.0)
    if z < -entry:
        return "buy", conf
    if z > entry:
        return "sell", conf
    return "hold", 0.0


def ensemble_signal(prices, params):
    if len(prices) < 50:
        return "hold", 0.0
    cur = prices[-1]
    rsi = _rsi(prices, 14)
    macd_val, _ = _macd(prices)
    s20, s50 = _sma(prices, 20), _sma(prices, 50)
    upper, _, lower = _bb(prices, 20)

    buy_v = sell_v = 0.0
    if rsi < 35: buy_v += 0.25
    elif rsi > 65: sell_v += 0.25
    if macd_val > 0: buy_v += 0.25
    else: sell_v += 0.25
    if cur > s20 > s50: buy_v += 0.25
    elif cur < s20 < s50: sell_v += 0.25
    if cur < lower * 1.02: buy_v += 0.25
    elif cur > upper * 0.98: sell_v += 0.25

    thr = params.get("confidence_threshold", 0.6)
    if buy_v >= thr:
        return "buy", buy_v
    if sell_v >= thr:
        return "sell", sell_v
    return "hold", 0.0


def breakout_signal(prices, params):
    period = params.get("breakout_period", 20)
    if len(prices) < period + 1:
        return "hold", 0.0
    lookback = prices[-(period + 1):-1]
    cur = prices[-1]
    high = max(lookback)
    low = min(lookback)
    buffer = params.get("buffer_pct", 0.005)
    if cur > high * (1 + buffer):
        return "buy", min(0.8, (cur / high - 1) * 10)
    if cur < low * (1 - buffer):
        return "sell", min(0.8, (1 - cur / low) * 10)
    return "hold", 0.0


STRATEGIES = {
    "momentum": {"func": momentum_signal, "params": {}},
    "mean_reversion": {"func": mean_reversion_signal, "params": {}},
    "stat_arb": {"func": stat_arb_signal, "params": {"lookback": 60, "entry_threshold": 2.0}},
    "ensemble": {"func": ensemble_signal, "params": {"confidence_threshold": 0.6}},
    "breakout": {"func": breakout_signal, "params": {"breakout_period": 20}},
}

# ---------------------------------------------------------------------------
# Helper dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Position:
    entry_price: float
    quantity: int
    entry_date: date
    source: str  # which strategy triggered entry


@dataclass
class ClosedTrade:
    symbol: str
    source: str
    side: str
    qty: int
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    pnl: float
    pnl_pct: float


# ---------------------------------------------------------------------------
# Data fetching (real Alpaca)
# ---------------------------------------------------------------------------

async def fetch_alpaca_data(
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data from Alpaca for each symbol."""
    from backend.data.alpaca_client import AlpacaClient

    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not secret:
        raise RuntimeError("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY in .env")

    client = AlpacaClient(api_key=api_key, secret_key=secret, paper=True)
    result: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = client.get_historical_data(
                symbol=sym,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                timeframe="1Day",
            )
            if df is not None and not df.empty:
                result[sym] = df
                print(f"    {sym}: {len(df)} bars")
            else:
                print(f"    {sym}: no data")
        except Exception as exc:
            print(f"    {sym}: ERROR {exc}")
    return result


# ---------------------------------------------------------------------------
# Organism-integrated backtest engine
# ---------------------------------------------------------------------------

class OrganismBacktestEngine:
    """
    Day-by-day backtest that feeds every tick through the Living Organism:
      GovernanceController  →  RegimeDetector  →  RegimeConditionedEnsemble
      →  LivingPolicyEngine  →  OrganismRunner  →  Signal Generation
      →  Weighted Execution  →  P&L Attribution  →  Policy Update
    """

    def __init__(
        self,
        *,
        initial_capital: float = 100_000.0,
        position_size_pct: float = 0.08,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
    ):
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

        # Organism components
        self.governance = GovernanceController()
        self.regime_detector = RegimeDetector()
        self.ensemble = RegimeConditionedEnsemble()
        self.drift_detector = DriftDetector()
        self.runner = OrganismRunner(
            governance=self.governance,
            regime_detector=self.regime_detector,
            ensemble=self.ensemble,
            drift_detector=self.drift_detector,
        )
        self.living_policy = LivingPolicyEngine()

        # Tracking
        self.regime_history: list[dict] = []
        self.weight_history: list[dict] = []
        self.governance_events: list[str] = []

    def run(
        self,
        price_data: dict[str, pd.DataFrame],
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Execute the backtest day-by-day with organism integration."""
        symbols = list(price_data.keys())
        min_len = min(len(df) for df in price_data.values())
        warmup = 60
        if min_len <= warmup:
            raise ValueError(f"Need > {warmup} bars, got {min_len}")

        cash = self.initial_capital
        positions: dict[str, Position] = {}
        trades: list[ClosedTrade] = []
        equity_curve: list[dict] = []
        strategy_trade_counts: dict[str, int] = defaultdict(int)
        strategy_pnl: dict[str, float] = defaultdict(float)

        print(f"\n{'='*80}")
        print(f"   LIVING ORGANISM BACKTEST — {len(symbols)} symbols, "
              f"{min_len - warmup} trading days")
        print(f"{'='*80}")
        print(f"   Capital: ${self.initial_capital:,.0f}  |  "
              f"Strategies: {', '.join(STRATEGIES)}  |  "
              f"Position size: {self.position_size_pct*100:.0f}%")
        print(f"{'='*80}\n")

        prev_peak = self.initial_capital
        max_dd = 0.0
        halted_days = 0

        for day_idx in range(warmup, min_len):
            # Build per-symbol price slices & features for regime detector
            day_date = None
            features_rows = []
            symbol_prices: dict[str, list[float]] = {}
            symbol_closes: dict[str, float] = {}

            for sym in symbols:
                df = price_data[sym]
                if day_idx >= len(df):
                    continue
                row = df.iloc[day_idx]
                if day_date is None:
                    day_date = row.name if hasattr(row.name, 'date') else start_date + timedelta(days=day_idx)

                closes = df["close"].iloc[:day_idx + 1].tolist()
                highs = df["high"].iloc[:day_idx + 1].tolist()
                lows = df["low"].iloc[:day_idx + 1].tolist()
                symbol_prices[sym] = closes
                symbol_closes[sym] = closes[-1]

                sma50 = _sma(closes, 50)
                atr_val = _atr(highs, lows, closes, 14)
                atr_ratio = atr_val / closes[-1] if closes[-1] else 0

                features_rows.append({
                    "close": closes[-1],
                    "sma_50": sma50,
                    "atr_ratio": atr_ratio,
                    "volume": float(row.get("volume", 1e6)),
                })

            if not features_rows:
                continue

            features_df = pd.DataFrame(features_rows)

            # ── 1. ORGANISM PRE-EXECUTION HOOK ──────────────────────────
            base_weights = dict(self.living_policy.weights)
            pre = self.runner.pre_execution_hook(
                features_df=features_df,
                base_weights=base_weights,
                reference_features=features_df,  # self-reference for demo
            )

            regime_label = pre.get("regime", {})
            if hasattr(regime_label, "primary"):
                regime_str = regime_label.primary
            elif isinstance(regime_label, dict):
                regime_str = regime_label.get("primary", "unknown")
            else:
                regime_str = str(regime_label)

            trading_allowed = pre.get("trading_allowed", True)
            final_weights = pre.get("final_weights", base_weights)

            # Record regime
            self.regime_history.append({
                "day": day_idx - warmup,
                "date": str(day_date),
                "regime": regime_str,
            })

            if not trading_allowed:
                halted_days += 1
                if halted_days <= 3:
                    self.governance_events.append(
                        f"Day {day_idx-warmup}: HALTED ({regime_str})")
                equity_val = cash + sum(
                    symbol_closes.get(s, p.entry_price) * p.quantity
                    for s, p in positions.items()
                )
                equity_curve.append({"day": day_idx - warmup, "value": equity_val})
                continue

            # ── 2. GENERATE SIGNALS (all strategies, all symbols) ───────
            engine_signals = []
            all_raw_signals: list[dict] = []

            for strat_name, strat_info in STRATEGIES.items():
                w = final_weights.get(strat_name, 1.0)
                if w < 0.01:
                    continue  # effectively disabled

                for sym in symbols:
                    if sym not in symbol_prices:
                        continue
                    prices = symbol_prices[sym]
                    sig, conf = strat_info["func"](prices, strat_info["params"])
                    if sig == "hold":
                        continue

                    weighted_conf = conf * w

                    # Build signal for living policy
                    signal_obj = SimpleNamespace(
                        source=strat_name,
                        symbol=sym,
                        target_exposure=1.0 if sig == "buy" else -1.0,
                        metadata={
                            "price_close": symbol_closes[sym],
                            "sma_50": _sma(prices, 50),
                            "atr_ratio": _atr(
                                price_data[sym]["high"].iloc[:day_idx+1].tolist(),
                                price_data[sym]["low"].iloc[:day_idx+1].tolist(),
                                prices, 14
                            ) / prices[-1] if prices[-1] else 0,
                        },
                    )
                    engine_signals.append(signal_obj)
                    all_raw_signals.append({
                        "source": strat_name,
                        "symbol": sym,
                        "signal": sig,
                        "raw_conf": conf,
                        "weighted_conf": weighted_conf,
                        "weight": w,
                    })

            # ── 3. CONFLICT RESOLUTION (conviction-weighted) ────────────
            # Group signals by symbol, resolve conflicts
            per_symbol: dict[str, list[dict]] = defaultdict(list)
            for s in all_raw_signals:
                per_symbol[s["symbol"]].append(s)

            resolved: list[dict] = []
            for sym, sigs in per_symbol.items():
                buys = [s for s in sigs if s["signal"] == "buy"]
                sells = [s for s in sigs if s["signal"] == "sell"]

                if buys and not sells:
                    best = max(buys, key=lambda x: x["weighted_conf"])
                    resolved.append(best)
                elif sells and not buys:
                    best = max(sells, key=lambda x: x["weighted_conf"])
                    resolved.append(best)
                elif buys and sells:
                    buy_conv = sum(s["weighted_conf"] for s in buys)
                    sell_conv = sum(s["weighted_conf"] for s in sells)
                    total = buy_conv + sell_conv
                    if total > 0 and abs(buy_conv - sell_conv) / total > 0.5:
                        winner = buys if buy_conv > sell_conv else sells
                        resolved.append(max(winner, key=lambda x: x["weighted_conf"]))
                    # else: ambiguous → HOLD (skip)

            # ── 4. EXECUTE RESOLVED SIGNALS ─────────────────────────────
            for sig in resolved:
                sym = sig["symbol"]
                direction = sig["signal"]
                source = sig["source"]
                cur_price = symbol_closes[sym]

                # EXIT existing position
                if sym in positions:
                    pos = positions[sym]
                    pnl_pct = (cur_price - pos.entry_price) / pos.entry_price

                    should_exit = False
                    if pnl_pct <= -self.stop_loss_pct:
                        should_exit = True
                    elif pnl_pct >= self.take_profit_pct:
                        should_exit = True
                    elif direction == "sell":
                        should_exit = True

                    if should_exit:
                        pnl = (cur_price - pos.entry_price) * pos.quantity
                        cash += cur_price * pos.quantity
                        trades.append(ClosedTrade(
                            symbol=sym, source=pos.source, side="long",
                            qty=pos.quantity,
                            entry_date=pos.entry_date,
                            entry_price=pos.entry_price,
                            exit_date=day_date, exit_price=cur_price,
                            pnl=pnl, pnl_pct=pnl_pct * 100,
                        ))
                        strategy_trade_counts[pos.source] += 1
                        strategy_pnl[pos.source] += pnl
                        del positions[sym]

                # ENTER new position
                if sym not in positions and direction == "buy":
                    alloc = cash * self.position_size_pct
                    if alloc > 500:
                        qty = int(alloc / cur_price)
                        if qty > 0:
                            cash -= qty * cur_price
                            positions[sym] = Position(
                                entry_price=cur_price,
                                quantity=qty,
                                entry_date=day_date,
                                source=source,
                            )

            # ── 5. MARK-TO-MARKET ──────────────────────────────────────
            pos_value = sum(
                symbol_closes.get(s, p.entry_price) * p.quantity
                for s, p in positions.items()
            )
            total_value = cash + pos_value
            equity_curve.append({"day": day_idx - warmup, "value": total_value})

            if total_value > prev_peak:
                prev_peak = total_value
            dd = (prev_peak - total_value) / prev_peak
            if dd > max_dd:
                max_dd = dd

            # ── 6. ORGANISM POST-EXECUTION HOOK ────────────────────────
            post = self.runner.post_execution_hook(live_metrics={"drawdown": dd})

            # ── 7. LIVING POLICY UPDATE ─────────────────────────────────
            if engine_signals:
                try:
                    snapshot = self.living_policy.observe_signals(
                        engine_signals=engine_signals,
                        breakout_candidates=[],
                    )
                except Exception:
                    pass  # non-fatal for backtest

            # Record weight history periodically
            if (day_idx - warmup) % 20 == 0:
                self.weight_history.append({
                    "day": day_idx - warmup,
                    "date": str(day_date),
                    "regime": regime_str,
                    **{f"w_{k}": round(v, 3) for k, v in self.living_policy.weights.items()},
                })

            # Progress indicator
            progress = (day_idx - warmup) / (min_len - warmup) * 100
            if (day_idx - warmup) % 50 == 0 and day_idx > warmup:
                print(f"    Day {day_idx-warmup:>4d} | "
                      f"${total_value:>12,.2f} | "
                      f"Regime: {regime_str:<15s} | "
                      f"DD: {dd*100:>5.2f}% | "
                      f"Trades: {len(trades):>3d} | "
                      f"Progress: {progress:>5.1f}%")

        # ── CLOSE REMAINING POSITIONS ──────────────────────────────────
        for sym, pos in list(positions.items()):
            cur = symbol_closes.get(sym, pos.entry_price)
            pnl = (cur - pos.entry_price) * pos.quantity
            pnl_pct = (cur - pos.entry_price) / pos.entry_price
            trades.append(ClosedTrade(
                symbol=sym, source=pos.source, side="long",
                qty=pos.quantity, entry_date=pos.entry_date,
                entry_price=pos.entry_price, exit_date=day_date,
                exit_price=cur, pnl=pnl, pnl_pct=pnl_pct * 100,
            ))
            strategy_trade_counts[pos.source] += 1
            strategy_pnl[pos.source] += pnl
            cash += cur * pos.quantity
        positions.clear()

        # ── COMPUTE METRICS ────────────────────────────────────────────
        final_value = cash
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        trading_days = len(equity_curve)
        years = trading_days / 252 if trading_days else 1
        annual_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

        # Sharpe
        if len(equity_curve) > 1:
            vals = [e["value"] for e in equity_curve]
            rets = [(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals))]
            sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) else 0
        else:
            sharpe = 0

        # Sortino
        if len(equity_curve) > 1:
            down = [r for r in rets if r < 0]
            down_std = np.std(down) if down else 1e-10
            sortino = (np.mean(rets) / down_std) * np.sqrt(252)
        else:
            sortino = 0

        # Win rate
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

        # Regime breakdown
        regime_counts: dict[str, int] = defaultdict(int)
        for r in self.regime_history:
            regime_counts[r["regime"]] += 1

        return {
            "metrics": {
                "final_value": final_value,
                "total_return": total_return,
                "annualized_return": annual_return,
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "max_drawdown": max_dd * 100,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "total_trades": len(trades),
                "avg_trade_pnl": sum(t.pnl for t in trades) / len(trades) if trades else 0,
                "trading_days": trading_days,
                "halted_days": halted_days,
            },
            "per_strategy": {
                name: {
                    "trades": strategy_trade_counts.get(name, 0),
                    "pnl": strategy_pnl.get(name, 0),
                }
                for name in STRATEGIES
            },
            "regime_breakdown": dict(regime_counts),
            "weight_evolution": self.weight_history,
            "final_weights": dict(self.living_policy.weights),
            "governance": {
                "halted_days": halted_days,
                "events": self.governance_events,
            },
            "trades": trades,
            "equity_curve": equity_curve,
        }


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(result: dict[str, Any]) -> None:
    m = result["metrics"]

    print(f"\n{'='*80}")
    print(f"   LIVING ORGANISM BACKTEST RESULTS")
    print(f"{'='*80}")

    print(f"\n   PERFORMANCE METRICS")
    print(f"   {'─'*40}")
    print(f"   Final Portfolio Value:  ${m['final_value']:>14,.2f}")
    print(f"   Total Return:           {m['total_return']:>+13.2f}%")
    print(f"   Annualized Return:      {m['annualized_return']:>+13.2f}%")
    print(f"   Sharpe Ratio:           {m['sharpe_ratio']:>13.2f}")
    print(f"   Sortino Ratio:          {m['sortino_ratio']:>13.2f}")
    print(f"   Max Drawdown:           {m['max_drawdown']:>13.2f}%")
    print(f"   Win Rate:               {m['win_rate']:>13.1f}%")
    print(f"   Profit Factor:          {m['profit_factor']:>13.2f}")
    print(f"   Total Trades:           {m['total_trades']:>13d}")
    print(f"   Avg Trade P&L:          ${m['avg_trade_pnl']:>13.2f}")
    print(f"   Trading Days:           {m['trading_days']:>13d}")
    print(f"   Halted Days:            {m['halted_days']:>13d}")

    print(f"\n   PER-STRATEGY ATTRIBUTION")
    print(f"   {'─'*55}")
    print(f"   {'Strategy':<20s} {'Trades':>8s} {'P&L':>14s}")
    print(f"   {'─'*55}")
    for name, data in result["per_strategy"].items():
        pnl = data["pnl"]
        print(f"   {name:<20s} {data['trades']:>8d} ${pnl:>+13,.2f}")

    print(f"\n   REGIME BREAKDOWN")
    print(f"   {'─'*40}")
    total_days = sum(result["regime_breakdown"].values())
    for regime, count in sorted(result["regime_breakdown"].items(),
                                 key=lambda x: -x[1]):
        pct = count / total_days * 100 if total_days else 0
        bar = "█" * int(pct / 2)
        print(f"   {regime:<15s} {count:>5d} days ({pct:>5.1f}%)  {bar}")

    print(f"\n   LIVING POLICY WEIGHT EVOLUTION")
    print(f"   {'─'*75}")
    wh = result["weight_evolution"]
    if wh:
        cols = [k for k in wh[0] if k.startswith("w_")]
        header = f"   {'Day':>4s} {'Regime':<15s}" + "".join(f" {c[2:]:>12s}" for c in cols)
        print(header)
        print(f"   {'─'*75}")
        for row in wh:
            line = f"   {row['day']:>4d} {row['regime']:<15s}"
            line += "".join(f" {row.get(c, 1.0):>12.3f}" for c in cols)
            print(line)

    print(f"\n   FINAL ADAPTED WEIGHTS")
    print(f"   {'─'*40}")
    for name, w in sorted(result["final_weights"].items()):
        bar = "█" * int(w * 20)
        print(f"   {name:<20s} {w:>6.3f}  {bar}")

    if result["governance"]["events"]:
        print(f"\n   GOVERNANCE EVENTS")
        print(f"   {'─'*40}")
        for evt in result["governance"]["events"][:10]:
            print(f"   {evt}")

    # Top 5 best & worst trades
    trades = result["trades"]
    if trades:
        trades_sorted = sorted(trades, key=lambda t: t.pnl, reverse=True)
        print(f"\n   TOP 5 BEST TRADES")
        print(f"   {'─'*65}")
        for t in trades_sorted[:5]:
            print(f"   {t.symbol:<6s} via {t.source:<15s}  "
                  f"${t.entry_price:>8.2f} → ${t.exit_price:>8.2f}  "
                  f"P&L: ${t.pnl:>+10,.2f} ({t.pnl_pct:>+6.1f}%)")

        print(f"\n   TOP 5 WORST TRADES")
        print(f"   {'─'*65}")
        for t in trades_sorted[-5:]:
            print(f"   {t.symbol:<6s} via {t.source:<15s}  "
                  f"${t.entry_price:>8.2f} → ${t.exit_price:>8.2f}  "
                  f"P&L: ${t.pnl:>+10,.2f} ({t.pnl_pct:>+6.1f}%)")

    print(f"\n{'='*80}")
    sharpe = m["sharpe_ratio"]
    if sharpe >= 2.0:
        verdict = "EXCELLENT — Institutional-grade risk-adjusted returns"
    elif sharpe >= 1.0:
        verdict = "STRONG — Competitive with mid-tier quant funds"
    elif sharpe >= 0.5:
        verdict = "VIABLE — Room for improvement but profitable"
    elif sharpe > 0:
        verdict = "MARGINAL — Needs optimization"
    else:
        verdict = "UNPROFITABLE — Review strategy logic"

    print(f"   VERDICT: {verdict}")
    print(f"   Sharpe {sharpe:.2f} | Return {m['total_return']:+.2f}% | "
          f"MaxDD {m['max_drawdown']:.2f}% | {m['total_trades']} trades")
    print(f"{'='*80}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 80)
    print("   LIVING ORGANISM MULTI-STRATEGY BACKTEST")
    print("   Powered by: Governance + Regime Detection + Adaptive Weights")
    print("=" * 80)

    # Configuration
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
    start_date = date(2023, 1, 1)
    end_date = date(2025, 12, 31)

    print(f"\n   Symbols:  {', '.join(symbols)}")
    print(f"   Period:   {start_date} → {end_date} ({(end_date - start_date).days} days)")
    print(f"   Capital:  $100,000")
    print(f"   Strategies: {', '.join(STRATEGIES.keys())}")

    # Fetch real data
    print(f"\n   Fetching historical data from Alpaca...")
    data = await fetch_alpaca_data(symbols, start_date, end_date)

    if not data:
        print("   ERROR: No data fetched. Check your Alpaca API keys.")
        return

    loaded_symbols = list(data.keys())
    print(f"\n   Loaded {len(loaded_symbols)} symbols: {', '.join(loaded_symbols)}")

    # Run organism backtest
    engine = OrganismBacktestEngine(
        initial_capital=100_000.0,
        position_size_pct=0.08,
        stop_loss_pct=0.05,
        take_profit_pct=0.15,
    )

    result = engine.run(data, start_date, end_date)

    # Print report
    print_report(result)

    # Save equity curve to CSV
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    eq_df = pd.DataFrame(result["equity_curve"])
    eq_path = out_dir / "organism_backtest_equity.csv"
    eq_df.to_csv(eq_path, index=False)
    print(f"   Equity curve saved to: {eq_path}")

    # Save trades to CSV
    if result["trades"]:
        trades_data = [
            {
                "symbol": t.symbol, "source": t.source, "side": t.side,
                "qty": t.qty, "entry_date": t.entry_date,
                "entry_price": t.entry_price, "exit_date": t.exit_date,
                "exit_price": t.exit_price, "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
            }
            for t in result["trades"]
        ]
        trades_df = pd.DataFrame(trades_data)
        trades_path = out_dir / "organism_backtest_trades.csv"
        trades_df.to_csv(trades_path, index=False)
        print(f"   Trade log saved to:    {trades_path}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
