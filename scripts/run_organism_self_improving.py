#!/usr/bin/env python3
"""
Self-Improving Living Organism Backtest
=======================================

This is the REAL organism loop — the one that goes back, learns from its
results, and improves itself across generations.

Architecture (mirrors production nightly scheduler):
┌──────────────────────────────────────────────────────────────────┐
│                    EPOCH LOOP (slow brain)                       │
│                                                                  │
│  For each epoch (60 trading days):                               │
│    1. TRADE with current weights (fast brain per-day loop)       │
│    2. ATTRIBUTE — compute fill-based P&L per strategy            │
│    3. PRODUCE CANDIDATE — new weights from attribution rewards   │
│    4. WALK-FORWARD EVALUATE — OOS acceptance gates               │
│    5. PROMOTE or REJECT — adopt new weights or keep current      │
│    6. DRIFT CHECK — detect feature distribution shift            │
│                                                                  │
│  This IS the living organism: it literally trains itself on      │
│  its own trading results and evolves better weights each epoch.  │
└──────────────────────────────────────────────────────────────────┘

Output:
  - Per-epoch metrics showing improvement (or not)
  - Weight evolution across generations
  - Final vs initial performance comparison
  - reports/organism_evolution_*.csv
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Suppress noisy logs during backtest
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ALPACA_PAPER", "true")

from dotenv import load_dotenv
load_dotenv()


# ═══════════════════════════════════════════════════════════════════
# Data classes for tracking
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """A single executed trade."""
    date: str
    symbol: str
    strategy_source: str
    side: str  # 'buy' or 'sell'
    qty: float
    price: float
    conviction: float
    pnl: float = 0.0  # realized when position closes


@dataclass
class StrategyAttribution:
    """Per-strategy P&L attribution for an epoch."""
    source: str
    total_pnl: float = 0.0
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    total_turnover: float = 0.0
    daily_returns: list[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trade_count if self.trade_count > 0 else 0.0

    @property
    def sharpe(self) -> float:
        if len(self.daily_returns) < 2:
            return 0.0
        mean = np.mean(self.daily_returns)
        std = np.std(self.daily_returns, ddof=1)
        return float(mean / std * math.sqrt(252)) if std > 0 else 0.0


@dataclass
class EpochResult:
    """Results of one training epoch."""
    epoch: int
    generation: int  # increments only when new weights are accepted
    start_date: str
    end_date: str
    weights_used: dict[str, float]
    weights_produced: dict[str, float] | None
    accepted: bool
    rejection_reasons: list[str]
    # Performance
    total_return_pct: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_count: int = 0
    win_rate: float = 0.0
    per_strategy: dict[str, dict] = field(default_factory=dict)
    # Attribution rewards
    reward_signals: dict[str, float] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Signal generators (same as before — pure functions)
# ═══════════════════════════════════════════════════════════════════

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators."""
    d = df.copy()
    d["sma_20"] = d["close"].rolling(20).mean()
    d["sma_50"] = d["close"].rolling(50).mean()
    d["ema_12"] = d["close"].ewm(span=12).mean()
    d["ema_26"] = d["close"].ewm(span=26).mean()
    d["macd"] = d["ema_12"] - d["ema_26"]
    d["macd_signal"] = d["macd"].ewm(span=9).mean()
    d["rsi_14"] = _rsi(d["close"], 14)
    d["bb_mid"] = d["close"].rolling(20).mean()
    d["bb_std"] = d["close"].rolling(20).std()
    d["bb_upper"] = d["bb_mid"] + 2 * d["bb_std"]
    d["bb_lower"] = d["bb_mid"] - 2 * d["bb_std"]
    d["atr_14"] = _atr(d, 14)
    d["vol_ratio"] = d["volume"] / d["volume"].rolling(20).mean()
    d["ret_1d"] = d["close"].pct_change()
    d["ret_5d"] = d["close"].pct_change(5)
    return d


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def signal_momentum(row: pd.Series) -> tuple[float, float]:
    """Trend-following. Returns (direction, conviction)."""
    direction = 0.0
    conviction = 0.0
    if pd.isna(row.get("sma_20")) or pd.isna(row.get("sma_50")):
        return 0.0, 0.0
    if row["sma_20"] > row["sma_50"] and row["macd"] > row["macd_signal"]:
        direction = 1.0
        conviction = min(abs(row["macd"] - row["macd_signal"]) / (abs(row["close"]) * 0.01 + 1e-9), 1.0)
    elif row["sma_20"] < row["sma_50"] and row["macd"] < row["macd_signal"]:
        direction = -1.0
        conviction = min(abs(row["macd"] - row["macd_signal"]) / (abs(row["close"]) * 0.01 + 1e-9), 1.0)
    return direction, conviction


def signal_mean_reversion(row: pd.Series) -> tuple[float, float]:
    """Mean reversion from Bollinger Bands + RSI. Returns (direction, conviction)."""
    if pd.isna(row.get("bb_lower")) or pd.isna(row.get("rsi_14")):
        return 0.0, 0.0
    rsi = row["rsi_14"]
    close = row["close"]
    direction = 0.0
    conviction = 0.0
    if close < row["bb_lower"] and rsi < 30:
        direction = 1.0
        conviction = min((30.0 - rsi) / 30.0, 1.0) * 0.8
    elif close > row["bb_upper"] and rsi > 70:
        direction = -1.0
        conviction = min((rsi - 70.0) / 30.0, 1.0) * 0.8
    return direction, conviction


def signal_stat_arb(row: pd.Series) -> tuple[float, float]:
    """Statistical arbitrage — z-score based. Returns (direction, conviction)."""
    if pd.isna(row.get("bb_mid")) or pd.isna(row.get("bb_std")) or row.get("bb_std", 0) == 0:
        return 0.0, 0.0
    z = (row["close"] - row["bb_mid"]) / (row["bb_std"] + 1e-10)
    direction = 0.0
    conviction = 0.0
    if z < -2.0:
        direction = 1.0
        conviction = min(abs(z) / 3.0, 1.0)
    elif z > 2.0:
        direction = -1.0
        conviction = min(abs(z) / 3.0, 1.0)
    return direction, conviction


def signal_breakout(row: pd.Series) -> tuple[float, float]:
    """Breakout detection — ATR and volume spike. Returns (direction, conviction)."""
    if pd.isna(row.get("atr_14")) or pd.isna(row.get("vol_ratio")):
        return 0.0, 0.0
    vol_spike = row["vol_ratio"] > 1.5
    atr = row["atr_14"]
    ret = row.get("ret_1d", 0.0)
    if pd.isna(ret):
        return 0.0, 0.0

    direction = 0.0
    conviction = 0.0
    if vol_spike and abs(ret) > atr / row["close"] and ret > 0:
        direction = 1.0
        conviction = min(row["vol_ratio"] / 3.0, 1.0) * 0.7
    elif vol_spike and abs(ret) > atr / row["close"] and ret < 0:
        direction = -1.0
        conviction = min(row["vol_ratio"] / 3.0, 1.0) * 0.7
    return direction, conviction


def signal_ensemble(row: pd.Series) -> tuple[float, float]:
    """Meta-ensemble: majority vote of other signals. Returns (direction, conviction)."""
    signals = [
        signal_momentum(row),
        signal_mean_reversion(row),
        signal_stat_arb(row),
        signal_breakout(row),
    ]
    directions = [s[0] for s in signals if s[0] != 0.0]
    if not directions:
        return 0.0, 0.0
    avg_dir = sum(directions) / len(directions)
    avg_conv = sum(s[1] for s in signals if s[0] != 0.0) / len(directions)
    direction = 1.0 if avg_dir > 0.2 else (-1.0 if avg_dir < -0.2 else 0.0)
    return direction, avg_conv * 0.9


STRATEGY_SIGNALS = {
    "momentum": signal_momentum,
    "mean_reversion": signal_mean_reversion,
    "stat_arb": signal_stat_arb,
    "breakout": signal_breakout,
    "ensemble": signal_ensemble,
}


# ═══════════════════════════════════════════════════════════════════
# Attribution engine (mirrors backend/organism/attribution.py)
# ═══════════════════════════════════════════════════════════════════

class BacktestAttributionEngine:
    """Compute fill-based P&L attribution per strategy from trade records.

    This mirrors AttributionService._compute_reward_signals() exactly.
    """

    def compute(
        self, trades: list[TradeRecord], daily_equity: list[float]
    ) -> tuple[dict[str, StrategyAttribution], dict[str, float]]:
        """Returns (per_strategy_attribution, reward_signals)."""
        attrs: dict[str, StrategyAttribution] = {}

        # Group trades by strategy
        by_strategy: dict[str, list[TradeRecord]] = defaultdict(list)
        for t in trades:
            by_strategy[t.strategy_source].append(t)

        # Compute per-strategy metrics
        for source, strades in by_strategy.items():
            attr = StrategyAttribution(source=source)
            for t in strades:
                attr.trade_count += 1
                attr.total_pnl += t.pnl
                attr.total_turnover += abs(t.qty * t.price)
                if t.pnl > 0:
                    attr.wins += 1
                elif t.pnl < 0:
                    attr.losses += 1
                if t.pnl != 0:
                    attr.daily_returns.append(t.pnl)
            attrs[source] = attr

        # Compute reward signals (exact formula from AttributionService)
        rewards: dict[str, float] = {}
        for src, attr in attrs.items():
            if attr.trade_count == 0:
                rewards[src] = 0.0
                continue
            pnl_per_turnover = attr.total_pnl / max(attr.total_turnover, 1.0)
            slippage_penalty = 0.05  # 5 bps simulated
            turnover_penalty = min(attr.total_turnover / 100_000.0, 0.1)
            raw = pnl_per_turnover * 100 - slippage_penalty - turnover_penalty
            rewards[src] = max(-1.0, min(1.0, raw))

        return attrs, rewards


# ═══════════════════════════════════════════════════════════════════
# Weight producer (mirrors TrainingOrchestrator._produce_candidate)
# ═══════════════════════════════════════════════════════════════════

class WeightProducer:
    """Produce new candidate weights from attribution rewards.

    Formula: new_w = current_w * (1 + alpha * reward)
    Then normalize to mean=1.0, clamp to [0.10, 2.50].
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha

    def produce(
        self,
        current_weights: dict[str, float],
        reward_signals: dict[str, float],
    ) -> dict[str, float]:
        all_sources = set(current_weights.keys()) | set(reward_signals.keys())
        raw: dict[str, float] = {}
        for src in all_sources:
            cw = current_weights.get(src, 1.0)
            reward = reward_signals.get(src, 0.0)
            raw[src] = cw * (1.0 + self.alpha * reward)

        # Normalize to mean = 1.0
        mean_w = sum(raw.values()) / len(raw) if raw else 1.0
        if mean_w > 0:
            weights = {k: v / mean_w for k, v in raw.items()}
        else:
            weights = {k: 1.0 for k in raw}

        # Clamp
        weights = {k: max(0.10, min(2.50, v)) for k, v in weights.items()}
        return weights


# ═══════════════════════════════════════════════════════════════════
# Walk-forward evaluator (mirrors backend/organism/walk_forward.py)
# ═══════════════════════════════════════════════════════════════════

class BacktestWalkForward:
    """Miniature walk-forward evaluation on recent data.

    Runs the candidate weights on a held-out window and checks
    acceptance gates: Sharpe ≥ 0.3, DD ≤ 15%, improvement ≥ 5%.
    """

    def __init__(
        self,
        min_sharpe: float = 0.3,
        max_drawdown: float = 0.15,
        min_improvement: float = 0.05,
    ):
        self.min_sharpe = min_sharpe
        self.max_drawdown = max_drawdown
        self.min_improvement = min_improvement

    def evaluate(
        self,
        price_data: dict[str, pd.DataFrame],
        candidate_weights: dict[str, float],
        baseline_weights: dict[str, float],
        eval_days: int = 20,
    ) -> tuple[bool, list[str], dict[str, float]]:
        """Returns (accepted, rejection_reasons, metrics)."""
        # Run both candidate and baseline on eval window
        candidate_metrics = self._simulate(price_data, candidate_weights, eval_days)
        baseline_metrics = self._simulate(price_data, baseline_weights, eval_days)

        reasons: list[str] = []

        if candidate_metrics["sharpe"] < self.min_sharpe:
            reasons.append(f"Sharpe {candidate_metrics['sharpe']:.3f} < min {self.min_sharpe}")

        if candidate_metrics["max_dd"] > self.max_drawdown:
            reasons.append(f"MaxDD {candidate_metrics['max_dd']:.3%} > limit {self.max_drawdown:.0%}")

        # Must improve over baseline
        if baseline_metrics["sharpe"] > 0:
            improvement = (candidate_metrics["sharpe"] - baseline_metrics["sharpe"]) / abs(baseline_metrics["sharpe"])
        else:
            improvement = candidate_metrics["sharpe"] - baseline_metrics["sharpe"]

        if improvement < self.min_improvement:
            reasons.append(
                f"Improvement {improvement:.2%} < min {self.min_improvement:.0%} "
                f"(candidate Sharpe {candidate_metrics['sharpe']:.3f} vs baseline {baseline_metrics['sharpe']:.3f})"
            )

        accepted = len(reasons) == 0
        return accepted, reasons, {
            "candidate_sharpe": candidate_metrics["sharpe"],
            "candidate_return": candidate_metrics["total_return"],
            "baseline_sharpe": baseline_metrics["sharpe"],
            "baseline_return": baseline_metrics["total_return"],
            "improvement": improvement,
        }

    def _simulate(
        self,
        price_data: dict[str, pd.DataFrame],
        weights: dict[str, float],
        eval_days: int,
    ) -> dict[str, float]:
        """Run a quick simulation with the given weights on the last eval_days.

        Uses at least 60 bars of lookback for indicator warmup, then
        evaluates signals on the final eval_days bars.
        """
        daily_returns: list[float] = []
        lookback = 60  # Warmup bars for indicators

        for symbol, df in price_data.items():
            if len(df) < eval_days + lookback:
                continue
            # Take the tail for evaluation (with lookback for indicator warmup)
            window_df = df.iloc[-(eval_days + lookback):].copy()
            indicators = _compute_indicators(window_df)

            # Only evaluate signals on the last eval_days bars
            eval_start = len(indicators) - eval_days - 1
            if eval_start < 0:
                eval_start = 0

            for i in range(max(eval_start, lookback), len(indicators) - 1):
                row = indicators.iloc[i]
                next_close = indicators.iloc[i + 1]["close"]

                if pd.isna(row.get("close")) or row["close"] <= 0:
                    continue
                if pd.isna(next_close) or next_close <= 0:
                    continue

                bar_return = (next_close - row["close"]) / row["close"]
                weighted_signal = 0.0
                total_w = 0.0

                for name, sig_fn in STRATEGY_SIGNALS.items():
                    w = weights.get(name, 1.0)
                    direction, conviction = sig_fn(row)
                    weighted_signal += w * direction * conviction
                    total_w += w

                if total_w > 0:
                    position = max(-1.0, min(1.0, weighted_signal / total_w))
                else:
                    position = 0.0

                daily_returns.append(position * bar_return)

        if not daily_returns:
            return {"sharpe": 0.0, "total_return": 0.0, "max_dd": 0.0}

        mean = np.mean(daily_returns)
        std = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 1.0
        sharpe = float(mean / std * math.sqrt(252)) if std > 0 else 0.0
        total_ret = float(np.sum(daily_returns))

        cum = np.cumsum(daily_returns)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

        return {"sharpe": sharpe, "total_return": total_ret, "max_dd": max_dd}


# ═══════════════════════════════════════════════════════════════════
# Drift detector (mirrors backend/organism/regime.py DriftDetector)
# ═══════════════════════════════════════════════════════════════════

class BacktestDriftDetector:
    """PSI-based feature distribution drift between epochs."""

    PSI_THRESHOLD = 0.25

    def check_drift(
        self, ref_features: pd.DataFrame, cur_features: pd.DataFrame
    ) -> tuple[bool, float]:
        """Returns (drifted, mean_psi)."""
        psi_scores: list[float] = []
        numeric_cols = ref_features.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            ref = ref_features[col].dropna().values
            cur = cur_features[col].dropna().values
            if len(ref) < 10 or len(cur) < 10:
                continue
            psi = self._psi(ref, cur)
            psi_scores.append(psi)

        mean_psi = float(np.mean(psi_scores)) if psi_scores else 0.0
        return mean_psi > self.PSI_THRESHOLD, mean_psi

    @staticmethod
    def _psi(ref: np.ndarray, cur: np.ndarray, bins: int = 10) -> float:
        """Population Stability Index."""
        breakpoints = np.percentile(ref, np.linspace(0, 100, bins + 1))
        breakpoints = np.unique(breakpoints)
        if len(breakpoints) < 2:
            return 0.0
        ref_counts = np.histogram(ref, bins=breakpoints)[0] + 1
        cur_counts = np.histogram(cur, bins=breakpoints)[0] + 1
        ref_pct = ref_counts / ref_counts.sum()
        cur_pct = cur_counts / cur_counts.sum()
        return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


# ═══════════════════════════════════════════════════════════════════
# The self-improving organism engine
# ═══════════════════════════════════════════════════════════════════

class SelfImprovingOrganism:
    """The real organism loop: trade → attribute → learn → retrain → repeat.

    Each epoch:
    1. Trade using current weights (with per-day LivingPolicy fine-tuning)
    2. Run attribution on trades to get reward signals
    3. Produce candidate weights from rewards
    4. Walk-forward evaluate candidate vs baseline
    5. If accepted → adopt new weights (new generation!)
    6. If rejected → keep current weights
    7. Check for feature drift
    """

    STRATEGIES = list(STRATEGY_SIGNALS.keys())
    INITIAL_CAPITAL = 100_000.0
    POSITION_SIZE_PCT = 0.10  # 10% per position
    SLIPPAGE_BPS = 5.0
    STOP_LOSS_PCT = 0.05
    TAKE_PROFIT_PCT = 0.15

    def __init__(
        self,
        price_data: dict[str, pd.DataFrame],
        epoch_days: int = 60,
        training_alpha: float = 0.3,
        living_policy_alpha: float = 0.15,
    ):
        self.price_data = price_data
        self.epoch_days = epoch_days

        # Core components
        self.attribution = BacktestAttributionEngine()
        self.weight_producer = WeightProducer(alpha=training_alpha)
        self.walk_forward = BacktestWalkForward()
        self.drift_detector = BacktestDriftDetector()

        # State
        self.current_weights = {s: 1.0 for s in self.STRATEGIES}
        self.generation = 1
        self.capital = self.INITIAL_CAPITAL
        self.equity_curve: list[dict] = []
        self.all_trades: list[TradeRecord] = []
        self.epoch_results: list[EpochResult] = []
        self.weight_history: list[dict] = []

        # Living policy state (online learning within epoch)
        self._lp_alpha = living_policy_alpha
        self._lp_scores: dict[str, float] = {s: 0.0 for s in self.STRATEGIES}
        self._lp_weights: dict[str, float] = {s: 1.0 for s in self.STRATEGIES}

        # Positions
        self._positions: dict[str, dict] = {}  # symbol -> {qty, cost, strategy, entry_date}

    def run(self) -> list[EpochResult]:
        """Run the full self-improving loop across all data."""
        # Build unified date index
        all_dates = self._build_date_index()
        n_epochs = len(all_dates) // self.epoch_days
        if n_epochs < 2:
            print("ERROR: Not enough data for epoch-based training")
            return []

        print(f"\n{'='*70}")
        print(f"  SELF-IMPROVING LIVING ORGANISM BACKTEST")
        print(f"  {len(all_dates)} trading days → {n_epochs} epochs × {self.epoch_days} days")
        print(f"  Symbols: {', '.join(sorted(self.price_data.keys()))}")
        print(f"  Initial capital: ${self.INITIAL_CAPITAL:,.0f}")
        print(f"  Training alpha: {self.weight_producer.alpha}")
        print(f"  Acceptance gates: Sharpe≥0.3, DD≤15%, Improvement≥5%")
        print(f"{'='*70}\n")

        # Prepare per-symbol indicator DataFrames
        symbol_indicators: dict[str, pd.DataFrame] = {}
        for sym, df in self.price_data.items():
            symbol_indicators[sym] = _compute_indicators(df)

        ref_features: pd.DataFrame | None = None  # for drift detection

        for epoch_idx in range(n_epochs):
            epoch_start = epoch_idx * self.epoch_days
            epoch_end = min(epoch_start + self.epoch_days, len(all_dates))
            epoch_dates = all_dates[epoch_start:epoch_end]

            if len(epoch_dates) < 10:
                break

            print(f"━━━ EPOCH {epoch_idx + 1}/{n_epochs} | Generation {self.generation} "
                  f"| {epoch_dates[0]} → {epoch_dates[-1]} ━━━")

            # Record weights at epoch start
            self.weight_history.append({
                "epoch": epoch_idx + 1,
                "generation": self.generation,
                **self.current_weights,
            })

            # ── 1. TRADE with current weights ──
            epoch_trades, epoch_daily_equity, epoch_features = self._trade_epoch(
                symbol_indicators, epoch_dates, all_dates
            )
            self.all_trades.extend(epoch_trades)

            # ── 2. ATTRIBUTE — compute P&L per strategy ──
            per_strategy, reward_signals = self.attribution.compute(
                epoch_trades, epoch_daily_equity
            )

            # ── 3. PRODUCE CANDIDATE weights ──
            candidate_weights = self.weight_producer.produce(
                self.current_weights, reward_signals
            )

            # ── 4. WALK-FORWARD EVALUATION ──
            # Use raw price data up to this epoch end for walk-forward
            eval_data = {}
            for sym, df in self.price_data.items():
                # Take data up to the current epoch end
                end_idx = min(epoch_end + 50, len(df))
                eval_data[sym] = df.iloc[:end_idx].copy()

            accepted, reasons, wf_metrics = self.walk_forward.evaluate(
                eval_data, candidate_weights, self.current_weights, eval_days=20
            )

            # ── 5. PROMOTE or REJECT ──
            if accepted:
                old_weights = dict(self.current_weights)
                self.current_weights = candidate_weights
                self._lp_weights = dict(candidate_weights)
                self.generation += 1
                status = "✅ PROMOTED"
            else:
                status = "❌ REJECTED"

            # ── 6. DRIFT CHECK ──
            drift_detected = False
            drift_psi = 0.0
            if epoch_features is not None and ref_features is not None:
                drift_detected, drift_psi = self.drift_detector.check_drift(
                    ref_features, epoch_features
                )
            ref_features = epoch_features  # next epoch's reference

            # ── Compute epoch metrics ──
            epoch_returns = []
            if len(epoch_daily_equity) >= 2:
                for i in range(1, len(epoch_daily_equity)):
                    if epoch_daily_equity[i - 1] > 0:
                        epoch_returns.append(
                            (epoch_daily_equity[i] - epoch_daily_equity[i - 1]) / epoch_daily_equity[i - 1]
                        )

            epoch_return_pct = 0.0
            if epoch_daily_equity and epoch_daily_equity[0] > 0:
                epoch_return_pct = (epoch_daily_equity[-1] - epoch_daily_equity[0]) / epoch_daily_equity[0] * 100

            epoch_sharpe = 0.0
            if len(epoch_returns) > 1:
                mean_r = np.mean(epoch_returns)
                std_r = np.std(epoch_returns, ddof=1)
                epoch_sharpe = float(mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

            epoch_dd = 0.0
            if epoch_daily_equity:
                cum = np.array(epoch_daily_equity)
                peak = np.maximum.accumulate(cum)
                dd_pct = (peak - cum) / np.where(peak > 0, peak, 1)
                epoch_dd = float(np.max(dd_pct)) * 100

            wins = sum(1 for t in epoch_trades if t.pnl > 0)
            losses = sum(1 for t in epoch_trades if t.pnl < 0)
            win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

            result = EpochResult(
                epoch=epoch_idx + 1,
                generation=self.generation,
                start_date=str(epoch_dates[0]),
                end_date=str(epoch_dates[-1]),
                weights_used=dict(self.current_weights if accepted else self.current_weights),
                weights_produced=candidate_weights,
                accepted=accepted,
                rejection_reasons=reasons,
                total_return_pct=epoch_return_pct,
                sharpe=epoch_sharpe,
                max_drawdown_pct=epoch_dd,
                trade_count=len(epoch_trades),
                win_rate=win_rate,
                per_strategy={
                    src: {
                        "pnl": attr.total_pnl,
                        "trades": attr.trade_count,
                        "win_rate": attr.win_rate,
                        "sharpe": attr.sharpe,
                    }
                    for src, attr in per_strategy.items()
                },
                reward_signals=reward_signals,
            )
            self.epoch_results.append(result)

            # ── Print epoch summary ──
            print(f"  Performance: {epoch_return_pct:+.2f}% | "
                  f"Sharpe: {epoch_sharpe:.2f} | DD: {epoch_dd:.1f}% | "
                  f"Trades: {len(epoch_trades)} | WR: {win_rate:.0%}")

            print(f"  Rewards: ", end="")
            for s in sorted(reward_signals.keys()):
                print(f"{s}={reward_signals[s]:+.3f}  ", end="")
            print()

            print(f"  Candidate weights: ", end="")
            for s in sorted(candidate_weights.keys()):
                delta = candidate_weights[s] - self.current_weights.get(s, candidate_weights[s]) if not accepted \
                    else candidate_weights[s] - 1.0
                print(f"{s}={candidate_weights[s]:.2f}  ", end="")
            print()

            if wf_metrics:
                print(f"  Walk-forward: candidate Sharpe={wf_metrics.get('candidate_sharpe', 0):.3f} "
                      f"vs baseline={wf_metrics.get('baseline_sharpe', 0):.3f} "
                      f"→ improvement={wf_metrics.get('improvement', 0):.1%}")

            print(f"  {status} (generation {self.generation})")
            if reasons:
                for r in reasons:
                    print(f"    → {r}")

            if drift_detected:
                print(f"  ⚠️  DRIFT DETECTED (PSI={drift_psi:.4f}) — feature distributions shifted")

            print(f"  Portfolio: ${self.capital:,.0f}")
            print()

        return self.epoch_results

    def _trade_epoch(
        self,
        symbol_indicators: dict[str, pd.DataFrame],
        epoch_dates: list,
        all_dates: list,
    ) -> tuple[list[TradeRecord], list[float], pd.DataFrame | None]:
        """Trade one epoch using current weights. Returns (trades, equity_curve, features)."""
        trades: list[TradeRecord] = []
        equity_curve: list[float] = [self.capital]
        features_accum: list[pd.DataFrame] = []

        for day_idx, date in enumerate(epoch_dates):
            day_pnl = 0.0
            day_features: list[pd.Series] = []

            for symbol, indicators in symbol_indicators.items():
                # Find this date's row
                sym_dates = self.price_data[symbol].get("_date", pd.Series())
                if sym_dates.empty:
                    df = self.price_data[symbol].copy()
                    df["_date"] = pd.to_datetime(df.get("timestamp", df.index)).dt.date
                    self.price_data[symbol] = df
                    sym_dates = df["_date"]

                mask = sym_dates == date
                if not mask.any():
                    continue

                row_idx = mask.idxmax()
                if row_idx >= len(indicators):
                    continue
                row = indicators.iloc[row_idx] if row_idx < len(indicators) else None
                if row is None or pd.isna(row.get("close")):
                    continue

                day_features.append(row)

                # Generate weighted signal from all strategies
                weighted_direction = 0.0
                total_weight = 0.0
                best_strategy = None
                best_conviction = 0.0
                strategy_signals: dict[str, tuple[float, float]] = {}

                for name, sig_fn in STRATEGY_SIGNALS.items():
                    w = self._lp_weights.get(name, self.current_weights.get(name, 1.0))
                    direction, conviction = sig_fn(row)
                    strategy_signals[name] = (direction, conviction)
                    weighted_direction += w * direction * conviction
                    total_weight += w
                    if conviction > best_conviction and direction != 0:
                        best_conviction = conviction
                        best_strategy = name

                if total_weight > 0:
                    net_signal = weighted_direction / total_weight
                else:
                    net_signal = 0.0

                # Position management
                pos_key = symbol
                close_price = row["close"]

                # Check existing position for stop/take profit
                if pos_key in self._positions:
                    pos = self._positions[pos_key]
                    entry_cost = pos["cost"]
                    pos_pnl_pct = (close_price - entry_cost) / entry_cost * (1 if pos["qty"] > 0 else -1)

                    should_close = False
                    close_reason = ""

                    if pos_pnl_pct <= -self.STOP_LOSS_PCT:
                        should_close = True
                        close_reason = "stop_loss"
                    elif pos_pnl_pct >= self.TAKE_PROFIT_PCT:
                        should_close = True
                        close_reason = "take_profit"
                    elif abs(net_signal) < 0.05:  # signal faded
                        should_close = True
                        close_reason = "signal_exit"
                    elif (pos["qty"] > 0 and net_signal < -0.3) or (pos["qty"] < 0 and net_signal > 0.3):
                        should_close = True
                        close_reason = "reversal"

                    if should_close:
                        realized = (close_price - entry_cost) * pos["qty"]
                        # Slippage
                        realized -= abs(pos["qty"]) * close_price * self.SLIPPAGE_BPS / 10000
                        day_pnl += realized
                        self.capital += realized

                        trade = TradeRecord(
                            date=str(date),
                            symbol=symbol,
                            strategy_source=pos["strategy"],
                            side="sell" if pos["qty"] > 0 else "buy",
                            qty=abs(pos["qty"]),
                            price=close_price,
                            conviction=pos.get("conviction", 0.5),
                            pnl=realized,
                        )
                        trades.append(trade)
                        del self._positions[pos_key]

                # Open new position if signal is strong enough
                if pos_key not in self._positions and abs(net_signal) > 0.15 and best_strategy:
                    position_value = self.capital * self.POSITION_SIZE_PCT * min(abs(net_signal), 1.0)
                    if position_value > 100 and self.capital > position_value:
                        qty = position_value / close_price
                        if net_signal < 0:
                            qty = -qty

                        # Apply slippage
                        entry_cost = close_price * (1 + self.SLIPPAGE_BPS / 10000 * (1 if qty > 0 else -1))

                        self._positions[pos_key] = {
                            "qty": qty,
                            "cost": entry_cost,
                            "strategy": best_strategy,
                            "entry_date": str(date),
                            "conviction": best_conviction,
                        }

                        trade = TradeRecord(
                            date=str(date),
                            symbol=symbol,
                            strategy_source=best_strategy,
                            side="buy" if qty > 0 else "sell",
                            qty=abs(qty),
                            price=entry_cost,
                            conviction=best_conviction,
                        )
                        trades.append(trade)

            # ── Living Policy: per-day online weight update ──
            # This is the fast brain — adjusts within the epoch
            if trades:
                recent_trades = [t for t in trades[-20:] if t.pnl != 0]
                per_strat_ret: dict[str, float] = defaultdict(float)
                per_strat_cnt: dict[str, int] = defaultdict(int)
                for t in recent_trades:
                    per_strat_ret[t.strategy_source] += t.pnl
                    per_strat_cnt[t.strategy_source] += 1

                for s in self.STRATEGIES:
                    if per_strat_cnt.get(s, 0) > 0:
                        avg_ret = per_strat_ret[s] / per_strat_cnt[s]
                        score_signal = 1.0 if avg_ret > 0 else -1.0
                        self._lp_scores[s] = (1 - self._lp_alpha) * self._lp_scores[s] + self._lp_alpha * score_signal
                        # Bounded weight update (max ±0.05 per step)
                        base = self.current_weights.get(s, 1.0)
                        target = base * (1 + 5.0 * self._lp_scores[s])
                        delta = max(-0.05, min(0.05, target - self._lp_weights[s]))
                        self._lp_weights[s] = max(0.10, min(2.50, self._lp_weights[s] + delta))

            # Mark-to-market for equity
            unrealized = 0.0
            for sym, pos in self._positions.items():
                sym_dates = self.price_data.get(sym, pd.DataFrame()).get("_date", pd.Series())
                mask = sym_dates == date if not sym_dates.empty else pd.Series(dtype=bool)
                if mask.any():
                    row_idx = mask.idxmax()
                    if row_idx < len(self.price_data[sym]):
                        cur_price = self.price_data[sym].iloc[row_idx]["close"]
                        unrealized += (cur_price - pos["cost"]) * pos["qty"]

            equity_curve.append(self.capital + unrealized)

            # Accumulate features for drift detection
            if day_features:
                features_accum.extend(day_features)

        # Build features DataFrame for drift detection
        epoch_features = None
        if features_accum:
            epoch_features = pd.DataFrame(features_accum)

        return trades, equity_curve, epoch_features

    def _build_date_index(self) -> list:
        """Build sorted unique date index across all symbols."""
        all_dates = set()
        for sym, df in self.price_data.items():
            if "_date" not in df.columns:
                df = df.copy()
                df["_date"] = pd.to_datetime(df.get("timestamp", df.index)).dt.date
                self.price_data[sym] = df
            all_dates.update(df["_date"].dropna().unique())
        return sorted(all_dates)

    def print_report(self):
        """Print the full evolution report."""
        print(f"\n{'='*70}")
        print(f"         ORGANISM EVOLUTION REPORT")
        print(f"{'='*70}\n")

        # Overall
        if self.equity_curve:
            final_equity = self.equity_curve[-1]["equity"] if isinstance(self.equity_curve[-1], dict) else self.capital
        else:
            final_equity = self.capital

        total_return = (final_equity - self.INITIAL_CAPITAL) / self.INITIAL_CAPITAL * 100
        print(f"  Initial Capital:     ${self.INITIAL_CAPITAL:>12,.0f}")
        print(f"  Final Capital:       ${self.capital:>12,.0f}")
        print(f"  Total Return:        {total_return:>+11.2f}%")
        print(f"  Final Generation:    {self.generation}")
        print(f"  Total Epochs:        {len(self.epoch_results)}")
        print(f"  Total Trades:        {len(self.all_trades)}")

        accepted_count = sum(1 for e in self.epoch_results if e.accepted)
        rejected_count = sum(1 for e in self.epoch_results if not e.accepted)
        print(f"  Candidates Accepted: {accepted_count}")
        print(f"  Candidates Rejected: {rejected_count}")
        print(f"  Acceptance Rate:     {accepted_count / len(self.epoch_results) * 100:.0f}%" if self.epoch_results else "")

        # Per-epoch evolution table
        print(f"\n{'─'*100}")
        print(f"  EPOCH-BY-EPOCH EVOLUTION")
        print(f"{'─'*100}")
        print(f"  {'Epoch':>5} {'Gen':>4} {'Return%':>8} {'Sharpe':>7} {'DD%':>6} "
              f"{'Trades':>6} {'WR%':>5} {'Status':>10} {'Dates'}")
        print(f"  {'─'*5} {'─'*4} {'─'*8} {'─'*7} {'─'*6} {'─'*6} {'─'*5} {'─'*10} {'─'*23}")

        for r in self.epoch_results:
            status = "PROMOTED" if r.accepted else "REJECTED"
            print(f"  {r.epoch:>5} {r.generation:>4} {r.total_return_pct:>+8.2f} "
                  f"{r.sharpe:>7.2f} {r.max_drawdown_pct:>6.1f} {r.trade_count:>6} "
                  f"{r.win_rate:>5.0%} {status:>10} {r.start_date}→{r.end_date}")

        # Weight evolution
        print(f"\n{'─'*80}")
        print(f"  WEIGHT EVOLUTION (organism learning)")
        print(f"{'─'*80}")
        print(f"  {'Epoch':>5} {'Gen':>4} ", end="")
        for s in sorted(self.STRATEGIES):
            print(f"  {s[:8]:>8}", end="")
        print()
        print(f"  {'─'*5} {'─'*4} ", end="")
        for _ in self.STRATEGIES:
            print(f"  {'─'*8}", end="")
        print()

        for wh in self.weight_history:
            epoch = wh["epoch"]
            gen = wh["generation"]
            print(f"  {epoch:>5} {gen:>4} ", end="")
            for s in sorted(self.STRATEGIES):
                w = wh.get(s, 1.0)
                # Color-code: above 1.0 = boosted, below = suppressed
                marker = "↑" if w > 1.05 else ("↓" if w < 0.95 else " ")
                print(f"  {w:>7.3f}{marker}", end="")
            print()

        # Per-strategy cumulative P&L
        print(f"\n{'─'*70}")
        print(f"  PER-STRATEGY CUMULATIVE P&L ATTRIBUTION")
        print(f"{'─'*70}")
        strat_pnl: dict[str, float] = defaultdict(float)
        strat_trades: dict[str, int] = defaultdict(int)
        strat_wins: dict[str, int] = defaultdict(int)
        for t in self.all_trades:
            if t.pnl != 0:
                strat_pnl[t.strategy_source] += t.pnl
                strat_trades[t.strategy_source] += 1
                if t.pnl > 0:
                    strat_wins[t.strategy_source] += 1

        print(f"  {'Strategy':<16} {'Total P&L':>12} {'Trades':>8} {'Win Rate':>9}")
        print(f"  {'─'*16} {'─'*12} {'─'*8} {'─'*9}")
        for s in sorted(strat_pnl.keys()):
            wr = strat_wins.get(s, 0) / strat_trades.get(s, 1) * 100
            print(f"  {s:<16} ${strat_pnl[s]:>11,.0f} {strat_trades.get(s, 0):>8} {wr:>8.0f}%")

        # Generation comparison
        print(f"\n{'─'*70}")
        print(f"  GENERATION COMPARISON (did it actually improve?)")
        print(f"{'─'*70}")

        gen_performance: dict[int, list[EpochResult]] = defaultdict(list)
        for r in self.epoch_results:
            gen_performance[r.generation].append(r)

        print(f"  {'Gen':>4} {'Epochs':>7} {'Avg Return%':>12} {'Avg Sharpe':>11} {'Avg DD%':>8}")
        print(f"  {'─'*4} {'─'*7} {'─'*12} {'─'*11} {'─'*8}")
        for gen in sorted(gen_performance.keys()):
            epochs = gen_performance[gen]
            avg_ret = np.mean([e.total_return_pct for e in epochs])
            avg_sharpe = np.mean([e.sharpe for e in epochs])
            avg_dd = np.mean([e.max_drawdown_pct for e in epochs])
            print(f"  {gen:>4} {len(epochs):>7} {avg_ret:>+12.2f} {avg_sharpe:>11.2f} {avg_dd:>8.1f}")

        print(f"\n{'='*70}")
        if self.generation > 1:
            first_gen = gen_performance.get(1, [])
            last_gen = gen_performance.get(max(gen_performance.keys()), [])
            if first_gen and last_gen:
                first_sharpe = np.mean([e.sharpe for e in first_gen])
                last_sharpe = np.mean([e.sharpe for e in last_gen])
                improvement = last_sharpe - first_sharpe
                print(f"  VERDICT: Organism evolved through {self.generation} generations")
                print(f"  Sharpe: {first_sharpe:.2f} (Gen 1) → {last_sharpe:.2f} (Gen {max(gen_performance.keys())})")
                if improvement > 0:
                    print(f"  ✅ SELF-IMPROVEMENT CONFIRMED: Sharpe improved by {improvement:+.2f}")
                else:
                    print(f"  ⚠️  No Sharpe improvement detected ({improvement:+.2f})")
        else:
            print(f"  Organism stayed at Generation 1 — all candidates were rejected")
            print(f"  This means the walk-forward gates protected against regression")
        print(f"{'='*70}\n")

    def save_reports(self):
        """Save CSV reports."""
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)

        # Epoch results
        rows = []
        for r in self.epoch_results:
            rows.append({
                "epoch": r.epoch,
                "generation": r.generation,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "return_pct": round(r.total_return_pct, 4),
                "sharpe": round(r.sharpe, 4),
                "max_dd_pct": round(r.max_drawdown_pct, 4),
                "trades": r.trade_count,
                "win_rate": round(r.win_rate, 4),
                "accepted": r.accepted,
                **{f"reward_{k}": round(v, 4) for k, v in r.reward_signals.items()},
            })
        pd.DataFrame(rows).to_csv(reports_dir / "organism_evolution_epochs.csv", index=False)

        # Weight evolution
        pd.DataFrame(self.weight_history).to_csv(
            reports_dir / "organism_evolution_weights.csv", index=False
        )

        # Trade log
        trade_rows = []
        for t in self.all_trades:
            trade_rows.append({
                "date": t.date,
                "symbol": t.symbol,
                "strategy": t.strategy_source,
                "side": t.side,
                "qty": round(t.qty, 4),
                "price": round(t.price, 2),
                "conviction": round(t.conviction, 4),
                "pnl": round(t.pnl, 2),
            })
        pd.DataFrame(trade_rows).to_csv(
            reports_dir / "organism_evolution_trades.csv", index=False
        )

        print(f"Reports saved to {reports_dir}/organism_evolution_*.csv")


# ═══════════════════════════════════════════════════════════════════
# Data fetching
# ═══════════════════════════════════════════════════════════════════

async def fetch_alpaca_data(
    symbols: list[str], lookback_days: int = 1000
) -> dict[str, pd.DataFrame]:
    """Fetch historical data from Alpaca."""
    from backend.data.alpaca_client import AlpacaClient

    api_key = os.environ.get("ALPACA_API_KEY_ID", "")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY", "")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() in ("1", "true", "yes")
    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=paper)
    price_data: dict[str, pd.DataFrame] = {}

    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    for symbol in symbols:
        try:
            df = client.get_historical_data(
                symbol, timeframe="1Day", start=start_date, end=end_date, limit=lookback_days
            )
            if df is not None and len(df) > 100:
                # Normalize column names to lowercase
                col_map = {"Open": "open", "High": "high", "Low": "low",
                           "Close": "close", "Volume": "volume"}
                df = df.rename(columns=col_map)
                # Ensure we have lowercase columns
                df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
                price_data[symbol] = df
                print(f"  ✓ {symbol}: {len(df)} bars")
        except Exception as e:
            print(f"  ✗ {symbol}: {e}")

    return price_data


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main():
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

    print("\n📊 Fetching market data from Alpaca...")
    price_data = await fetch_alpaca_data(symbols, lookback_days=1000)

    if not price_data:
        print("ERROR: No data fetched")
        return

    print(f"\n📈 Loaded {len(price_data)} symbols, "
          f"{sum(len(df) for df in price_data.values())} total bars\n")

    # Create and run the self-improving organism
    organism = SelfImprovingOrganism(
        price_data=price_data,
        epoch_days=60,          # 60 trading days (~3 months) per epoch
        training_alpha=0.3,     # Weight update intensity (from TrainingOrchestrator)
        living_policy_alpha=0.15,  # Per-day fine-tuning rate
    )

    organism.run()
    organism.print_report()
    organism.save_reports()


if __name__ == "__main__":
    asyncio.run(main())
