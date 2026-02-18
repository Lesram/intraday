#!/usr/bin/env python3
"""
Breakout Alpha Organism v3.0 — Master Backtest
===============================================

Complete overhaul targeting 100 %+ returns via:

    1. BREAKOUT SCANNING  — 6-detector proprietary breakout system
    2. MOMENTUM PYRAMIDING — add to winners at +1.5R & +3R
    3. ATR-DISTANCE TRAILS — let winners ride (not 1 % trailing)
    4. PARTIAL TAKE-PROFIT — sell 30 % at 3R, let 70 % run
    5. BIGGER POSITIONS    — 12 % max per position (was 5 %)
    6. EXPANDED UNIVERSE   — 50 + symbols (was 10)
    7. LONG-ONLY           — shorts were net negative, eliminated
    8. SELF-LEARNING       — XGBoost retrain + drift detection

Architecture:
┌──────────────────────────────────────────────────────────────────┐
│  PER-BAR LOOP                                                    │
│    1. Check exits           → partial TP + trailing ATR stops    │
│    2. Check pyramid adds    → add to winners at +1.5R / +3R     │
│    3. Breakout scan         → rank all symbols by breakout score │
│    4. ML predictions        → direction + confidence             │
│    5. Combine scores        → breakout × ML × alpha             │
│    6. Kelly-size w/ bonus   → bigger for high breakout scores    │
│    7. Open new positions    → long-only, pyramid-aware sizing    │
│    8. Update equity         → MTM all positions                  │
└──────────────────────────────────────────────────────────────────┘

Usage:
    python scripts/run_breakout_organism.py [--epochs N] [--symbols SYM1,SYM2,...]
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Project root ─────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ALPACA_PAPER", "true")

from dotenv import load_dotenv
load_dotenv()

# ── Import organism modules ─────────────────────────────────────
from backend.organism.ml_features import compute_ml_features, FEATURE_COLUMNS
from backend.organism.ml_signal import MLSignalGenerator, MLSignal
from backend.organism.alpha_scanner import AlphaScanner, AlphaCandidate
from backend.organism.kelly_sizer import KellySizer, PositionSize
from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels, ExitSignal
from backend.organism.continuous_learner import ContinuousLearner, TradeRecord, LearningState
from backend.organism.breakout_scanner import BreakoutScanner, BreakoutSignal
from backend.organism.pyramider import MomentumPyramider, PyramidPosition, PyramidLevel, PyramidAction
from backend.organism.brain_persistence import OrganismBrain
from backend.organism.self_evolution import (
    EvolutionEngine, EvolvedParams, apply_evolved_params,
)
from backend.organism.regime import RegimeDetector, RegimeLabel
from backend.organism.governance import GovernanceController

# ── Import broker for data ──────────────────────────────────────
from backend.data.alpaca_client import AlpacaClient


# ═════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════

# v3 expanded universe — 50+ symbols across sectors, cap ranges, beta
DEFAULT_UNIVERSE = [
    # Mega-cap tech (momentum leaders)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # High-beta semiconductors
    "AMD", "AVGO", "MRVL", "MU", "QCOM", "INTC", "ARM",
    # Software / cloud (growth)
    "CRM", "NOW", "SHOP", "SNOW", "NET", "DDOG", "CRWD", "PLTR",
    # Fintech / payments
    "SQ", "PYPL", "COIN",
    # Consumer / retail
    "COST", "WMT", "TGT", "LULU",
    # Healthcare / biotech
    "LLY", "ABBV", "MRNA", "REGN",
    # Energy / commodities
    "XOM", "CVX", "SLB",
    # Industrials / EV
    "CAT", "GE", "BA", "RIVN", "LCID",
    # ETFs (for regime detection & relative strength)
    "SPY", "QQQ", "IWM", "XLK", "XLE", "XLF",
    # High-momentum mid-caps (breakout candidates)
    "SMCI", "CAVA", "DUOL", "CELH",
]

DEFAULT_LOOKBACK = 500     # 500 bars of history
DEFAULT_EPOCHS = 5         # 5 training epochs
BARS_PER_EPOCH = 60        # 60 trading days per epoch
INITIAL_CAPITAL = 100_000  # $100k starting capital
SLIPPAGE_BPS = 5           # 5 bps slippage per trade
COMMISSION_BPS = 1         # 1 bps commission
TRAIN_WINDOW = 200         # Train on 200 bars of features
RETRAIN_INTERVAL = 60      # Retrain every 60 bars
MAX_OPEN_POSITIONS = 8     # Max concurrent positions (concentrated)
LONG_ONLY = True           # v3: eliminate shorts (net negative in v2)


# ═════════════════════════════════════════════════════════════════
# Regime Detector — uses full RegimeDetector module (Phase 1.4)
# ═════════════════════════════════════════════════════════════════

# Module-level detector (used by the helper function below)
_regime_detector = RegimeDetector()


def detect_regime(features_by_symbol: dict[str, pd.DataFrame]) -> str:
    """Detect market regime using the full RegimeDetector module.

    Uses market-level aggregation across all symbols for a robust
    regime signal instead of the previous simplified inline version.
    """
    if not features_by_symbol:
        return RegimeLabel.UNKNOWN

    state = _regime_detector.detect_market_regime(features_by_symbol)
    return state.primary


# ═════════════════════════════════════════════════════════════════
# Position Tracker (v3 — pyramid-aware)
# ═════════════════════════════════════════════════════════════════

@dataclass
class OpenPosition:
    """Tracks an open position with pyramid layer support."""
    symbol: str
    direction: float
    shares: int                    # Current total shares
    entry_price: float             # Weighted avg entry
    entry_bar: int
    exit_levels: ExitLevels
    predicted_return: float
    confidence: float
    breakout_score: float = 0.0    # v3: breakout score at entry
    notional: float = 0.0
    # Pyramid tracking
    pyramid_position: PyramidPosition | None = None
    total_cost_basis: float = 0.0  # Total $ invested across all layers
    partial_tp_shares_sold: int = 0  # Shares already sold via partial TP

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price


@dataclass
class EpochMetrics:
    """Metrics for one training epoch."""
    epoch: int = 0
    generation: int = 0
    start_bar: int = 0
    end_bar: int = 0
    total_return_pct: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    accuracy: float = 0.0
    ml_accuracy: float = 0.0
    model_accepted: bool = False
    retrain_reason: str = ""
    regime: str = "normal"
    top_features: list[str] = field(default_factory=list)
    equity_start: float = 0.0
    equity_end: float = 0.0
    # v3 additions
    breakout_trades: int = 0
    pyramid_adds: int = 0
    partial_tp_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "generation": self.generation,
            "start_bar": self.start_bar,
            "end_bar": self.end_bar,
            "total_return_pct": round(self.total_return_pct, 4),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "accuracy": round(self.accuracy, 4),
            "ml_accuracy": round(self.ml_accuracy, 4),
            "model_accepted": self.model_accepted,
            "retrain_reason": self.retrain_reason,
            "regime": self.regime,
            "top_features": self.top_features[:5],
            "equity_start": round(self.equity_start, 2),
            "equity_end": round(self.equity_end, 2),
            "breakout_trades": self.breakout_trades,
            "pyramid_adds": self.pyramid_adds,
            "partial_tp_count": self.partial_tp_count,
        }


# ═════════════════════════════════════════════════════════════════
# Data Loader
# ═════════════════════════════════════════════════════════════════

def load_data(
    symbols: list[str],
    lookback_days: int = 500,
) -> dict[str, pd.DataFrame]:
    """Load historical OHLCV data from Alpaca."""
    api_key = os.environ.get("ALPACA_API_KEY_ID", "")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY", "")

    if not api_key or not secret_key:
        print("ERROR: ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not set.")
        sys.exit(1)

    client = AlpacaClient(api_key=api_key, secret_key=secret_key, paper=True)

    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days + 100)).strftime("%Y-%m-%d")

    data: dict[str, pd.DataFrame] = {}
    failed = []
    for sym in symbols:
        try:
            df = client.get_historical_data(
                sym, timeframe="1Day", start=start_date, end=end_date,
                limit=lookback_days + 100,
            )
            if df is not None and len(df) >= 100:
                df.columns = [c.lower() for c in df.columns]
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"])
                df = df.sort_index() if isinstance(df.index, pd.DatetimeIndex) else df.sort_values(
                    "timestamp" if "timestamp" in df.columns else df.columns[0]
                )
                df = df.reset_index(drop=True)
                data[sym] = df
                print(f"  ✓ {sym}: {len(df)} bars")
            else:
                failed.append(sym)
                print(f"  ✗ {sym}: insufficient data ({len(df) if df is not None else 0} bars)")
        except Exception as e:
            failed.append(sym)
            print(f"  ✗ {sym}: {e}")

    if failed:
        print(f"\n  ⚠ {len(failed)} symbols failed: {', '.join(failed[:10])}...")

    return data


# ═════════════════════════════════════════════════════════════════
# Breakout Alpha Organism v3.0
# ═════════════════════════════════════════════════════════════════

class BreakoutOrganismEngine:
    """The Breakout Alpha Self-Learning Organism v3.0.

    Key differences vs v2.0:
        * BreakoutScanner replaces pure ML as primary signal
        * MomentumPyramider adds to winners
        * AdaptiveExitEngine v2 with ATR trails + partial TP
        * KellySizer v2 with breakout bonus sizing
        * Long-only (shorts eliminated)
        * 50+ symbol expanded universe
    """

    def __init__(
        self,
        raw_data: dict[str, pd.DataFrame],
        initial_capital: float = INITIAL_CAPITAL,
        epochs: int = DEFAULT_EPOCHS,
        bars_per_epoch: int = BARS_PER_EPOCH,
        brain: OrganismBrain | None = None,
    ):
        self.raw_data = raw_data
        self.initial_capital = initial_capital
        self.epochs = epochs
        self.bars_per_epoch = bars_per_epoch
        self.symbols = list(raw_data.keys())
        self.brain = brain

        # Separate SPY for cross-asset features
        self.spy_data = raw_data.get("SPY")

        # ── Initialize organism components ──────────────────────
        self.signal_gen = MLSignalGenerator(
            train_window=TRAIN_WINDOW,
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
        )
        self.alpha_scanner = AlphaScanner(top_n=MAX_OPEN_POSITIONS)
        self.breakout_scanner = BreakoutScanner(top_n=MAX_OPEN_POSITIONS)
        self.pyramider = MomentumPyramider()
        self.kelly_sizer = KellySizer(
            max_position_pct=0.12,       # 12 % max (was 5 %)
            max_portfolio_pct=0.95,
            vol_target=0.15,
            min_position_usd=2000.0,     # $2k min (was $500)
        )
        self.exit_engine = AdaptiveExitEngine(
            atr_multiplier=1.5,          # Tighter initial stop (was 2.0)
            profit_r_multiple=4.0,       # 4R default TP (was 3.0)
            trailing_start_atr=3.0,      # Trail after 3× ATR (not 1 %)
            trailing_distance_atr=2.5,   # 2.5 ATR from peak
            max_bars_held=40,
            time_decay_start=30,
            partial_tp_r=3.0,            # Partial TP at 3R
            partial_tp_pct=0.30,         # Sell 30 %
        )
        self.learner = ContinuousLearner(
            signal_generator=self.signal_gen,
            retrain_every_n_bars=RETRAIN_INTERVAL,
            min_trades_for_eval=10,
            improvement_threshold=0.05,
        )

        # ── Portfolio state ─────────────────────────────────────
        self.equity = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, OpenPosition] = {}
        self.equity_curve: list[float] = [initial_capital]
        self.daily_returns: list[float] = []
        self.all_trades: list[TradeRecord] = []
        self.epoch_metrics: list[EpochMetrics] = []
        self.peak_equity = initial_capital

        # v3 tracking
        self.breakout_trade_count = 0
        self.pyramid_add_count = 0
        self.partial_tp_count = 0

        # ── Self-evolution engine ───────────────────────────────
        self.evolution_engine = EvolutionEngine(
            alpha=0.30,         # EMA smoothing factor
            max_shift=0.20,     # Max 20% parameter shift per epoch
            min_trades=8,       # Need 8+ trades before adapting
        )
        self.evolved_params = EvolvedParams()

        # ── Regime detector (full module — Phase 1.4) ──────────
        self.regime_detector = RegimeDetector()

        # ── Governance controller (Phase 1.2) ──────────────────
        self.governance = GovernanceController()

        # ── Precompute features ─────────────────────────────────
        # Filter out symbols with too few bars for train + trade
        min_required = TRAIN_WINDOW + bars_per_epoch  # Need at least 1 epoch
        short_symbols = [
            sym for sym, df in raw_data.items()
            if len(df) < min_required
        ]
        if short_symbols:
            print(f"\n  ⚠ Dropping {len(short_symbols)} symbols with <{min_required} bars: "
                  f"{', '.join(short_symbols)}")
            for sym in short_symbols:
                raw_data.pop(sym, None)
            self.symbols = list(raw_data.keys())

        print(f"\n📊 Computing 68 ML features for {len(raw_data)} symbols...")
        self.features_by_symbol: dict[str, pd.DataFrame] = {}
        for sym, df in raw_data.items():
            if sym == "SPY":
                feats = compute_ml_features(df, spy_df=None)
            else:
                feats = compute_ml_features(df, spy_df=self.spy_data)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    feats[col] = df[col].values[:len(feats)]
            self.features_by_symbol[sym] = feats
            # Only print every 10th symbol to avoid spam
            if len(self.features_by_symbol) % 10 == 0 or len(self.features_by_symbol) == len(raw_data):
                print(f"  ✓ {len(self.features_by_symbol)}/{len(raw_data)} symbols processed")

        # Determine trading window
        min_rows = min(len(df) for df in self.features_by_symbol.values())
        self.total_bars = min(min_rows, TRAIN_WINDOW + epochs * bars_per_epoch)
        self.train_start = 0
        self.trade_start = TRAIN_WINDOW
        print(f"\n  Total bars available: {min_rows}")
        print(f"  Training window: 0-{TRAIN_WINDOW}")
        print(f"  Trading window: {self.trade_start}-{self.total_bars}")
        print(f"  Epochs: {epochs} × {bars_per_epoch} bars = {epochs * bars_per_epoch} bars")

    def run(self) -> dict[str, Any]:
        """Execute the full breakout alpha organism backtest."""
        start_time = time.time()

        print("\n" + "═" * 70)
        print("  🚀 BREAKOUT ALPHA ORGANISM v3.0")
        print("═" * 70)
        print(f"  Capital: ${self.initial_capital:,.0f}")
        print(f"  Universe: {len(self.symbols)} symbols")
        print(f"  Epochs: {self.epochs}")
        print(f"  ML Features: {len(FEATURE_COLUMNS)}")
        print(f"  Max positions: {MAX_OPEN_POSITIONS}")
        print(f"  Long-only: {LONG_ONLY}")
        print(f"  Max position size: 12 %")
        print(f"  Min position: $2,000")
        print("═" * 70)

        # ── Initial ML training ──────────────────────────────────
        brain_loaded = False
        if self.brain is not None and self.brain.exists:
            brain_loaded = self.brain.load()

        if brain_loaded and self.brain is not None:
            # ── Restore from previous brain ──────────────────────
            print("\n🧠 Phase 1: Restoring ML Models from Brain...")
            ml_ok = self.brain.apply_to_signal_generator(self.signal_gen)
            lr_ok = self.brain.apply_to_learner(self.learner)

            if ml_ok:
                gen = self.signal_gen.generation
                print(f"  ✓ ML models restored at generation {gen}")
                if self.signal_gen._latest_metrics:
                    m = self.signal_gen._latest_metrics
                    print(f"  ✓ Last metrics: accuracy={m.accuracy:.3f}, "
                          f"hit_rate={m.hit_rate:.3f}")
            else:
                # Brain exists but ML models failed — train fresh
                print("  ⚠ ML restoration failed — training from scratch")
                train_features = self._get_features_slice(0, TRAIN_WINDOW)
                metrics = self.signal_gen.train(train_features)
                if metrics:
                    print(f"  ✓ Fresh model: accuracy={metrics.accuracy:.3f}")

            if lr_ok:
                print(f"  ✓ Learner state restored: "
                      f"gen={self.learner.state.generation}, "
                      f"trades={self.learner.state.total_trades}, "
                      f"PnL=${self.learner.state.cumulative_pnl:,.2f}")
            else:
                print("  ⚠ Learner state restoration failed — fresh state")

            # ── Restore cumulative data from brain ───────────────
            # Trade history: seed engine.all_trades so saves accumulate
            prev_trade_records = self.brain.get_trade_records()
            if prev_trade_records:
                self.all_trades = prev_trade_records
                print(f"  ✓ Restored {len(prev_trade_records)} historical trades")

            # Equity curve: prepend previous history
            if self.brain.equity_curve:
                prev_final = self.brain.equity_curve[-1]
                prev_runs = self.brain.total_runs
                # Prepend previous equity history (current run appends to this)
                self.equity_curve = list(self.brain.equity_curve)
                print(f"  ✓ Previous runs: {prev_runs}, "
                      f"equity history: {len(self.equity_curve)} points, "
                      f"last equity: ${prev_final:,.2f}")

            # Epoch metrics: restore historical epochs
            if self.brain.epoch_metrics:
                self.epoch_metrics = [
                    EpochMetrics(**m) if not isinstance(m, EpochMetrics) else m
                    for m in self.brain.epoch_metrics
                ]
                print(f"  ✓ Restored {len(self.epoch_metrics)} historical epoch metrics")

            # Restore counters
            if self.brain.extra_counters:
                ec = self.brain.extra_counters
                self.breakout_trade_count = ec.get("breakout_trade_count", 0)
                self.pyramid_add_count = ec.get("pyramid_add_count", 0)
                self.partial_tp_count = ec.get("partial_tp_count", 0)
                self.peak_equity = ec.get("peak_equity", self.peak_equity)

            # Restore evolved parameters from brain (Phase 1.1: own file)
            if self.brain.evolved_params:
                self.evolved_params = EvolvedParams.from_dict(
                    self.brain.evolved_params
                )
                eg = self.evolved_params.evolution_generation
                ta = self.evolved_params.total_adaptations
                print(f"  ✓ Evolution state restored: "
                      f"gen={eg}, adaptations={ta}")
            elif self.brain.extra_counters.get("evolved_params"):
                # Backward compat: load from extra_counters
                self.evolved_params = EvolvedParams.from_dict(
                    self.brain.extra_counters["evolved_params"]
                )
                eg = self.evolved_params.evolution_generation
                ta = self.evolved_params.total_adaptations
                print(f"  ✓ Evolution state restored (legacy): "
                      f"gen={eg}, adaptations={ta}")
                # Apply evolved params to all components
                apply_evolved_params(
                    self.evolved_params,
                    alpha_scanner=self.alpha_scanner,
                    breakout_scanner=self.breakout_scanner,
                    kelly_sizer=self.kelly_sizer,
                    exit_engine=self.exit_engine,
                    signal_gen=self.signal_gen,
                )
                # Also set feature weights on signal generator
                if self.evolved_params.feature_weights:
                    self.signal_gen._evolved_feature_weights = (
                        self.evolved_params.feature_weights
                    )
                    n_active = sum(
                        1 for w in self.evolved_params.feature_weights.values()
                        if w >= 0.20
                    )
                    print(f"  ✓ Feature selection: {n_active} active features "
                          f"(from {len(self.evolved_params.feature_weights)})")
                print("  ✓ Evolved parameters applied to all components")

            # Restore governance state (Phase 1.2)
            if self.brain.governance_state:
                self.brain.apply_governance_state(self.governance)
                print("  ✓ Governance state restored")

            # Restore regime detector state (Phase 1.3)
            if self.brain.regime_state:
                self.brain.apply_regime_state(self.regime_detector)
                print(f"  ✓ Regime detector state restored "
                      f"({len(self.regime_detector._history)} history entries)")

            # Validate brain integrity (Phase 1.6)
            warnings = self.brain.validate_brain()
            if warnings:
                for w in warnings:
                    print(f"  ⚠ Brain warning: {w}")
            else:
                print("  ✓ Brain integrity validated — all checks passed")

            # Do a quick re-tune on latest data so the model adapts
            # Preserve generation number — fine-tune is not a new generation
            print("\n🔄 Phase 1b: Fine-tuning on latest data...")
            saved_gen = self.signal_gen.generation
            train_features = self._get_features_slice(0, TRAIN_WINDOW)
            metrics = self.signal_gen.train(train_features)
            self.signal_gen.generation = saved_gen  # restore — fine-tune ≠ new gen
            if metrics:
                print(f"  ✓ Fine-tuned: accuracy={metrics.accuracy:.3f}, "
                      f"hit_rate={metrics.hit_rate:.3f}")
        else:
            print("\n🧠 Phase 1: Initial ML Training...")
            train_features = self._get_features_slice(0, TRAIN_WINDOW)
            metrics = self.signal_gen.train(train_features)
            if metrics:
                print(f"  ✓ Initial model: accuracy={metrics.accuracy:.3f}, "
                      f"hit_rate={metrics.hit_rate:.3f}")
                if metrics.feature_importance_top10:
                    top5 = [name for name, _ in metrics.feature_importance_top10[:5]]
                    print(f"  ✓ Top features: {', '.join(top5)}")
            else:
                print("  ⚠ Initial training failed — proceeding with breakout signals only")

        # ── Epoch loop ───────────────────────────────────────────
        bar_idx = self.trade_start
        for epoch in range(self.epochs):
            epoch_start_bar = bar_idx
            epoch_end_bar = min(bar_idx + self.bars_per_epoch, self.total_bars)

            if epoch_start_bar >= self.total_bars:
                print(f"\n  ⚠ No more data after epoch {epoch}")
                break

            print(f"\n{'─' * 60}")
            print(f"  📈 EPOCH {epoch + 1}/{self.epochs} "
                  f"(bars {epoch_start_bar}-{epoch_end_bar})")
            print(f"{'─' * 60}")

            epoch_metric = self._run_epoch(epoch, epoch_start_bar, epoch_end_bar)
            self.epoch_metrics.append(epoch_metric)
            self._print_epoch_summary(epoch_metric)
            bar_idx = epoch_end_bar

            # ── Save brain checkpoint after each epoch ───────────
            if self.brain is not None:
                try:
                    # Walk-forward gate: skip save if regression detected
                    should_save, gate_reason = self.brain.walk_forward_gate(
                        self.all_trades[-100:],
                        min_trades=10,
                        regression_threshold=0.95,
                    )
                    if not should_save:
                        print(f"  ⚠ Brain checkpoint SKIPPED (walk-forward gate): {gate_reason}")
                    else:
                        self.brain.save(
                            signal_gen=self.signal_gen,
                            learner=self.learner,
                            equity_curve=self.equity_curve,
                            all_trades=self.all_trades,
                            epoch_metrics=self.epoch_metrics,
                            peak_equity=self.peak_equity,
                            extra_counters={
                                "breakout_trade_count": self.breakout_trade_count,
                                "pyramid_add_count": self.pyramid_add_count,
                                "partial_tp_count": self.partial_tp_count,
                            },
                            evolved_params=self.evolved_params.to_dict(),
                            governance_controller=self.governance,
                            regime_detector=self.regime_detector,
                        )
                except Exception as e:
                    print(f"  ⚠ Brain checkpoint failed: {e}")

        # ── Close all remaining positions ────────────────────────
        self._close_all_positions(bar_idx - 1)

        # ── Final brain save (all positions closed) ──────────────
        if self.brain is not None:
            try:
                # Walk-forward gate on final save
                should_save, gate_reason = self.brain.walk_forward_gate(
                    self.all_trades[-100:],
                    min_trades=10,
                    regression_threshold=0.95,
                )
                if not should_save:
                    print(f"\n  ⚠ Final brain save SKIPPED (walk-forward gate): {gate_reason}")
                else:
                    self.brain.save(
                        signal_gen=self.signal_gen,
                        learner=self.learner,
                        equity_curve=self.equity_curve,
                        all_trades=self.all_trades,
                        epoch_metrics=self.epoch_metrics,
                        peak_equity=self.peak_equity,
                        extra_counters={
                            "breakout_trade_count": self.breakout_trade_count,
                            "pyramid_add_count": self.pyramid_add_count,
                            "partial_tp_count": self.partial_tp_count,
                        },
                        evolved_params=self.evolved_params.to_dict(),
                        governance_controller=self.governance,
                        regime_detector=self.regime_detector,
                    )
                    print("\n  💾 Final brain state saved — ready for next run")
            except Exception as e:
                print(f"\n  ⚠ Final brain save failed: {e}")

        # ── Final report ─────────────────────────────────────────
        duration = time.time() - start_time
        report = self._generate_report(duration)
        self._save_report(report)
        self._print_final_report(report)

        return report

    def _run_epoch(
        self, epoch: int, start_bar: int, end_bar: int
    ) -> EpochMetrics:
        """Run one trading epoch: per-bar loop, then retrain."""
        epoch_equity_start = self.equity
        epoch_trades: list[TradeRecord] = []
        epoch_daily_returns: list[float] = []
        epoch_peak = self.equity
        epoch_breakouts = 0
        epoch_pyramids = 0
        epoch_partials = 0

        for bar in range(start_bar, end_bar):
            prev_equity = self.equity

            # Current features for all symbols (lookback window)
            current_features = self._get_features_slice(
                max(0, bar - 60), bar + 1
            )

            # ── 1. Check exits on open positions ────────────────
            closed, partials = self._check_exits(bar, current_features)
            epoch_trades.extend(closed)
            epoch_partials += partials

            # ── 2. Check pyramid opportunities on winners ────────
            pyramids = self._check_pyramids(bar, current_features)
            epoch_pyramids += pyramids

            # ── 3. Breakout scan across entire universe ──────────
            # Build data dict for breakout scanner
            data_for_scanner = {}
            for sym, df in current_features.items():
                if len(df) >= 20:
                    data_for_scanner[sym] = df

            spy_slice = current_features.get("SPY")
            breakout_signals = self.breakout_scanner.scan(
                data_for_scanner, spy_slice
            )
            breakout_by_sym = {s.symbol: s for s in breakout_signals}

            # ── 4. Generate ML predictions ───────────────────────
            ml_signals = self.signal_gen.predict_batch(current_features)

            # ── 5. Detect regime ─────────────────────────────────
            regime = detect_regime(current_features)

            # ── 6. Alpha scan + breakout fusion ──────────────────
            candidates = self.alpha_scanner.scan(
                current_features, ml_signals, regime
            )

            # ── 7. Build candidate list with breakout scores ─────
            drawdown = (
                (self.peak_equity - self.equity) / self.peak_equity
                if self.peak_equity > 0 else 0
            )

            cand_dicts = []
            for c in candidates:
                # Skip if already in portfolio
                if c.symbol in self.positions:
                    continue
                # v3: long-only mode
                if LONG_ONLY and c.direction < 0:
                    continue

                bs = breakout_by_sym.get(c.symbol)
                breakout_score = bs.composite_score if bs else 0.0

                # Boost priority: breakout candidates get extra weight
                effective_confidence = (
                    (c.ml_signal.confidence if c.ml_signal else 0.5)
                    * (1.0 + breakout_score)  # breakout doubles confidence
                )

                cand_dicts.append({
                    "symbol": c.symbol,
                    "direction": c.direction,
                    "predicted_return": (
                        c.ml_signal.predicted_return if c.ml_signal else 0.01
                    ),
                    "confidence": min(effective_confidence, 1.0),
                    "breakout_score": breakout_score,
                })

            # Also add pure breakout signals not in alpha candidates
            alpha_syms = {d["symbol"] for d in cand_dicts}
            for bs in breakout_signals:
                if (
                    bs.symbol not in alpha_syms
                    and bs.symbol not in self.positions
                    and bs.composite_score >= 0.55
                ):
                    ml_sig = ml_signals.get(bs.symbol)
                    direction = 1.0  # breakout signals are inherently long
                    if ml_sig and ml_sig.direction < 0:
                        continue  # ML says short — skip

                    cand_dicts.append({
                        "symbol": bs.symbol,
                        "direction": direction,
                        "predicted_return": (
                            ml_sig.predicted_return if ml_sig else 0.02
                        ),
                        "confidence": min(bs.composite_score, 1.0),
                        "breakout_score": bs.composite_score,
                    })

            # Sort by combined score (breakout_score × confidence)
            cand_dicts.sort(
                key=lambda x: x["breakout_score"] * x["confidence"],
                reverse=True,
            )

            # Limit to available position slots
            open_slots = MAX_OPEN_POSITIONS - len(self.positions)
            cand_dicts = cand_dicts[:max(0, open_slots)]

            # ── 8. Kelly-size with breakout bonus ────────────────
            sizes = self.kelly_sizer.size_positions(
                cand_dicts, self.equity, drawdown,
                current_features, regime,
            )

            # ── 9. Open new positions (pyramid-aware sizing) ─────
            for sz in sizes:
                bs = breakout_by_sym.get(sz.symbol)
                breakout_score = bs.composite_score if bs else 0.0
                is_breakout = breakout_score >= 0.5
                if is_breakout:
                    epoch_breakouts += 1

                self._open_position(
                    bar, sz, current_features, regime, breakout_score
                )

            # ── 10. Update equity ────────────────────────────────
            self._update_equity(bar)
            daily_ret = (
                (self.equity - prev_equity) / prev_equity
                if prev_equity > 0 else 0
            )
            epoch_daily_returns.append(daily_ret)
            self.daily_returns.append(daily_ret)
            self.equity_curve.append(self.equity)

            self.peak_equity = max(self.peak_equity, self.equity)
            epoch_peak = max(epoch_peak, self.equity)

            # ── 11. Feed learner ─────────────────────────────────
            self.learner.should_retrain(current_features)

        # ── End of epoch: retrain ────────────────────────────────
        retrain_features = self._get_features_slice(
            max(0, end_bar - TRAIN_WINDOW), end_bar
        )

        accepted = False
        ml_accuracy = 0.0
        top_features: list[str] = []

        accepted, train_metrics = self.learner.retrain(retrain_features)
        if train_metrics:
            ml_accuracy = train_metrics.accuracy
            if train_metrics.feature_importance_top10:
                top_features = [
                    name for name, _ in train_metrics.feature_importance_top10[:5]
                ]

        self.learner.compute_attribution()

        # ── Self-evolution: adapt ALL tunable parameters ─────────
        if epoch_trades:
            # Gather feature importances from the latest model
            fi = self.signal_gen._get_feature_importance()

            self.evolved_params = self.evolution_engine.evolve(
                params=self.evolved_params,
                trades=epoch_trades,
                feature_importances=fi if fi else None,
                epoch_regime=detect_regime(
                    self._get_features_slice(max(0, end_bar - 20), end_bar)
                ),
                all_feature_names=list(FEATURE_COLUMNS),
            )

            # Apply evolved params to all components for next epoch
            apply_evolved_params(
                self.evolved_params,
                alpha_scanner=self.alpha_scanner,
                breakout_scanner=self.breakout_scanner,
                kelly_sizer=self.kelly_sizer,
                exit_engine=self.exit_engine,
                signal_gen=self.signal_gen,
            )
            # Update feature weights on signal generator
            if self.evolved_params.feature_weights:
                self.signal_gen._evolved_feature_weights = (
                    self.evolved_params.feature_weights
                )

        # Compute epoch stats
        epoch_return = (
            (self.equity - epoch_equity_start) / epoch_equity_start
            if epoch_equity_start > 0 else 0
        )
        epoch_dd = (
            (epoch_peak - self.equity) / epoch_peak if epoch_peak > 0 else 0
        )

        if len(epoch_daily_returns) > 1:
            mean_r = np.mean(epoch_daily_returns)
            std_r = np.std(epoch_daily_returns, ddof=1)
            epoch_sharpe = (
                float(mean_r / std_r * math.sqrt(252)) if std_r > 1e-8 else 0.0
            )
        else:
            epoch_sharpe = 0.0

        wins = sum(1 for t in epoch_trades if t.pnl > 0)
        accuracy = wins / len(epoch_trades) if epoch_trades else 0.0

        return EpochMetrics(
            epoch=epoch + 1,
            generation=self.learner.state.generation,
            start_bar=start_bar,
            end_bar=end_bar,
            total_return_pct=epoch_return * 100,
            sharpe=epoch_sharpe,
            max_drawdown_pct=epoch_dd * 100,
            trade_count=len(epoch_trades),
            win_count=wins,
            accuracy=accuracy,
            ml_accuracy=ml_accuracy,
            model_accepted=accepted,
            retrain_reason="epoch_end",
            regime=detect_regime(
                self._get_features_slice(max(0, end_bar - 20), end_bar)
            ),
            top_features=top_features,
            equity_start=epoch_equity_start,
            equity_end=self.equity,
            breakout_trades=epoch_breakouts,
            pyramid_adds=epoch_pyramids,
            partial_tp_count=epoch_partials,
        )

    # ── Exit handling (v3: partial TP aware) ─────────────────────

    def _check_exits(
        self, bar: int, features: dict[str, pd.DataFrame]
    ) -> tuple[list[TradeRecord], int]:
        """Check all open positions for exit conditions.

        Returns (closed_trades, partial_tp_count).
        """
        closed: list[TradeRecord] = []
        to_close: list[str] = []
        partials = 0

        for sym, pos in list(self.positions.items()):
            df = features.get(sym)
            if df is None or len(df) < 1:
                continue

            current_price = float(df["close"].iloc[-1])
            regime = detect_regime(features)

            exit_sig = self.exit_engine.check_exit(
                pos.exit_levels, current_price, regime
            )

            if exit_sig.should_exit:
                if exit_sig.partial_exit:
                    # ── Partial take-profit: sell fraction, keep rest ──
                    sell_shares = max(
                        1,
                        int(pos.shares * exit_sig.partial_pct),
                    )
                    if sell_shares >= pos.shares:
                        # Would sell everything — treat as full exit instead
                        pass
                    else:
                        # Partial exit
                        exit_price = self._apply_slippage(
                            current_price, pos.direction, is_exit=True
                        )
                        if pos.direction > 0:
                            partial_pnl = (exit_price - pos.entry_price) * sell_shares
                        else:
                            partial_pnl = (pos.entry_price - exit_price) * sell_shares

                        commission = (
                            exit_price * COMMISSION_BPS / 10000 * sell_shares
                        )
                        partial_pnl -= commission

                        # Record partial trade
                        actual_return = (
                            (exit_price - pos.entry_price)
                            / pos.entry_price * pos.direction
                        )
                        trade = TradeRecord(
                            symbol=sym,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            entry_bar=pos.entry_bar,
                            exit_bar=bar,
                            shares=sell_shares,
                            pnl=partial_pnl,
                            exit_reason="partial_take_profit",
                            predicted_return=pos.predicted_return,
                            actual_return=actual_return,
                            confidence=pos.confidence,
                        )
                        closed.append(trade)
                        self.all_trades.append(trade)
                        self.learner.record_trade(trade)

                        # Update position: fewer shares, return partial capital
                        pos.shares -= sell_shares
                        pos.partial_tp_shares_sold += sell_shares
                        self.cash += pos.entry_price * sell_shares + partial_pnl
                        partials += 1
                        self.partial_tp_count += 1
                        continue  # Don't close position — rest rides

                # ── Full exit ──
                exit_price = self._apply_slippage(
                    exit_sig.exit_price if exit_sig.exit_price > 0 else current_price,
                    pos.direction,
                    is_exit=True,
                )

                if pos.direction > 0:
                    pnl = (exit_price - pos.entry_price) * pos.shares
                else:
                    pnl = (pos.entry_price - exit_price) * pos.shares

                commission = (
                    pos.entry_price * COMMISSION_BPS / 10000 * pos.shares
                    + exit_price * COMMISSION_BPS / 10000 * pos.shares
                )
                pnl -= commission

                actual_return = (
                    (exit_price - pos.entry_price) / pos.entry_price * pos.direction
                )

                trade = TradeRecord(
                    symbol=sym,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    entry_bar=pos.entry_bar,
                    exit_bar=bar,
                    shares=pos.shares,
                    pnl=pnl,
                    exit_reason=exit_sig.reason,
                    predicted_return=pos.predicted_return,
                    actual_return=actual_return,
                    confidence=pos.confidence,
                )

                closed.append(trade)
                self.all_trades.append(trade)
                self.learner.record_trade(trade)

                self.cash += pos.entry_price * pos.shares + pnl
                to_close.append(sym)

        for sym in to_close:
            del self.positions[sym]

        return closed, partials

    # ── Pyramid handling (v3: add to winners) ────────────────────

    def _check_pyramids(
        self, bar: int, features: dict[str, pd.DataFrame]
    ) -> int:
        """Check open positions for pyramid add opportunities."""
        adds = 0

        for sym, pos in list(self.positions.items()):
            if pos.pyramid_position is None:
                continue

            df = features.get(sym)
            if df is None or len(df) < 1:
                continue

            current_price = float(df["close"].iloc[-1])

            action = self.pyramider.check_pyramid(
                pos.pyramid_position, current_price
            )

            if action.action == "add" and action.shares_to_add > 0:
                add_shares = action.shares_to_add
                add_cost = current_price * add_shares

                if add_cost > self.cash * 0.5:
                    add_shares = max(1, int(self.cash * 0.4 / current_price))
                    add_cost = current_price * add_shares

                if add_shares < 1 or add_cost > self.cash:
                    continue

                add_price = self._apply_slippage(
                    current_price, pos.direction, is_exit=False
                )

                # Use slippage-adjusted price for cash and cost basis
                slipped_cost = add_price * add_shares

                # Update position: new weighted avg entry & more shares
                total_shares = pos.shares + add_shares
                new_avg_entry = (
                    (pos.entry_price * pos.shares + add_price * add_shares)
                    / total_shares
                )
                pos.entry_price = new_avg_entry
                pos.shares = total_shares
                pos.total_cost_basis += slipped_cost

                # Add layer to pyramid position
                pos.pyramid_position.layers.append(PyramidLevel(
                    shares=add_shares,
                    entry_price=add_price,
                    bar_added=bar,
                    level=pos.pyramid_position.layer_count,
                ))

                self.cash -= slipped_cost
                adds += 1
                self.pyramid_add_count += 1

                # Update stop to new action level
                if action.new_stop > 0:
                    pos.exit_levels.stop_loss = action.new_stop
                    pos.pyramid_position.current_stop = action.new_stop

            elif action.action == "tighten_stop" and action.new_stop > 0:
                # Just tighten the stop, no size change
                pos.exit_levels.stop_loss = action.new_stop
                pos.pyramid_position.current_stop = action.new_stop

            elif action.action == "close_partial" and action.shares_to_add < 0:
                # Anti-pyramid: cut position
                cut_shares = min(abs(action.shares_to_add), pos.shares - 1)
                if cut_shares < 1:
                    continue

                exit_price = self._apply_slippage(
                    current_price, pos.direction, is_exit=True
                )

                if pos.direction > 0:
                    cut_pnl = (exit_price - pos.entry_price) * cut_shares
                else:
                    cut_pnl = (pos.entry_price - exit_price) * cut_shares

                commission = exit_price * COMMISSION_BPS / 10000 * cut_shares
                cut_pnl -= commission

                actual_return = (
                    (exit_price - pos.entry_price) / pos.entry_price * pos.direction
                )

                trade = TradeRecord(
                    symbol=sym,
                    direction=pos.direction,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    entry_bar=pos.entry_bar,
                    exit_bar=bar,
                    shares=cut_shares,
                    pnl=cut_pnl,
                    exit_reason="anti_pyramid_cut",
                    predicted_return=pos.predicted_return,
                    actual_return=actual_return,
                    confidence=pos.confidence,
                )
                self.all_trades.append(trade)
                self.learner.record_trade(trade)

                pos.shares -= cut_shares
                self.cash += pos.entry_price * cut_shares + cut_pnl

        return adds

    # ── Position opening (v3: pyramid-aware) ─────────────────────

    def _open_position(
        self,
        bar: int,
        size: PositionSize,
        features: dict[str, pd.DataFrame],
        regime: str,
        breakout_score: float = 0.0,
    ) -> None:
        """Open a new position with pyramid-aware initial sizing."""
        df = features.get(size.symbol)
        if df is None or len(df) < 1:
            return

        price = float(df["close"].iloc[-1])
        entry_price = self._apply_slippage(price, size.direction, is_exit=False)

        # Pyramid-aware: initial entry = 60 % of target shares
        initial_shares = self.pyramider.initial_shares(size.shares)
        if initial_shares < 1:
            initial_shares = size.shares  # fallback

        cost = entry_price * initial_shares
        if cost > self.cash:
            initial_shares = max(1, int(self.cash * 0.95 / entry_price))
            cost = entry_price * initial_shares
            if cost > self.cash or initial_shares < 1:
                return

        # ML predicted return
        predicted_return = 0.01
        if self.signal_gen.is_trained:
            sig = self.signal_gen.predict(df, size.symbol)
            if sig:
                predicted_return = abs(sig.predicted_return)

        # Create exit levels
        exit_levels = self.exit_engine.create_exit_levels(
            symbol=size.symbol,
            direction=size.direction,
            entry_price=entry_price,
            predicted_return=predicted_return,
            features_df=df,
            regime=regime,
        )

        # Create pyramid position tracker
        atr = exit_levels.atr_at_entry
        risk_per_share = atr * 1.5  # initial stop distance
        pyramid_pos = PyramidPosition(
            symbol=size.symbol,
            direction=size.direction,
            layers=[PyramidLevel(
                shares=initial_shares,
                entry_price=entry_price,
                bar_added=bar,
                level=0,
            )],
            target_total_shares=size.shares,
            atr_at_entry=atr,
            initial_stop=exit_levels.stop_loss,
            current_stop=exit_levels.stop_loss,
            highest_price=entry_price,
            lowest_price=entry_price,
        )

        self.positions[size.symbol] = OpenPosition(
            symbol=size.symbol,
            direction=size.direction,
            shares=initial_shares,
            entry_price=entry_price,
            entry_bar=bar,
            exit_levels=exit_levels,
            predicted_return=predicted_return,
            confidence=0.6,
            breakout_score=breakout_score,
            notional=cost,
            pyramid_position=pyramid_pos,
            total_cost_basis=cost,
        )

        self.cash -= cost
        if breakout_score >= 0.5:
            self.breakout_trade_count += 1

    # ── Utilities ────────────────────────────────────────────────

    @staticmethod
    def _apply_slippage(
        price: float, direction: float, is_exit: bool
    ) -> float:
        """Apply slippage: adverse for both entry and exit."""
        slip = price * SLIPPAGE_BPS / 10000
        if is_exit:
            return price - slip if direction > 0 else price + slip
        else:
            return price + slip if direction > 0 else price - slip

    def _close_all_positions(self, bar: int) -> None:
        """Close all remaining positions at last available price.

        Phase 1.5: Now creates proper TradeRecord for each closed
        position so end-of-run positions are captured in trade history.
        """
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            df = self.features_by_symbol.get(sym)
            if df is None or len(df) < 1:
                continue
            current_price = float(
                df["close"].iloc[min(bar, len(df) - 1)]
            )
            exit_price = self._apply_slippage(
                current_price, pos.direction, is_exit=True
            )
            if pos.direction > 0:
                pnl = (exit_price - pos.entry_price) * pos.shares
            else:
                pnl = (pos.entry_price - exit_price) * pos.shares

            commission = (
                exit_price * COMMISSION_BPS / 10000 * pos.shares
            )
            pnl -= commission

            actual_return = (
                (exit_price - pos.entry_price)
                / pos.entry_price * pos.direction
                if pos.entry_price > 0 else 0
            )

            trade = TradeRecord(
                symbol=sym,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                entry_bar=pos.entry_bar,
                exit_bar=bar,
                shares=pos.shares,
                pnl=pnl,
                exit_reason="end_of_run",
                predicted_return=pos.predicted_return,
                actual_return=actual_return,
                confidence=pos.confidence,
            )
            self.all_trades.append(trade)
            self.learner.record_trade(trade)

            self.cash += pos.entry_price * pos.shares + pnl
            del self.positions[sym]

    def _update_equity(self, bar: int) -> None:
        """Update portfolio equity (cash + open positions MTM)."""
        mtm = 0.0
        for sym, pos in self.positions.items():
            df = self.features_by_symbol.get(sym)
            if df is None or bar >= len(df):
                continue
            current_price = float(
                df["close"].iloc[min(bar, len(df) - 1)]
            )
            if pos.direction > 0:
                mtm += (current_price - pos.entry_price) * pos.shares
            else:
                mtm += (pos.entry_price - current_price) * pos.shares

        invested = sum(
            p.entry_price * p.shares for p in self.positions.values()
        )
        self.equity = self.cash + invested + mtm

    def _get_features_slice(
        self, start: int, end: int
    ) -> dict[str, pd.DataFrame]:
        """Get a slice of features for each symbol."""
        result = {}
        for sym, df in self.features_by_symbol.items():
            s = max(0, start)
            e = min(end, len(df))
            if e > s:
                result[sym] = df.iloc[s:e].copy()
        return result

    # ── Printing & reporting ─────────────────────────────────────

    def _print_epoch_summary(self, m: EpochMetrics) -> None:
        symbol = "✅" if m.model_accepted else "❌"
        arrow = "↑" if m.total_return_pct > 0 else "↓"
        print(f"  {arrow} Return: {m.total_return_pct:+.2f}%  |  "
              f"Sharpe: {m.sharpe:.2f}  |  "
              f"DD: {m.max_drawdown_pct:.1f}%  |  "
              f"Trades: {m.trade_count}  |  "
              f"Accuracy: {m.accuracy:.1%}")
        print(f"  ML: {m.ml_accuracy:.1%}  |  "
              f"Model: {symbol}  |  "
              f"Regime: {m.regime}  |  "
              f"Breakouts: {m.breakout_trades}  |  "
              f"Pyramids: {m.pyramid_adds}  |  "
              f"Partial TPs: {m.partial_tp_count}")
        print(f"  Equity: ${m.equity_start:,.0f} → ${m.equity_end:,.0f}  |  "
              f"Gen: {m.generation}")
        if m.top_features:
            print(f"  Top features: {', '.join(m.top_features)}")
        # Evolution status
        ep = self.evolved_params
        evo_log = self.evolution_engine.log
        if evo_log:
            last = evo_log[-1]
            n_changes = len(last.get("changes", {}))
            print(f"  🧬 Evolution gen {ep.evolution_generation}: "
                  f"{n_changes} params adapted  |  "
                  f"ML wt={ep.alpha_weight_ml:.2f}  "
                  f"stop_scale={ep.stop_atr_scale:.2f}  "
                  f"buy_thr={ep.direction_threshold_buy:.3f}")

    def _generate_report(self, duration: float) -> dict[str, Any]:
        total_return = (
            (self.equity - self.initial_capital) / self.initial_capital
        )
        running_peak = self.equity_curve[0]
        max_dd = 0.0
        for e in self.equity_curve:
            running_peak = max(running_peak, e)
            dd = (running_peak - e) / running_peak if running_peak > 0 else 0
            max_dd = max(max_dd, dd)

        if len(self.daily_returns) > 1:
            mean_r = np.mean(self.daily_returns)
            std_r = np.std(self.daily_returns, ddof=1)
            sharpe = (
                float(mean_r / std_r * math.sqrt(252)) if std_r > 1e-8 else 0
            )
        else:
            sharpe = 0

        wins = sum(1 for t in self.all_trades if t.pnl > 0)
        losses = sum(1 for t in self.all_trades if t.pnl < 0)
        total_trades = len(self.all_trades)

        exit_reasons: dict[str, int] = defaultdict(int)
        for t in self.all_trades:
            exit_reasons[t.exit_reason] += 1

        avg_pnl = np.mean([t.pnl for t in self.all_trades]) if self.all_trades else 0
        avg_win = np.mean([t.pnl for t in self.all_trades if t.pnl > 0]) if wins > 0 else 0
        avg_loss = np.mean([t.pnl for t in self.all_trades if t.pnl < 0]) if losses > 0 else 0
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        correct_dir = sum(1 for t in self.all_trades if t.correct_direction)
        dir_accuracy = correct_dir / total_trades if total_trades > 0 else 0

        # Breakout vs non-breakout trade analysis
        breakout_trades = [t for t in self.all_trades if hasattr(t, "confidence") and t.confidence > 0.5]
        non_breakout = [t for t in self.all_trades if t not in breakout_trades]

        learning = self.learner.state.to_dict()
        attribution = self.learner.compute_attribution()

        return {
            "summary": {
                "version": "v3.0 Breakout Alpha",
                "initial_capital": self.initial_capital,
                "final_equity": round(self.equity, 2),
                "total_return_pct": round(total_return * 100, 2),
                "sharpe": round(sharpe, 4),
                "max_drawdown_pct": round(max_dd * 100, 2),
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / total_trades, 4) if total_trades > 0 else 0,
                "direction_accuracy": round(dir_accuracy, 4),
                "avg_pnl": round(float(avg_pnl), 2),
                "avg_win": round(float(avg_win), 2),
                "avg_loss": round(float(avg_loss), 2),
                "win_loss_ratio": round(win_loss_ratio, 2) if win_loss_ratio != float("inf") else "inf",
                "exit_reasons": dict(exit_reasons),
                "duration_seconds": round(duration, 1),
                "universe_size": len(self.symbols),
                "breakout_trades": self.breakout_trade_count,
                "pyramid_adds": self.pyramid_add_count,
                "partial_tp_count": self.partial_tp_count,
            },
            "learning": learning,
            "attribution": attribution,
            "evolution": self.evolved_params.to_dict(),
            "evolution_log": self.evolution_engine.log,
            "epochs": [m.to_dict() for m in self.epoch_metrics],
            "equity_curve": [round(e, 2) for e in self.equity_curve],
        }

    def _save_report(self, report: dict[str, Any]) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)

        if self.epoch_metrics:
            df = pd.DataFrame([m.to_dict() for m in self.epoch_metrics])
            path = reports_dir / f"breakout_v3_evolution_{ts}.csv"
            df.to_csv(path, index=False)
            print(f"\n  📁 Epoch metrics saved to {path}")

        if self.all_trades:
            trades_data = [
                {
                    "symbol": t.symbol,
                    "direction": "LONG" if t.direction > 0 else "SHORT",
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2),
                    "shares": t.shares,
                    "pnl": round(t.pnl, 2),
                    "exit_reason": t.exit_reason,
                    "predicted_return": round(t.predicted_return, 4),
                    "actual_return": round(t.actual_return, 4),
                    "correct_direction": t.correct_direction,
                    "bars_held": t.exit_bar - t.entry_bar,
                    "confidence": round(t.confidence, 4),
                }
                for t in self.all_trades
            ]
            df = pd.DataFrame(trades_data)
            path = reports_dir / f"breakout_v3_trades_{ts}.csv"
            df.to_csv(path, index=False)
            print(f"  📁 Trade log saved to {path}")

        df = pd.DataFrame({"equity": self.equity_curve})
        path = reports_dir / f"breakout_v3_equity_{ts}.csv"
        df.to_csv(path, index=False)
        print(f"  📁 Equity curve saved to {path}")

    def _print_final_report(self, report: dict[str, Any]) -> None:
        s = report["summary"]
        l = report["learning"]

        print("\n" + "═" * 70)
        print("  🏆 BREAKOUT ALPHA v3.0 — FINAL REPORT")
        print("═" * 70)
        print(f"  💰 Initial Capital:    ${s['initial_capital']:>12,.2f}")
        print(f"  💰 Final Equity:       ${s['final_equity']:>12,.2f}")
        arrow = "↑" if s["total_return_pct"] > 0 else "↓"
        print(f"  {arrow}  Total Return:       {s['total_return_pct']:>+11.2f}%")
        print(f"  📊 Sharpe Ratio:       {s['sharpe']:>12.4f}")
        print(f"  📉 Max Drawdown:       {s['max_drawdown_pct']:>11.2f}%")
        print()
        print(f"  🔁 Total Trades:       {s['total_trades']:>12}")
        print(f"  ✅ Wins:               {s['wins']:>12}")
        print(f"  ❌ Losses:             {s['losses']:>12}")
        print(f"  🎯 Win Rate:           {s['win_rate']:>11.1%}")
        print(f"  🧭 Direction Accuracy: {s['direction_accuracy']:>11.1%}")
        print(f"  💵 Avg Win:            ${s['avg_win']:>12,.2f}")
        print(f"  💸 Avg Loss:           ${s['avg_loss']:>12,.2f}")
        print(f"  ⚖️  Win/Loss Ratio:    {s['win_loss_ratio']:>12}")
        print()
        print(f"  🚀 Breakout Trades:    {s['breakout_trades']:>12}")
        print(f"  📐 Pyramid Adds:       {s['pyramid_adds']:>12}")
        print(f"  💰 Partial TPs:        {s['partial_tp_count']:>12}")
        print(f"  🌐 Universe Size:      {s['universe_size']:>12}")
        print()
        print(f"  🧬 Generations:        {l['generation']:>12}")
        print(f"  🔄 Retrains:           {l['retrain_count']:>12}")
        print(f"  📡 Drift Events:       {l['drift_events']:>12}")
        print(f"  🏆 Best Sharpe:        {l['best_sharpe']:>12.4f}")
        print(f"  🏆 Best Generation:    {l['best_generation']:>12}")
        print()

        # Self-evolution summary
        evo = report.get("evolution", {})
        if evo:
            print(f"  🧬 SELF-EVOLUTION STATUS:")
            print(f"     Evolution Gen:    {evo.get('evolution_generation', 0):>8}")
            print(f"     Total Adaptations:{evo.get('total_adaptations', 0):>8}")
            print(f"     Alpha ML weight:  {evo.get('alpha_weight_ml', 0.35):>8.3f}")
            print(f"     Alpha Mom weight: {evo.get('alpha_weight_momentum', 0.20):>8.3f}")
            print(f"     Buy threshold:    {evo.get('direction_threshold_buy', 0.55):>8.3f}")
            print(f"     Stop ATR scale:   {evo.get('stop_atr_scale', 1.0):>8.3f}")
            print(f"     Trail dist scale: {evo.get('trailing_distance_scale', 1.0):>8.3f}")
            print(f"     Partial TP %:     {evo.get('partial_tp_pct', 0.30):>8.1%}")
            fw = evo.get("feature_weights", {})
            if fw:
                active = sum(1 for v in fw.values() if v >= 0.20)
                print(f"     Active features:  {active:>8} / {len(fw)}")
            sf = evo.get("symbol_fitness", {})
            if sf:
                top = sorted(sf.items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"     Top symbols: {', '.join(f'{s}({v:.2f})' for s, v in top)}")
        print()

        if s["exit_reasons"]:
            print("  Exit Reason Breakdown:")
            for reason, count in sorted(
                s["exit_reasons"].items(), key=lambda x: -x[1]
            ):
                print(f"    {reason:.<30}{count:>5}")

        if self.epoch_metrics:
            print()
            print("  📈 Epoch Evolution:")
            print("  " + "-" * 76)
            print(f"  {'Ep':>3} {'Return':>8} {'Sharpe':>8} {'DD':>6} "
                  f"{'Trades':>7} {'Acc':>6} {'Brk':>5} {'Pyr':>5} {'Model':>6}")
            print("  " + "-" * 76)
            for m in self.epoch_metrics:
                sym = "✓" if m.model_accepted else "✗"
                print(f"  {m.epoch:>3} {m.total_return_pct:>+7.2f}% "
                      f"{m.sharpe:>8.2f} {m.max_drawdown_pct:>5.1f}% "
                      f"{m.trade_count:>7} {m.accuracy:>5.1%} "
                      f"{m.breakout_trades:>5} {m.pyramid_adds:>5} "
                      f"{sym:>6}")

        # v2.0 comparison
        print()
        print("  📊 v2.0 Baseline Comparison:")
        print("  " + "-" * 50)
        print(f"  {'Metric':<25} {'v2.0':>12} {'v3.0':>12}")
        print("  " + "-" * 50)
        print(f"  {'Return':<25} {'+11.17%':>12} {s['total_return_pct']:>+11.2f}%")
        print(f"  {'Sharpe':<25} {'2.42':>12} {s['sharpe']:>12.2f}")
        print(f"  {'Win Rate':<25} {'72.9%':>12} {s['win_rate']:>11.1%}")
        print(f"  {'Trades':<25} {'107':>12} {s['total_trades']:>12}")
        print(f"  {'Avg Win':<25} {'$249':>12} ${s['avg_win']:>11,.0f}")
        print(f"  {'Avg Loss':<25} {'-$275':>12} ${s['avg_loss']:>11,.0f}")
        print(f"  {'W/L Ratio':<25} {'0.90':>12} {s['win_loss_ratio']:>12}")

        print("═" * 70)
        print(f"  ⏱  Duration: {s['duration_seconds']:.1f}s")
        if self.brain is not None and self.brain.exists:
            print(f"  🧠 Brain: {self.brain.brain_dir}")
            print(f"     Generation: {self.brain.generation} | "
                  f"Runs: {self.brain.total_runs}")
        print("═" * 70)


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Breakout Alpha Organism v3.0 Backtest"
    )
    parser.add_argument(
        "--epochs", type=int, default=DEFAULT_EPOCHS,
        help=f"Number of training epochs (default: {DEFAULT_EPOCHS})",
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated symbols (default: 50+ stock universe)",
    )
    parser.add_argument(
        "--capital", type=float, default=INITIAL_CAPITAL,
        help=f"Initial capital (default: ${INITIAL_CAPITAL:,.0f})",
    )
    parser.add_argument(
        "--bars-per-epoch", type=int, default=BARS_PER_EPOCH,
        help=f"Bars per epoch (default: {BARS_PER_EPOCH})",
    )
    parser.add_argument(
        "--lookback", type=int, default=DEFAULT_LOOKBACK,
        help=f"Lookback days for data (default: {DEFAULT_LOOKBACK})",
    )
    parser.add_argument(
        "--max-positions", type=int, default=MAX_OPEN_POSITIONS,
        help=f"Max concurrent positions (default: {MAX_OPEN_POSITIONS})",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Start fresh — ignore any saved brain state",
    )
    parser.add_argument(
        "--brain-dir", type=str, default="organism_brain",
        help="Directory for brain persistence (default: organism_brain)",
    )
    args = parser.parse_args()

    # Override max positions if specified
    max_positions = args.max_positions

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_UNIVERSE

    # ── Brain setup ──────────────────────────────────────────────
    brain = OrganismBrain(brain_dir=args.brain_dir)
    if args.fresh:
        print("🔄 Fresh start requested — previous brain state will be ignored")
        print("   (Results will still be saved for future runs)")
        # Create brand new brain — don't load old one
        brain._manifest = {}  # Clear so load() won't be called
    else:
        brain.print_brain_status()

    print("🔌 Loading data from Alpaca...")
    print(f"   Requesting {len(symbols)} symbols, {args.lookback} days lookback")
    raw_data = load_data(symbols, lookback_days=args.lookback)

    if len(raw_data) < 3:
        print(f"ERROR: Only got data for {len(raw_data)} symbols. Need at least 3.")
        sys.exit(1)

    print(f"\n  ✓ Loaded {len(raw_data)}/{len(symbols)} symbols successfully")

    engine = BreakoutOrganismEngine(
        raw_data=raw_data,
        initial_capital=args.capital,
        epochs=args.epochs,
        bars_per_epoch=args.bars_per_epoch,
        brain=brain,
    )

    engine.run()


if __name__ == "__main__":
    main()
