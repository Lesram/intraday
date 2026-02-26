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
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

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
from backend.organism.sector_map import sector_gate_allows, get_sector
from backend.organism.decision_telemetry import (
    DecisionSnapshot,
    DecisionTelemetryStore,
    FilteringSummary,
    KellySizingDetail,
    PositionExitDetail,
    SymbolAlphaDetail,
    SymbolBreakoutDetail,
)
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
    # ── Safety invariant monitors ──────────────────────────────
    ORGANISM_HALTED_WITH_POSITIONS = Counter(
        "organism_halted_with_positions_total",
        "Ticks where trading was halted while open positions exist",
    )
    ORGANISM_EXITS_SKIPPED_NO_DATA = Counter(
        "organism_exits_skipped_no_data_total",
        "Exit checks that fell back to broker price due to missing features",
    )
    ORGANISM_SECTOR_CAP_BLOCKED = Counter(
        "organism_sector_cap_blocked_total",
        "Entries blocked by intra-tick sector limit enforcement",
    )
    ORGANISM_SAFETY_NET_TRIGGERED = Counter(
        "organism_safety_net_triggered_total",
        "Positions closed by the 15% max-loss safety net",
    )
    ORGANISM_ENTRIES_BLOCKED = Counter(
        "organism_entries_blocked_total",
        "Ticks where new entries were blocked (halt/drawdown/zero equity)",
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
        timeframe: str | None = None,  # Override module-level LIVE_TIMEFRAME
    ) -> None:
        self._data_client = data_client
        self._order_service = order_service
        self._positions_service = positions_service
        self._streaming_provider = streaming_provider
        self._sessionmaker = sessionmaker  # For DB-based trade reconstruction

        self._universe = universe or [
            s.strip().upper()
            for s in LIVE_UNIVERSE_CSV.split(",")
            if s.strip()
        ]

        # ── Timeframe-aware config ───────────────────────────────
        self._timeframe = timeframe or LIVE_TIMEFRAME
        self._is_intraday = self._timeframe in ("1Min", "5Min", "15Min", "1Hour")

        # ── Organism components ──────────────────────────────────
        self.signal_gen = MLSignalGenerator(
            train_window=TRAIN_WINDOW,
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
        )
        self.alpha_scanner = AlphaScanner(top_n=3)  # was MAX_OPEN_POSITIONS — reduce overtrading
        self.breakout_scanner = BreakoutScanner(top_n=MAX_OPEN_POSITIONS)
        # Scale breakout scanner lookbacks for intraday bars (4x ≈ 6.5 hrs)
        if self._is_intraday:
            _intraday_scale = 4
            self.breakout_scanner.BB_PERIOD = 20 * _intraday_scale      # 80
            self.breakout_scanner.ATR_SHORT = 10 * _intraday_scale      # 40
            self.breakout_scanner.ATR_LONG = 50 * _intraday_scale       # 200
            self.breakout_scanner.VOL_AVG_PERIOD = 20 * _intraday_scale # 80
        self.pyramider = MomentumPyramider()
        if self._is_intraday:
            self.kelly_sizer = KellySizer(
                max_position_pct=0.08,    # HFT: smaller positions, faster turns
                max_portfolio_pct=0.95,
                vol_target=0.15,
                min_position_usd=500.0,   # HFT: allow small scalps ($500 min)
            )
        else:
            self.kelly_sizer = KellySizer(
                max_position_pct=0.10,
                max_portfolio_pct=0.95,
                vol_target=0.15,
                min_position_usd=2000.0,
            )
        self.exit_engine = AdaptiveExitEngine.for_timeframe(self._timeframe)

        # ML reversal thresholds — higher bar for daily to reduce false chipping
        self._ml_reversal_confidence = 0.6 if self._is_intraday else 0.65
        self._ml_reversal_partial_pct = 0.30 if self._is_intraday else 0.25

        self.learner = ContinuousLearner(
            signal_generator=self.signal_gen,
            retrain_every_n_bars=RETRAIN_INTERVAL,
            min_trades_for_eval=10,
            improvement_threshold=0.05,
        )
        self.regime_detector = RegimeDetector(is_intraday=self._is_intraday)
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

        # ── Decision telemetry (in-memory ring buffer) ────────
        self._telemetry = DecisionTelemetryStore()

        # ── Live state ──────────────────────────────────────────
        self._session_id = uuid.uuid4().hex[:8]  # unique per engine lifetime
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
        self._EXIT_COOLDOWN_TICKS = 10  # Wait 10 ticks (~100s) wash-trade prevention (was 3)

        # Symbols with recent entry orders — prevents re-submitting the same
        # order every tick when the order hasn't settled or was rejected.
        # Maps symbol → tick number when entry order was submitted
        self._pending_entry: dict[str, int] = {}
        self._PENDING_ENTRY_TICKS = 30  # Wait 30 ticks (~5 min) per-symbol cooldown (was 15)

        # Liquidity gate — block entries on illiquid symbols (seed universe bypass)
        self._MIN_AVG_VOLUME = 500_000

        # Symbols with pending exit orders — prevents duplicate exits across
        # ticks while the broker is still processing the exit.
        # Maps symbol → tick number when exit order was submitted
        self._pending_exit: dict[str, int] = {}
        self._PENDING_EXIT_TICKS = 3  # Wait 3 ticks (~30s) before re-trying exit

        # SPY MA filter — block long entries when SPY < SMA
        # Disabled: individual stock gates (ML, alpha, breakout) are more granular
        self._spy_filter_enabled = False
        self._spy_ma_period = 50

        # ML reversal one-shot guard — once ml_reversal fires on a symbol,
        # it cannot fire again until the position is fully closed.  Prevents
        # repeated 50% partials from chipping positions to 1 share.
        self._ml_reversal_used: set[str] = set()

        # Global entries-per-hour throttle — prevents overtrading
        self._entry_timestamps: list[float] = []
        self._MAX_ENTRIES_PER_HOUR = 3

        # Warmup period — skip entries for first N ticks after startup to let
        # features stabilize and avoid cold-start entry burst.
        self._WARMUP_TICKS = 5  # ~50s at 10s tick interval

        # Consecutive equity-zero counter — avoids permanent halt on
        # transient broker API glitches.  Requires N consecutive zeros
        # before blocking entries (soft block, auto-recovers).
        self._consecutive_equity_zero: int = 0
        self._EQUITY_ZERO_THRESHOLD = 3  # 3 consecutive zeros (~30s) before blocking

        # Serialize live_tick() calls to prevent concurrent state mutation
        # (scheduler loop + manual /tick endpoint)
        self._tick_lock = asyncio.Lock()

        # Clock overrides for replay/testing — defaults to real time
        self._time_fn: Callable[[], float] = time.time
        self._now_fn: Callable[[], datetime] = lambda: datetime.now(UTC)

        # ── Background trainer for non-blocking retraining ────────
        self._bg_trainer = BackgroundTrainer()
        self._bg_training_metadata: dict[str, Any] = {}
        self._bg_training_started_tick: int = 0  # tick when bg training started
        self._BG_TRAINING_TIMEOUT_TICKS = 30  # ~5 min at 10s/tick

        # ── Diagnostics ──────────────────────────────────────────
        self._last_diagnostic_report: Any = None

    # ── Private helpers ────────────────────────────────────────

    def _passes_liquidity_gate(
        self,
        symbol: str,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> bool:
        """Return False if symbol's avg volume over last 20 bars < minimum."""
        df = features_by_symbol.get(symbol)
        if df is None or "volume" not in df.columns or len(df) < 20:
            return True  # No data → conservative pass
        avg_vol = float(df["volume"].iloc[-20:].mean())
        return avg_vol >= self._MIN_AVG_VOLUME

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

            # Restore cumulative data — try brain first, then DB fallback
            prev_trades = self.brain.get_trade_records()
            if prev_trades:
                self._all_trades = prev_trades
            elif self._sessionmaker:
                try:
                    await self._reconstruct_trades_from_db()
                except Exception as e:
                    logger.warning("Trade reconstruction from DB failed: %s", e)
            if self.brain.equity_curve:
                self._equity_curve = list(self.brain.equity_curve)
            if self.brain.epoch_metrics:
                self._epoch_metrics = list(self.brain.epoch_metrics)
            self._peak_equity = self.brain.extra_counters.get(
                "peak_equity", 0.0
            )
            # Restore tick counters — without this, cooldowns reference
            # old tick numbers and never expire after restart.
            self._tick_count = self.brain.extra_counters.get(
                "tick_count", 0
            )
            self._bars_since_retrain = self.brain.extra_counters.get(
                "bars_since_retrain", 0
            )

            # Restore entry timestamps — prevents cold-start burst
            saved_ts = self.brain.extra_counters.get("entry_timestamps", [])
            if saved_ts and isinstance(saved_ts, list):
                now_ts = self._time_fn()
                # Only keep timestamps from last hour (still valid for throttle)
                self._entry_timestamps = [
                    float(t) for t in saved_ts if now_ts - float(t) < 3600
                ]
                if self._entry_timestamps:
                    logger.info(
                        "Restored %d entry timestamps (throttle state preserved)",
                        len(self._entry_timestamps),
                    )

            # Restore exit levels — preserves trailing stop state,
            # partial_tp_taken, stress_tightened flags across restarts.
            saved_exit_levels = self.brain.extra_counters.get("exit_levels", {})
            if saved_exit_levels and isinstance(saved_exit_levels, dict):
                from backend.organism.adaptive_exits import ExitLevels
                for sym, lvl_data in saved_exit_levels.items():
                    try:
                        self._exit_levels[sym] = ExitLevels(
                            symbol=lvl_data.get("symbol", sym),
                            direction=float(lvl_data.get("direction", 1.0)),
                            entry_price=float(lvl_data.get("entry", 0)),
                            stop_loss=float(lvl_data.get("stop_loss", 0)),
                            take_profit=float(lvl_data.get("take_profit", 0)),
                            trailing_stop=float(lvl_data.get("trailing_stop", 0)),
                            atr_at_entry=float(lvl_data.get("atr", 0)),
                            regime_at_entry=lvl_data.get("regime_at_entry", "unknown"),
                            highest_favorable=float(lvl_data.get("highest_favorable", lvl_data.get("entry", 0))),
                            bars_held=int(lvl_data.get("bars_held", 0)),
                            partial_tp_taken=bool(lvl_data.get("partial_tp_taken", False)),
                            trailing_active=bool(lvl_data.get("trailing_active", False)),
                            profit_locked=bool(lvl_data.get("profit_locked", False)),
                        )
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug("Cannot restore exit levels for %s: %s", sym, e)
                if self._exit_levels:
                    logger.info(
                        "Restored exit levels for %d positions from brain",
                        len(self._exit_levels),
                    )

            # Restore entry metadata
            saved_entry_meta = self.brain.extra_counters.get("entry_metadata", {})
            if saved_entry_meta and isinstance(saved_entry_meta, dict):
                self._entry_metadata = saved_entry_meta
                logger.info(
                    "Restored entry metadata for %d positions from brain",
                    len(self._entry_metadata),
                )

            # Restore regime-stratified Kelly stats
            rk_data = self.brain.extra_counters.get("regime_kelly_stats")
            if rk_data:
                self.kelly_sizer.load_regime_stats(rk_data)
                logger.info("Restored regime Kelly stats from brain")

            # Restore ML confidence calibration
            cal_data = self.brain.extra_counters.get("ml_calibration")
            if cal_data:
                self.signal_gen.load_calibration(cal_data)
                logger.info("Restored ML calibration from brain")

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
                    current_regime = "unknown"
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

        # ── Preflight diagnostics (non-fatal) ────────────────────
        try:
            from backend.organism.diagnostics import diagnostics as _diag, CheckMode
            import backend.organism.diagnostic_checks  # noqa: F401 — registers checks
            report = await _diag.run(CheckMode.PREFLIGHT, engine=self)
            self._last_diagnostic_report = report
            store = getattr(self, "_diag_store", None)
            if store:
                await store.append(report, trigger="preflight")
            summary = report.summary
            logger.info(
                "PREFLIGHT: %d/%d checks passed (%d critical failures, %d warnings)",
                summary["passed"], summary["total"],
                summary["critical_failures"], summary["warnings"],
            )
            for r in report.results:
                if not r.passed and r.severity == "critical":
                    logger.error("PREFLIGHT CRITICAL FAIL: %s — %s", r.name, r.message)
        except Exception as e:
            logger.debug("Preflight diagnostics error (non-fatal): %s", e)

        return brain_loaded

    async def _reconstruct_trades_from_db(self) -> None:
        """Reconstruct trade history from filled organism orders in DB.

        Called on startup when brain has no trade records (e.g. after a
        Docker restart that wiped trade_history.csv before it was written).
        Pairs entry and exit orders per symbol to build TradeRecord objects.
        """
        from sqlalchemy import select, text as sa_text
        from backend.infra.schemas import Order

        async with self._sessionmaker() as session:
            stmt = (
                select(Order)
                .where(
                    Order.status == "filled",
                    sa_text("attributes->>'source' = 'organism'"),
                )
                .order_by(Order.submitted_at.asc())
            )
            result = await session.execute(stmt)
            orders = list(result.scalars().all())

        if not orders:
            logger.info("No filled organism orders in DB — nothing to reconstruct")
            return

        # Separate entries and exits
        entry_reasons = {"entry", "pyramid", "ml_entry", "alpha_entry", "breakout_entry"}
        entries: dict[str, list] = {}  # symbol → [order, ...]
        exits: dict[str, list] = {}

        for o in orders:
            attrs = o.attributes or {}
            reason = (attrs.get("reason") or "").lower()
            sym = o.symbol

            is_entry = (
                any(r in reason for r in entry_reasons)
                or (o.side == "buy" and not reason)
            )
            if is_entry:
                entries.setdefault(sym, []).append(o)
            else:
                exits.setdefault(sym, []).append(o)

        # Pair exits to entries
        reconstructed: list[TradeRecord] = []
        entry_idx: dict[str, int] = {}  # symbol → next unmatched entry index

        for sym, exit_orders in exits.items():
            sym_entries = entries.get(sym, [])
            idx = entry_idx.get(sym, 0)

            for ex_order in exit_orders:
                if idx >= len(sym_entries):
                    break  # No more entries to match

                en_order = sym_entries[idx]
                idx += 1

                entry_price = float(en_order.avg_fill_price or 0)
                exit_price = float(ex_order.avg_fill_price or 0)
                shares = int(float(en_order.filled_qty or en_order.qty or 0))

                if entry_price <= 0 or exit_price <= 0 or shares <= 0:
                    continue

                pnl = (exit_price - entry_price) * shares
                actual_return = (exit_price - entry_price) / entry_price

                en_attrs = en_order.attributes or {}
                ex_attrs = ex_order.attributes or {}

                reconstructed.append(TradeRecord(
                    symbol=sym,
                    direction=1.0,  # LONG_ONLY
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_bar=0,
                    exit_bar=0,
                    shares=shares,
                    pnl=pnl,
                    exit_reason=ex_attrs.get("reason", "unknown"),
                    predicted_return=0.0,
                    actual_return=actual_return,
                    confidence=float(en_attrs.get("confidence", 0.0)),
                ))

            entry_idx[sym] = idx

        if not reconstructed:
            logger.info("No matched entry/exit pairs found in DB")
            return

        self._all_trades = reconstructed
        cumulative = 0.0
        for t in reconstructed:
            cumulative += t.pnl
            self._equity_curve.append(cumulative)
        self._peak_equity = max(self._equity_curve) if self._equity_curve else 0.0

        # Feed reconstructed trades to learner so ML can train
        if hasattr(self, 'learner') and self.learner:
            for t in reconstructed:
                try:
                    self.learner.record_trade(t)
                except Exception as e:
                    logger.warning("Failed to record reconstructed trade for %s: %s", t.symbol, e)
            logger.info(
                "Fed %d reconstructed trades to learner (total_trades=%d)",
                len(reconstructed), self.learner.state.total_trades,
            )

        logger.info(
            "Reconstructed %d trades from DB: cumulative PnL=$%.2f",
            len(reconstructed),
            cumulative,
        )

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
            timestamp=self._now_fn().isoformat(),
        )
        self._tick_count += 1
        # Expire old cooldowns (keep only recent exits)
        self._exit_cooldown = {
            sym: tick for sym, tick in self._exit_cooldown.items()
            if self._tick_count - tick < self._EXIT_COOLDOWN_TICKS
        }
        # Expire old pending entries
        self._pending_entry = {
            sym: tick for sym, tick in self._pending_entry.items()
            if self._tick_count - tick < self._PENDING_ENTRY_TICKS
        }
        # Expire old pending exits
        self._pending_exit = {
            sym: tick for sym, tick in self._pending_exit.items()
            if self._tick_count - tick < self._PENDING_EXIT_TICKS
        }

        try:
            now_iso = result.timestamp

            # 0. STREAM HEALTH — detect and recover stale WebSocket data.
            # Run every 30 ticks (~5 min) to avoid hammering reconnect.
            if (
                self._streaming_provider is not None
                and self._tick_count % 30 == 0
            ):
                try:
                    recovered = await self._streaming_provider.check_and_recover_stale_stream()
                    if recovered:
                        result.activity.append(ActivityEvent(
                            event_type="stream",
                            message="Stale data detected — stream reconnect attempted",
                            timestamp=now_iso,
                        ))
                except Exception as e:
                    logger.debug("Stream staleness check error (non-fatal): %s", e)

            # 1. GOVERNANCE CHECK
            # When halted, we still MUST process exits and reconciliation
            # to manage open risk.  Only new entries are blocked.
            entries_blocked = False
            if self.governance.is_trading_halted:
                entries_blocked = True
                result.errors.append("Trading halted by governance — exits still active")
                result.activity.append(ActivityEvent(
                    event_type="governance", message="Trading halted — blocking new entries, exits still running",
                    timestamp=now_iso,
                ))

            # 1.1 WARMUP GATE — let features stabilize before entering
            if not entries_blocked and self._tick_count <= self._WARMUP_TICKS:
                entries_blocked = True
                logger.info(
                    "Warmup period: %d/%d ticks — blocking entries",
                    self._tick_count, self._WARMUP_TICKS,
                )
                result.activity.append(ActivityEvent(
                    event_type="skip",
                    message=f"Warmup: tick {self._tick_count}/{self._WARMUP_TICKS} — entries blocked",
                    timestamp=now_iso,
                ))

            # 1.5 MARKET SCAN (Phase 5) — discover new stocks
            # Skip scanner when entries are blocked (halt/drawdown) — no point
            # scanning for new candidates we won't enter.
            if (
                not entries_blocked
                and self.market_scanner is not None
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
            # Save for telemetry: latest close prices and feature count
            self._last_features_count = len(features_by_symbol)
            self._last_prices = {}
            for _sym, _df in features_by_symbol.items():
                if len(_df) > 0 and "close" in _df.columns:
                    self._last_prices[_sym] = float(_df["close"].iloc[-1])
            insufficient_features = len(features_by_symbol) < 3
            if insufficient_features:
                result.errors.append(
                    f"Insufficient data: got {len(features_by_symbol)} symbols"
                )
                entries_blocked = True
                logger.warning(
                    "Insufficient features (%d symbols) — blocking entries, "
                    "exits still active via broker price fallback",
                    len(features_by_symbol),
                )

            # 3. DETECT REGIME (Phase 4.3: cross-asset conditioning)
            # Skip regime detection when features are insufficient — it
            # requires meaningful price data to function.
            regime = RegimeLabel.UNKNOWN  # default — overwritten below if features are sufficient
            if not insufficient_features:
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

            # Equity-zero resilience: require N consecutive zeros before
            # blocking entries.  A single transient API glitch should NOT
            # permanently halt the engine.  Auto-recovers when equity returns.
            if equity > 0:
                if self._consecutive_equity_zero > 0:
                    logger.info(
                        "Equity recovered after %d consecutive zero readings",
                        self._consecutive_equity_zero,
                    )
                self._consecutive_equity_zero = 0
                self._peak_equity = max(self._peak_equity, equity)
            else:
                self._consecutive_equity_zero += 1
                if self._consecutive_equity_zero >= self._EQUITY_ZERO_THRESHOLD:
                    entries_blocked = True
                    logger.error(
                        "equity_returned_zero for %d consecutive ticks — "
                        "soft-blocking entries, exits still active",
                        self._consecutive_equity_zero,
                    )
                    result.errors.append(
                        f"Equity zero for {self._consecutive_equity_zero} ticks "
                        f"— entries soft-blocked, exits still active."
                    )
                else:
                    logger.warning(
                        "equity_returned_zero (%d/%d before block) — "
                        "skipping drawdown check this tick",
                        self._consecutive_equity_zero,
                        self._EQUITY_ZERO_THRESHOLD,
                    )

            # Check drawdown — only when we have valid equity readings
            if self._peak_equity > 0 and equity > 0:
                drawdown = (self._peak_equity - equity) / self._peak_equity
                was_halted = self.governance.is_trading_halted
                self.governance.trigger_drawdown_kill(drawdown)
                if not was_halted and self.governance.is_trading_halted:
                    entries_blocked = True
                    result.errors.append(
                        f"Drawdown kill triggered ({drawdown:.2%} >= "
                        f"{self.governance._drawdown_limit:.0%}) — exits still active"
                    )
                    logger.warning(
                        "Drawdown kill: %.2f%% drawdown, blocking new entries "
                        "but continuing exit checks for %d open positions",
                        drawdown * 100,
                        len(current_positions),
                    )

            # Propagate any pre-existing governance halt (from manual halt
            # or prior drawdown cooldown) — separate from drawdown check
            if self.governance.is_trading_halted and not entries_blocked:
                entries_blocked = True
                result.errors.append("Trading halted by governance — exits still active")

            # 5. CHECK EXITS on existing positions
            _MAX_LOSS_PCT = self.exit_engine.max_loss_pct
            exits_submitted = 0
            for sym, pos_data in list(current_positions.items()):
                # LONG_ONLY guard: skip exit processing for SHORT positions.
                # Short positions should not exist when LONG_ONLY=true; they
                # are artifacts of a previous bug.  Log and skip — they will
                # be closed via manual liquidation or the close-shorts script.
                pos_side = pos_data.get("side", "long")
                if LONG_ONLY and pos_side != "long":
                    logger.warning(
                        "LONG_ONLY: skipping exit check for SHORT position %s "
                        "(%s shares) — should not exist",
                        sym, pos_data.get("qty", "?"),
                    )
                    continue
                # Skip symbols with pending exit orders (prevent duplicate exits)
                if sym in self._pending_exit:
                    logger.debug(
                        "Skipping exit check for %s — pending exit from tick %d",
                        sym, self._pending_exit[sym],
                    )
                    continue
                feat_df = features_by_symbol.get(sym)
                if feat_df is None or len(feat_df) < 1:
                    # Fallback: use broker position data for safety net check
                    # even when feature computation fails.  We NEVER skip exit
                    # checks for open positions — data outages must not disable
                    # risk management.
                    broker_price = float(pos_data.get("current_price", 0))
                    avg_entry = float(pos_data.get("avg_entry_price", 0))
                    if broker_price > 0 and avg_entry > 0:
                        side = pos_data.get("side", "long")
                        _dir = 1.0 if side == "long" else -1.0
                        pnl_pct = (broker_price - avg_entry) / avg_entry * _dir
                        if pnl_pct <= -_MAX_LOSS_PCT:
                            from backend.organism.adaptive_exits import ExitSignal
                            qty = abs(float(pos_data.get("qty", 0)))
                            sell_shares = int(qty)
                            if sell_shares > 0:
                                try:
                                    await self._submit_exit_order(
                                        sym, sell_shares, "safety_net_no_features",
                                        direction=_dir,
                                        broker_positions=current_positions,
                                    )
                                    exits_submitted += 1
                                    if _PROMETHEUS_AVAILABLE:
                                        ORGANISM_SAFETY_NET_TRIGGERED.inc()
                                        ORGANISM_EXITS_SKIPPED_NO_DATA.inc()
                                    logger.warning(
                                        "SAFETY NET (no features) triggered for %s: "
                                        "%.1f%% loss (broker price=%.2f, entry=%.2f)",
                                        sym, pnl_pct * 100, broker_price, avg_entry,
                                    )
                                    result.activity.append(ActivityEvent(
                                        event_type="exit",
                                        symbol=sym,
                                        message=f"EXIT: {sym} — safety net (no features, "
                                                f"{pnl_pct*100:.1f}% loss)",
                                        details={"reason": "safety_net_no_features",
                                                 "shares": sell_shares, "pnl_pct": pnl_pct,
                                                 "broker_price": broker_price},
                                        timestamp=now_iso,
                                    ))
                                except Exception as e:
                                    result.errors.append(
                                        f"Safety net exit (no features) failed for {sym}: {e}"
                                    )
                                finally:
                                    self._exit_cooldown[sym] = self._tick_count
                                    self._pending_exit[sym] = self._tick_count
                    else:
                        logger.warning(
                            "No features AND no valid broker price for %s — "
                            "cannot evaluate exit (broker_price=%.2f, entry=%.2f)",
                            sym, broker_price, avg_entry,
                        )
                    continue

                result.exits_checked += 1
                exit_levels = self._exit_levels.get(sym)
                current_price = float(feat_df["close"].iloc[-1])

                # SAFETY NET: enforce max loss even without exit_levels.
                # This prevents positions from losing >15% when exit_levels
                # are missing (e.g. after restart with failed reconstruction).
                if exit_levels is None:
                    avg_entry = float(pos_data.get("avg_entry_price", 0))
                    if avg_entry > 0:
                        side = pos_data.get("side", "long")
                        _dir = 1.0 if side == "long" else -1.0
                        pnl_pct = (current_price - avg_entry) / avg_entry * _dir
                        if pnl_pct <= -_MAX_LOSS_PCT:
                            from backend.organism.adaptive_exits import ExitSignal
                            exit_sig = ExitSignal(
                                True, "max_loss_safety_net", current_price,
                            )
                            qty = abs(float(pos_data.get("qty", 0)))
                            sell_shares = int(qty)
                            if sell_shares > 0:
                                try:
                                    await self._submit_exit_order(
                                        sym, sell_shares, exit_sig.reason,
                                        direction=_dir,
                                        broker_positions=current_positions,
                                    )
                                    self._exit_cooldown[sym] = self._tick_count
                                    exits_submitted += 1
                                    if _PROMETHEUS_AVAILABLE:
                                        ORGANISM_SAFETY_NET_TRIGGERED.inc()
                                    logger.warning(
                                        "SAFETY NET triggered for %s: %.1f%% loss "
                                        "(no exit_levels)", sym, pnl_pct * 100,
                                    )
                                    result.activity.append(ActivityEvent(
                                        event_type="exit",
                                        symbol=sym,
                                        message=f"EXIT: {sym} — safety net "
                                                f"({pnl_pct*100:.1f}% loss, no exit_levels)",
                                        details={"reason": "max_loss_safety_net",
                                                 "shares": sell_shares, "pnl_pct": pnl_pct},
                                        timestamp=now_iso,
                                    ))
                                except Exception as e:
                                    result.errors.append(f"Safety net exit failed for {sym}: {e}")
                                finally:
                                    self._exit_cooldown[sym] = self._tick_count
                                    self._pending_exit[sym] = self._tick_count
                    continue
                exit_sig = self.exit_engine.check_exit(
                    exit_levels, current_price, regime
                )

                # ML reversal check: if ML signal flips, trigger partial exit.
                # One-shot guard: only fire once per position lifetime.
                if (
                    not exit_sig.should_exit
                    and self.signal_gen.is_trained
                    and sym not in self._ml_reversal_used
                ):
                    try:
                        ml_sig = self.signal_gen.predict(feat_df, sym)
                        pos_direction = exit_levels.direction
                        if (
                            ml_sig.direction != 0
                            and ml_sig.direction != pos_direction
                            and ml_sig.confidence > self._ml_reversal_confidence
                        ):
                            from backend.organism.adaptive_exits import ExitSignal
                            exit_sig = ExitSignal(
                                should_exit=True,
                                reason="ml_reversal",
                                exit_price=current_price,
                                partial_exit=True,
                                partial_pct=self._ml_reversal_partial_pct,
                            )
                            self._ml_reversal_used.add(sym)
                    except Exception:
                        pass  # ML reversal check is non-fatal

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
                                sym, sell_shares, exit_sig.reason, direction=_dir,
                                broker_positions=current_positions,
                            )
                            self._exit_cooldown[sym] = self._tick_count
                            self._pending_exit[sym] = self._tick_count
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
                        finally:
                            # Always set cooldown to prevent retry spam on failures
                            self._exit_cooldown[sym] = self._tick_count
                            self._pending_exit[sym] = self._tick_count
            result.trades_closed = exits_submitted

            # ── Steps 6-9 and 11 are gated: skip when entries are blocked ──
            if entries_blocked:
                if _PROMETHEUS_AVAILABLE:
                    ORGANISM_ENTRIES_BLOCKED.inc()
                    if current_positions:
                        ORGANISM_HALTED_WITH_POSITIONS.inc()
                logger.info(
                    "Entries blocked (halt/drawdown/insufficient data) — "
                    "skipping pyramids, scans, sizing, entries, and retrain. "
                    "Exits processed: %d", exits_submitted,
                )
                result.activity.append(ActivityEvent(
                    event_type="governance",
                    message=f"Entries blocked — processed {exits_submitted} exits, "
                            f"skipping new entries/pyramids/evolution",
                    timestamp=now_iso,
                ))
                # Fall through to reconcile, brain save, metadata, and
                # metric export — these ALWAYS run regardless of halt state.

            # ── SPY MA filter: block longs when SPY < SMA ──────
            if not entries_blocked and self._spy_filter_enabled and LONG_ONLY:
                spy_df = features_by_symbol.get("SPY")
                if spy_df is not None and len(spy_df) >= self._spy_ma_period:
                    spy_close = float(spy_df["close"].iloc[-1])
                    spy_sma = float(spy_df["close"].iloc[-self._spy_ma_period:].mean())
                    if spy_close < spy_sma:
                        entries_blocked = True
                        logger.info(
                            "SPY MA filter: SPY %.2f < SMA%d %.2f — blocking entries",
                            spy_close, self._spy_ma_period, spy_sma,
                        )
                        result.activity.append(ActivityEvent(
                            event_type="skip",
                            message=f"SPY filter: {spy_close:.2f} < SMA{self._spy_ma_period} "
                                    f"{spy_sma:.2f} — entries blocked",
                            details={"spy_close": spy_close, "spy_sma": spy_sma},
                            timestamp=now_iso,
                        ))

            # ── Opening 30-min block: no entries 9:30-10:00 AM ET ──
            if not entries_blocked and self._is_intraday:
                _now_open = self._now_fn()
                try:
                    import zoneinfo
                    _now_et = _now_open.astimezone(zoneinfo.ZoneInfo("America/New_York"))
                except Exception:
                    _now_et = _now_open
                _hhmm_open = _now_et.hour * 100 + _now_et.minute
                if 930 <= _hhmm_open < 1000:
                    entries_blocked = True
                    logger.info(
                        "Opening block: %d ET — no entries first 30 min",
                        _hhmm_open,
                    )
                    result.activity.append(ActivityEvent(
                        event_type="skip",
                        message=f"Opening 30-min block: {_hhmm_open} ET — entries paused",
                        timestamp=now_iso,
                    ))

            # ── Fix B: Regime sit-out gate ─────────────────────
            _regime_sit_out = False
            _sitout_ml = None
            if not entries_blocked and LONG_ONLY and regime in ("high_vol", "stress"):
                _sitout_ml = self.signal_gen.predict_batch(features_by_symbol)
                _bearish = sum(1 for s in _sitout_ml.values() if s.direction < 0)
                _bullish = sum(1 for s in _sitout_ml.values() if s.direction > 0)
                if _bearish > 0 and _bullish == 0:
                    _regime_sit_out = True
                    logger.info(
                        "Regime sit-out: %s regime, %d bearish / %d bullish ML signals — "
                        "skipping entries",
                        regime, _bearish, _bullish,
                    )
                    result.activity.append(ActivityEvent(
                        event_type="skip",
                        message=f"Regime sit-out: {regime} + all bearish ({_bearish} short, 0 long)",
                        timestamp=now_iso,
                    ))

            # ── Fix E: Global entries-per-hour throttle ───────
            _throttled = False
            if not entries_blocked and not _regime_sit_out:
                now_ts = self._time_fn()
                self._entry_timestamps = [
                    t for t in self._entry_timestamps if now_ts - t < 3600
                ]
                if len(self._entry_timestamps) >= self._MAX_ENTRIES_PER_HOUR:
                    _throttled = True
                    logger.info(
                        "Entry throttle: %d entries in last hour (max %d) — "
                        "blocking new entries this tick",
                        len(self._entry_timestamps), self._MAX_ENTRIES_PER_HOUR,
                    )
                    result.activity.append(ActivityEvent(
                        event_type="skip",
                        message=f"Entry throttle: {len(self._entry_timestamps)}/{self._MAX_ENTRIES_PER_HOUR} entries/hour — pausing",
                        timestamp=now_iso,
                    ))

            # ── Steps 6-9: Entry-side logic (gated) ─────────────
            if not entries_blocked and not _regime_sit_out and not _throttled:

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
                        if sym in self._pending_entry:
                            continue  # Already submitted an order recently
                        try:
                            await self._submit_entry_order(
                                sym,
                                action.shares_to_add,
                                confidence=0.7,
                                reason="pyramid_add",
                            )
                            self._pending_entry[sym] = self._tick_count
                            result.orders_submitted += 1

                            # Record the pyramid layer so layer_count increments
                            # and the pyramider won't re-trigger the same level.
                            pyr.layers.append(PyramidLevel(
                                shares=action.shares_to_add,
                                entry_price=current_price,
                                bar_added=self._tick_count,
                                level=pyr.layer_count - 1,  # just appended
                            ))
                            # Re-anchor exit levels to new weighted avg entry
                            exit_lvl = self._exit_levels.get(sym)
                            if exit_lvl is not None:
                                self.exit_engine.update_levels_for_pyramid(
                                    exit_lvl, pyr.avg_entry, regime,
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

                # ML predictions — reuse sit-out batch if available
                ml_signals = _sitout_ml if _sitout_ml else self.signal_gen.predict_batch(features_by_symbol)

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

                # Symbol fitness gate threshold — block re-entry on chronic losers
                _FITNESS_GATE = 0.45

                # Track symbols planned for entry in THIS tick so the sector gate
                # counts them when evaluating subsequent candidates.  Prevents
                # intra-tick sector-limit violations.
                _planned_entries: set[str] = set()

                cand_dicts = []
                for c in candidates:
                    if c.symbol in open_symbols:
                        continue
                    if c.symbol in self._exit_cooldown:
                        continue  # Wash trade cooldown
                    if c.symbol in self._pending_entry:
                        continue  # Already submitted an order recently
                    if c.symbol in self._entry_metadata:
                        continue  # Already tracking this position
                    if LONG_ONLY and c.direction < 0:
                        continue
                    # Sector diversification gate — includes planned entries from
                    # earlier in this loop to prevent intra-tick sector breaches.
                    if not sector_gate_allows(c.symbol, open_symbols, _planned_entries):
                        logger.info(
                            "Sector gate blocked %s (sector=%s, planned=%s)",
                            c.symbol, get_sector(c.symbol), _planned_entries,
                        )
                        if _PROMETHEUS_AVAILABLE:
                            ORGANISM_SECTOR_CAP_BLOCKED.inc()
                        continue
                    # Block symbols with poor fitness scores from evolved params
                    sym_fitness = self.evolved_params.symbol_fitness.get(c.symbol, 0.5)
                    if sym_fitness < _FITNESS_GATE:
                        logger.info(
                            "Fitness gate blocked %s (fitness=%.2f < %.2f)",
                            c.symbol, sym_fitness, _FITNESS_GATE,
                        )
                        continue
                    # Liquidity gate — block illiquid symbols that gap violently
                    if not self._passes_liquidity_gate(c.symbol, features_by_symbol):
                        logger.info("Liquidity gate blocked %s", c.symbol)
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
                    _planned_entries.add(c.symbol)

                # Pure breakout signals not in alpha candidates (capped at 2)
                alpha_syms = {d["symbol"] for d in cand_dicts}
                _breakout_added = 0
                _MAX_PURE_BREAKOUT = 2
                for bs in breakout_signals:
                    if _breakout_added >= _MAX_PURE_BREAKOUT:
                        break
                    if (
                        bs.symbol not in alpha_syms
                        and bs.symbol not in open_symbols
                        and bs.symbol not in self._exit_cooldown
                        and bs.symbol not in self._pending_entry
                        and bs.symbol not in self._entry_metadata
                        and bs.composite_score >= 0.55
                        and self.evolved_params.symbol_fitness.get(bs.symbol, 0.5) >= _FITNESS_GATE
                    ):
                        if not sector_gate_allows(bs.symbol, open_symbols, _planned_entries):
                            if _PROMETHEUS_AVAILABLE:
                                ORGANISM_SECTOR_CAP_BLOCKED.inc()
                            continue
                        ml_sig = ml_signals.get(bs.symbol)
                        if ml_sig and ml_sig.direction < 0:
                            continue
                        cand_dicts.append({
                            "symbol": bs.symbol,
                            "direction": 1.0,
                            "predicted_return": max(
                                ml_sig.predicted_return if ml_sig else 0.02,
                                0.01,  # Floor: breakout signals always get min 1%
                            ),
                            "confidence": min(bs.composite_score, 1.0),
                            "breakout_score": bs.composite_score,
                        })
                        _planned_entries.add(bs.symbol)
                        _breakout_added += 1

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
                    cand_dicts, equity, drawdown, features_by_symbol, regime,
                    ml_is_trained=self.signal_gen.is_trained,
                )
                self._last_kelly_sizes = sizes

                # 8b. INTRADAY SEASONALITY FILTER — reduce allocation
                # during first/last 15 min (highest volatility, worst fills)
                if self._is_intraday and sizes:
                    _now = self._now_fn()
                    try:
                        import zoneinfo
                        now_et = _now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
                    except Exception:
                        now_et = _now
                    hhmm = now_et.hour * 100 + now_et.minute
                    if 1545 <= hhmm <= 1600:
                        for sz in sizes:
                            sz.shares = max(1, int(sz.shares * 0.6))
                            sz.notional = sz.notional * 0.6
                            sz.target_weight = sz.target_weight * 0.6
                        logger.info(
                            "Seasonality filter: reduced allocation 40%% (time=%d)",
                            hhmm,
                        )

                # 9. SUBMIT ENTRY ORDERS
                # Re-check positions right before ordering to catch partial
                # fills from cancelled orders that silently accumulated shares
                try:
                    fresh_positions = await self._positions_service.get_all_positions()
                    fresh_open = set(fresh_positions.keys())
                except Exception:
                    fresh_open = open_symbols

                for sz in sizes:
                    # Skip if position already exists (e.g. from partial fill
                    # on a cancelled order that the earlier check missed)
                    # Also enforce MAX_OPEN_POSITIONS within this tick
                    if sz.symbol in fresh_open or len(fresh_open) >= MAX_OPEN_POSITIONS:
                        logger.info(
                            "Skipping entry for %s — position already exists at broker",
                            sz.symbol,
                        )
                        continue
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
                            filled_qty = order_result.get("filled_qty")
                            if filled_qty:
                                filled_shares = max(1, int(float(filled_qty)))

                        result.orders_submitted += 1
                        fresh_open.add(sz.symbol)  # Track to enforce MAX_OPEN_POSITIONS within tick
                        # Mark as pending so we don't re-submit next tick
                        self._pending_entry[sz.symbol] = self._tick_count
                        # Fix E: Record entry timestamp for hourly throttle
                        self._entry_timestamps.append(self._time_fn())
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
                                "filled_shares": filled_shares,
                                "predicted_return": predicted_return,
                                "confidence": 0.6,
                            }

                    except Exception as e:
                        result.errors.append(
                            f"Entry order failed for {sz.symbol}: {e}"
                        )

            # 10. RECORD TRADE OUTCOMES from closed positions
            await self._reconcile_fills(features_by_symbol)

            # ── Step 11: Retrain/evolve (gated) ────────────────
            if not entries_blocked:
                # 11. PERIODIC RETRAIN + EVOLVE (non-blocking background training)
                self._bars_since_retrain += 1

                # Fast initial training: if model has never been trained, retrain
                # after just 30 ticks (~5 min) so we get real predicted_return
                # values early instead of relying on the 1% floor.
                _retrain_threshold = RETRAIN_INTERVAL
                if not self.signal_gen.is_trained and _retrain_threshold > 30:
                    _retrain_threshold = 30

                # Check if previous background training completed
                if self._bg_trainer.is_training:
                    # Detect stuck training — if it's been running for too long,
                    # force-reset and fall back to synchronous training
                    ticks_training = self._tick_count - self._bg_training_started_tick
                    if ticks_training > self._BG_TRAINING_TIMEOUT_TICKS:
                        logger.warning(
                            "Background training stuck for %d ticks — force-resetting",
                            ticks_training,
                        )
                        self._bg_trainer._is_training = False
                        self._bg_trainer._future = None
                        try:
                            self._retrain_and_evolve(features_by_symbol, regime)
                            logger.info("Sync retrain after stuck bg trainer completed")
                        except Exception as e:
                            logger.warning("Sync retrain after stuck reset failed: %s", e)

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
                        # Background training failed — log error and fall back
                        # to synchronous training so the model still gets updated
                        logger.warning(
                            "Background training rejected/failed: %s — falling back to sync",
                            train_result.error,
                        )
                        self._bg_training_metadata = {
                            "status": "rejected",
                            "error": train_result.error,
                            "last_trained_tick": self._tick_count,
                        }
                        try:
                            self._retrain_and_evolve(features_by_symbol, regime)
                            logger.info("Synchronous fallback retrain completed")
                        except Exception as e:
                            logger.warning("Sync retrain fallback also failed: %s", e)
                elif self._bars_since_retrain >= _retrain_threshold:
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
                        self._bg_training_started_tick = self._tick_count
                        logger.info(
                            "Background training submitted (trades=%d, bars_since=%d, threshold=%d)",
                            len(self._all_trades), self._bars_since_retrain, _retrain_threshold,
                        )
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

            # 12. BRAIN SAVE (every 20 ticks ~3.3 min — was 50/~8.3 min)
            if self._tick_count % 20 == 0:
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

        # ── Decision telemetry capture (non-fatal) ──────────────
        try:
            snapshot = self._build_decision_snapshot(result)
            self._telemetry.append(snapshot)
        except Exception:
            pass  # Telemetry must never break the tick loop

        # ── Production invariant checks ────────────────────────────
        # These catch state inconsistencies before they compound into
        # silent bugs.  Violations are logged as warnings (not exceptions)
        # so the tick loop keeps running.
        self._check_tick_invariants()

        return result

    def _build_decision_snapshot(self, result: LiveTickResult) -> DecisionSnapshot:
        """Assemble a full decision snapshot from data already computed during the tick."""
        snap = DecisionSnapshot(
            tick_number=self._tick_count,
            timestamp=result.timestamp,
            duration_s=result.duration_s,
            regime=result.regime,
            is_halted=self.governance.is_trading_halted,
            is_frozen=self.governance.is_frozen,
            evolution_generation=self.evolved_params.evolution_generation,
            open_positions=len(self._exit_levels),
            max_positions=MAX_OPEN_POSITIONS,
        )

        # Regime probabilities from detector
        regime_state = getattr(self.regime_detector, "_last_state", None)
        if regime_state and hasattr(regime_state, "probabilities"):
            snap.regime_probabilities = dict(regime_state.probabilities)
            snap.regime_confidence = regime_state.confidence
            snap.regime_features = dict(regime_state.features_used)

        # Equity / drawdown
        if self._equity_curve:
            snap.equity = self._equity_curve[-1]
        snap.peak_equity = self._peak_equity
        if self._peak_equity > 0 and snap.equity > 0:
            snap.drawdown_pct = (self._peak_equity - snap.equity) / self._peak_equity

        # Evolved params summary
        snap.evolved_params_summary = {
            "generation": self.evolved_params.evolution_generation,
            "shorts_enabled": self.evolved_params.shorts_enabled,
        }
        if self.evolved_params.symbol_fitness:
            snap.evolved_params_summary["symbol_fitness_count"] = len(
                self.evolved_params.symbol_fitness
            )

        # Alpha details — from _last_full_scan
        full_alpha = getattr(self.alpha_scanner, "_last_full_scan", [])
        fitness_gate = 0.35
        for c in full_alpha:
            sym_fitness = self.evolved_params.symbol_fitness.get(c.symbol, 0.5)
            ad = SymbolAlphaDetail(
                symbol=c.symbol,
                composite_score=c.composite_score,
                ml_score=c.ml_score,
                breakout_score=c.breakout_score,
                institutional_score=getattr(c, "institutional_score", 0.0),
                momentum_score=c.momentum_score,
                momentum_quality_score=getattr(c, "momentum_quality_score", 0.0),
                vol_price_div_score=c.volume_score,
                regime_score=c.regime_score,
                direction=c.direction,
                weights={
                    "ml": self.alpha_scanner.WEIGHT_ML,
                    "breakout": self.alpha_scanner.WEIGHT_BREAKOUT,
                    "institutional": self.alpha_scanner.WEIGHT_INSTITUTIONAL,
                    "momentum": self.alpha_scanner.WEIGHT_MOMENTUM,
                    "momentum_quality": self.alpha_scanner.WEIGHT_MOM_QUALITY,
                    "vol_price_div": self.alpha_scanner.WEIGHT_VOLUME,
                    "regime": self.alpha_scanner.WEIGHT_REGIME,
                },
                min_composite_threshold=self.alpha_scanner.MIN_COMPOSITE,
                distance_to_threshold=c.composite_score - self.alpha_scanner.MIN_COMPOSITE,
                passed_threshold=c.composite_score >= self.alpha_scanner.MIN_COMPOSITE,
                symbol_fitness=sym_fitness,
                fitness_gate=fitness_gate,
                passed_fitness=sym_fitness >= fitness_gate,
            )
            snap.alpha_details.append(ad)

        # Breakout details — from _last_full_scan
        full_breakout = getattr(self.breakout_scanner, "_last_full_scan", [])
        for s in full_breakout:
            bd = SymbolBreakoutDetail(
                symbol=s.symbol,
                composite_score=s.composite_score,
                squeeze_score=s.squeeze_score,
                volume_score=s.volume_score,
                contraction_score=s.contraction_score,
                rs_score=s.rs_score,
                pivot_score=s.pivot_score,
                flow_score=s.flow_score,
                direction=s.direction,
                squeeze_fired=s.squeeze_fired,
                volume_ratio=s.volume_ratio,
                weights={
                    "squeeze": self.breakout_scanner.W_SQUEEZE,
                    "volume": self.breakout_scanner.W_VOLUME,
                    "contraction": self.breakout_scanner.W_CONTRACTION,
                    "rs": self.breakout_scanner.W_RS,
                    "pivot": self.breakout_scanner.W_PIVOT,
                    "flow": self.breakout_scanner.W_FLOW,
                },
                min_breakout_threshold=self.breakout_scanner.MIN_BREAKOUT_SCORE,
                distance_to_threshold=s.composite_score - self.breakout_scanner.MIN_BREAKOUT_SCORE,
                passed_threshold=s.composite_score >= self.breakout_scanner.MIN_BREAKOUT_SCORE,
            )
            snap.breakout_details.append(bd)

        # Exit proximity for all positions
        last_prices = getattr(self, "_last_prices", {})
        for sym, levels in self._exit_levels.items():
            # Use latest close price from features; fall back to highest_favorable
            price = last_prices.get(sym, levels.highest_favorable)
            if levels.entry_price > 0:
                pnl_pct = (price - levels.entry_price) / levels.entry_price * levels.direction
            else:
                pnl_pct = 0.0

            max_bars = self.exit_engine.REGIME_MAX_BARS.get(result.regime, self.exit_engine.max_bars_held)
            time_dist = 0.0
            if max_bars > 0 and levels.bars_held < max_bars:
                time_dist = ((max_bars - levels.bars_held) / max_bars) * 100

            sl_dist = abs((levels.stop_loss - price) / price * 100) if price > 0 else 0
            tp_dist = abs((levels.take_profit - price) / price * 100) if price > 0 else 0
            trail_dist = abs((levels.trailing_stop - price) / price * 100) if price > 0 else 0
            partial_dist = abs((levels.partial_tp_price - price) / price * 100) if price > 0 else 0

            # Nearest exit
            exits_map = {"stop_loss": sl_dist, "take_profit": tp_dist}
            if levels.trailing_active:
                exits_map["trailing_stop"] = trail_dist
            if not levels.partial_tp_taken and levels.partial_tp_price > 0:
                exits_map["partial_tp"] = partial_dist
            if max_bars > 0:
                exits_map["time"] = time_dist
            nearest = min(exits_map, key=exits_map.get) if exits_map else ""
            nearest_dist = exits_map.get(nearest, 0.0)

            ed = PositionExitDetail(
                symbol=sym,
                current_price=price,
                entry_price=levels.entry_price,
                direction=levels.direction,
                pnl_pct=pnl_pct,
                stop_loss=levels.stop_loss,
                take_profit=levels.take_profit,
                trailing_stop=levels.trailing_stop,
                partial_tp_price=levels.partial_tp_price,
                stop_loss_distance_pct=sl_dist,
                take_profit_distance_pct=tp_dist,
                trailing_stop_distance_pct=trail_dist,
                partial_tp_distance_pct=partial_dist,
                trailing_active=levels.trailing_active,
                partial_tp_taken=levels.partial_tp_taken,
                bars_held=levels.bars_held,
                max_bars=max_bars,
                time_exit_distance_pct=time_dist,
                atr_at_entry=levels.atr_at_entry,
                regime_at_entry=levels.regime_at_entry,
                highest_favorable=levels.highest_favorable,
                nearest_exit=nearest,
                nearest_exit_distance_pct=nearest_dist,
            )
            snap.exit_details.append(ed)

        # Kelly sizing details — from last sizing step
        last_sizes = getattr(self, "_last_kelly_sizes", [])
        kelly_intermediates = getattr(self.kelly_sizer, "_last_intermediates", {})
        for sz in last_sizes:
            intermed = kelly_intermediates.get(sz.symbol, {})
            kd = KellySizingDetail(
                symbol=sz.symbol,
                kelly_raw=intermed.get("kelly_raw", sz.kelly_raw),
                kelly_half=intermed.get("kelly_half", sz.kelly_half),
                drawdown_scale=sz.drawdown_scale,
                vol_scale=sz.vol_scale,
                regime_scale=sz.regime_scale,
                confidence_scale=intermed.get("confidence_scale", 0.0),
                breakout_bonus=intermed.get("breakout_bonus", 1.0),
                final_weight=sz.target_weight,
                position_cap=self.kelly_sizer.max_position_pct,
                shares=sz.shares,
                notional=sz.notional,
                direction=sz.direction,
                ml_floor_applied=intermed.get("ml_floor_applied", False),
            )
            snap.kelly_details.append(kd)

        # Filtering funnel
        snap.filtering = FilteringSummary(
            total_universe=len(self._universe),
            had_features=getattr(self, "_last_features_count", 0),
            alpha_scored=len(full_alpha),
            above_alpha_threshold=sum(
                1 for c in full_alpha
                if c.composite_score >= self.alpha_scanner.MIN_COMPOSITE
            ),
            breakout_scored=len(full_breakout),
            above_breakout_threshold=sum(
                1 for s in full_breakout
                if s.composite_score >= self.breakout_scanner.MIN_BREAKOUT_SCORE
            ),
            kelly_sized=len(snap.kelly_details),
            orders_submitted=result.orders_submitted,
        )

        return snap

    def _check_tick_invariants(self) -> None:
        """Runtime invariant checks — called at the end of every tick.

        Catches:
            - Exit levels without matching entry metadata
            - Stale pending entries / exit cooldowns
            - Entry metadata for symbols with no position and no exit levels
            - Tick count sanity
        """
        try:
            # INV-1: Every symbol in _exit_levels should have entry_metadata
            for sym in list(self._exit_levels.keys()):
                if sym not in self._entry_metadata:
                    logger.warning(
                        "INVARIANT: exit_levels exists for %s but no "
                        "entry_metadata — creating stub",
                        sym,
                    )
                    lvl = self._exit_levels[sym]
                    self._entry_metadata[sym] = {
                        "entry_price": getattr(lvl, "entry_price", 0),
                        "entry_tick": 0,
                        "direction": getattr(lvl, "direction", 1.0),
                        "predicted_return": 0.01,
                        "confidence": 0.5,
                    }

            # INV-2: _tick_count must be positive after first tick
            if self._tick_count < 0:
                logger.error(
                    "INVARIANT: tick_count is negative (%d) — resetting to 0",
                    self._tick_count,
                )
                self._tick_count = 0

            # INV-3: _bars_since_retrain cannot exceed tick_count
            if self._bars_since_retrain > self._tick_count:
                logger.warning(
                    "INVARIANT: bars_since_retrain (%d) > tick_count (%d) "
                    "— clamping",
                    self._bars_since_retrain,
                    self._tick_count,
                )
                self._bars_since_retrain = self._tick_count

            # INV-4: Detect orphaned pending entries that somehow survived
            # expiry (should be impossible but guards against logic errors)
            stale_pending = [
                sym for sym, tick in self._pending_entry.items()
                if self._tick_count - tick >= self._PENDING_ENTRY_TICKS * 2
            ]
            if stale_pending:
                logger.warning(
                    "INVARIANT: stale pending entries detected: %s — clearing",
                    stale_pending,
                )
                for sym in stale_pending:
                    del self._pending_entry[sym]

            # INV-5: Run continuous diagnostics every 100 ticks
            if self._tick_count > 0 and self._tick_count % 100 == 0:
                asyncio.create_task(self._run_continuous_diagnostics())

        except Exception as e:
            logger.debug("Invariant check error (non-fatal): %s", e)

    async def _run_continuous_diagnostics(self) -> None:
        """Run CONTINUOUS diagnostic checks and store the report."""
        try:
            from backend.organism.diagnostics import diagnostics as _diag, CheckMode
            import backend.organism.diagnostic_checks  # noqa: F401
            report = await _diag.run(CheckMode.CONTINUOUS, engine=self)
            self._last_diagnostic_report = report
            store = getattr(self, "_diag_store", None)
            if store:
                await store.append(report, trigger="continuous")
            if not report.all_critical_passed:
                for r in report.results:
                    if not r.passed and r.severity == "critical":
                        logger.error(
                            "CONTINUOUS DIAGNOSTIC FAIL: %s — %s",
                            r.name, r.message,
                        )
        except Exception as e:
            logger.debug("Continuous diagnostics error (non-fatal): %s", e)

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

        # Fetch all universe symbols concurrently (semaphore-limited)
        tasks = [_fetch_one(sym) for sym in self._universe]
        results = await asyncio.gather(*tasks)
        for sym, feats in results:
            if feats is not None:
                features_by_symbol[sym] = feats

        # Also fetch features for open position symbols that aren't in
        # the universe.  Without this, exit checks are silently skipped
        # for positions whose symbols rotated out of the universe.
        try:
            current_positions = await self._positions_service.get_all_positions()
            position_syms_missing = [
                sym for sym in current_positions
                if sym not in features_by_symbol
            ]
            if position_syms_missing:
                pos_tasks = [_fetch_one(sym) for sym in position_syms_missing]
                pos_results = await asyncio.gather(*pos_tasks)
                for sym, feats in pos_results:
                    if feats is not None:
                        features_by_symbol[sym] = feats
                logger.info(
                    "Fetched features for %d position symbols outside universe: %s",
                    len(position_syms_missing),
                    position_syms_missing,
                )
        except Exception as e:
            logger.warning("Failed to fetch position symbol features: %s", e)

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
            f"organism_{symbol}"
            f"_{datetime.now(UTC).strftime('%Y%m%d')}"
            f"_{self._session_id}_t{self._tick_count}"
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
        broker_positions: dict | None = None,
    ) -> dict[str, Any]:
        """Submit an exit order via OrderService.

        For longs (direction > 0) we sell; for shorts (direction < 0) we buy-to-cover.

        Safety: LONG_ONLY mode blocks sell orders that would create new short
        positions.  The idempotency key uses tick_count (not wall-clock) so
        the same exit intent across rapid ticks is deduplicated.
        """
        side = "buy" if direction < 0 else "sell"

        # LONG_ONLY guard: never submit a sell (short-creating) exit when
        # LONG_ONLY is active.  Only buy-to-cover (direction < 0) is allowed
        # to close accidental shorts.
        if LONG_ONLY and side == "sell":
            # Verify we actually hold a long position of this size before selling
            try:
                if broker_positions is None:
                    broker_positions = await self._positions_service.get_all_positions()
                broker_pos = broker_positions.get(symbol)
                if broker_pos is None:
                    logger.warning(
                        "LONG_ONLY guard: skipping sell for %s — no broker position exists",
                        symbol,
                    )
                    return {"status": "blocked", "reason": "no_broker_position"}
                broker_qty = abs(float(broker_pos.get("qty", 0)))
                broker_side = broker_pos.get("side", "long")
                if broker_side != "long":
                    logger.warning(
                        "LONG_ONLY guard: skipping sell for %s — broker position is %s, not long",
                        symbol, broker_side,
                    )
                    return {"status": "blocked", "reason": "position_not_long"}
                # Clamp shares to actual broker quantity — never sell more than we own
                if shares > int(broker_qty):
                    logger.warning(
                        "LONG_ONLY guard: clamping exit shares for %s from %d to %d (broker qty)",
                        symbol, shares, int(broker_qty),
                    )
                    shares = int(broker_qty)
                if shares <= 0:
                    logger.warning(
                        "LONG_ONLY guard: skipping sell for %s — broker qty is 0",
                        symbol,
                    )
                    return {"status": "blocked", "reason": "zero_quantity"}
            except Exception as e:
                logger.error(
                    "LONG_ONLY guard: broker position check failed for %s: %s — blocking sell",
                    symbol, e,
                )
                return {"status": "blocked", "reason": f"broker_check_failed: {e}"}

        # Idempotency key: use tick_count so the same exit intent within the
        # same tick is deduplicated, but different ticks get different keys.
        # This prevents the old bug where second-level timestamps caused
        # duplicate exit orders across rapid 10s ticks.
        idem_key = (
            f"organism_exit_{symbol}"
            f"_{datetime.now(UTC).strftime('%Y%m%d')}"
            f"_{self._session_id}_t{self._tick_count}"
        )
        return await self._order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=shares,
            idempotency_key=idem_key,
            order_type="market",
            tif="day",
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
        except Exception as e:
            logger.warning("Reconciliation skipped — broker API failed: %s", e)
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
                # Fallback to tracked filled_shares from entry metadata
                shares = meta.get("filled_shares", 0)
            if shares == 0:
                logger.error("Zero shares for closed position %s — skipping trade record", sym)
                continue

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

            # Record for regime-stratified Kelly
            exit_lvl = self._exit_levels.get(sym)
            regime_at_trade = (
                exit_lvl.regime_at_entry if exit_lvl else "unknown"
            )
            self.kelly_sizer.record_trade(regime_at_trade, pnl)

            # Record for ML calibration
            if meta.get("confidence") is not None:
                was_correct = actual_return > 0
                self.signal_gen.record_prediction_outcome(
                    meta["confidence"], was_correct
                )

            # Clean up tracking state
            self._exit_levels.pop(sym, None)
            self._pyramid_positions.pop(sym, None)
            self._ml_reversal_used.discard(sym)

            logger.info(
                "Trade recorded: %s %s PnL=$%.2f",
                sym,
                "LONG" if direction > 0 else "SHORT",
                pnl,
            )

        # Save brain immediately after recording fills to prevent data loss
        if closed:
            try:
                self._save_brain()
                logger.info("Brain saved after %d fill(s) recorded", len(closed))
            except Exception as e:
                logger.warning("Post-fill brain save failed: %s", e)

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

            # LONG_ONLY guard: never adopt SHORT positions — they are artifacts
            # of bugs (duplicate exit orders).  Log and skip.
            if LONG_ONLY and side != "long":
                logger.warning(
                    "LONG_ONLY: refusing to adopt orphaned SHORT position %s "
                    "(%d shares @ $%.2f) — this should not exist",
                    sym, int(qty), avg_entry,
                )
                continue

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

            # Skip symbols that already have exit levels restored from
            # the brain — those have richer state (trailing stop progress,
            # partial_tp_taken, stress_tightened) that would be lost if we
            # overwrite with fresh conservative defaults.
            if sym in self._exit_levels:
                logger.debug(
                    "Skipping reconstruction for %s — exit levels "
                    "already restored from brain",
                    sym,
                )
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
                else:
                    # Fallback: create exit levels with a 2% ATR estimate.
                    # Better than nothing — ensures max-loss safety net is
                    # enforced through normal check_exit() rather than only
                    # through the emergency safety net added in the tick loop.
                    fallback_atr = avg_entry * 0.02
                    fallback_df = pd.DataFrame({
                        "close": [avg_entry] * 20,
                        "high": [avg_entry * 1.01] * 20,
                        "low": [avg_entry * 0.99] * 20,
                    })
                    exit_lvl = self.exit_engine.create_exit_levels(
                        symbol=sym,
                        direction=direction,
                        entry_price=avg_entry,
                        predicted_return=0.02,
                        features_df=fallback_df,
                        regime=RegimeLabel.UNKNOWN,
                    )
                    logger.warning(
                        "Using fallback ATR ($%.2f) for %s — "
                        "no historical data available",
                        fallback_atr, sym,
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
                logger.warning("Cannot reconstruct %s: %s", sym, e)

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

        # Update ML confidence calibration map
        self.signal_gen.update_calibration_map()

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
                    "exit_levels": {
                        sym: lvl.to_dict()
                        for sym, lvl in self._exit_levels.items()
                    },
                    "entry_metadata": dict(self._entry_metadata),
                    "regime_kelly_stats": self.kelly_sizer.regime_stats_to_dict(),
                    "ml_calibration": self.signal_gen.calibration_to_dict(),
                    "entry_timestamps": list(self._entry_timestamps),
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
                    current_regime = "unknown"
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
