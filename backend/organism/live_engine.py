"""
Phase 2 — Organism Live Engine.

Unified live trading engine that bridges the backtest organism with the
production trading infrastructure.  Combines ALL organism modules into
a single ``async live_tick()`` call:

    ML Signal Generator  →  Alpha Scanner  →  Breakout Scanner  →
    Kelly Sizer  →  Adaptive Exits  →  Pyramider  →  Brain Persistence  →
    Self-Evolution  →  Governance  →  Regime Detector

Usage (paper mode):

    engine = OrganismLiveEngine(
        data_client=alpaca_client,
        order_service=order_service,
        positions_service=positions_service,
    )
    await engine.initialize()      # Load brain, warm up
    await engine.live_tick()       # One full organism cycle
    await engine.shutdown()        # Persist final state

Wire into the live server scheduler for automatic bar-by-bar execution.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from backend.organism.adaptive_exits import AdaptiveExitEngine
from backend.organism.alpha_scanner import AlphaScanner
from backend.organism.brain_persistence import OrganismBrain
from backend.organism.breakout_scanner import BreakoutScanner
from backend.organism.continuous_learner import ContinuousLearner, TradeRecord
from backend.organism.governance import GovernanceController
from backend.organism.kelly_sizer import KellySizer
from backend.organism.ml_features import compute_ml_features, FEATURE_COLUMNS
from backend.organism.multi_timeframe import add_multi_timeframe_features
from backend.organism.ml_signal import MLSignalGenerator
from backend.organism.pyramider import (
    MomentumPyramider,
    PyramidPosition,
    PyramidLevel,
)
from backend.organism.regime import RegimeDetector, RegimeLabel
from backend.organism.self_evolution import (
    EvolutionEngine,
    EvolvedParams,
    apply_evolved_params,
)
from backend.organism.universe_selector import DynamicUniverseSelector
from backend.organism.transfer_learning import TransferLearningEngine
from backend.organism.background_trainer import BackgroundTrainer
from backend.organism.market_scanner import MarketScanner, SCAN_INTERVAL_TICKS
from backend.strategies.types import TradingSignal
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Prometheus metrics (Phase 3.5) ────────────────────────────
try:
    from prometheus_client import Counter, Gauge, Histogram

    ORGANISM_TICK_DURATION = Histogram(
        "organism_tick_duration_seconds",
        "Duration of a single organism live tick",
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    )
    ORGANISM_GENERATION = Gauge(
        "organism_evolution_generation",
        "Current organism evolution generation",
    )
    ORGANISM_DIRECTION_ACCURACY = Gauge(
        "organism_direction_accuracy",
        "Current organism ML direction accuracy",
    )
    ORGANISM_SHARPE = Gauge(
        "organism_sharpe_per_epoch",
        "Latest organism Sharpe ratio",
    )
    ORGANISM_TOTAL_TRADES = Gauge(
        "organism_total_trades",
        "Total trades accumulated across all runs",
    )
    ORGANISM_ORDERS_SUBMITTED = Counter(
        "organism_orders_submitted_total",
        "Total organism orders submitted",
    )
    ORGANISM_ERRORS = Counter(
        "organism_tick_errors_total",
        "Total errors across organism ticks",
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


# ── Configuration (env-overridable) ───────────────────────────────

def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


LIVE_LOOKBACK = _env_int("ORGANISM_LIVE_LOOKBACK", 500)
LIVE_TIMEFRAME = _env_str("ORGANISM_LIVE_TIMEFRAME", "1Day")
LIVE_UNIVERSE_CSV = _env_str(
    "ORGANISM_LIVE_SYMBOLS",
    "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,AVGO,CRM,"
    "COST,WMT,LLY,XOM,CAT,SPY,QQQ,IWM,XLK,XLE",
)
MAX_OPEN_POSITIONS = _env_int("ORGANISM_MAX_POSITIONS", 8)
BRAIN_DIR = _env_str("ORGANISM_BRAIN_DIR", "organism_brain")
RETRAIN_INTERVAL = _env_int("ORGANISM_RETRAIN_INTERVAL", 60)
TRAIN_WINDOW = _env_int("ORGANISM_TRAIN_WINDOW", 200)
MIN_BARS = _env_int("ORGANISM_MIN_BARS", 200)
LONG_ONLY = _env_bool("ORGANISM_LONG_ONLY", True)
SCANNER_ENABLED = _env_bool("SCANNER_ENABLED", True)
USE_STREAMING = _env_bool("ORGANISM_USE_STREAMING", False)

# ── Dynamic intraday adjustments ────────────────────────────────
_IS_INTRADAY = LIVE_TIMEFRAME in ("1Min", "5Min", "15Min", "1Hour")
if _IS_INTRADAY and MIN_BARS == 200:
    MIN_BARS = _env_int("ORGANISM_MIN_BARS", 50)
if _IS_INTRADAY and RETRAIN_INTERVAL == 60:
    RETRAIN_INTERVAL = _env_int("ORGANISM_RETRAIN_INTERVAL", 200)


@dataclass
class ActivityEvent:
    """One activity event for the frontend activity feed."""
    event_type: str       # "signal", "order", "exit", "scanner", "retrain", "regime", "skip"
    symbol: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.event_type,
            "symbol": self.symbol,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class LiveTickResult:
    """Return value from one ``live_tick()`` call."""
    timestamp: str = ""
    regime: str = RegimeLabel.UNKNOWN
    signals_generated: int = 0
    orders_submitted: int = 0
    exits_checked: int = 0
    trades_closed: int = 0
    brain_saved: bool = False
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    # Phase 5: Scanner & Universe metadata for frontend
    universe_size: int = 0
    scanner_candidates_count: int = 0
    scanner_ran: bool = False
    # Activity feed for frontend visibility
    activity: list[ActivityEvent] = field(default_factory=list)
    # Background training metadata
    training_status: str = ""  # "training", "completed", "rejected", ""
    training_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "regime": self.regime,
            "signals_generated": self.signals_generated,
            "orders_submitted": self.orders_submitted,
            "exits_checked": self.exits_checked,
            "trades_closed": self.trades_closed,
            "brain_saved": self.brain_saved,
            "errors": self.errors,
            "duration_s": round(self.duration_s, 3),
            "universe_size": self.universe_size,
            "scanner_candidates_count": self.scanner_candidates_count,
            "scanner_ran": self.scanner_ran,
            "activity": [a.to_dict() for a in self.activity[-50:]],
            "training_status": self.training_status,
            "training_metadata": self.training_metadata,
        }


class OrganismLiveEngine:
    """Unified live trading engine — the organism in production.

    Combines all organism modules into a single ``live_tick()`` method
    that can be called by a scheduler (every bar interval).
    """

    def __init__(
        self,
        *,
        data_client: Any,          # AlpacaClient
        order_service: Any,        # OrderService
        positions_service: Any,    # PositionsService
        brain_dir: str = BRAIN_DIR,
        universe: list[str] | None = None,
        sessionmaker: Any | None = None,  # Phase 3.3: for VersionedFeatureStore
        streaming_provider: Any | None = None,  # StreamingDataProvider
    ) -> None:
        self._data_client = data_client
        self._order_service = order_service
        self._positions_service = positions_service
        self._streaming_provider = streaming_provider

        self._universe = universe or [
            s.strip().upper()
            for s in LIVE_UNIVERSE_CSV.split(",")
            if s.strip()
        ]

        # ── Organism components ──────────────────────────────────
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
            max_position_pct=0.08,    # HFT: smaller positions, faster turns
            max_portfolio_pct=0.95,
            vol_target=0.15,
            min_position_usd=500.0,   # HFT: allow small scalps ($500 min)
        )
        self.exit_engine = AdaptiveExitEngine(
            atr_multiplier=1.0,        # HFT: tighter stops for intraday
            profit_r_multiple=3.0,     # HFT: take profit sooner
            trailing_start_atr=2.0,    # HFT: engage trailing stop sooner
            trailing_distance_atr=1.5, # HFT: tighter trailing
            max_bars_held=120,         # 1-min bars: 2 hours max hold
            time_decay_start=60,       # start penalizing after 1 hour
            partial_tp_r=2.0,          # HFT: partial take-profit sooner
            partial_tp_pct=0.40,       # HFT: take 40% off at partial TP
        )
        self.learner = ContinuousLearner(
            signal_generator=self.signal_gen,
            retrain_every_n_bars=RETRAIN_INTERVAL,
            min_trades_for_eval=10,
            improvement_threshold=0.05,
        )
        self.regime_detector = RegimeDetector()
        self.governance = GovernanceController()
        self.evolution_engine = EvolutionEngine(
            alpha=0.30,
            max_shift=0.20,
            min_trades=8,
        )
        self.evolved_params = EvolvedParams()

        # ── Dynamic Universe Selector (Phase 4.1) ──────────────
        self.universe_selector = DynamicUniverseSelector(
            seed_symbols=list(self._universe),
        )

        # ── Market Scanner (Phase 5) ───────────────────────────
        self.market_scanner: MarketScanner | None = (
            MarketScanner() if SCANNER_ENABLED else None
        )
        self._scanner_candidates: list[str] = []

        # ── Brain persistence ────────────────────────────────────
        self.brain = OrganismBrain(brain_dir=brain_dir)

        # ── Transfer Learning Engine (Phase 4.7) ─────────────────
        self.transfer_engine = TransferLearningEngine(brain_dir=brain_dir)

        # ── Versioned Feature Store (Phase 3.3) ────────────────
        self._feature_store: Any = None
        if sessionmaker:
            try:
                from backend.organism.feature_store import VersionedFeatureStore
                self._feature_store = VersionedFeatureStore(
                    sessionmaker=sessionmaker,
                )
                logger.info(
                    "VersionedFeatureStore enabled (hash=%s)",
                    self._feature_store.config_hash,
                )
            except Exception as e:
                logger.debug("VersionedFeatureStore not available: %s", e)

        # ── Live state ──────────────────────────────────────────
        self._tick_count: int = 0
        self._bars_since_retrain: int = 0
        self._all_trades: list[TradeRecord] = []
        self._equity_curve: list[float] = []
        self._epoch_metrics: list[dict[str, Any]] = []
        self._peak_equity: float = 0.0
        self._initialized: bool = False

        # Track positions for exit and pyramid management
        # Maps symbol → ExitLevels (from exit engine)
        self._exit_levels: dict[str, Any] = {}
        # Maps symbol → PyramidPosition
        self._pyramid_positions: dict[str, PyramidPosition] = {}
        # Maps symbol → entry metadata for TradeRecord creation
        self._entry_metadata: dict[str, dict[str, Any]] = {}
        # Symbols with recent exit orders — cooldown prevents wash trade rejections
        # Maps symbol → tick number when exit was submitted
        self._exit_cooldown: dict[str, int] = {}
        self._EXIT_COOLDOWN_TICKS = 3  # Wait 3 ticks (~30s) before re-entering

        # Serialize live_tick() calls to prevent concurrent state mutation
        # (scheduler loop + manual /tick endpoint)
        self._tick_lock = asyncio.Lock()

        # ── Background trainer for non-blocking retraining ────────
        self._bg_trainer = BackgroundTrainer()
        self._bg_training_metadata: dict[str, Any] = {}

    # ═════════════════════════════════════════════════════════════
    #  INITIALIZATION / SHUTDOWN
    # ═════════════════════════════════════════════════════════════

    async def initialize(self) -> bool:
        """Load brain and warm up ML models.

        Returns True if brain was loaded (continuing from previous run).
        """
        brain_loaded = self.brain.load() if self.brain.exists else False

        if brain_loaded:
            # Restore ML models
            ml_ok = self.brain.apply_to_signal_generator(self.signal_gen)
            lr_ok = self.brain.apply_to_learner(self.learner)

            # Restore evolved params (Phase 1.1 — own file)
            if self.brain.evolved_params:
                self.evolved_params = EvolvedParams.from_dict(
                    self.brain.evolved_params
                )
                apply_evolved_params(
                    self.evolved_params,
                    alpha_scanner=self.alpha_scanner,
                    breakout_scanner=self.breakout_scanner,
                    kelly_sizer=self.kelly_sizer,
                    exit_engine=self.exit_engine,
                    signal_gen=self.signal_gen,
                )
                if self.evolved_params.feature_weights:
                    self.signal_gen._evolved_feature_weights = (
                        self.evolved_params.feature_weights
                    )

            # Restore governance & regime (Phase 1.2-1.3)
            self.brain.apply_governance_state(self.governance)
            self.brain.apply_regime_state(self.regime_detector)

            # Restore universe selector (Phase 4.1)
            us_data = self.brain.extra_counters.get("universe_selector")
            if us_data and isinstance(us_data, dict):
                self.universe_selector = DynamicUniverseSelector.from_dict(
                    us_data, seed_symbols=list(self._universe),
                )
                restored_universe = self.universe_selector.active_universe
                if restored_universe:
                    self._universe = restored_universe
                    logger.info(
                        "Universe selector restored: %d symbols",
                        len(self._universe),
                    )

            # Restore cumulative data
            prev_trades = self.brain.get_trade_records()
            if prev_trades:
                self._all_trades = prev_trades
            if self.brain.equity_curve:
                self._equity_curve = list(self.brain.equity_curve)
            if self.brain.epoch_metrics:
                self._epoch_metrics = list(self.brain.epoch_metrics)
            self._peak_equity = self.brain.extra_counters.get(
                "peak_equity", 0.0
            )

            # Validate brain
            warnings = self.brain.validate_brain()
            for w in warnings:
                logger.warning("Brain validation: %s", w)

            logger.info(
                "Organism live engine initialized from brain: "
                "gen=%d, trades=%d",
                self.brain.generation,
                len(self._all_trades),
            )
        else:
            logger.info("Organism live engine starting fresh (no brain)")

        # ── Phase 4.7: Transfer learning warm-start ──────────────
        try:
            tk_loaded = self.transfer_engine.load_knowledge()
            if tk_loaded:
                current_regime = self.regime_detector.current_regime
                if current_regime == RegimeLabel.UNKNOWN:
                    current_regime = "normal"
                self.evolved_params = self.transfer_engine.warm_start_params(
                    self.evolved_params,
                    current_regime=current_regime,
                )
                # Push warm-started params to components
                apply_evolved_params(
                    self.evolved_params,
                    alpha_scanner=self.alpha_scanner,
                    breakout_scanner=self.breakout_scanner,
                    kelly_sizer=self.kelly_sizer,
                    exit_engine=self.exit_engine,
                    signal_gen=self.signal_gen,
                )
                logger.info(
                    "Transfer learning applied: %d historical runs",
                    len(self.transfer_engine.knowledge.snapshots),
                )
        except Exception as e:
            logger.debug("Transfer learning warm-start skipped: %s", e)

        # Reconstruct live positions → exit levels + pyramid state
        await self._reconstruct_position_state()

        # Start background trainer
        await self._bg_trainer.start()

        self._initialized = True
        return brain_loaded

    async def shutdown(self) -> None:
        """Save brain state on graceful shutdown."""
        if not self._initialized:
            return
        self._save_brain()
        # Clean up background trainer
        await self._bg_trainer.stop()
        # Clean up market scanner
        if self.market_scanner is not None:
            await self.market_scanner.close()
        logger.info("Organism live engine shut down — brain saved")

    # ═════════════════════════════════════════════════════════════
    #  MAIN LIVE TICK
    # ═════════════════════════════════════════════════════════════

    async def live_tick(self) -> LiveTickResult:
        """Execute one full organism cycle — called every bar interval.

        Steps:
            1. Governance check
            2. Fetch latest data
            3. Compute features
            4. Detect regime
            5. Check exits on existing positions
            6. Check pyramids on existing positions
            7. Scan for new entries (breakout + ML + alpha)
            8. Size positions (Kelly)
            9. Submit entry orders
            10. Record trade outcomes from recent fills
            11. Periodic retrain + evolve
            12. Brain save (periodic checkpoint)
        """
        async with self._tick_lock:
            return await self._live_tick_inner()

    async def _live_tick_inner(self) -> LiveTickResult:
        """Inner tick logic — always called under _tick_lock."""
        t0 = time.time()
        result = LiveTickResult(
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._tick_count += 1
        # Expire old cooldowns (keep only recent exits)
        self._exit_cooldown = {
            sym: tick for sym, tick in self._exit_cooldown.items()
            if self._tick_count - tick < self._EXIT_COOLDOWN_TICKS
        }

        try:
            now_iso = result.timestamp

            # 1. GOVERNANCE CHECK
            if self.governance.is_trading_halted:
                result.errors.append("Trading halted by governance")
                result.activity.append(ActivityEvent(
                    event_type="skip", message="Trading halted by governance kill-switch",
                    timestamp=now_iso,
                ))
                result.duration_s = time.time() - t0
                return result

            # 1.5 MARKET SCAN (Phase 5) — discover new stocks
            if (
                self.market_scanner is not None
                and self._tick_count % SCAN_INTERVAL_TICKS == 0
            ):
                try:
                    new_candidates = await self.market_scanner.scan()
                    if new_candidates:
                        self._scanner_candidates = new_candidates
                        # Temporarily add top scanner picks to universe for this tick
                        scanner_additions = [
                            s for s in new_candidates[:20]
                            if s not in self._universe
                        ]
                        if scanner_additions:
                            self._universe = list(self._universe) + scanner_additions
                            logger.info(
                                "Scanner injected %d symbols into universe (total: %d)",
                                len(scanner_additions),
                                len(self._universe),
                            )
                        result.activity.append(ActivityEvent(
                            event_type="scanner",
                            message=f"Market scan found {len(new_candidates)} candidates",
                            details={
                                "top_5": new_candidates[:5],
                                "new_additions": scanner_additions[:10],
                                "total_candidates": len(new_candidates),
                            },
                            timestamp=now_iso,
                        ))
                except Exception as e:
                    logger.warning("Market scan failed: %s", e)

            # 2. FETCH LATEST DATA
            features_by_symbol = await self._fetch_and_compute_features()
            if len(features_by_symbol) < 3:
                result.errors.append(
                    f"Insufficient data: got {len(features_by_symbol)} symbols"
                )
                result.duration_s = time.time() - t0
                return result

            # 3. DETECT REGIME (Phase 4.3: cross-asset conditioning)
            spy_features = features_by_symbol.get("SPY")
            sector_features = {
                sym: features_by_symbol[sym]
                for sym in self.regime_detector.SECTOR_ETFS
                if sym in features_by_symbol
                and len(features_by_symbol[sym]) >= 10
            }

            if sector_features:
                regime_state = self.regime_detector.detect_cross_asset_regime(
                    features_by_symbol, sector_features=sector_features,
                )
            elif spy_features is not None and len(spy_features) >= 10:
                regime_state = self.regime_detector.detect(spy_features)
            else:
                regime_state = self.regime_detector.detect_market_regime(
                    features_by_symbol
                )
            regime = regime_state.primary
            result.regime = regime
            result.activity.append(ActivityEvent(
                event_type="regime",
                message=f"Market regime: {regime}",
                details={"regime": regime, "tick": self._tick_count},
                timestamp=now_iso,
            ))

            # 4. GET CURRENT POSITIONS from broker
            current_positions = await self._positions_service.get_all_positions()
            open_symbols = set(current_positions.keys())
            equity = await self._get_equity()
            self._peak_equity = max(self._peak_equity, equity)

            # Check drawdown — skip when equity is 0 (broker unavailable / cold-start)
            if self._peak_equity > 0 and equity > 0:
                drawdown = (self._peak_equity - equity) / self._peak_equity
                self.governance.trigger_drawdown_kill(drawdown)
                if self.governance.is_trading_halted:
                    result.errors.append("Drawdown kill triggered")
                    result.duration_s = time.time() - t0
                    return result
            elif equity == 0:
                self.logger.error("equity_returned_zero — halting to prevent unprotected trading")
                result.errors.append("Equity is zero — cannot compute drawdown. Trading halted.")
                result.duration_s = time.time() - t0
                return result

            # 5. CHECK EXITS on existing positions
            exits_submitted = 0
            for sym, pos_data in current_positions.items():
                feat_df = features_by_symbol.get(sym)
                if feat_df is None or len(feat_df) < 1:
                    continue

                result.exits_checked += 1
                exit_levels = self._exit_levels.get(sym)
                if exit_levels is None:
                    continue

                current_price = float(feat_df["close"].iloc[-1])
                exit_sig = self.exit_engine.check_exit(
                    exit_levels, current_price, regime
                )

                if exit_sig.should_exit:
                    qty = abs(float(pos_data.get("qty", 0)))
                    if exit_sig.partial_exit:
                        sell_shares = max(1, int(qty * exit_sig.partial_pct))
                        if sell_shares >= qty:
                            sell_shares = int(qty)
                    else:
                        sell_shares = int(qty)

                    if sell_shares > 0:
                        try:
                            _dir = getattr(exit_levels, "direction", 1.0)
                            await self._submit_exit_order(
                                sym, sell_shares, exit_sig.reason, direction=_dir
                            )
                            self._exit_cooldown[sym] = self._tick_count
                            exits_submitted += 1
                            result.activity.append(ActivityEvent(
                                event_type="exit",
                                symbol=sym,
                                message=f"EXIT: {sym} — {exit_sig.reason} "
                                        f"({'partial' if exit_sig.partial_exit else 'full'} "
                                        f"{sell_shares} shares)",
                                details={
                                    "reason": exit_sig.reason,
                                    "shares": sell_shares,
                                    "partial": exit_sig.partial_exit,
                                },
                                timestamp=now_iso,
                            ))
                        except Exception as e:
                            result.errors.append(
                                f"Exit order failed for {sym}: {e}"
                            )
            result.trades_closed = exits_submitted

            # 6. CHECK PYRAMIDS
            for sym, pos_data in current_positions.items():
                pyr = self._pyramid_positions.get(sym)
                if pyr is None:
                    continue
                feat_df = features_by_symbol.get(sym)
                if feat_df is None or len(feat_df) < 1:
                    continue

                current_price = float(feat_df["close"].iloc[-1])
                action = self.pyramider.check_pyramid(pyr, current_price)

                if action.action == "add" and action.shares_to_add > 0:
                    if sym in self._exit_cooldown:
                        continue  # Don't pyramid a symbol with pending exit
                    try:
                        await self._submit_entry_order(
                            sym,
                            action.shares_to_add,
                            confidence=0.7,
                            reason="pyramid_add",
                        )
                    except Exception as e:
                        result.errors.append(
                            f"Pyramid order failed for {sym}: {e}"
                        )

            # 7. SCAN FOR NEW ENTRIES
            # Breakout scan
            data_for_scanner = {
                sym: df
                for sym, df in features_by_symbol.items()
                if len(df) >= 20
            }
            spy_slice = features_by_symbol.get("SPY")
            breakout_signals = self.breakout_scanner.scan(
                data_for_scanner, spy_slice
            )
            breakout_by_sym = {s.symbol: s for s in breakout_signals}

            # ML predictions
            ml_signals = self.signal_gen.predict_batch(features_by_symbol)

            # Alpha scan
            candidates = self.alpha_scanner.scan(
                features_by_symbol, ml_signals, regime
            )

            # Build candidate list
            # Build tension lookup from scanner
            _tension_lookup: dict[str, float] = {}
            if self.market_scanner is not None:
                for ss in self.market_scanner.scanned_stocks:
                    _tension_lookup[ss.symbol] = ss.tension_score

            cand_dicts = []
            for c in candidates:
                if c.symbol in open_symbols:
                    continue
                if c.symbol in self._exit_cooldown:
                    continue  # Wash trade cooldown
                if LONG_ONLY and not self.evolved_params.shorts_enabled and c.direction < 0:
                    continue

                bs = breakout_by_sym.get(c.symbol)
                breakout_score = bs.composite_score if bs else 0.0
                tension = _tension_lookup.get(c.symbol, 0.0)
                confidence = (
                    (c.ml_signal.confidence if c.ml_signal else 0.5)
                    * (1.0 + breakout_score)
                    * (1.0 + tension * 0.5)  # Phase 5: scanner tension boost
                )
                cand_dicts.append({
                    "symbol": c.symbol,
                    "direction": c.direction,
                    "predicted_return": (
                        c.ml_signal.predicted_return if c.ml_signal else 0.01
                    ),
                    "confidence": min(confidence, 1.0),
                    "breakout_score": breakout_score,
                })

            # Pure breakout signals not in alpha candidates
            alpha_syms = {d["symbol"] for d in cand_dicts}
            for bs in breakout_signals:
                if (
                    bs.symbol not in alpha_syms
                    and bs.symbol not in open_symbols
                    and bs.symbol not in self._exit_cooldown
                    and bs.composite_score >= 0.55
                ):
                    ml_sig = ml_signals.get(bs.symbol)
                    if ml_sig and ml_sig.direction < 0:
                        continue
                    cand_dicts.append({
                        "symbol": bs.symbol,
                        "direction": 1.0,
                        "predicted_return": (
                            ml_sig.predicted_return if ml_sig else 0.02
                        ),
                        "confidence": min(bs.composite_score, 1.0),
                        "breakout_score": bs.composite_score,
                    })

            cand_dicts.sort(
                key=lambda x: x["breakout_score"] * x["confidence"],
                reverse=True,
            )

            open_slots = MAX_OPEN_POSITIONS - len(open_symbols)
            cand_dicts = cand_dicts[: max(0, open_slots)]
            result.signals_generated = len(cand_dicts)

            # Log signal activity
            for cd in cand_dicts[:10]:
                result.activity.append(ActivityEvent(
                    event_type="signal",
                    symbol=cd["symbol"],
                    message=f"{'BUY' if cd['direction'] > 0 else 'SELL'} signal: {cd['symbol']} "
                            f"(confidence={cd['confidence']:.2f}, breakout={cd['breakout_score']:.2f})",
                    details=cd,
                    timestamp=now_iso,
                ))

            # 8. SIZE POSITIONS (Kelly)
            drawdown = (
                (self._peak_equity - equity) / self._peak_equity
                if self._peak_equity > 0
                else 0
            )
            sizes = self.kelly_sizer.size_positions(
                cand_dicts, equity, drawdown, features_by_symbol, regime
            )

            # 9. SUBMIT ENTRY ORDERS
            for sz in sizes:
                initial_shares = self.pyramider.initial_shares(sz.shares)
                if initial_shares < 1:
                    initial_shares = sz.shares
                try:
                    order_result = await self._submit_entry_order(
                        sz.symbol,
                        initial_shares,
                        direction=sz.direction,
                        confidence=getattr(sz, "confidence", 0.6),
                        reason="organism_entry",
                    )

                    # Use filled qty from broker response when available
                    # (IOC orders may partially fill)
                    filled_shares = initial_shares
                    if isinstance(order_result, dict):
                        filled = order_result.get("filled_qty") or order_result.get("filled_avg_price") and initial_shares
                        if filled:
                            filled_shares = max(1, int(float(filled)))

                    result.orders_submitted += 1
                    result.activity.append(ActivityEvent(
                        event_type="order",
                        symbol=sz.symbol,
                        message=f"ORDER SUBMITTED: {'BUY' if sz.direction >= 0 else 'SELL'} "
                                f"{filled_shares} shares of {sz.symbol}",
                        details={
                            "shares_requested": initial_shares,
                            "shares_filled": filled_shares,
                            "direction": sz.direction,
                            "confidence": getattr(sz, "confidence", 0.6),
                        },
                        timestamp=now_iso,
                    ))

                    # Create exit levels for the new position
                    feat_df = features_by_symbol.get(sz.symbol)
                    if feat_df is not None and len(feat_df) > 0:
                        price = float(feat_df["close"].iloc[-1])
                        predicted_return = 0.01
                        if self.signal_gen.is_trained:
                            sig = self.signal_gen.predict(feat_df, sz.symbol)
                            if sig:
                                predicted_return = abs(sig.predicted_return)

                        exit_lvl = self.exit_engine.create_exit_levels(
                            symbol=sz.symbol,
                            direction=sz.direction,
                            entry_price=price,
                            predicted_return=predicted_return,
                            features_df=feat_df,
                            regime=regime,
                        )
                        self._exit_levels[sz.symbol] = exit_lvl

                        # Create pyramid tracker using filled shares
                        atr = exit_lvl.atr_at_entry
                        self._pyramid_positions[sz.symbol] = PyramidPosition(
                            symbol=sz.symbol,
                            direction=sz.direction,
                            layers=[
                                PyramidLevel(
                                    shares=filled_shares,
                                    entry_price=price,
                                    bar_added=self._tick_count,
                                    level=0,
                                )
                            ],
                            target_total_shares=sz.shares,
                            atr_at_entry=atr,
                            initial_stop=exit_lvl.stop_loss,
                            current_stop=exit_lvl.stop_loss,
                            highest_price=price,
                            lowest_price=price,
                        )

                        # Track entry metadata for TradeRecord
                        self._entry_metadata[sz.symbol] = {
                            "entry_price": price,
                            "entry_tick": self._tick_count,
                            "direction": sz.direction,
                            "predicted_return": predicted_return,
                            "confidence": 0.6,
                        }

                except Exception as e:
                    result.errors.append(
                        f"Entry order failed for {sz.symbol}: {e}"
                    )

            # 10. RECORD TRADE OUTCOMES from closed positions
            await self._reconcile_fills(features_by_symbol)

            # 11. PERIODIC RETRAIN + EVOLVE (non-blocking background training)
            self._bars_since_retrain += 1

            # Check if previous background training completed
            if self._bg_trainer.is_training:
                done, train_result = self._bg_trainer.get_result()
                if done and train_result and train_result.accepted:
                    self.evolved_params = self._bg_trainer.apply_result(
                        signal_gen=self.signal_gen,
                        evolution_engine=self.evolution_engine,
                        evolved_params=self.evolved_params,
                        alpha_scanner=self.alpha_scanner,
                        breakout_scanner=self.breakout_scanner,
                        kelly_sizer=self.kelly_sizer,
                        exit_engine=self.exit_engine,
                    )
                    self._bg_training_metadata = {
                        "status": "completed",
                        "accepted": train_result.accepted,
                        "duration_s": train_result.duration_s,
                        "last_trained_tick": self._tick_count,
                    }
                    self.governance.record_change()
                    result.activity.append(ActivityEvent(
                        event_type="retrain",
                        message=f"Background training completed (gen={self.evolved_params.evolution_generation}, "
                                f"duration={train_result.duration_s:.1f}s)",
                        details={
                            "generation": self.evolved_params.evolution_generation,
                            "total_trades": len(self._all_trades),
                            "is_trained": self.signal_gen.is_trained,
                            "background": True,
                            "duration_s": train_result.duration_s,
                        },
                        timestamp=now_iso,
                    ))
                elif done and train_result:
                    self._bg_training_metadata = {
                        "status": "rejected",
                        "error": train_result.error,
                        "last_trained_tick": self._tick_count,
                    }
            elif self._bars_since_retrain >= RETRAIN_INTERVAL:
                self._bars_since_retrain = 0
                try:
                    await self._bg_trainer.submit_retrain(
                        features_by_symbol=features_by_symbol,
                        regime=regime,
                        trades=self._all_trades,
                        signal_gen=self.signal_gen,
                        evolution_engine=self.evolution_engine,
                        evolved_params=self.evolved_params,
                    )
                    self._bg_training_metadata["status"] = "training"
                    result.activity.append(ActivityEvent(
                        event_type="retrain",
                        message=f"Background training submitted (trades={len(self._all_trades)})",
                        details={
                            "total_trades": len(self._all_trades),
                            "background": True,
                        },
                        timestamp=now_iso,
                    ))
                except Exception as e:
                    # Fallback to synchronous training
                    logger.warning("Background training failed, falling back to sync: %s", e)
                    self._retrain_and_evolve(features_by_symbol, regime)
                    result.activity.append(ActivityEvent(
                        event_type="retrain",
                        message=f"ML model retrained synchronously (gen={self.evolved_params.evolution_generation})",
                        details={
                            "generation": self.evolved_params.evolution_generation,
                            "total_trades": len(self._all_trades),
                            "is_trained": self.signal_gen.is_trained,
                            "background": False,
                        },
                        timestamp=now_iso,
                    ))

            # 12. BRAIN SAVE (every 50 ticks — disk I/O is expensive at HFT speeds)
            if self._tick_count % 50 == 0:
                await asyncio.to_thread(self._save_brain)
                result.brain_saved = True

            # Phase 5: Populate scanner/universe metadata
            result.universe_size = len(self._universe)
            result.scanner_candidates_count = len(self._scanner_candidates)
            result.scanner_ran = (
                self.market_scanner is not None
                and self._tick_count % SCAN_INTERVAL_TICKS == 0
            )

            # Training metadata for dashboard visibility
            result.training_status = self._bg_training_metadata.get("status", "")
            result.training_metadata = dict(self._bg_training_metadata)

        except Exception as e:
            logger.exception("Organism live tick failed")
            result.errors.append(f"Live tick error: {e}")

        # Update equity curve
        try:
            eq = await self._get_equity()
            self._equity_curve.append(eq)
        except Exception:
            pass

        result.duration_s = time.time() - t0

        # ── Phase 3.5: Export Prometheus metrics ─────────────────
        if _PROMETHEUS_AVAILABLE:
            ORGANISM_TICK_DURATION.observe(result.duration_s)
            ORGANISM_GENERATION.set(self.evolved_params.evolution_generation)
            ORGANISM_TOTAL_TRADES.set(len(self._all_trades))
            ORGANISM_ORDERS_SUBMITTED.inc(result.orders_submitted)
            if result.errors:
                ORGANISM_ERRORS.inc(len(result.errors))
            # Direction accuracy from signal gen
            if (
                self.signal_gen.is_trained
                and hasattr(self.signal_gen, "_latest_metrics")
                and self.signal_gen._latest_metrics
            ):
                ORGANISM_DIRECTION_ACCURACY.set(
                    self.signal_gen._latest_metrics.direction_accuracy
                )
            # Sharpe from brain manifest
            manifest = getattr(self.brain, "_manifest", None) or {}
            best_sharpe = manifest.get("best_sharpe", 0)
            if isinstance(best_sharpe, (int, float)) and np.isfinite(best_sharpe):
                ORGANISM_SHARPE.set(best_sharpe)

        return result

    # ═════════════════════════════════════════════════════════════
    #  DATA PIPELINE
    # ═════════════════════════════════════════════════════════════

    async def _fetch_and_compute_features(
        self,
    ) -> dict[str, pd.DataFrame]:
        """Fetch latest bars and compute ML features for the universe.

        Uses VersionedFeatureStore when available (Phase 3.3),
        falling back to raw compute_ml_features otherwise.
        Phase 5: Handles larger dynamic universe with concurrency control.
        """
        features_by_symbol: dict[str, pd.DataFrame] = {}
        spy_df = None
        _concurrency = asyncio.Semaphore(10)  # Max 10 parallel bar fetches
        _streaming_active = self._streaming_provider is not None

        # Fetch SPY first (needed for cross-asset features)
        # When streaming, SPY is already buffered so this is instant
        spy_df = await self._fetch_bars("SPY")

        def _compute_features_sync(
            raw_df: pd.DataFrame, sym: str, spy_ref: pd.DataFrame | None,
        ) -> pd.DataFrame:
            """CPU-bound feature computation — runs in thread when streaming."""
            if self._feature_store is not None:
                feats, _snapshot = self._feature_store.compute_features(
                    raw_df, symbol=sym,
                )
                feats_ml = compute_ml_features(
                    raw_df,
                    spy_df=spy_ref if sym != "SPY" else None,
                )
                feats = feats.reset_index(drop=True)
                feats_ml = feats_ml.reset_index(drop=True)
                n_min = min(len(feats), len(feats_ml))
                feats = feats.iloc[-n_min:].reset_index(drop=True)
                feats_ml = feats_ml.iloc[-n_min:].reset_index(drop=True)
                for col in feats.columns:
                    if col not in feats_ml.columns:
                        feats_ml[col] = feats[col].values
                feats = feats_ml
            else:
                feats = compute_ml_features(
                    raw_df,
                    spy_df=spy_ref if sym != "SPY" else None,
                )
                feats = feats.reset_index(drop=True)

            # Preserve OHLCV columns
            n_feats = len(feats)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in raw_df.columns and col not in feats.columns:
                    feats[col] = raw_df[col].values[-n_feats:]

            # Phase 4.2: Multi-timeframe features
            feats = add_multi_timeframe_features(feats)
            return feats

        async def _fetch_one(sym: str) -> tuple[str, pd.DataFrame | None]:
            async with _concurrency:
                try:
                    if sym == "SPY" and spy_df is not None:
                        raw_df = spy_df
                    else:
                        raw_df = await self._fetch_bars(sym)

                    if raw_df is None or len(raw_df) < MIN_BARS:
                        return sym, None

                    # When streaming is active, offload CPU-bound work
                    # to a thread so the event loop stays responsive
                    if _streaming_active:
                        feats = await asyncio.to_thread(
                            _compute_features_sync, raw_df, sym, spy_df,
                        )
                    else:
                        feats = _compute_features_sync(raw_df, sym, spy_df)

                    return sym, feats
                except Exception as e:
                    logger.warning("Failed to fetch/compute %s: %s", sym, e)
                    return sym, None

        # Fetch all symbols concurrently (semaphore-limited)
        tasks = [_fetch_one(sym) for sym in self._universe]
        results = await asyncio.gather(*tasks)
        for sym, feats in results:
            if feats is not None:
                features_by_symbol[sym] = feats

        return features_by_symbol

    async def _fetch_bars(self, symbol: str) -> pd.DataFrame | None:
        """Fetch historical bars for a single symbol.

        When a streaming provider is active, returns bars from the
        in-memory ring buffer (zero latency).  Falls back to REST
        if streaming has no data for this symbol.

        Handles both sync clients (AlpacaClient) and async clients
        (AlpacaDataClient) transparently.
        """
        # ── Streaming fast-path ──────────────────────────────────
        if self._streaming_provider is not None:
            try:
                df = self._streaming_provider.get_bars(symbol, LIVE_LOOKBACK)
                if df is not None and not df.empty and len(df) >= MIN_BARS:
                    return df
                # Fall through to REST if streaming buffer insufficient
            except Exception as e:
                logger.debug("Streaming fallback for %s: %s", symbol, e)

        try:
            if hasattr(self._data_client, "get_historical_bars_df"):
                method = self._data_client.get_historical_bars_df
                if asyncio.iscoroutinefunction(method):
                    df = await method(
                        symbol,
                        lookback=LIVE_LOOKBACK,
                        timeframe=LIVE_TIMEFRAME,
                    )
                else:
                    df = await asyncio.to_thread(
                        method,
                        symbol,
                        lookback=LIVE_LOOKBACK,
                        timeframe=LIVE_TIMEFRAME,
                    )
            elif hasattr(self._data_client, "get_historical_data"):
                method = self._data_client.get_historical_data
                if asyncio.iscoroutinefunction(method):
                    df = await method(
                        symbol,
                        timeframe=LIVE_TIMEFRAME,
                        limit=LIVE_LOOKBACK,
                    )
                else:
                    df = await asyncio.to_thread(
                        method,
                        symbol,
                        timeframe=LIVE_TIMEFRAME,
                        limit=LIVE_LOOKBACK,
                    )
            else:
                return None

            if df is None or df.empty:
                return None

            # Normalize columns
            col_map = {
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            df = df.rename(columns=col_map)
            return df

        except Exception as e:
            logger.warning("Bar fetch failed for %s: %s", symbol, e)
            return None

    # ═════════════════════════════════════════════════════════════
    #  ORDER SUBMISSION
    # ═════════════════════════════════════════════════════════════

    async def _submit_entry_order(
        self,
        symbol: str,
        shares: int,
        direction: float = 1.0,
        confidence: float = 0.6,
        reason: str = "organism_entry",
    ) -> dict[str, Any]:
        """Submit an entry order via OrderService.

        Uses *direction* to decide the order side:
        direction >= 0 → buy, direction < 0 → sell (short).
        """
        side = "sell" if direction < 0 else "buy"
        idem_key = (
            f"organism_{symbol}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        )
        return await self._order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=shares,
            idempotency_key=idem_key,
            order_type="market",
            tif="ioc",
            attributes={
                "source": "organism",
                "reason": reason,
                "confidence": round(confidence, 4),
                "tick": self._tick_count,
            },
        )

    async def _submit_exit_order(
        self,
        symbol: str,
        shares: int,
        reason: str = "organism_exit",
        direction: float = 1.0,
    ) -> dict[str, Any]:
        """Submit an exit order via OrderService.

        For longs (direction > 0) we sell; for shorts (direction < 0) we buy-to-cover.
        """
        side = "buy" if direction < 0 else "sell"
        idem_key = (
            f"organism_exit_{symbol}"
            f"_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        )
        return await self._order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=shares,
            idempotency_key=idem_key,
            order_type="market",
            tif="ioc",
            attributes={
                "source": "organism",
                "reason": reason,
                "tick": self._tick_count,
            },
        )

    # ═════════════════════════════════════════════════════════════
    #  FILL RECONCILIATION (Phase 2.4)
    # ═════════════════════════════════════════════════════════════

    # Minimum ticks to wait after entry before reconciling a position
    # as "closed". Prevents race condition where order hasn't settled
    # at the broker yet when reconciliation runs on the same tick.
    _RECONCILE_GRACE_TICKS = 3

    async def _reconcile_fills(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> None:
        """Check for closed positions and create TradeRecords.

        Compares current broker positions with tracked entry metadata.
        If a position disappears (after a grace period to let orders
        settle), record it as a completed trade.

        Also detects orphaned broker positions (exist at broker but
        have no tracking metadata) and reconstructs tracking state
        so they can be properly managed.
        """
        try:
            current_positions = await self._positions_service.get_all_positions()
        except Exception:
            return

        # Cache for sync callers (e.g. _retrain_and_evolve universe rotation)
        self._last_positions = current_positions

        current_symbols = set(current_positions.keys())
        tracked_symbols = set(self._entry_metadata.keys())

        # Detect closed positions — but skip recently-entered positions
        # whose orders may not have settled at the broker yet.
        candidates = tracked_symbols - current_symbols
        closed = set()
        for sym in candidates:
            meta = self._entry_metadata.get(sym)
            if meta is None:
                continue
            entry_tick = meta.get("entry_tick", 0)
            ticks_held = self._tick_count - entry_tick
            if ticks_held < self._RECONCILE_GRACE_TICKS:
                # Order may still be settling — skip for now
                logger.debug(
                    "Skipping reconciliation for %s (entered %d ticks ago, "
                    "grace=%d)",
                    sym,
                    ticks_held,
                    self._RECONCILE_GRACE_TICKS,
                )
                continue
            closed.add(sym)

        for sym in closed:
            meta = self._entry_metadata.pop(sym, None)
            if meta is None:
                continue

            # Get last known price for exit
            feat_df = features_by_symbol.get(sym)
            exit_price = meta["entry_price"]  # fallback
            if feat_df is not None and len(feat_df) > 0:
                exit_price = float(feat_df["close"].iloc[-1])

            direction = meta.get("direction", 1.0)
            entry_price = meta["entry_price"]
            shares = 0
            pyr = self._pyramid_positions.get(sym)
            if pyr:
                shares = sum(l.shares for l in pyr.layers)

            if shares == 0:
                shares = 1  # at minimum

            if direction > 0:
                pnl = (exit_price - entry_price) * shares
            else:
                pnl = (entry_price - exit_price) * shares

            actual_return = (
                (exit_price - entry_price) / entry_price * direction
                if entry_price > 0
                else 0
            )

            trade = TradeRecord(
                symbol=sym,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_bar=meta.get("entry_tick", 0),
                exit_bar=self._tick_count,
                shares=shares,
                pnl=pnl,
                exit_reason="live_close",
                predicted_return=meta.get("predicted_return", 0),
                actual_return=actual_return,
                confidence=meta.get("confidence", 0),
            )
            self._all_trades.append(trade)
            self.learner.record_trade(trade)

            # Clean up tracking state
            self._exit_levels.pop(sym, None)
            self._pyramid_positions.pop(sym, None)

            logger.info(
                "Trade recorded: %s %s PnL=$%.2f",
                sym,
                "LONG" if direction > 0 else "SHORT",
                pnl,
            )

        # Detect orphaned broker positions — positions that exist at the
        # broker but have no tracking metadata.  This happens when entry
        # metadata was lost (e.g. engine restart without reconstruction,
        # or a previous phantom-close bug deleted the metadata while the
        # real fill was still pending).  Re-create tracking so exit logic
        # and pyramid management can work.
        orphaned = current_symbols - tracked_symbols
        for sym in orphaned:
            # Don't adopt positions that we're actively exiting
            if sym in self._exit_levels:
                continue
            pos = current_positions[sym]
            qty = abs(float(pos.get("qty", 0)))
            avg_entry = float(pos.get("avg_entry_price", 0))
            if qty <= 0 or avg_entry <= 0:
                continue

            side = pos.get("side", "long")
            direction = 1.0 if side == "long" else -1.0

            # Re-create entry metadata so reconciliation can track it
            self._entry_metadata[sym] = {
                "entry_price": avg_entry,
                "entry_tick": self._tick_count,
                "direction": direction,
                "predicted_return": 0.01,
                "confidence": 0.5,
            }

            # Try to create exit levels for proper management
            feat_df = features_by_symbol.get(sym)
            if feat_df is not None and len(feat_df) > 10:
                try:
                    exit_lvl = self.exit_engine.create_exit_levels(
                        symbol=sym,
                        direction=direction,
                        entry_price=avg_entry,
                        predicted_return=0.02,
                        features_df=feat_df,
                        regime=RegimeLabel.UNKNOWN,
                    )
                    self._exit_levels[sym] = exit_lvl

                    atr = exit_lvl.atr_at_entry
                    self._pyramid_positions[sym] = PyramidPosition(
                        symbol=sym,
                        direction=direction,
                        layers=[
                            PyramidLevel(
                                shares=int(qty),
                                entry_price=avg_entry,
                                bar_added=self._tick_count,
                                level=0,
                            )
                        ],
                        target_total_shares=int(qty * 1.5),
                        atr_at_entry=atr,
                        initial_stop=exit_lvl.stop_loss,
                        current_stop=exit_lvl.stop_loss,
                        highest_price=avg_entry,
                        lowest_price=avg_entry,
                    )
                except Exception as e:
                    logger.debug("Cannot create exit levels for orphaned %s: %s", sym, e)

            logger.info(
                "Adopted orphaned broker position: %s %s %d shares @ $%.2f",
                sym,
                "LONG" if direction > 0 else "SHORT",
                int(qty),
                avg_entry,
            )

    # ═════════════════════════════════════════════════════════════
    #  POSITION STATE RECONSTRUCTION (Phase 2.5)
    # ═════════════════════════════════════════════════════════════

    async def _reconstruct_position_state(self) -> None:
        """On startup, reconstruct exit levels and pyramid state
        from live broker positions.

        This handles the case where the engine restarts mid-trade.
        """
        try:
            positions = await self._positions_service.get_all_positions()
        except Exception as e:
            logger.warning("Cannot reconstruct positions: %s", e)
            return

        if not positions:
            return

        for sym, pos_data in positions.items():
            qty = abs(float(pos_data.get("qty", 0)))
            avg_entry = float(pos_data.get("avg_entry_price", 0))
            side = pos_data.get("side", "long")
            direction = 1.0 if side == "long" else -1.0

            if qty <= 0 or avg_entry <= 0:
                continue

            # Create basic exit levels (conservative defaults)
            try:
                feat_df = None
                if hasattr(self._data_client, "get_historical_data"):
                    raw = await asyncio.to_thread(
                        self._data_client.get_historical_data,
                        sym, timeframe=LIVE_TIMEFRAME, limit=100,
                    )
                    if raw is not None and not raw.empty:
                        col_map = {
                            "Open": "open", "High": "high",
                            "Low": "low", "Close": "close",
                            "Volume": "volume",
                        }
                        feat_df = raw.rename(columns=col_map)

                if feat_df is not None and len(feat_df) > 10:
                    exit_lvl = self.exit_engine.create_exit_levels(
                        symbol=sym,
                        direction=direction,
                        entry_price=avg_entry,
                        predicted_return=0.02,
                        features_df=feat_df,
                        regime=RegimeLabel.UNKNOWN,
                    )
                    self._exit_levels[sym] = exit_lvl

                    atr = exit_lvl.atr_at_entry
                    self._pyramid_positions[sym] = PyramidPosition(
                        symbol=sym,
                        direction=direction,
                        layers=[
                            PyramidLevel(
                                shares=int(qty),
                                entry_price=avg_entry,
                                bar_added=0,
                                level=0,
                            )
                        ],
                        target_total_shares=int(qty * 1.5),
                        atr_at_entry=atr,
                        initial_stop=exit_lvl.stop_loss,
                        current_stop=exit_lvl.stop_loss,
                        highest_price=avg_entry,
                        lowest_price=avg_entry,
                    )

                    self._entry_metadata[sym] = {
                        "entry_price": avg_entry,
                        "entry_tick": 0,
                        "direction": direction,
                        "predicted_return": 0.02,
                        "confidence": 0.5,
                    }

                    logger.info(
                        "Reconstructed position state for %s: "
                        "%d shares @ $%.2f",
                        sym,
                        int(qty),
                        avg_entry,
                    )

            except Exception as e:
                logger.debug("Cannot reconstruct %s: %s", sym, e)

    # ═════════════════════════════════════════════════════════════
    #  RETRAIN & EVOLVE
    # ═════════════════════════════════════════════════════════════

    def _retrain_and_evolve(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        regime: str,
    ) -> None:
        """Retrain ML model and run self-evolution on accumulated trades."""
        # Retrain
        accepted, train_metrics = self.learner.retrain(features_by_symbol)
        if train_metrics:
            logger.info(
                "Retrained: accuracy=%.3f, accepted=%s",
                train_metrics.accuracy,
                accepted,
            )

        self.learner.compute_attribution()

        # Evolve
        recent_trades = self._all_trades[-200:]  # last 200 trades
        if recent_trades:
            fi = self.signal_gen._get_feature_importance()
            self.evolved_params = self.evolution_engine.evolve(
                params=self.evolved_params,
                trades=recent_trades,
                feature_importances=fi if fi else None,
                epoch_regime=regime,
                all_feature_names=list(FEATURE_COLUMNS),
            )
            apply_evolved_params(
                self.evolved_params,
                alpha_scanner=self.alpha_scanner,
                breakout_scanner=self.breakout_scanner,
                kelly_sizer=self.kelly_sizer,
                exit_engine=self.exit_engine,
                signal_gen=self.signal_gen,
            )
            if self.evolved_params.feature_weights:
                self.signal_gen._evolved_feature_weights = (
                    self.evolved_params.feature_weights
                )

            self.governance.record_change()

        # Phase 4.1 — Dynamic universe rotation
        try:
            current_positions = {}
            try:
                pos_coro = self._positions_service.get_all_positions()
                if asyncio.iscoroutine(pos_coro):
                    # We're in a sync method — try to get the running loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Schedule and don't block: use cached positions instead
                        current_positions = getattr(self, "_last_positions", {})
                    else:
                        current_positions = loop.run_until_complete(pos_coro)
                else:
                    current_positions = pos_coro or {}
            except Exception:
                current_positions = getattr(self, "_last_positions", {})
            open_syms = set(current_positions.keys())
            new_universe = self.universe_selector.rotate(
                trades=recent_trades,
                candidate_pool=self._scanner_candidates or None,
                open_positions=open_syms,
                generation=self.evolved_params.evolution_generation,
            )
            if set(new_universe) != set(self._universe):
                logger.info(
                    "Universe rotated: %d → %d symbols",
                    len(self._universe),
                    len(new_universe),
                )
                self._universe = new_universe
        except Exception as e:
            logger.debug("Universe rotation skipped: %s", e)

    # ═════════════════════════════════════════════════════════════
    #  BRAIN PERSISTENCE
    # ═════════════════════════════════════════════════════════════

    def _save_brain(self) -> None:
        """Save full brain state to disk (with walk-forward gate)."""
        try:
            # Walk-forward gate: skip save if regression detected
            should_save, reason = self.brain.walk_forward_gate(
                self._all_trades[-100:],  # evaluate on last 100 trades
                min_trades=10,
                regression_threshold=0.95,
            )
            if not should_save:
                logger.warning(
                    "Brain save SKIPPED by walk-forward gate: %s", reason
                )
                return

            self.brain.save(
                signal_gen=self.signal_gen,
                learner=self.learner,
                equity_curve=self._equity_curve,
                all_trades=self._all_trades,
                epoch_metrics=self._epoch_metrics,
                peak_equity=self._peak_equity,
                extra_counters={
                    "tick_count": self._tick_count,
                    "bars_since_retrain": self._bars_since_retrain,
                    "universe_selector": self.universe_selector.to_dict(),
                },
                evolved_params=self.evolved_params.to_dict(),
                governance_controller=self.governance,
                regime_detector=self.regime_detector,
            )
            logger.info(
                "Brain saved at tick %d (%s)", self._tick_count, reason
            )

            # Phase 4.7 — Record run into transfer knowledge
            try:
                fi = self.signal_gen._get_feature_importance()
                current_regime = self.regime_detector.current_regime
                if current_regime == RegimeLabel.UNKNOWN:
                    current_regime = "normal"
                self.transfer_engine.record_run(
                    evolved_params=self.evolved_params,
                    trades=self._all_trades[-200:],
                    epoch_metrics=self._epoch_metrics,
                    feature_importances=fi if fi else None,
                    regime=current_regime,
                )
                self.transfer_engine.save_knowledge()
            except Exception as te:
                logger.debug("Transfer knowledge save skipped: %s", te)
        except Exception as e:
            logger.error("Brain save failed: %s", e)

    # ═════════════════════════════════════════════════════════════
    #  HELPERS
    # ═════════════════════════════════════════════════════════════

    async def _get_equity(self) -> float:
        """Get current portfolio equity from broker."""
        try:
            value = await self._positions_service.get_total_portfolio_value()
            return float(value) if value else 0.0
        except Exception:
            try:
                bp = await self._positions_service.get_buying_power()
                return float(bp) if bp else 0.0
            except Exception:
                return 0.0

    def status(self) -> dict[str, Any]:
        """Return organism engine status for API/monitoring."""
        scanner_info = {}
        if self.market_scanner is not None:
            scanner_info = {
                "scanner_enabled": True,
                "scanner_scan_count": self.market_scanner.scan_count,
                "scanner_candidates_count": len(self._scanner_candidates),
                "scanner_last_scan_time": self.market_scanner.last_scan_time,
            }

        # Compute trade performance stats
        trades = self._all_trades
        total_trades = len(trades)
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl < 0]
        cumulative_pnl = sum(t.pnl for t in trades)
        win_rate = len(winning) / total_trades if total_trades > 0 else 0.0
        avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0.0
        avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else 0.0

        # ML model metrics
        ml_accuracy = 0.0
        if self.signal_gen.is_trained and hasattr(self.signal_gen, "_latest_metrics"):
            metrics = self.signal_gen._latest_metrics
            if isinstance(metrics, dict):
                ml_accuracy = metrics.get("accuracy", 0.0)

        # Training history from learner
        training_history = []
        if hasattr(self.learner, "generation_metrics"):
            training_history = list(self.learner.generation_metrics)

        return {
            "initialized": self._initialized,
            "tick_count": self._tick_count,
            "total_trades": total_trades,
            "brain_generation": self.brain.generation,
            "brain_total_runs": self.brain.total_runs,
            "evolved_generation": self.evolved_params.evolution_generation,
            "evolved_adaptations": self.evolved_params.total_adaptations,
            "peak_equity": self._peak_equity,
            "current_equity": self._equity_curve[-1] if self._equity_curve else 0.0,
            "governance": self.governance.to_dict(),
            "universe_size": len(self._universe),
            "universe_symbols": list(self._universe),
            "positions_tracked": len(self._entry_metadata),
            # Performance stats
            "cumulative_pnl": round(cumulative_pnl, 2),
            "win_rate": round(win_rate, 4),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "ml_accuracy": round(ml_accuracy, 4),
            "ml_trained": self.signal_gen.is_trained,
            "training_history": training_history,
            "regime": self.regime_detector.current_regime,
            "shorts_enabled": self.evolved_params.shorts_enabled,
            **scanner_info,
        }

    def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Hot-reload engine configuration at next tick boundary.

        Called by scheduler.update_config() when settings are changed
        via the Settings API.  The tick lock ensures atomic updates.

        Returns a dict of parameters that were actually changed.
        """
        global MAX_OPEN_POSITIONS, RETRAIN_INTERVAL, LIVE_LOOKBACK, MIN_BARS, LONG_ONLY

        changed: dict[str, Any] = {}

        if "max_positions" in config:
            MAX_OPEN_POSITIONS = int(config["max_positions"])
            self.alpha_scanner = AlphaScanner(top_n=MAX_OPEN_POSITIONS)
            self.breakout_scanner = BreakoutScanner(top_n=MAX_OPEN_POSITIONS)
            changed["max_positions"] = MAX_OPEN_POSITIONS

        if "retrain_interval" in config:
            RETRAIN_INTERVAL = int(config["retrain_interval"])
            self.learner._retrain_every_n = RETRAIN_INTERVAL
            changed["retrain_interval"] = RETRAIN_INTERVAL

        if "lookback" in config:
            LIVE_LOOKBACK = int(config["lookback"])
            changed["lookback"] = LIVE_LOOKBACK

        if "min_bars" in config:
            MIN_BARS = int(config["min_bars"])
            changed["min_bars"] = MIN_BARS

        if "long_only" in config:
            LONG_ONLY = bool(config["long_only"])
            changed["long_only"] = LONG_ONLY

        # Kelly sizer params
        kelly_keys = {"max_position_pct", "vol_target", "min_position_usd"}
        for key in kelly_keys & config.keys():
            setattr(self.kelly_sizer, key, float(config[key]))
            changed[key] = float(config[key])

        # Exit engine params
        exit_keys = {
            "atr_multiplier", "profit_r_multiple", "trailing_distance_atr",
            "max_bars_held", "partial_tp_pct",
        }
        for key in exit_keys & config.keys():
            setattr(self.exit_engine, key, float(config[key]))
            changed[key] = float(config[key])

        # ML params
        if "n_estimators" in config:
            self.signal_gen._n_estimators = int(config["n_estimators"])
            changed["n_estimators"] = int(config["n_estimators"])
        if "max_depth" in config:
            self.signal_gen._max_depth = int(config["max_depth"])
            changed["max_depth"] = int(config["max_depth"])
        if "learning_rate" in config:
            self.signal_gen._learning_rate = float(config["learning_rate"])
            changed["learning_rate"] = float(config["learning_rate"])
        if "direction_threshold" in config:
            self.signal_gen._direction_threshold = float(config["direction_threshold"])
            changed["direction_threshold"] = float(config["direction_threshold"])

        if "universe" in config and isinstance(config["universe"], list):
            self._universe = [s.strip().upper() for s in config["universe"] if s.strip()]
            changed["universe"] = self._universe

        if changed:
            logger.info("Engine config updated: %s", changed)
        return changed

    def generate_trading_signals(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        regime: str,
    ) -> list[TradingSignal]:
        """Generate TradingSignal objects for the multi-strategy runner.

        This lets the organism participate as one strategy source
        alongside the existing 10 strategies.
        """
        ml_signals = self.signal_gen.predict_batch(features_by_symbol)
        candidates = self.alpha_scanner.scan(
            features_by_symbol, ml_signals, regime
        )

        signals = []
        now = datetime.now(UTC)
        for c in candidates:
            if LONG_ONLY and not self.evolved_params.shorts_enabled and c.direction < 0:
                continue
            confidence = c.ml_signal.confidence if c.ml_signal else 0.3
            target_exposure = 0.25 * c.direction * confidence
            target_exposure = max(-1.0, min(1.0, target_exposure))

            signals.append(
                TradingSignal(
                    symbol=c.symbol,
                    source="organism",
                    ts=now,
                    target_exposure=target_exposure,
                    confidence=confidence,
                    metadata={
                        "predicted_return": (
                            c.ml_signal.predicted_return
                            if c.ml_signal
                            else 0.0
                        ),
                        "composite_score": c.composite_score,
                        "regime": regime,
                    },
                )
            )

        return signals
