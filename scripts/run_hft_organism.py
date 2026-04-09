#!/usr/bin/env python3
"""
Ultimate Self-Learning HFT Organism — Master Backtest
=====================================================

This is the REAL thing. Full ML-powered self-learning organism that:

    1. SCANS the universe for alpha with ML + technical + volume signals
    2. PREDICTS direction & magnitude via XGBoost ensemble (68 features)
    3. SIZES positions via half-Kelly with drawdown + vol-target scaling
    4. MANAGES exits with ATR stops, trailing, and regime-aware tightening
    5. LEARNS continuously — retrains after every epoch on its own results
    6. SELF-CORRECTS via drift detection → forced retrain
    7. EVOLVES across generations — walk-forward gates prevent degradation

Architecture:
┌──────────────────────────────────────────────────────────────────────┐
│                   ORGANISM MASTER LOOP                               │
│                                                                      │
│  OUTER LOOP (EPOCHS — every N bars):                                 │
│    ┌──────────────────────────────────────────────────────────────┐  │
│    │  1. ML TRAIN on accumulated history (XGBoost ensemble)       │  │
│    │  2. Walk-forward validate → accept or reject new model       │  │
│    │  3. Detect regime (trending/chop/stress/high-vol)            │  │
│    └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  INNER LOOP (PER-BAR — daily):                                       │
│    ┌──────────────────────────────────────────────────────────────┐  │
│    │  1. Compute 68 ML features for all symbols                   │  │
│    │  2. Generate ML predictions (direction + return + conf)      │  │
│    │  3. Alpha-scan: rank symbols by composite score              │  │
│    │  4. Kelly-size positions with regime + drawdown scaling      │  │
│    │  5. Check adaptive exits on open positions                   │  │
│    │  6. Execute trades (simulated fills + slippage)              │  │
│    │  7. Track trade outcomes for attribution                     │  │
│    └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  END-OF-EPOCH:                                                       │
│    ┌──────────────────────────────────────────────────────────────┐  │
│    │  1. Compute attribution (accuracy, Sharpe, feature imp)      │  │
│    │  2. Check drift → force retrain if distribution shifted      │  │
│    │  3. Retrain ML model on expanded dataset                     │  │
│    │  4. Walk-forward gate → accept only if improvement > 5%      │  │
│    │  5. Log generation metrics, update learning state            │  │
│    └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Output: reports/organism_ml_evolution_<timestamp>.csv               │
│          Per-generation metrics, equity curve, attribution breakdown │
└──────────────────────────────────────────────────────────────────────┘

Usage:
    python scripts/run_hft_organism.py [--epochs N] [--symbols SYM1,SYM2,...]
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
from backend.organism.brain_persistence import OrganismBrain

# ── Import broker for data ──────────────────────────────────────
from backend.data.alpaca_client import AlpacaClient


# ═════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "AMD", "SPY", "QQQ",
]

DEFAULT_LOOKBACK = 500     # 500 bars of history to start
DEFAULT_EPOCHS = 5         # 5 training epochs
BARS_PER_EPOCH = 60        # 60 trading days per epoch
INITIAL_CAPITAL = 100_000  # $100k starting capital
SLIPPAGE_BPS = 5           # 5 bps slippage per trade
COMMISSION_BPS = 1         # 1 bps commission
TRAIN_WINDOW = 200         # Train on 200 bars of features
RETRAIN_INTERVAL = 60      # Retrain every 60 bars


# ═════════════════════════════════════════════════════════════════
# Regime Detector (lightweight inline version)
# ═════════════════════════════════════════════════════════════════

def detect_regime(features_by_symbol: dict[str, pd.DataFrame]) -> str:
    """Simple regime detection from feature means across symbols."""
    adx_vals = []
    vol_regime_vals = []
    trend_vals = []

    for sym, df in features_by_symbol.items():
        if len(df) < 10:
            continue
        row = df.iloc[-1]
        adx = float(row.get("adx_14", 20))
        vr = int(row.get("vol_regime", 1))
        ts = float(row.get("trend_strength", 0.2))
        adx_vals.append(adx)
        vol_regime_vals.append(vr)
        trend_vals.append(ts)

    if not adx_vals:
        return "normal"

    avg_adx = np.mean(adx_vals)
    avg_vol_regime = np.mean(vol_regime_vals)
    avg_trend = np.mean(trend_vals)

    if avg_vol_regime >= 2:
        return "high_vol"
    if avg_adx > 30 and avg_trend > 0.4:
        return "trending_up"
    if avg_adx > 25:
        return "trending"
    if avg_adx < 18:
        return "chop"
    return "normal"


# ═════════════════════════════════════════════════════════════════
# Position Tracker
# ═════════════════════════════════════════════════════════════════

@dataclass
class OpenPosition:
    """Tracks an open position."""
    symbol: str
    direction: float
    shares: int
    entry_price: float
    entry_bar: int
    exit_levels: ExitLevels
    predicted_return: float
    confidence: float
    notional: float = 0.0

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "generation": self.generation,
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
    for sym in symbols:
        try:
            df = client.get_historical_data(
                sym, timeframe="1Day", start=start_date, end=end_date,
                limit=lookback_days + 100,
            )
            if df is not None and len(df) >= 100:
                # Normalize columns
                df.columns = [c.lower() for c in df.columns]
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"])
                df = df.sort_index() if isinstance(df.index, pd.DatetimeIndex) else df.sort_values("timestamp" if "timestamp" in df.columns else df.columns[0])
                df = df.reset_index(drop=True)
                data[sym] = df
                print(f"  ✓ {sym}: {len(df)} bars")
            else:
                print(f"  ✗ {sym}: insufficient data ({len(df) if df is not None else 0} bars)")
        except Exception as e:
            print(f"  ✗ {sym}: {e}")

    return data


# ═════════════════════════════════════════════════════════════════
# Master Organism Engine
# ═════════════════════════════════════════════════════════════════

class OrganismEngine:
    """The Ultimate Self-Learning Trading Organism.

    Ties together:
        - MLSignalGenerator (XGBoost ensemble)
        - AlphaScanner (composite alpha scoring)
        - KellySizer (half-Kelly position sizing)
        - AdaptiveExitEngine (ATR stops + trailing)
        - ContinuousLearner (retrain + drift + attribution)
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
        self.alpha_scanner = AlphaScanner(top_n=5)
        self.kelly_sizer = KellySizer(
            max_position_pct=0.05,
            max_portfolio_pct=0.95,
            vol_target=0.15,
        )
        self.exit_engine = AdaptiveExitEngine(
            atr_multiplier=2.0,
            profit_r_multiple=3.0,
            max_bars_held=30,
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
        self.positions: dict[str, OpenPosition] = {}  # symbol → position
        self.equity_curve: list[float] = [initial_capital]
        self.daily_returns: list[float] = []
        self.all_trades: list[TradeRecord] = []
        self.epoch_metrics: list[EpochMetrics] = []
        self.peak_equity = initial_capital

        # ── Precompute features ─────────────────────────────────
        print("\n📊 Computing 68 ML features for all symbols...")
        self.features_by_symbol: dict[str, pd.DataFrame] = {}
        for sym, df in raw_data.items():
            if sym == "SPY":
                feats = compute_ml_features(df, spy_df=None)
            else:
                feats = compute_ml_features(df, spy_df=self.spy_data)
            # Merge raw price data into features for exit engine
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    feats[col] = df[col].values[:len(feats)]
            self.features_by_symbol[sym] = feats
            print(f"  ✓ {sym}: {len(feats)} feature rows, {len(FEATURE_COLUMNS)} features")

        # Determine trading window
        min_rows = min(len(df) for df in self.features_by_symbol.values())
        self.total_bars = min(min_rows, TRAIN_WINDOW + epochs * bars_per_epoch)
        self.train_start = 0
        self.trade_start = TRAIN_WINDOW  # First trading bar after initial training
        print(f"\n  Total bars available: {min_rows}")
        print(f"  Training window: 0-{TRAIN_WINDOW}")
        print(f"  Trading window: {self.trade_start}-{self.total_bars}")
        print(f"  Epochs: {epochs} × {bars_per_epoch} bars = {epochs * bars_per_epoch} bars")

    def run(self) -> dict[str, Any]:
        """Execute the full self-learning organism backtest."""
        start_time = time.time()

        print("\n" + "═" * 70)
        print("  🧬 ULTIMATE SELF-LEARNING ORGANISM v2.0")
        print("═" * 70)
        print(f"  Capital: ${self.initial_capital:,.0f}")
        print(f"  Universe: {', '.join(self.symbols)}")
        print(f"  Epochs: {self.epochs}")
        print(f"  ML Features: {len(FEATURE_COLUMNS)}")
        print("═" * 70)

        # ── Initial ML training ──────────────────────────────────
        brain_loaded = False
        if self.brain is not None and self.brain.exists:
            brain_loaded = self.brain.load()

        if brain_loaded and self.brain is not None:
            print("\n🧠 Phase 1: Restoring ML Models from Brain...")
            ml_ok = self.brain.apply_to_signal_generator(self.signal_gen)
            lr_ok = self.brain.apply_to_learner(self.learner)
            if ml_ok:
                print(f"  ✓ ML models restored at generation {self.signal_gen.generation}")
            if lr_ok:
                print(f"  ✓ Learner restored: gen={self.learner.state.generation}, "
                      f"trades={self.learner.state.total_trades}")
            # Restore cumulative data
            prev_trades = self.brain.get_trade_records()
            if prev_trades:
                self.all_trades = prev_trades
            if self.brain.equity_curve:
                self.equity_curve = list(self.brain.equity_curve)
            if self.brain.extra_counters:
                self.peak_equity = self.brain.extra_counters.get(
                    "peak_equity", self.peak_equity
                )
            # Fine-tune on latest data (preserve gen number)
            print("\n🔄 Fine-tuning on latest data...")
            saved_gen = self.signal_gen.generation
            train_features = self._get_features_slice(0, TRAIN_WINDOW)
            metrics = self.signal_gen.train(train_features)
            self.signal_gen.generation = saved_gen
            if metrics:
                print(f"  ✓ Fine-tuned: accuracy={metrics.accuracy:.3f}")
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
                print("  ⚠ Initial training failed — proceeding with basic signals")

        # ── Epoch loop ───────────────────────────────────────────
        bar_idx = self.trade_start
        for epoch in range(self.epochs):
            epoch_start_bar = bar_idx
            epoch_end_bar = min(bar_idx + self.bars_per_epoch, self.total_bars)

            if epoch_start_bar >= self.total_bars:
                print(f"\n  ⚠ No more data after epoch {epoch}")
                break

            print(f"\n{'─' * 50}")
            print(f"  📈 EPOCH {epoch + 1}/{self.epochs} "
                  f"(bars {epoch_start_bar}-{epoch_end_bar})")
            print(f"{'─' * 50}")

            epoch_metric = self._run_epoch(epoch, epoch_start_bar, epoch_end_bar)
            self.epoch_metrics.append(epoch_metric)

            self._print_epoch_summary(epoch_metric)

            bar_idx = epoch_end_bar

            # ── Save brain checkpoint after each epoch ───────────
            if self.brain is not None:
                try:
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
                            evolved_params=self.evolved_params.to_dict() if hasattr(self.evolved_params, "to_dict") else None,
                            governance_controller=getattr(self, "governance", None),
                            regime_detector=getattr(self, "regime_detector", None),
                        )
                except Exception as e:
                    print(f"  ⚠ Brain checkpoint failed: {e}")

        # ── Close all remaining positions ────────────────────────
        self._close_all_positions(bar_idx - 1)

        # ── Final brain save ─────────────────────────────────────
        if self.brain is not None:
            try:
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
                        evolved_params=self.evolved_params.to_dict() if hasattr(self.evolved_params, "to_dict") else None,
                        governance_controller=getattr(self, "governance", None),
                        regime_detector=getattr(self, "regime_detector", None),
                    )
                    print("\n  💾 Brain saved — ready for next run")
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
        """Run one training epoch: trade all bars, then evaluate & retrain."""
        epoch_equity_start = self.equity
        epoch_trades: list[TradeRecord] = []
        epoch_daily_returns: list[float] = []
        epoch_peak = self.equity

        for bar in range(start_bar, end_bar):
            prev_equity = self.equity

            # Get current features for all symbols
            current_features = self._get_features_slice(
                max(0, bar - 60), bar + 1
            )

            # ── 1. Check exits on open positions ────────────────
            closed = self._check_exits(bar, current_features)
            epoch_trades.extend(closed)

            # ── 2. Generate ML predictions ───────────────────────
            ml_signals = self.signal_gen.predict_batch(current_features)

            # ── 3. Detect regime ─────────────────────────────────
            regime = detect_regime(current_features)

            # ── 4. Alpha scan — find best candidates ─────────────
            candidates = self.alpha_scanner.scan(
                current_features, ml_signals, regime
            )

            # ── 5. Size positions with Kelly ─────────────────────
            drawdown = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
            cand_dicts = [
                {
                    "symbol": c.symbol,
                    "direction": c.direction,
                    "predicted_return": c.ml_signal.predicted_return if c.ml_signal else 0.01,
                    "confidence": c.ml_signal.confidence if c.ml_signal else 0.5,
                }
                for c in candidates
                if c.symbol not in self.positions  # Don't add to existing
            ]

            sizes = self.kelly_sizer.size_positions(
                cand_dicts, self.equity, drawdown,
                current_features, regime,
            )

            # ── 6. Execute new positions ─────────────────────────
            for sz in sizes:
                self._open_position(bar, sz, current_features, regime)

            # ── 7. Update equity ─────────────────────────────────
            self._update_equity(bar)
            daily_ret = (self.equity - prev_equity) / prev_equity if prev_equity > 0 else 0
            epoch_daily_returns.append(daily_ret)
            self.daily_returns.append(daily_ret)
            self.equity_curve.append(self.equity)

            # Track peak
            self.peak_equity = max(self.peak_equity, self.equity)
            epoch_peak = max(epoch_peak, self.equity)

            # ── 8. Feed learner ──────────────────────────────────
            should_retrain, reason = self.learner.should_retrain(current_features)

        # ── End of epoch: retrain ────────────────────────────────
        retrain_features = self._get_features_slice(
            max(0, end_bar - TRAIN_WINDOW), end_bar
        )

        accepted = False
        ml_accuracy = 0.0
        retrain_reason = "scheduled"
        top_features: list[str] = []

        # Always retrain at end of epoch
        accepted, train_metrics = self.learner.retrain(retrain_features)
        if train_metrics:
            ml_accuracy = train_metrics.accuracy
            if train_metrics.feature_importance_top10:
                top_features = [name for name, _ in train_metrics.feature_importance_top10[:5]]
        retrain_reason = "epoch_end"

        # Compute attribution (updates best_sharpe in learner state)
        self.learner.compute_attribution()

        # Compute epoch metrics
        epoch_return = (self.equity - epoch_equity_start) / epoch_equity_start if epoch_equity_start > 0 else 0
        epoch_dd = (epoch_peak - self.equity) / epoch_peak if epoch_peak > 0 else 0

        # Sharpe of epoch
        if len(epoch_daily_returns) > 1:
            mean_r = np.mean(epoch_daily_returns)
            std_r = np.std(epoch_daily_returns, ddof=1)
            epoch_sharpe = float(mean_r / std_r * math.sqrt(252)) if std_r > 1e-8 else 0.0
        else:
            epoch_sharpe = 0.0

        # Trade accuracy
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
            retrain_reason=retrain_reason,
            regime=detect_regime(self._get_features_slice(max(0, end_bar - 20), end_bar)),
            top_features=top_features,
            equity_start=epoch_equity_start,
            equity_end=self.equity,
        )

    def _check_exits(
        self, bar: int, features: dict[str, pd.DataFrame]
    ) -> list[TradeRecord]:
        """Check all open positions for exit conditions."""
        closed: list[TradeRecord] = []
        to_close: list[str] = []

        for sym, pos in self.positions.items():
            df = features.get(sym)
            if df is None or len(df) < 1:
                continue

            current_price = float(df["close"].iloc[-1])
            regime = detect_regime(features)

            exit_sig = self.exit_engine.check_exit(
                pos.exit_levels, current_price, regime
            )

            if exit_sig.should_exit:
                exit_price = exit_sig.exit_price if exit_sig.exit_price > 0 else current_price
                # Apply slippage
                slippage = exit_price * SLIPPAGE_BPS / 10000
                if pos.direction > 0:
                    exit_price -= slippage
                else:
                    exit_price += slippage

                # Compute PnL
                if pos.direction > 0:
                    pnl = (exit_price - pos.entry_price) * pos.shares
                else:
                    pnl = (pos.entry_price - exit_price) * pos.shares

                # Commission
                commission = pos.entry_price * COMMISSION_BPS / 10000 * pos.shares
                commission += exit_price * COMMISSION_BPS / 10000 * pos.shares
                pnl -= commission

                actual_return = (exit_price - pos.entry_price) / pos.entry_price * pos.direction

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

                # Return capital
                self.cash += pos.entry_price * pos.shares + pnl
                to_close.append(sym)

        for sym in to_close:
            del self.positions[sym]

        return closed

    def _open_position(
        self,
        bar: int,
        size: PositionSize,
        features: dict[str, pd.DataFrame],
        regime: str,
    ) -> None:
        """Open a new position."""
        df = features.get(size.symbol)
        if df is None or len(df) < 1:
            return

        price = float(df["close"].iloc[-1])

        # Apply entry slippage
        slippage = price * SLIPPAGE_BPS / 10000
        if size.direction > 0:
            entry_price = price + slippage
        else:
            entry_price = price - slippage

        cost = entry_price * size.shares
        if cost > self.cash:
            # Reduce shares to fit
            size.shares = int(self.cash * 0.95 / entry_price)
            if size.shares < 1:
                return
            cost = entry_price * size.shares

        # Get ML signal for predicted return
        predicted_return = 0.01  # default
        if self.signal_gen.is_trained:
            sig = self.signal_gen.predict(
                df, size.symbol
            )
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

        self.positions[size.symbol] = OpenPosition(
            symbol=size.symbol,
            direction=size.direction,
            shares=size.shares,
            entry_price=entry_price,
            entry_bar=bar,
            exit_levels=exit_levels,
            predicted_return=predicted_return,
            confidence=0.6,
            notional=cost,
        )

        self.cash -= cost

    def _close_all_positions(self, bar: int) -> None:
        """Close all remaining positions at bar-indexed price with proper records."""
        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            df = self.features_by_symbol.get(sym)
            if df is None or len(df) < 1:
                continue
            current_price = float(
                df["close"].iloc[min(bar, len(df) - 1)]
            )
            # Apply slippage (same as normal exits)
            slippage = current_price * 0.0005
            exit_price = (
                current_price - slippage if pos.direction > 0
                else current_price + slippage
            )
            if pos.direction > 0:
                pnl = (exit_price - pos.entry_price) * pos.shares
            else:
                pnl = (pos.entry_price - exit_price) * pos.shares

            # Commission
            commission = (
                exit_price * 1.0 / 10000 * pos.shares
                + pos.entry_price * 1.0 / 10000 * pos.shares
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
                predicted_return=getattr(pos, "predicted_return", 0.0),
                actual_return=actual_return,
                confidence=getattr(pos, "confidence", 0.5),
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
            current_price = float(df["close"].iloc[min(bar, len(df) - 1)])
            if pos.direction > 0:
                mtm += (current_price - pos.entry_price) * pos.shares
            else:
                mtm += (pos.entry_price - current_price) * pos.shares

        invested = sum(p.entry_price * p.shares for p in self.positions.values())
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

    def _print_epoch_summary(self, m: EpochMetrics) -> None:
        """Print summary for one epoch."""
        symbol = "✅" if m.model_accepted else "❌"
        arrow = "↑" if m.total_return_pct > 0 else "↓"
        print(f"  {arrow} Return: {m.total_return_pct:+.2f}%  |  "
              f"Sharpe: {m.sharpe:.2f}  |  "
              f"DD: {m.max_drawdown_pct:.1f}%  |  "
              f"Trades: {m.trade_count}  |  "
              f"Accuracy: {m.accuracy:.1%}  |  "
              f"ML acc: {m.ml_accuracy:.1%}  |  "
              f"Model: {symbol}  |  "
              f"Regime: {m.regime}")
        print(f"  Equity: ${m.equity_start:,.0f} → ${m.equity_end:,.0f}  |  "
              f"Gen: {m.generation}")
        if m.top_features:
            print(f"  Top features: {', '.join(m.top_features)}")

    def _generate_report(self, duration: float) -> dict[str, Any]:
        """Generate final performance report."""
        total_return = (self.equity - self.initial_capital) / self.initial_capital
        # Running max drawdown (peak-to-trough)
        running_peak = self.equity_curve[0]
        max_dd = 0.0
        for e in self.equity_curve:
            running_peak = max(running_peak, e)
            dd = (running_peak - e) / running_peak if running_peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Overall Sharpe
        if len(self.daily_returns) > 1:
            mean_r = np.mean(self.daily_returns)
            std_r = np.std(self.daily_returns, ddof=1)
            sharpe = float(mean_r / std_r * math.sqrt(252)) if std_r > 1e-8 else 0
        else:
            sharpe = 0

        # Win/loss
        wins = sum(1 for t in self.all_trades if t.pnl > 0)
        losses = sum(1 for t in self.all_trades if t.pnl < 0)
        total_trades = len(self.all_trades)

        # By exit reason
        exit_reasons: dict[str, int] = defaultdict(int)
        for t in self.all_trades:
            exit_reasons[t.exit_reason] += 1

        # Avg PnL
        avg_pnl = np.mean([t.pnl for t in self.all_trades]) if self.all_trades else 0
        avg_win = np.mean([t.pnl for t in self.all_trades if t.pnl > 0]) if wins > 0 else 0
        avg_loss = np.mean([t.pnl for t in self.all_trades if t.pnl < 0]) if losses > 0 else 0
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

        # Direction accuracy
        correct_dir = sum(1 for t in self.all_trades if t.correct_direction)
        dir_accuracy = correct_dir / total_trades if total_trades > 0 else 0

        # Learning state
        learning = self.learner.state.to_dict()
        attribution = self.learner.compute_attribution()

        return {
            "summary": {
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
                "avg_pnl": round(avg_pnl, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "win_loss_ratio": round(win_loss_ratio, 2) if win_loss_ratio != float('inf') else "inf",
                "exit_reasons": dict(exit_reasons),
                "duration_seconds": round(duration, 1),
            },
            "learning": learning,
            "attribution": attribution,
            "epochs": [m.to_dict() for m in self.epoch_metrics],
            "equity_curve": [round(e, 2) for e in self.equity_curve],
        }

    def _save_report(self, report: dict[str, Any]) -> None:
        """Save results to CSV."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)

        # Epoch metrics CSV
        if self.epoch_metrics:
            df = pd.DataFrame([m.to_dict() for m in self.epoch_metrics])
            path = reports_dir / f"organism_ml_evolution_{ts}.csv"
            df.to_csv(path, index=False)
            print(f"\n  📁 Epoch metrics saved to {path}")

        # Trade log CSV
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
                }
                for t in self.all_trades
            ]
            df = pd.DataFrame(trades_data)
            path = reports_dir / f"organism_ml_trades_{ts}.csv"
            df.to_csv(path, index=False)
            print(f"  📁 Trade log saved to {path}")

        # Equity curve CSV
        df = pd.DataFrame({"equity": self.equity_curve})
        path = reports_dir / f"organism_ml_equity_{ts}.csv"
        df.to_csv(path, index=False)
        print(f"  📁 Equity curve saved to {path}")

    def _print_final_report(self, report: dict[str, Any]) -> None:
        """Print the final performance summary."""
        s = report["summary"]
        l = report["learning"]

        print("\n" + "═" * 70)
        print("  🏆 FINAL PERFORMANCE REPORT")
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
        print(f"  🧬 Generations:        {l['generation']:>12}")
        print(f"  🔄 Retrains:           {l['retrain_count']:>12}")
        print(f"  📡 Drift Events:       {l['drift_events']:>12}")
        print(f"  🏆 Best Sharpe:        {l['best_sharpe']:>12.4f}")
        print(f"  🏆 Best Generation:    {l['best_generation']:>12}")
        print()

        if s["exit_reasons"]:
            print("  Exit Reason Breakdown:")
            for reason, count in sorted(s["exit_reasons"].items(), key=lambda x: -x[1]):
                print(f"    {reason:.<30}{count:>5}")

        # Epoch evolution
        if self.epoch_metrics:
            print()
            print("  📈 Epoch Evolution:")
            print("  " + "-" * 66)
            print(f"  {'Epoch':>5} {'Return':>8} {'Sharpe':>8} {'DD':>6} "
                  f"{'Trades':>7} {'Acc':>6} {'ML Acc':>7} {'Model':>6}")
            print("  " + "-" * 66)
            for m in self.epoch_metrics:
                symbol = "✓" if m.model_accepted else "✗"
                print(f"  {m.epoch:>5} {m.total_return_pct:>+7.2f}% "
                      f"{m.sharpe:>8.2f} {m.max_drawdown_pct:>5.1f}% "
                      f"{m.trade_count:>7} {m.accuracy:>5.1%} "
                      f"{m.ml_accuracy:>6.1%} {symbol:>6}")

        print("═" * 70)
        print(f"  ⏱  Duration: {s['duration_seconds']:.1f}s")
        print("═" * 70)


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Ultimate Self-Learning HFT Organism Backtest"
    )
    parser.add_argument(
        "--epochs", type=int, default=DEFAULT_EPOCHS,
        help=f"Number of training epochs (default: {DEFAULT_EPOCHS})"
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated list of symbols (default: AAPL,MSFT,GOOGL,...)"
    )
    parser.add_argument(
        "--capital", type=float, default=INITIAL_CAPITAL,
        help=f"Initial capital (default: ${INITIAL_CAPITAL:,.0f})"
    )
    parser.add_argument(
        "--bars-per-epoch", type=int, default=BARS_PER_EPOCH,
        help=f"Bars per epoch (default: {BARS_PER_EPOCH})"
    )
    parser.add_argument(
        "--lookback", type=int, default=DEFAULT_LOOKBACK,
        help=f"Lookback days for data (default: {DEFAULT_LOOKBACK})"
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Start fresh — ignore any saved brain state",
    )
    parser.add_argument(
        "--brain-dir", type=str, default="organism_brain_sandbox",
        help="Directory for brain persistence (default: organism_brain_sandbox)",
    )
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else DEFAULT_UNIVERSE

    # ── Brain setup ──────────────────────────────────────────────
    brain = OrganismBrain(brain_dir=args.brain_dir)
    if args.fresh:
        print("🔄 Fresh start — previous brain ignored (results still saved)")
        brain._manifest = {}
    else:
        brain.print_brain_status()

    print("🔌 Loading data from Alpaca...")
    raw_data = load_data(symbols, lookback_days=args.lookback)

    if len(raw_data) < 3:
        print(f"ERROR: Only got data for {len(raw_data)} symbols. Need at least 3.")
        sys.exit(1)

    engine = OrganismEngine(
        raw_data=raw_data,
        initial_capital=args.capital,
        epochs=args.epochs,
        bars_per_epoch=args.bars_per_epoch,
        brain=brain,
    )

    engine.run()


if __name__ == "__main__":
    main()
