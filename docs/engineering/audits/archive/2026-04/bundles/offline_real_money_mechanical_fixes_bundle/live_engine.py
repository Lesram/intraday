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
    # improve9 B4: Added SH (inverse S&P) and PSQ (inverse Nasdaq) so the
    # long-only framework can participate in bearish tapes without shorting.
    "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,AVGO,CRM,"
    "COST,WMT,LLY,XOM,CAT,SPY,QQQ,IWM,XLK,XLE,SH,PSQ",
)
MAX_OPEN_POSITIONS = _env_int("ORGANISM_MAX_POSITIONS", 8)
ALPHA_TOP_N = _env_int("ORGANISM_ALPHA_TOP_N", 5)
PROTECTED_SYMBOLS: set[str] = {
    s.strip() for s in _env_str("ORGANISM_PROTECTED_SYMBOLS", "SH,PSQ").split(",") if s.strip()
}
BRAIN_DIR = _env_str("ORGANISM_BRAIN_DIR", "organism_brain")
RETRAIN_INTERVAL = _env_int("ORGANISM_RETRAIN_INTERVAL", 60)
TRAIN_WINDOW = _env_int("ORGANISM_TRAIN_WINDOW", 200)
MIN_BARS = _env_int("ORGANISM_MIN_BARS", 200)
LONG_ONLY = _env_bool("ORGANISM_LONG_ONLY", True)
SCANNER_ENABLED = _env_bool("SCANNER_ENABLED", True)
USE_STREAMING = _env_bool("ORGANISM_USE_STREAMING", False)

# Multi-bar prediction horizon — aligns ML target with typical holding period
_HORIZON_DEFAULTS = {"1Min": 15, "5Min": 6, "15Min": 3, "1Hour": 2, "1Day": 1}
PREDICTION_HORIZON = _env_int(
    "ORGANISM_PREDICTION_HORIZON",
    _HORIZON_DEFAULTS.get(LIVE_TIMEFRAME, 1),
)

# Exploration bucket — micro-size trades on rejected candidates to prevent data starvation
EXPLORATION_ENABLED = _env_bool("ORGANISM_EXPLORATION_ENABLED", False)
EXPLORATION_MAX_NOTIONAL = _env_float("ORGANISM_EXPLORATION_MAX_NOTIONAL", 200.0)
EXPLORATION_MAX_POSITIONS = _env_int("ORGANISM_EXPLORATION_MAX_POSITIONS", 3)

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
    # C5: Watchdog state (populated by engine at end of tick)
    watchdog: dict[str, Any] = field(default_factory=dict)

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
            "watchdog": self.watchdog,
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
        _TIMEFRAME_BPD = {"1Min": 390, "5Min": 78, "15Min": 26, "1Hour": 7, "1Day": 1}
        self._bars_per_day = _TIMEFRAME_BPD.get(self._timeframe, 1)

        # ── Organism components ──────────────────────────────────
        self.signal_gen = MLSignalGenerator(
            train_window=TRAIN_WINDOW,
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            prediction_horizon=PREDICTION_HORIZON,
        )
        # improve9 B2: top_n separate from max_positions.
        # Burst cap (4/15min) and position limits still prevent overtrading.
        self.alpha_scanner = AlphaScanner(top_n=ALPHA_TOP_N)
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
                bars_per_day=self._bars_per_day,
            )
        else:
            self.kelly_sizer = KellySizer(
                max_position_pct=0.10,
                max_portfolio_pct=0.95,
                vol_target=0.15,
                min_position_usd=2000.0,
                bars_per_day=self._bars_per_day,
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

        # F4 — forensic fingerprints for detecting unexpected object
        # replacement. If id() changes after init, something swapped the
        # live learner or signal_gen mid-session.
        self._forensic_signal_gen_id: int = id(self.signal_gen)
        self._forensic_learner_id: int = id(self.learner)
        self.regime_detector = RegimeDetector(is_intraday=self._is_intraday, bars_per_day=self._bars_per_day)
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
            protected_symbols=PROTECTED_SYMBOLS,
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
        self._cumulative_pnl: float = 0.0
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

        # CORE-011: Track order IDs for pending entry orders so we can
        # cancel them at the broker level on drawdown kill.
        # Maps symbol → order_id (from order service response)
        self._pending_entry_order_ids: dict[str, str] = {}

        # Liquidity gate — block entries on illiquid symbols (seed universe bypass)
        # NOTE: This is per-bar volume, not daily. For 1-min bars, mega-caps
        # do 50K-200K/bar. 10K/bar ≈ 3.9M daily — filters out true penny stocks.
        self._MIN_AVG_VOLUME = 10_000

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

        # Bar boundary detection — track last bar timestamp per symbol
        # to only advance bars_held on actual new bars, not 10s sub-ticks.
        self._last_bar_times: dict[str, str] = {}

        # Exit attribution — capture real exit reasons and fill prices
        self._last_exit_reason: dict[str, str] = {}
        self._last_exit_fill_price: dict[str, float] = {}

        # Global entries-per-hour throttle — prevents overtrading
        self._entry_timestamps: list[float] = []
        # Static fallback; overridden by _dynamic_max_entries_per_hour property
        self._MAX_ENTRIES_PER_HOUR = 3
        # Learning mode threshold: < 200 completed trades = learning (was 50)
        from backend.organism.trading_phase import LEARNING_MODE_TRADES
        self._LEARNING_MODE_TRADES = LEARNING_MODE_TRADES

        # C2 (improve8): Burst cap — rolling 15-min window
        self._entry_timestamps_15m: list[float] = []
        self._MAX_ENTRIES_15M = 4  # max 4 entries per rolling 15 minutes
        # Per-exit-type symbol cooldowns
        self._symbol_exit_type: dict[str, str] = {}  # symbol → last exit type
        self._symbol_exit_tick: dict[str, int] = {}   # symbol → tick of last exit
        self._STOP_LOSS_REENTRY_TICKS = 180   # 30 min at 10s/tick
        self._FTF_LOSS_REENTRY_TICKS = 60     # 10 min at 10s/tick
        self._PROFIT_EXIT_REENTRY_TICKS = 10  # keep current 10 ticks

        # Stale data gating — block entries when WebSocket data is stale
        self._data_stale: bool = False
        self._DATA_STALE_THRESHOLD_S = 120.0  # 2 minutes

        # v5 (improve8): Session-aware symbol loss gating
        # Tracks daily wins/losses, PnL, and stop-loss times per symbol.
        self._symbol_daily_pnl: dict[str, float] = {}         # symbol → cumulative daily P&L
        self._symbol_consecutive_losses: dict[str, int] = {}   # symbol → consecutive loss count
        self._symbol_wins_today: dict[str, int] = {}           # symbol → win count today
        self._symbol_closed_today: dict[str, int] = {}         # symbol → total closed count today
        self._symbol_stop_loss_times: dict[str, list[float]] = {}  # symbol → timestamps of stop-loss exits
        self._symbol_banned: set[str] = set()                  # banned symbols for the session
        self._SYMBOL_BAN_CONSEC_LOSSES = 2  # ban after this many consecutive losers with 0 wins

        # A5 (improve8): Regime transition cooldown
        self._last_regime: str = "unknown"
        self._regime_change_tick: int = 0
        self._REGIME_COOLDOWN_TICKS = 12  # 120s at 10s/tick

        # Warmup period — skip entries for first N ticks after startup to let
        # features stabilize and avoid cold-start entry burst.
        self._WARMUP_TICKS = 5  # ~50s at 10s tick interval

        # Consecutive equity-zero counter — avoids permanent halt on
        # transient broker API glitches.  Requires N consecutive zeros
        # before blocking entries (soft block, auto-recovers).
        self._consecutive_equity_zero: int = 0
        self._EQUITY_ZERO_THRESHOLD = 3  # 3 consecutive zeros (~30s) before blocking

        # Last-known-good equity fallback — avoids false equity-zero soft-blocks
        # when broker API transiently returns 0 or errors.
        self._last_valid_equity: float = 0.0
        self._last_valid_equity_tick: int = 0
        self._EQUITY_FALLBACK_MAX_TICKS: int = 30  # ~5 minutes at 10s ticks

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

        # ── C1-C5: Away-mode watchdog state ──────────────────────
        # C1: No-trade watchdog
        self._watchdog_last_order_tick: int = 0
        self._watchdog_no_trade_sessions: int = 0
        self._watchdog_zero_candidates_ticks: int = 0
        self._watchdog_state: str = "OK"  # "OK", "WARNING_NO_TRADES", "CRITICAL_MULTI_SESSION"
        # C2: Equity fallback watchdog
        self._watchdog_equity_fallback_count: int = 0
        self._watchdog_equity_fallback_streak: int = 0
        # C3: Universe drift watchdog
        self._watchdog_universe_drift: dict[str, Any] = {}
        # C4: Brain save watchdog
        self._watchdog_last_brain_save_tick: int = 0
        # Apr-7 P0 fix: monotonic authoritative submission counters.
        # These are bumped inside _submit_entry_order / _submit_exit_order
        # on every successful broker submission, independent of per-tick
        # LiveTickResult counters. The C1 watchdog reads these so it can
        # never disagree with reality even if a result field is missed.
        self._total_orders_submitted: int = 0
        self._total_exits_submitted: int = 0
        self._watchdog_last_total_orders: int = 0

    # ── Dynamic throttle ──────────────────────────────────────

    @property
    def _is_learning_mode(self) -> bool:
        """True when engine has < LEARNING_MODE_TRADES completed trades."""
        from backend.organism.trading_phase import LEARNING_MODE_TRADES
        return len(self._all_trades) < LEARNING_MODE_TRADES

    @property
    def _dynamic_max_entries_per_hour(self) -> int:
        """Learning mode: 12/hr. Production: max(3, 6 - open_positions)."""
        if self._is_learning_mode:
            return 12  # was 8 — more entries for faster data collection
        open_pos = len(self._exit_levels)
        return max(3, 6 - open_pos)

    # ── Private helpers ────────────────────────────────────────

    def _passes_liquidity_gate(
        self,
        symbol: str,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> bool:
        """Return False if symbol's avg volume over last 20 bars < minimum.

        Fails closed: missing data, missing volume column, or fewer than
        20 bars all return False.
        """
        df = features_by_symbol.get(symbol)
        if df is None or "volume" not in df.columns or len(df) < 20:
            return False  # Fail closed — insufficient data
        avg_vol = float(df["volume"].iloc[-20:].mean())
        return avg_vol >= self._MIN_AVG_VOLUME

    def _passes_entry_gates(
        self,
        symbol: str,
        direction: float,
        features_by_symbol: dict[str, pd.DataFrame],
        open_symbols: set[str],
        planned_entries: set[str],
        *,
        fitness_gate: float,
        min_trades_for_fitness: int,
    ) -> tuple[bool, str]:
        """Shared entry gate check used by both alpha and pure-breakout paths.

        Returns (passed, rejection_reason). If passed is True, rejection_reason
        is empty.
        """
        if symbol in open_symbols:
            return False, "open_position"
        if symbol in self._exit_cooldown:
            return False, "exit_cooldown"
        # Per-exit-type re-entry cooldown
        _last_exit_type = self._symbol_exit_type.get(symbol)
        _last_exit_tick = self._symbol_exit_tick.get(symbol, 0)
        if _last_exit_type and _last_exit_tick > 0:
            _ticks_since = self._tick_count - _last_exit_tick
            if _last_exit_type in ("stop_loss", "safety_net") and _ticks_since < self._STOP_LOSS_REENTRY_TICKS:
                return False, "exit_cooldown"
            elif _last_exit_type == "ftf_loss" and _ticks_since < self._FTF_LOSS_REENTRY_TICKS:
                return False, "exit_cooldown"
        if symbol in self._pending_entry:
            return False, "pending_entry"
        if symbol in self._entry_metadata:
            return False, "entry_metadata"
        if LONG_ONLY and direction < 0:
            return False, "long_only"
        if not sector_gate_allows(symbol, open_symbols, planned_entries):
            return False, "sector_gate"
        # Fitness gate: learning = no gate, production = hard gate for 10+ trades
        sym_fitness = self.evolved_params.symbol_fitness.get(symbol, 0.5)
        _sym_trade_count = self.evolved_params.symbol_trade_counts.get(symbol, 0)
        if (
            not self._is_learning_mode
            and _sym_trade_count >= min_trades_for_fitness
            and sym_fitness < fitness_gate
        ):
            return False, "fitness_gate"
        # Liquidity gate
        if not self._passes_liquidity_gate(symbol, features_by_symbol):
            return False, "liquidity"
        # Circuit breaker
        if symbol in self._symbol_banned:
            return False, "circuit_breaker"
        return True, ""

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
            # Hardening: only restore bookkeeping fields (symbol_fitness,
            # symbol_trade_counts, metadata) during the 300-trade freeze
            # window. Do NOT apply strategy-param overrides (signal weights,
            # exit scales, regime scales) until enough trades exist to
            # validate them.
            if self.brain.evolved_params:
                self.evolved_params = EvolvedParams.from_dict(
                    self.brain.evolved_params
                )
                _EVOLUTION_FREEZE_TRADES = 300
                _trade_count = len(self.brain.get_trade_records() or [])
                if _trade_count >= _EVOLUTION_FREEZE_TRADES:
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
                else:
                    logger.info(
                        "Evolution freeze active (%d/%d trades) — "
                        "restoring bookkeeping only, not applying param overrides",
                        _trade_count, _EVOLUTION_FREEZE_TRADES,
                    )

            # Restore governance & regime (Phase 1.2-1.3)
            self.brain.apply_governance_state(self.governance)
            self.brain.apply_regime_state(self.regime_detector)

            # Restore universe selector (Phase 4.1)
            us_data = self.brain.extra_counters.get("universe_selector")
            if us_data and isinstance(us_data, dict):
                self.universe_selector = DynamicUniverseSelector.from_dict(
                    us_data, seed_symbols=list(self._universe),
                    protected_symbols=PROTECTED_SYMBOLS,
                )
                restored_universe = self.universe_selector.active_universe
                if restored_universe:
                    self._universe = restored_universe
                    # Log whether protected symbols are present after restore+merge
                    active_set = set(self._universe)
                    missing_protected = PROTECTED_SYMBOLS - active_set
                    logger.info(
                        "Universe selector restored: %d symbols, "
                        "protected present: %s, protected missing: %s",
                        len(self._universe),
                        sorted(PROTECTED_SYMBOLS & active_set) or "none",
                        sorted(missing_protected) or "none",
                    )

            # A2: In learning mode, converge restored universe to the
            # configured base + protected symbols.  This prevents stale
            # dynamic additions from inflating API calls and causing
            # ConnectTimeout cascades.
            if self._is_learning_mode:
                base = set(
                    s.strip().upper()
                    for s in LIVE_UNIVERSE_CSV.split(",")
                    if s.strip()
                )
                base |= PROTECTED_SYMBOLS  # ensure SH/PSQ
                active_set = set(self._universe)
                extras = active_set - base
                if extras:
                    self._universe = [s for s in self._universe if s in base]
                    # Ensure all base symbols are present
                    for s in sorted(base):
                        if s not in self._universe:
                            self._universe.append(s)
                    logger.info(
                        "Learning-mode universe converged: removed %d extras %s, "
                        "active=%d symbols",
                        len(extras), sorted(extras), len(self._universe),
                    )
                    # Update selector to match
                    self.universe_selector._active = list(self._universe)

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
                        _entry = float(lvl_data.get("entry", 0))
                        _atr = float(lvl_data.get("atr", 0))
                        # ATR floor: prevent zero/NaN ATR from disabling
                        # trailing, profit lock, and pyramid adjustments
                        if _atr < 1e-6 and _entry > 0:
                            _atr = _entry * 0.02
                        self._exit_levels[sym] = ExitLevels(
                            symbol=lvl_data.get("symbol", sym),
                            direction=float(lvl_data.get("direction", 1.0)),
                            entry_price=_entry,
                            stop_loss=float(lvl_data.get("stop_loss", 0)),
                            take_profit=float(lvl_data.get("take_profit", 0)),
                            trailing_stop=float(lvl_data.get("trailing_stop", 0)),
                            atr_at_entry=_atr,
                            regime_at_entry=lvl_data.get("regime_at_entry", "unknown"),
                            highest_favorable=float(lvl_data.get("highest_favorable", lvl_data.get("entry", 0))),
                            bars_held=int(lvl_data.get("bars_held", 0)),
                            partial_tp_price=float(lvl_data.get("partial_tp_price", 0)),
                            partial_tp_taken=bool(lvl_data.get("partial_tp_taken", False)),
                            trailing_active=bool(lvl_data.get("trailing_active", False)),
                            stress_tightened=bool(lvl_data.get("stress_tightened", False)),
                            profit_locked=bool(lvl_data.get("profit_locked", False)),
                            last_bar_time=str(lvl_data.get("last_bar_time", "")),
                            prediction_horizon=int(lvl_data.get("prediction_horizon", PREDICTION_HORIZON)),
                            price_at_prior_bar=float(lvl_data.get("price_at_prior_bar", 0.0)),
                            ftf_stop_tightened=bool(lvl_data.get("ftf_stop_tightened", False)),
                            price_two_bars_ago=float(lvl_data.get("price_two_bars_ago", 0.0)),
                            initial_risk_at_entry=float(lvl_data.get("initial_risk_at_entry", 0.0)),
                        )
                    except (KeyError, ValueError, TypeError) as e:
                        # G1: promote from DEBUG to WARNING. A position
                        # without exit levels runs without stop-loss
                        # protection. Mark for forced safety handling.
                        logger.warning(
                            "G1: Cannot restore exit levels for %s: %s — "
                            "position will use safety-net exit on next tick",
                            sym, e,
                        )
                        # Mark in entry_metadata so the safety net in step 5
                        # (lines 1555-1601) can detect and handle it.
                        if sym not in self._entry_metadata:
                            self._entry_metadata[sym] = {}
                        self._entry_metadata[sym]["exit_levels_failed"] = True
                if self._exit_levels:
                    logger.info(
                        "Restored exit levels for %d positions from brain",
                        len(self._exit_levels),
                    )

            # Restore entry metadata — cross-check with broker positions
            # to prevent stale/orphan metadata from creating phantom trades.
            saved_entry_meta = self.brain.extra_counters.get("entry_metadata", {})
            if saved_entry_meta and isinstance(saved_entry_meta, dict):
                try:
                    broker_positions = await self._positions_service.get_all_positions()
                    broker_symbols = set(broker_positions.keys()) if broker_positions else set()
                except Exception:
                    broker_symbols = None  # Cannot validate — keep all metadata

                if broker_symbols is not None:
                    stale_symbols = set(saved_entry_meta.keys()) - broker_symbols
                    if stale_symbols:
                        for sym in stale_symbols:
                            saved_entry_meta.pop(sym, None)
                        logger.warning(
                            "Pruned %d stale entry metadata (no broker position): %s",
                            len(stale_symbols),
                            sorted(stale_symbols),
                        )
                self._entry_metadata = saved_entry_meta
                if self._entry_metadata:
                    logger.info(
                        "Restored entry metadata for %d positions from brain",
                        len(self._entry_metadata),
                    )

            # REMEDIATION: Restore pending entry order IDs and cancel stale orders
            saved_pending_ids = self.brain.extra_counters.get("pending_entry_order_ids", {})
            if saved_pending_ids and isinstance(saved_pending_ids, dict):
                stale_count = 0
                for sym, order_id in saved_pending_ids.items():
                    try:
                        await self._order_service.cancel_order(order_id)
                        stale_count += 1
                        logger.warning(
                            "Cancelled stale pending entry order for %s: %s",
                            sym, order_id,
                        )
                    except Exception as e:
                        logger.debug(
                            "Could not cancel stale order %s for %s (may already be expired): %s",
                            order_id, sym, e,
                        )
                if stale_count:
                    logger.info(
                        "Cancelled %d stale pending entry orders from prior session",
                        stale_count,
                    )

            # A4 away-mode fix: Restore pending entry cooldowns from brain.
            # On restart, tick numbers are stale — reset each to current tick
            # so the symbol gets a fresh cooldown window of _PENDING_ENTRY_TICKS.
            saved_pending = self.brain.extra_counters.get("pending_entry")
            if saved_pending and isinstance(saved_pending, dict):
                for sym in saved_pending:
                    self._pending_entry[sym] = self._tick_count
                logger.info(
                    "Restored %d pending entry cooldowns from brain "
                    "(reset to tick %d for fresh cooldown)",
                    len(saved_pending), self._tick_count,
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

        # H4: Log resolved trading phase using shared resolver
        from backend.organism.trading_phase import log_trading_phase
        log_trading_phase(len(self._all_trades))

        # ── Phase 4.7: Transfer learning warm-start ──────────────
        # Hardening: skip warm-start during 300-trade evolution freeze.
        # Historical params may not be valid for the current post-reset
        # learning phase and can override the conservative defaults.
        _EVOLUTION_FREEZE_TRADES = 300
        _current_trade_count = len(self._all_trades)
        if _current_trade_count >= _EVOLUTION_FREEZE_TRADES:
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
        else:
            logger.info(
                "Transfer learning warm-start skipped — evolution freeze "
                "active (%d/%d trades)", _current_trade_count, _EVOLUTION_FREEZE_TRADES,
            )

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

        # Apr-7 P0: seed watchdog baselines so a fresh boot does NOT
        # immediately claim "no orders" / "no brain save" since tick 0.
        # Real liveness is enforced once tick_count advances past the
        # 6h/3h thresholds without a real order / save.
        self._watchdog_last_order_tick = self._tick_count
        self._watchdog_last_brain_save_tick = self._tick_count
        self._watchdog_last_total_orders = self._total_orders_submitted

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
                    closed_at="",
                ))

            entry_idx[sym] = idx

        if not reconstructed:
            logger.info("No matched entry/exit pairs found in DB")
            return

        self._all_trades = reconstructed
        cumulative = 0.0
        for t in reconstructed:
            cumulative += t.pnl
        self._cumulative_pnl = cumulative
        # Do NOT populate _equity_curve from PnL — it should only contain
        # actual broker equity snapshots from _get_equity().

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
        # Gate-level rejection telemetry (reset each tick)
        self._last_gate_rejections: dict[str, int] = {}
        self._last_entries_blocked_reason: str = ""
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
        # CORE-011: expire order ID tracking in sync with pending entries
        self._pending_entry_order_ids = {
            sym: oid for sym, oid in self._pending_entry_order_ids.items()
            if sym in self._pending_entry
        }
        # REMEDIATION: Clear pending entries whose orders reached terminal state
        # (rejected/cancelled/expired) without waiting for 30-tick expiry.
        try:
            from backend.integrations.alpaca_stream import get_stream_client
            _stream = get_stream_client() if get_stream_client is not None else None
        except Exception:
            _stream = None
        if _stream is not None and hasattr(_stream, 'is_order_terminal'):
            for sym, oid in list(self._pending_entry_order_ids.items()):
                if _stream.is_order_terminal(oid):
                    self._pending_entry.pop(sym, None)
                    self._pending_entry_order_ids.pop(sym, None)
                    logger.info(
                        "Cleared pending entry for %s: order %s reached terminal state",
                        sym, oid,
                    )
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

            # 0.5 STALE DATA GATE — check streaming provider freshness
            _was_stale = self._data_stale
            if self._streaming_provider is not None:
                try:
                    last_update = getattr(self._streaming_provider, "last_update_time", None)
                    if last_update is not None:
                        staleness_s = self._time_fn() - last_update
                        self._data_stale = staleness_s > self._DATA_STALE_THRESHOLD_S
                        if self._data_stale and not _was_stale:
                            logger.warning(
                                "Data stream stale: %.0fs since last update "
                                "(threshold=%.0fs) — blocking entries",
                                staleness_s, self._DATA_STALE_THRESHOLD_S,
                            )
                        elif not self._data_stale and _was_stale:
                            logger.info("Data stream fresh again — entries unblocked")
                    else:
                        self._data_stale = False
                except Exception:
                    pass  # Non-fatal — default to not-stale

            # 1. GOVERNANCE CHECK
            # When halted, we still MUST process exits and reconciliation
            # to manage open risk.  Only new entries are blocked.
            entries_blocked = False
            if self.governance.is_trading_halted:
                entries_blocked = True
                self._last_entries_blocked_reason = "governance_halt"
                result.errors.append("Trading halted by governance — exits still active")
                result.activity.append(ActivityEvent(
                    event_type="governance", message="Trading halted — blocking new entries, exits still running",
                    timestamp=now_iso,
                ))

            # 1.1 WARMUP GATE — let features stabilize before entering
            if not entries_blocked and self._tick_count <= self._WARMUP_TICKS:
                entries_blocked = True
                self._last_entries_blocked_reason = "warmup"
                logger.info(
                    "Warmup period: %d/%d ticks — blocking entries",
                    self._tick_count, self._WARMUP_TICKS,
                )
                result.activity.append(ActivityEvent(
                    event_type="skip",
                    message=f"Warmup: tick {self._tick_count}/{self._WARMUP_TICKS} — entries blocked",
                    timestamp=now_iso,
                ))

            # 1.2 STALE DATA GATE — block entries when data > 2 min stale
            if not entries_blocked and self._data_stale:
                entries_blocked = True
                self._last_entries_blocked_reason = "stale_data"
                result.activity.append(ActivityEvent(
                    event_type="skip",
                    message="Stale data — blocking entries (exits still active)",
                    timestamp=now_iso,
                ))

            # 1.3 EOD ENTRY BLOCK + FLATTEN (improve7)
            # Block new entries after 15:45 ET, force close all by 15:58 ET.
            _eod_flatten_triggered = False
            if self._is_intraday:
                try:
                    import zoneinfo
                    _now_utc = self._now_fn()
                    _now_et = _now_utc.astimezone(zoneinfo.ZoneInfo("America/New_York"))
                    _hhmm_eod = _now_et.hour * 100 + _now_et.minute
                    if _hhmm_eod >= 1545:
                        if not entries_blocked:
                            entries_blocked = True
                            self._last_entries_blocked_reason = "eod_entry_block"
                            result.activity.append(ActivityEvent(
                                event_type="skip",
                                message=f"EOD entry block — no new entries after 15:45 ET ({_hhmm_eod})",
                                timestamp=now_iso,
                            ))
                    if _hhmm_eod >= 1558:
                        _eod_flatten_triggered = True
                except Exception:
                    pass  # timezone parsing failure is non-fatal

            # 1.5 MARKET SCAN (Phase 5) — discover new stocks
            # A2 away-mode fix: scanner MUST run even when entries are blocked
            # so that tension_lookup stays populated (prevents death spiral
            # where blocked entries → empty scanner → zero tension → permanent block).
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
                self._last_entries_blocked_reason = "insufficient_data"
                logger.warning(
                    "Insufficient features (%d symbols) — blocking entries, "
                    "exits still active via broker price fallback",
                    len(features_by_symbol),
                )

            # 3. DETECT REGIME (Phase 4.3: cross-asset conditioning)
            # Skip regime detection when features are insufficient — it
            # requires meaningful price data to function.
            regime = RegimeLabel.UNKNOWN  # default — overwritten below if features are sufficient
            _regime_conf = 0.0  # confidence of regime label
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
                _regime_conf = getattr(regime_state, "confidence", 0.0)
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
                    self._last_entries_blocked_reason = "equity_zero"
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
                    self._last_entries_blocked_reason = "drawdown_kill"
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
                    # CORE-011 fix: cancel pending entry orders at the broker
                    # so they don't fill after the drawdown kill triggers.
                    await self._cancel_pending_entry_orders()

            # Propagate any pre-existing governance halt (from manual halt
            # or prior drawdown cooldown) — separate from drawdown check
            if self.governance.is_trading_halted and not entries_blocked:
                entries_blocked = True
                self._last_entries_blocked_reason = "governance_halt"
                result.errors.append("Trading halted by governance — exits still active")

            # 5. CHECK EXITS on existing positions
            # improve9: Set learning_mode on exit engine for horizon timeout
            # and partial TP disable.
            self.exit_engine.learning_mode = self._is_learning_mode
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
                                    result.orders_submitted += 1
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

                # Bar boundary detection: use wall-clock minute boundary.
                # Alpaca historical bar timestamps lag 2-3 min, causing
                # bars_held to advance too slowly. Wall clock gives
                # consistent 1-bar-per-minute counting.
                _bar_ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
                _prev_bar_ts = self._last_bar_times.get(sym, "")
                _is_new_bar = (_bar_ts != _prev_bar_ts)
                if _is_new_bar:
                    self._last_bar_times[sym] = _bar_ts

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
                                    result.orders_submitted += 1
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
                    exit_levels, current_price, regime,
                    is_new_bar=_is_new_bar,
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
                            result.orders_submitted += 1
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
                            # G2: do NOT set cooldown on failed exit submission.
                            # Failed exits should be retried on the next tick,
                            # not blocked for 3 ticks (30s) while the position
                            # drifts unmanaged. The cooldown on the SUCCESS
                            # path (line 1662-1663) prevents duplicate orders.
                            result.errors.append(
                                f"Exit order failed for {sym}: {e}"
                            )
                            logger.warning(
                                "G2: exit submission failed for %s — will retry "
                                "next tick (no cooldown set). Error: %s",
                                sym, e,
                            )
            result.trades_closed = exits_submitted

            # v4 (improve7): EOD FLATTEN — force close all positions at 15:58 ET
            if _eod_flatten_triggered and current_positions:
                for sym, pos_data in list(current_positions.items()):
                    if sym in self._pending_exit:
                        continue  # already has a pending exit
                    qty = abs(float(pos_data.get("qty", 0)))
                    sell_shares = int(qty)
                    if sell_shares > 0:
                        try:
                            _dir = 1.0 if pos_data.get("side", "long") == "long" else -1.0
                            await self._submit_exit_order(
                                sym, sell_shares, "eod_flatten",
                                direction=_dir,
                                broker_positions=current_positions,
                            )
                            self._exit_cooldown[sym] = self._tick_count
                            self._pending_exit[sym] = self._tick_count
                            result.trades_closed += 1
                            result.orders_submitted += 1
                            result.activity.append(ActivityEvent(
                                event_type="exit",
                                symbol=sym,
                                message=f"EOD FLATTEN: {sym} — closing {sell_shares} shares before market close",
                                details={"reason": "eod_flatten", "shares": sell_shares},
                                timestamp=now_iso,
                            ))
                            logger.info(
                                "EOD flatten: closing %s (%d shares)", sym, sell_shares,
                            )
                        except Exception as e:
                            result.errors.append(f"EOD flatten failed for {sym}: {e}")
                        finally:
                            self._exit_cooldown[sym] = self._tick_count
                            self._pending_exit[sym] = self._tick_count

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
                        self._last_entries_blocked_reason = "spy_ma_filter"
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
                    self._last_entries_blocked_reason = "opening_block"
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
                    self._last_entries_blocked_reason = "regime_sitout"
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

            # ── A5 (improve8): Regime transition cooldown ──────
            _regime_cooldown_active = False
            if regime != self._last_regime:
                _prev = self._last_regime
                self._last_regime = regime
                self._regime_change_tick = self._tick_count
                # Cooldown on adverse transitions
                if _prev in ("trending_up",) and regime in ("high_vol", "trending_down"):
                    _regime_cooldown_active = True
                    logger.info(
                        "Regime transition cooldown: %s → %s — blocking main-book for %d ticks",
                        _prev, regime, self._REGIME_COOLDOWN_TICKS,
                    )
            elif (
                self._regime_change_tick > 0
                and self._tick_count - self._regime_change_tick < self._REGIME_COOLDOWN_TICKS
            ):
                _regime_cooldown_active = True

            # ── A5 (improve8): Block trending_down main-book after 10:00 ET
            _trending_down_block = False
            if not entries_blocked and LONG_ONLY and regime == "trending_down":
                try:
                    import zoneinfo
                    _now_td = self._now_fn().astimezone(zoneinfo.ZoneInfo("America/New_York"))
                except Exception:
                    _now_td = self._now_fn()
                _hhmm_td = _now_td.hour * 100 + _now_td.minute
                if _hhmm_td >= 1000:
                    _trending_down_block = True
                    logger.info(
                        "Trending-down block: %s regime after 10:00 ET — main-book blocked",
                        regime,
                    )

            # ── Fix E: Global entries-per-hour throttle ───────
            _throttled = False
            if not entries_blocked and not _regime_sit_out:
                now_ts = self._time_fn()
                self._entry_timestamps = [
                    t for t in self._entry_timestamps if now_ts - t < 3600
                ]
                _effective_max = self._dynamic_max_entries_per_hour
                if len(self._entry_timestamps) >= _effective_max:
                    _throttled = True
                    self._last_entries_blocked_reason = "throttle"
                    logger.info(
                        "Entry throttle: %d entries in last hour (max %d, %s) — "
                        "blocking new entries this tick",
                        len(self._entry_timestamps), _effective_max,
                        "learning" if self._is_learning_mode else "production",
                    )
                    result.activity.append(ActivityEvent(
                        event_type="skip",
                        message=f"Entry throttle: {len(self._entry_timestamps)}/{_effective_max} entries/hour — pausing",
                        timestamp=now_iso,
                    ))

            # ── C2 (improve8): Burst cap — 15-min rolling window ──
            _burst_capped = False
            _burst_remaining = self._MAX_ENTRIES_15M
            if not entries_blocked and not _regime_sit_out and not _throttled:
                now_ts_burst = self._time_fn()
                self._entry_timestamps_15m = [
                    t for t in self._entry_timestamps_15m if now_ts_burst - t < 900
                ]
                _burst_remaining = max(0, self._MAX_ENTRIES_15M - len(self._entry_timestamps_15m))
                if _burst_remaining == 0:
                    _burst_capped = True
                    self._last_entries_blocked_reason = "burst_cap"
                    logger.info(
                        "Burst cap: %d entries in last 15 min (max %d)",
                        len(self._entry_timestamps_15m), self._MAX_ENTRIES_15M,
                    )

            # improve9 A6: Entries only on completed 1-min bars.
            # Exits/risk checks run every 10s tick, but new entries only
            # when a new minute boundary is reached. Reduces same-bar churn.
            _current_minute = self._now_fn().strftime("%Y-%m-%d %H:%M")
            _is_entry_bar = (_current_minute != getattr(self, "_last_entry_bar", ""))
            if _is_entry_bar:
                self._last_entry_bar = _current_minute

            # ── Steps 6-9: Entry-side logic (gated) ─────────────
            if not entries_blocked and not _regime_sit_out and not _throttled and not _burst_capped and _is_entry_bar:

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
                            pyr_order_result = await self._submit_entry_order(
                                sym,
                                action.shares_to_add,
                                confidence=0.7,
                                reason="pyramid_add",
                            )
                            self._pending_entry[sym] = self._tick_count
                            # CORE-011: track order_id for broker-level cancellation
                            if isinstance(pyr_order_result, dict) and pyr_order_result.get("order_id"):
                                self._pending_entry_order_ids[sym] = pyr_order_result["order_id"]
                            result.orders_submitted += 1

                            # H5 FIX: Do NOT record pyramid layer here.
                            # Layer state, avg_entry, and exit-level anchors are
                            # deferred until broker fill is confirmed via the
                            # avg_entry_price sync in _reconcile_fills(). This
                            # prevents phantom layers on rejected/canceled orders.
                            # The pending_entry tracking above prevents the
                            # pyramider from re-triggering on the next tick.
                        except Exception as e:
                            result.errors.append(
                                f"Pyramid order failed for {sym}: {e}"
                            )

                    # EXIT-001 fix: process close_partial and tighten_stop
                    # actions that were previously silently dropped.
                    elif action.action == "close_partial" and action.shares_to_add < 0:
                        # EXPERIMENT 1A: chop-regime minimum-hold gate for
                        # pyramid cuts. In chop, suppress pyramid_cut exits
                        # until the trade has been held for at least 10 bars.
                        # Rationale: Apr 7-10 baseline shows 24/32 trades
                        # exit via pyramid_cut, ALL losers (-$63.80), while
                        # 78% of entries go green (MFE > 0). Premature cuts
                        # in chop destroy edge that would have been captured
                        # by holding. Timeout exits (18-30 bars) are 100%
                        # winners (+$18.68).
                        _CHOP_MIN_HOLD_BARS = 10
                        _is_chop = (regime == "chop")
                        _meta = self._entry_metadata.get(sym, {})
                        _entry_tick = _meta.get("entry_tick", 0)
                        _bars_held = self._tick_count - _entry_tick
                        if _is_chop and _bars_held < _CHOP_MIN_HOLD_BARS:
                            _unrealized = pyr.unrealized_pnl(current_price) if pyr else 0.0
                            logger.info(
                                "Exp1A: pyramid_cut suppressed (chop min-hold): "
                                "%s bars_held=%d/%d regime=%s r=%.1fR "
                                "unrealized=$%.2f reason=%s",
                                sym, _bars_held, _CHOP_MIN_HOLD_BARS,
                                regime, pyr.r_multiple if pyr else 0.0,
                                _unrealized, action.reason,
                            )
                            # Skip the pyramid cut — let the trade breathe
                            continue

                        shares_to_close = abs(action.shares_to_add)
                        direction = float(pos_data.get("direction", 1.0)) if isinstance(pos_data, dict) else 1.0
                        try:
                            await self._submit_exit_order(
                                sym,
                                shares_to_close,
                                reason=f"pyramid_{action.reason}",
                                direction=direction,
                            )
                            self._pending_exit[sym] = self._tick_count
                            result.orders_submitted += 1
                            logger.info(
                                "Pyramider close_partial: %s %d shares (%s)",
                                sym, shares_to_close, action.reason,
                            )
                        except Exception as e:
                            result.errors.append(
                                f"Pyramid close_partial failed for {sym}: {e}"
                            )

                    elif action.action == "tighten_stop" and action.new_stop > 0:
                        exit_lvl = self._exit_levels.get(sym)
                        if exit_lvl is not None:
                            old_stop = exit_lvl.stop_loss
                            # Only tighten — never widen the stop
                            direction = exit_lvl.direction
                            if (direction > 0 and action.new_stop > old_stop) or \
                               (direction < 0 and action.new_stop < old_stop):
                                exit_lvl.stop_loss = action.new_stop
                                exit_lvl.trailing_stop = action.new_stop
                                logger.info(
                                    "Pyramider tighten_stop: %s %.4f -> %.4f (%s)",
                                    sym, old_stop, action.new_stop, action.reason,
                                )
                            else:
                                logger.debug(
                                    "Pyramider tighten_stop skipped (not tighter): "
                                    "%s new=%.4f old=%.4f",
                                    sym, action.new_stop, old_stop,
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
                    features_by_symbol, ml_signals, regime,
                    ml_is_trained=self.signal_gen.is_trained,
                    learning_mode=self._is_learning_mode,
                )

                # Build candidate list
                # Build tension lookup from scanner
                _tension_lookup: dict[str, float] = {}
                if self.market_scanner is not None:
                    for ss in self.market_scanner.scanned_stocks:
                        _tension_lookup[ss.symbol] = ss.tension_score

                # A2 (improve8): Two-tier entry quality gates
                # Main-book: strict gates for full-sized positions
                # Exploration: relaxed gates for micro-size learning trades
                # improve9 B1: Unified fitness system — canonical rules:
                # - Learning mode: fitness is soft ranking only (A5), no gate
                # - Production: hard gate at 0.45, but only for symbols with
                #   10+ closed trades (canonical trade count in evolved_params)
                _MAIN_FITNESS_GATE = 0.45
                _MIN_TRADES_FOR_FITNESS_GATE = 10
                # Main-book confidence gates (per-regime)
                _MAIN_CONF_BASELINE = 0.40
                _MAIN_CONF_DEFENSIVE = 0.45  # chop/high_vol/trending_down
                _EXPL_CONF_GATE = 0.25

                # Track symbols planned for entry in THIS tick so the sector gate
                # counts them when evaluating subsequent candidates.  Prevents
                # intra-tick sector-limit violations.
                _planned_entries: set[str] = set()

                # Store gate thresholds for telemetry
                self._last_eff_fitness_gate = 0.0 if self._is_learning_mode else _MAIN_FITNESS_GATE
                self._last_eff_conf_gate = _MAIN_CONF_BASELINE
                self._last_burst_remaining = _burst_remaining

                # Unified confidence threshold — used by BOTH alpha and
                # pure-breakout paths for gate parity.
                #
                # INCIDENT RECOVERY (2026-03-29): In learning mode, the
                # confidence formula (0.65*breakout + 0.35*tension) has a
                # realistic max of ~0.43.  The 0.40/0.45 gates are
                # mathematically unreachable under normal conditions,
                # which caused 10+ days of zero trades.  Learning mode
                # now uses the exploration floor (0.25) as its main-book
                # gate so trades can accumulate for ML training.
                # Production mode thresholds remain unchanged.
                if self._is_learning_mode:
                    _MIN_MAIN_CONF = _EXPL_CONF_GATE  # 0.25
                elif regime in ("chop", "high_vol", "trending_down"):
                    _MIN_MAIN_CONF = _MAIN_CONF_DEFENSIVE  # 0.45
                else:
                    _MIN_MAIN_CONF = _MAIN_CONF_BASELINE  # 0.40

                # Rejection counters dict — cleaner than individual vars
                _rej_counts = {
                    "open_position": 0, "exit_cooldown": 0,
                    "pending_entry": 0, "entry_metadata": 0,
                    "long_only": 0, "sector_gate": 0,
                    "fitness_gate": 0, "liquidity": 0,
                    "circuit_breaker": 0, "confidence_gate": 0,
                }

                cand_dicts = []
                for c in candidates:
                    # Shared entry gates (alpha + breakout use same helper)
                    _gate_ok, _gate_reason = self._passes_entry_gates(
                        c.symbol, c.direction, features_by_symbol,
                        open_symbols, _planned_entries,
                        fitness_gate=_MAIN_FITNESS_GATE,
                        min_trades_for_fitness=_MIN_TRADES_FOR_FITNESS_GATE,
                    )
                    if not _gate_ok:
                        _rej_counts[_gate_reason] = _rej_counts.get(_gate_reason, 0) + 1
                        if _gate_reason == "sector_gate":
                            logger.info(
                                "Sector gate blocked %s (sector=%s, planned=%s)",
                                c.symbol, get_sector(c.symbol), _planned_entries,
                            )
                            if _PROMETHEUS_AVAILABLE:
                                ORGANISM_SECTOR_CAP_BLOCKED.inc()
                        elif _gate_reason == "fitness_gate":
                            logger.info(
                                "Fitness gate blocked %s (fitness=%.2f < %.2f)",
                                c.symbol,
                                self.evolved_params.symbol_fitness.get(c.symbol, 0.5),
                                _MAIN_FITNESS_GATE,
                            )
                        elif _gate_reason == "liquidity":
                            logger.info("Liquidity gate blocked %s", c.symbol)
                        continue

                    # B3 (improve8): Data-source provenance — determine freshness
                    _data_source = "rest_fallback"
                    if self._streaming_provider is not None:
                        _bar_age = self._streaming_provider.get_bar_age(c.symbol)
                        if _bar_age < 20.0:
                            _data_source = "streaming"
                        elif _bar_age > 120.0:
                            _data_source = "stale"

                    bs = breakout_by_sym.get(c.symbol)
                    breakout_score = bs.composite_score if bs else 0.0
                    tension = _tension_lookup.get(c.symbol, 0.0)
                    # Fallback: compute tension proxy from feature data when
                    # market_scanner has no results (outside hours, API down).
                    # Uses volume ratio + absolute return as a simple proxy
                    # to avoid zeroing 35% of the confidence formula.
                    if tension == 0.0:
                        feat_df = features_by_symbol.get(c.symbol)
                        if feat_df is not None and len(feat_df) >= 1:
                            _row = feat_df.iloc[-1]
                            _vol_ratio = float(_row.get("vol_sma_ratio", 1.0))
                            _abs_ret = abs(float(_row.get("ret_1d", 0.0)))
                            # vol_ratio > 1 means above-average volume (capped contribution)
                            # abs_ret scaled to [0, 1] range (2% move = 0.4 tension)
                            tension = min(
                                max(_vol_ratio - 1.0, 0.0) / 3.0 + _abs_ret * 20.0,
                                0.80,
                            )
                    # Additive confidence — preserves ranking granularity
                    if self._is_learning_mode:
                        # improve9: ML weight = 0 in learning mode. ML is
                        # untrained and anti-predictive (high conf = worse
                        # outcomes on Mar 6). Use only observable signals.
                        confidence = (
                            0.65 * breakout_score
                            + 0.35 * min(tension, 1.0)
                        )
                    else:
                        ml_conf = c.ml_signal.confidence if c.ml_signal else 0.0
                        confidence = (
                            0.50 * ml_conf
                            + 0.30 * breakout_score
                            + 0.20 * min(tension, 1.0)
                        )
                    # EXPERIMENT 3 INSTRUMENTATION: side-by-side confidence
                    # comparison to detect ML contamination in chop.
                    # Logs the live production confidence alongside what the
                    # pure breakout+tension (learning-mode) formula would
                    # produce. Does NOT change any gating decision — read-only.
                    _conf_bt_only = (
                        0.65 * breakout_score
                        + 0.35 * min(tension, 1.0)
                    )
                    _conf_ml_component = (
                        (c.ml_signal.confidence if c.ml_signal else 0.0)
                        if not self._is_learning_mode
                        else 0.0
                    )
                    # Will the candidate pass the main-book gate?
                    # (computed here for logging; actual gate is below)
                    _would_pass_live = confidence >= _MIN_MAIN_CONF
                    _would_pass_bt_only = _conf_bt_only >= _MIN_MAIN_CONF
                    logger.debug(
                        "Exp3: confidence side-by-side: %s regime=%s "
                        "conf_live=%.4f conf_bt_only=%.4f ml_component=%.4f "
                        "gate_pass_live=%s gate_pass_bt_only=%s "
                        "breakout=%.4f tension=%.4f learning_mode=%s",
                        c.symbol, regime,
                        confidence, _conf_bt_only, _conf_ml_component,
                        _would_pass_live, _would_pass_bt_only,
                        breakout_score, tension, self._is_learning_mode,
                    )

                    # A2 (improve8): Two-tier confidence gate
                    # Main-book: baseline 0.40, higher in defensive regimes
                    # B1 parity: _MIN_MAIN_CONF is now computed once above
                    # both paths (unified threshold).

                    # B1 (improve8): Heuristic expected_return → exploration only
                    # Exception: in learning mode, allow heuristic through main-book
                    # (A4 risk caps protect sizing). Otherwise engine can never
                    # accumulate 200 trades to train ML.
                    _is_heuristic = (
                        c.expected_return_source == "heuristic"
                        and not self._is_learning_mode
                    )

                    # Use effective_confidence for gating (B2 improve8)
                    # Hardening: in learning mode, ML is untrained and
                    # effective_confidence is unreliable — use the pure
                    # breakout+tension confidence computed above instead.
                    if self._is_learning_mode:
                        _eff_conf = confidence
                    else:
                        _eff_conf = (
                            c.ml_signal.effective_confidence
                            if c.ml_signal and c.ml_signal.effective_confidence > 0
                            else confidence
                        )

                    _route_exploration = False
                    if _is_heuristic:
                        _route_exploration = True
                    elif _trending_down_block or _regime_cooldown_active:
                        # A5: Route to exploration during trending-down / regime cooldown
                        _route_exploration = True
                    elif _data_source != "streaming" and self._streaming_provider is not None:
                        # B3: Main-book requires streaming data; rest/stale → exploration
                        _route_exploration = True
                    elif _eff_conf < _EXPL_CONF_GATE:
                        # Below exploration gate → reject outright
                        _rej_counts["confidence_gate"] += 1
                        logger.info(
                            "Confidence reject: %s (eff_conf=%.2f < %.2f)",
                            c.symbol, _eff_conf, _EXPL_CONF_GATE,
                        )
                        continue
                    elif _eff_conf < _MIN_MAIN_CONF:
                        _route_exploration = True

                    if _route_exploration:
                        _rej_counts["confidence_gate"] += 1
                        # improve9 A7: Log exploration-eligible candidates
                        # instead of routing to dead queue. The exploration
                        # queue was dead code — no executor ever processed it.
                        logger.info(
                            "Entry below main-book threshold: %s "
                            "(eff_conf=%.2f, heuristic=%s, regime=%s)",
                            c.symbol, _eff_conf, _is_heuristic, regime,
                        )
                        continue
                    cand_dicts.append({
                        "symbol": c.symbol,
                        "direction": c.direction,
                        "predicted_return": (
                            c.ml_signal.predicted_return if c.ml_signal else 0.01
                        ),
                        "confidence": confidence,
                        "effective_confidence": _eff_conf,
                        "breakout_score": breakout_score,
                        "expected_return_source": c.expected_return_source,
                        "ranking_score": c.composite_score,
                        # Exp3 instrumentation: side-by-side confidence
                        "confidence_bt_only": _conf_bt_only,
                        "confidence_ml_component": _conf_ml_component,
                        "gate_pass_bt_only": _would_pass_bt_only,
                    })
                    _planned_entries.add(c.symbol)

                # Pure breakout signals not in alpha candidates (capped at 2)
                # Uses shared _passes_entry_gates helper — identical gate
                # logic to alpha path.
                alpha_syms = {d["symbol"] for d in cand_dicts}
                _breakout_added = 0
                _MAX_PURE_BREAKOUT = 2
                for bs in breakout_signals:
                    if _breakout_added >= _MAX_PURE_BREAKOUT:
                        break
                    if bs.symbol in alpha_syms:
                        continue
                    if bs.composite_score < 0.55:
                        continue
                    # Shared entry gates (same helper as alpha path)
                    _gate_ok, _gate_reason = self._passes_entry_gates(
                        bs.symbol, 1.0, features_by_symbol,
                        open_symbols, _planned_entries,
                        fitness_gate=_MAIN_FITNESS_GATE,
                        min_trades_for_fitness=_MIN_TRADES_FOR_FITNESS_GATE,
                    )
                    if not _gate_ok:
                        if _gate_reason == "sector_gate" and _PROMETHEUS_AVAILABLE:
                            ORGANISM_SECTOR_CAP_BLOCKED.inc()
                        continue
                    # Confidence threshold
                    _bo_conf = min(bs.composite_score, 1.0)
                    # B1 parity: use unified threshold (same as alpha path)
                    if _bo_conf < _MIN_MAIN_CONF:
                        continue
                    # ML negative-direction veto — production only.
                    # In learning mode ML is untrained and anti-predictive;
                    # vetoing breakout signals on ML direction blocks valid
                    # entries from accumulating training data.
                    ml_sig = ml_signals.get(bs.symbol)
                    if not self._is_learning_mode and ml_sig and ml_sig.direction < 0:
                        continue
                    # Predicted return: use ML when available (minimal 0.3%
                    # floor to avoid zero), otherwise scale from breakout
                    # score (0.5%-2.0% range avoids flat over-estimation).
                    if ml_sig and not self._is_learning_mode:
                        pred_ret = max(ml_sig.predicted_return, 0.003)
                    else:
                        pred_ret = 0.005 + 0.015 * bs.composite_score
                    # Determine expected_return_source for breakout
                    _bo_ret_source = "heuristic"
                    if (
                        ml_sig and not self._is_learning_mode
                        and ml_sig.direction > 0
                        and abs(ml_sig.predicted_return) > 1e-6
                    ):
                        _bo_ret_source = "calibrated_breakout"
                    cand_dicts.append({
                        "symbol": bs.symbol,
                        "direction": 1.0,
                        "predicted_return": pred_ret,
                        "confidence": _bo_conf,
                        "effective_confidence": _bo_conf,
                        "breakout_score": bs.composite_score,
                        "expected_return_source": _bo_ret_source,
                        "ranking_score": bs.composite_score * _bo_conf,
                    })
                    _planned_entries.add(bs.symbol)
                    _breakout_added += 1

                cand_dicts.sort(
                    key=lambda x: x["ranking_score"],
                    reverse=True,
                )

                open_slots = MAX_OPEN_POSITIONS - len(open_symbols)
                cand_dicts = cand_dicts[: max(0, open_slots)]
                # C2 (improve8): Max 2 new symbols per tick
                cand_dicts = cand_dicts[:2]
                # Also cap by burst remaining
                cand_dicts = cand_dicts[:max(0, _burst_remaining)]

                # 7b. MISSINGNESS GATE — block entries when feature data is
                # degraded (too many NaN/Inf replaced with 0.0).
                _NAN_MISS_THRESHOLD = 0.25  # >25% features missing → skip
                _rej_missingness = 0
                _filtered = []
                for cd in cand_dicts:
                    feat_df = features_by_symbol.get(cd["symbol"])
                    if feat_df is not None and len(feat_df) > 0:
                        miss = feat_df["_nan_missingness"].iloc[-1]
                        if miss > _NAN_MISS_THRESHOLD:
                            _rej_missingness += 1
                            logger.warning(
                                "Blocking entry for %s — %.0f%% feature "
                                "missingness (threshold %.0f%%)",
                                cd["symbol"],
                                miss * 100,
                                _NAN_MISS_THRESHOLD * 100,
                            )
                            continue
                    _filtered.append(cd)
                cand_dicts = _filtered
                result.signals_generated = len(cand_dicts)

                # Store gate-level rejection counts for telemetry
                _rej_counts["missingness"] = _rej_missingness
                self._last_gate_rejections = dict(_rej_counts)

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
                    quote_provider=(
                        self._streaming_provider.get_latest_quote
                        if self._streaming_provider is not None
                        else None
                    ),
                    trade_count=len(self._all_trades),
                )
                self._last_kelly_sizes = sizes

                # Wire sizer-level rejections into gate telemetry
                _sizer_rejects = getattr(self.kelly_sizer, "_exploration_rejects", [])
                _rej_cost_gate = sum(1 for r in _sizer_rejects if r.get("reason") == "weight_too_small")
                _rej_min_notional = sum(1 for r in _sizer_rejects if r.get("reason") == "below_min_notional")
                self._last_gate_rejections["cost_gate"] = _rej_cost_gate
                self._last_gate_rejections["min_notional"] = _rej_min_notional

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

                # INVERSE_ETFS that should not enter in chop regime.
                _INVERSE_ETFS_CHOP_SUPPRESSED = frozenset({"PSQ", "SH"})

                for sz in sizes:
                    # EXPERIMENT 2: suppress inverse ETF entries in chop.
                    # Evidence: Apr 7-10 baseline shows PSQ/SH have 0% win
                    # rate across 6 trades (-$28.54) in chop. 4/6 never went
                    # green. The improve9 inverse-ETF logic was intended for
                    # trending_down hedging, not chop entries.
                    if (
                        sz.symbol in _INVERSE_ETFS_CHOP_SUPPRESSED
                        and regime == "chop"
                    ):
                        logger.info(
                            "Exp2: inverse ETF entry suppressed in chop: "
                            "%s regime=%s confidence=%.3f reason=inverse_etf_suppressed_chop",
                            sz.symbol, regime, sz.confidence,
                        )
                        result.activity.append(ActivityEvent(
                            event_type="skip",
                            symbol=sz.symbol,
                            message=f"Exp2: {sz.symbol} entry suppressed — inverse ETF in chop regime",
                            details={"reason": "inverse_etf_suppressed_chop", "regime": str(regime)},
                            timestamp=now_iso,
                        ))
                        continue

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
                            confidence=sz.confidence,
                            reason="organism_entry",
                        )

                        # Use filled qty from broker response when available
                        # (partial fills may occur)
                        filled_shares = initial_shares
                        if isinstance(order_result, dict):
                            filled_qty = order_result.get("filled_qty")
                            if filled_qty:
                                filled_shares = max(1, int(float(filled_qty)))

                        result.orders_submitted += 1
                        fresh_open.add(sz.symbol)  # Track to enforce MAX_OPEN_POSITIONS within tick
                        # Mark as pending so we don't re-submit next tick
                        self._pending_entry[sz.symbol] = self._tick_count
                        # CORE-011: track order_id for broker-level cancellation
                        if isinstance(order_result, dict) and order_result.get("order_id"):
                            self._pending_entry_order_ids[sz.symbol] = order_result["order_id"]
                        # Fix E: Record entry timestamp for hourly throttle
                        _entry_ts = self._time_fn()
                        self._entry_timestamps.append(_entry_ts)
                        # C2 (improve8): Also record 15-min burst timestamp
                        self._entry_timestamps_15m.append(_entry_ts)
                        result.activity.append(ActivityEvent(
                            event_type="order",
                            symbol=sz.symbol,
                            message=f"ORDER SUBMITTED: {'BUY' if sz.direction >= 0 else 'SELL'} "
                                    f"{filled_shares} shares of {sz.symbol}",
                            details={
                                "shares_requested": initial_shares,
                                "shares_filled": filled_shares,
                                "direction": sz.direction,
                                "confidence": sz.confidence,
                            },
                            timestamp=now_iso,
                        ))

                        # Create exit levels for the new position
                        feat_df = features_by_symbol.get(sz.symbol)
                        if feat_df is not None and len(feat_df) > 0:
                            price = float(feat_df["close"].iloc[-1])
                            predicted_return = abs(sz.predicted_return) if sz.predicted_return else 0.01

                            exit_lvl = self.exit_engine.create_exit_levels(
                                symbol=sz.symbol,
                                direction=sz.direction,
                                entry_price=price,
                                predicted_return=predicted_return,
                                features_df=feat_df,
                                regime=regime,
                                prediction_horizon=PREDICTION_HORIZON,
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
                            # Determine entry source from breakout score
                            _entry_source = "alpha"
                            if sz.breakout_score >= 0.55 and (
                                not hasattr(sz, 'predicted_return') or abs(sz.predicted_return) < 0.003
                            ):
                                _entry_source = "breakout"
                            elif sz.breakout_score >= 0.4:
                                _entry_source = "alpha+breakout"
                            self._entry_metadata[sz.symbol] = {
                                "entry_price": price,
                                "entry_tick": self._tick_count,
                                "entry_time": self._time_fn(),
                                "direction": sz.direction,
                                "filled_shares": filled_shares,
                                "predicted_return": predicted_return,
                                "confidence": sz.confidence,
                                "entry_source": _entry_source,
                                "regime_at_entry": regime,
                            }

                    except Exception as e:
                        result.errors.append(
                            f"Entry order failed for {sz.symbol}: {e}"
                        )

                # 9b. EXPLORATION BUCKET — REMOVED (improve9 hardening)
                # The exploration execution path submitted live orders for
                # rejected candidates. This violated the "no live exploration
                # execution" invariant. Exploration-eligible candidates are
                # now logged only (see improve9 A7 above) and never executed.

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
                            total_trades=len(self._all_trades),
                        )
                        self._bg_training_metadata = {
                            "status": "completed",
                            "accepted": train_result.accepted,
                            "duration_s": train_result.duration_s,
                            "last_trained_tick": self._tick_count,
                        }
                        # Persist evaluation event into learner history (J5)
                        _bg_eval_event = self._bg_trainer.get_last_evaluation_event()
                        if _bg_eval_event:
                            self.learner.state.evaluation_events.append(_bg_eval_event)
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
                    elif done and train_result and train_result.error:
                        # True training error — fall back to synchronous retrain.
                        # No evaluation event: training failed before quality gate.
                        logger.warning(
                            "Background training failed: %s — falling back to sync",
                            train_result.error,
                        )
                        self._bg_training_metadata = {
                            "status": "error",
                            "error": train_result.error,
                            "last_trained_tick": self._tick_count,
                        }
                        try:
                            self._retrain_and_evolve(features_by_symbol, regime)
                            logger.info("Synchronous fallback retrain completed")
                        except Exception as e:
                            logger.warning("Sync retrain fallback also failed: %s", e)
                    elif done and train_result:
                        # Quality-gate rejection — model trained but didn't pass
                        # the acceptance bar. Do NOT fall back to sync retrain;
                        # let the next scheduled retrain attempt naturally.
                        logger.info(
                            "Background training model rejected: %s",
                            train_result.rejection_reason,
                        )
                        self._bg_training_metadata = {
                            "status": "rejected",
                            "rejection_reason": train_result.rejection_reason,
                            "train_metrics": train_result.train_metrics,
                            "duration_s": train_result.duration_s,
                            "last_trained_tick": self._tick_count,
                        }
                        # Persist evaluation event into learner history (J5)
                        _bg_eval_event = self._bg_trainer.get_last_evaluation_event()
                        if _bg_eval_event:
                            self.learner.state.evaluation_events.append(_bg_eval_event)
                        result.activity.append(ActivityEvent(
                            event_type="retrain",
                            message=f"Background model rejected by quality gate "
                                    f"(duration={train_result.duration_s:.1f}s)",
                            details={
                                "background": True,
                                "rejection_reason": train_result.rejection_reason,
                                "train_metrics": train_result.train_metrics,
                                "duration_s": train_result.duration_s,
                            },
                            timestamp=now_iso,
                        ))
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
                            total_trades=len(self._all_trades),
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
            # Persist to DB every 6th tick (~1/min)
            if self._tick_count % 6 == 0:
                await self._persist_telemetry_to_db()
            # Daily cleanup (every ~2160 ticks ≈ 6 hours at 10s/tick)
            if self._tick_count % 2160 == 0:
                await self._cleanup_old_telemetry()
        except Exception:
            pass  # Telemetry must never break the tick loop

        # ── Production invariant checks ────────────────────────────
        # These catch state inconsistencies before they compound into
        # silent bugs.  Violations are logged as warnings (not exceptions)
        # so the tick loop keeps running.
        self._check_tick_invariants(
            broker_positions=getattr(self, "_last_positions", None),
        )

        # ── C1-C5: Away-mode watchdog checks ─────────────────────
        try:
            self._update_watchdog_state(result)
        except Exception:
            pass  # Watchdog must never break the tick loop

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
        for c in full_alpha:
            sym_fitness = self.evolved_params.symbol_fitness.get(c.symbol, 0.5)
            _sym_tc = self.evolved_params.symbol_trade_counts.get(c.symbol, 0)
            # B1: fitness gate only applies in production with 10+ trades
            fitness_gate = 0.45 if (not self._is_learning_mode and _sym_tc >= 10) else 0.0
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
                regime_scale_source=intermed.get("regime_scale_source", sz.regime_scale_source),
                expected_return_source=intermed.get("expected_return_source", sz.expected_return_source),
                dollar_risk_cap_applied=intermed.get("dollar_risk_cap_applied", sz.dollar_risk_cap_applied),
            )
            snap.kelly_details.append(kd)

        # Filtering funnel
        rej = getattr(self, "_last_gate_rejections", {})
        _above_alpha = sum(
            1 for c in full_alpha
            if c.composite_score >= self.alpha_scanner.MIN_COMPOSITE
        )
        snap.filtering = FilteringSummary(
            total_universe=len(self._universe),
            had_features=getattr(self, "_last_features_count", 0),
            alpha_scored=len(full_alpha),
            above_alpha_threshold=_above_alpha,
            breakout_scored=len(full_breakout),
            above_breakout_threshold=sum(
                1 for s in full_breakout
                if s.composite_score >= self.breakout_scanner.MIN_BREAKOUT_SCORE
            ),
            passed_sector_gate=_above_alpha - rej.get("sector_gate", 0),
            passed_fitness_gate=_above_alpha - rej.get("fitness_gate", 0),
            passed_cooldown=_above_alpha - rej.get("exit_cooldown", 0) - rej.get("pending_entry", 0),
            passed_position_limit=_above_alpha - rej.get("open_position", 0),
            kelly_sized=len(snap.kelly_details),
            orders_submitted=result.orders_submitted,
            # Gate-level rejection counters
            rejected_by_open_position=rej.get("open_position", 0),
            rejected_by_exit_cooldown=rej.get("exit_cooldown", 0),
            rejected_by_pending_entry=rej.get("pending_entry", 0),
            rejected_by_entry_metadata=rej.get("entry_metadata", 0),
            rejected_by_long_only=rej.get("long_only", 0),
            rejected_by_sector_gate=rej.get("sector_gate", 0),
            rejected_by_fitness_gate=rej.get("fitness_gate", 0),
            rejected_by_liquidity=rej.get("liquidity", 0),
            rejected_by_missingness=rej.get("missingness", 0),
            rejected_by_cost_gate=rej.get("cost_gate", 0),
            rejected_by_min_notional=rej.get("min_notional", 0),
            entries_blocked_reason=getattr(self, "_last_entries_blocked_reason", ""),
            learning_mode=self._is_learning_mode,
            effective_max_entries_per_hour=self._dynamic_max_entries_per_hour,
            effective_fitness_gate=getattr(self, "_last_eff_fitness_gate", 0.45),
            effective_confidence_gate=getattr(self, "_last_eff_conf_gate", 0.30),
            burst_cap_remaining=getattr(self, "_last_burst_remaining", 4),
        )

        return snap

    def _check_tick_invariants(self, broker_positions: dict[str, Any] | None = None) -> None:
        """Runtime invariant checks — called at the end of every tick.

        Catches:
            - Exit levels without matching entry metadata
            - Stale pending entries / exit cooldowns
            - Entry metadata for symbols with no position and no exit levels
            - Tick count sanity
            - Orphan broker positions without tracking
        """
        _broker_syms = set(broker_positions.keys()) if broker_positions else set()
        try:
            # INV-1: Every symbol in _exit_levels should have entry_metadata
            # A6 (improve8): Enhanced — if broker also has no position, purge
            for sym in list(self._exit_levels.keys()):
                if sym not in self._entry_metadata:
                    if _broker_syms and sym not in _broker_syms:
                        # No broker position + no metadata → orphan state, purge
                        del self._exit_levels[sym]
                        self._pyramid_positions.pop(sym, None)
                        logger.warning(
                            "INVARIANT: orphan_state_purged for %s "
                            "(exit_levels existed, no metadata, no broker position)",
                            sym,
                        )
                    else:
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

            # INV-6 (A6 improve8): Broker has position but no tracking
            if _broker_syms:
                for sym in _broker_syms:
                    if sym not in self._entry_metadata and sym not in self._exit_levels:
                        # Skip if pending entry/exit
                        if sym in self._pending_entry or sym in self._pending_exit:
                            continue
                        logger.warning(
                            "INVARIANT INV-6: broker position for %s has no "
                            "entry_metadata or exit_levels — will be adopted "
                            "by orphan handler",
                            sym,
                        )

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
    #  C1-C5: AWAY-MODE WATCHDOG
    # ═════════════════════════════════════════════════════════════

    def _update_watchdog_state(self, result: LiveTickResult) -> None:
        """Update all watchdog states at the end of each tick."""
        # C1: No-trade watchdog
        # Apr-7 P0: drive from the authoritative monotonic counter
        # (`_total_orders_submitted`) so the watchdog can never disagree
        # with real broker submissions even if result.orders_submitted
        # is missed at a callsite.
        if self._total_orders_submitted > self._watchdog_last_total_orders:
            self._watchdog_last_order_tick = self._tick_count
            self._watchdog_last_total_orders = self._total_orders_submitted
            self._watchdog_zero_candidates_ticks = 0
        elif result.orders_submitted > 0:
            # Belt-and-suspenders: any local bump also counts
            self._watchdog_last_order_tick = self._tick_count
            self._watchdog_zero_candidates_ticks = 0
        elif result.signals_generated == 0:
            self._watchdog_zero_candidates_ticks += 1

        ticks_since_order = self._tick_count - self._watchdog_last_order_tick
        # ~360 ticks = 1 hour at 10s interval
        if ticks_since_order > 2160:  # ~6 hours with no orders
            self._watchdog_state = "WARNING_NO_TRADES"
            if ticks_since_order > 2160 * 2:  # ~12+ hours
                self._watchdog_state = "CRITICAL_MULTI_SESSION"
                logger.critical(
                    "C1 WATCHDOG: No orders for %d ticks (>12h) — system may be inert",
                    ticks_since_order,
                )
            else:
                logger.warning(
                    "C1 WATCHDOG: No orders for %d ticks (>6h)",
                    ticks_since_order,
                )
        else:
            self._watchdog_state = "OK"

        # C3: Universe drift (every ~360 ticks to avoid overhead)
        if self._tick_count % 360 == 0:
            self._watchdog_universe_drift = self._check_universe_drift()
            if self._watchdog_universe_drift.get("protected_missing"):
                logger.warning(
                    "C3 WATCHDOG: Protected symbols missing from active universe: %s",
                    self._watchdog_universe_drift["protected_missing"],
                )

        # C4: Brain save staleness
        ticks_since_save = self._tick_count - self._watchdog_last_brain_save_tick
        if ticks_since_save > 1080:  # ~3 hours
            logger.warning(
                "C4 WATCHDOG: Brain not saved for %d ticks (>3h) — last save at tick %d",
                ticks_since_save, self._watchdog_last_brain_save_tick,
            )

        # C5: Attach unified watchdog state to tick result
        result.watchdog = self.get_watchdog_state()

    def _check_universe_drift(self) -> dict[str, Any]:
        """C3: Check if runtime universe diverges from configured base."""
        base = set(s.strip().upper() for s in LIVE_UNIVERSE_CSV.split(",") if s.strip())
        active = set(self._universe)
        missing = base - active
        added = active - base
        protected_missing = set(PROTECTED_SYMBOLS) - active
        return {
            "base_size": len(base),
            "active_size": len(active),
            "missing_from_base": sorted(missing),
            "added_beyond_base": sorted(added),
            "protected_missing": sorted(protected_missing),
            "drift_detected": bool(missing or protected_missing),
        }

    def get_watchdog_state(self) -> dict[str, Any]:
        """C5: Return unified watchdog state for all away-mode monitors."""
        return {
            "no_trade": {
                "state": self._watchdog_state,
                "ticks_since_last_order": self._tick_count - self._watchdog_last_order_tick,
                "zero_candidate_ticks": self._watchdog_zero_candidates_ticks,
            },
            "equity_fallback": {
                "total_fallback_count": self._watchdog_equity_fallback_count,
                "current_streak": self._watchdog_equity_fallback_streak,
            },
            "universe_drift": self._watchdog_universe_drift,
            "brain_save": {
                "ticks_since_last_save": self._tick_count - self._watchdog_last_brain_save_tick,
                "healthy": (self._tick_count - self._watchdog_last_brain_save_tick) < 1080,
            },
        }

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
                    bars_per_day=self._bars_per_day,
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
                    bars_per_day=self._bars_per_day,
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

    # Slippage cap for marketable limit orders (0.1% above ask / below bid)
    _ENTRY_SLIPPAGE_CAP = 0.001

    async def _submit_entry_order(
        self,
        symbol: str,
        shares: int,
        direction: float = 1.0,
        confidence: float = 0.6,
        reason: str = "organism_entry",
    ) -> dict[str, Any]:
        """Submit an entry order via OrderService.

        Uses marketable limit orders when a live quote is available to cap
        slippage. Falls back to market orders when no quote data exists.

        Uses *direction* to decide the order side:
        direction >= 0 → buy, direction < 0 → sell (short).
        """
        side = "sell" if direction < 0 else "buy"
        idem_key = (
            f"organism_{symbol}"
            f"_{datetime.now(UTC).strftime('%Y%m%d')}"
            f"_{self._session_id}_t{self._tick_count}"
        )

        # Try to compute a marketable limit price from live quote
        _order_type = "market"
        _limit_price: float | None = None
        if self._streaming_provider is not None:
            try:
                quote = self._streaming_provider.get_latest_quote(symbol)
                bid = quote.get("bid")
                ask = quote.get("ask")
                if bid and ask and bid > 0 and ask > 0:
                    if side == "buy":
                        # Cap slippage above the ask
                        _limit_price = round(ask * (1 + self._ENTRY_SLIPPAGE_CAP), 2)
                    else:
                        # Cap slippage below the bid
                        _limit_price = round(bid * (1 - self._ENTRY_SLIPPAGE_CAP), 2)
                    _order_type = "limit"
            except Exception:
                pass  # Fallback to market order

        _entry_result = await self._order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=shares,
            idempotency_key=idem_key,
            order_type=_order_type,
            tif="day",
            limit_price=_limit_price,
            attributes={
                "source": "organism",
                "reason": reason,
                "confidence": round(confidence, 4),
                "tick": self._tick_count,
            },
        )
        # Apr-7 P0: authoritative monotonic counter — survives result
        # field drift. Counts every entry/pyramid order that broker-submit
        # did not raise on (blocked/rejected dicts are still submissions).
        try:
            self._total_orders_submitted += 1
        except Exception:
            pass
        return _entry_result

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
        # Track exit reason for trade attribution
        self._last_exit_reason[symbol] = reason
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
        result = await self._order_service.submit_symbol_order(
            symbol=symbol,
            side=side,
            qty=shares,
            idempotency_key=idem_key,
            order_type="market",
            tif="day",
            reduce_only=True,  # Exit orders bypass PnL circuit breaker
            attributes={
                "source": "organism",
                "reason": reason,
                "tick": self._tick_count,
            },
        )
        # Apr-7 P0: authoritative monotonic counters. Only reach here
        # after LONG_ONLY guard and a real broker submit attempt.
        try:
            self._total_orders_submitted += 1
            self._total_exits_submitted += 1
        except Exception:
            pass
        # Capture fill price for trade attribution
        if isinstance(result, dict):
            fp = result.get("avg_fill_price")
            if fp and float(fp) > 0:
                self._last_exit_fill_price[symbol] = float(fp)
        return result

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

        # Sync entry prices from broker for tracked positions:
        # The broker's avg_entry_price is the true cost-weighted fill
        # average across all pyramid legs, which is authoritative over
        # the bar-close estimate stored at order-submission time.
        for sym in current_symbols & tracked_symbols:
            broker_avg = float(current_positions[sym].get("avg_entry_price", 0))
            if broker_avg > 0:
                meta = self._entry_metadata.get(sym)
                if meta and abs(meta.get("entry_price", 0) - broker_avg) > 0.001:
                    meta["entry_price"] = broker_avg
                pyr = self._pyramid_positions.get(sym)
                if pyr and pyr.layers:
                    broker_qty = abs(float(current_positions[sym].get("qty", 0)))
                    if broker_qty > 0 and (
                        abs(pyr.avg_entry - broker_avg) > 0.001
                        or pyr.total_shares != int(broker_qty)
                    ):
                        old_shares = pyr.total_shares
                        # Collapse pyramid layers to a single layer with
                        # the broker's authoritative cost basis and qty.
                        # Preserve the highest layer level so the pyramider
                        # won't re-trigger already-filled add levels.
                        highest_level = max(lay.level for lay in pyr.layers)
                        # If broker qty increased, a pyramid add filled —
                        # advance the level so pyramider skips that tier.
                        if int(broker_qty) > old_shares and highest_level < 2:
                            highest_level += 1
                        pyr.layers = [PyramidLevel(
                            shares=int(broker_qty),
                            entry_price=broker_avg,
                            bar_added=pyr.layers[0].bar_added,
                            level=highest_level,
                        )]
                        # H5: Reanchor exit levels from confirmed fill,
                        # not speculative order-time state
                        exit_lvl = self._exit_levels.get(sym)
                        if exit_lvl is not None and int(broker_qty) != old_shares:
                            self.exit_engine.update_levels_for_pyramid(
                                exit_lvl, broker_avg,
                                self._last_regime if self._last_regime != "unknown" else "chop",
                            )

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

            # Use real fill price from exit order when available
            real_fill = self._last_exit_fill_price.pop(sym, None)
            exit_price: float | None = None
            if real_fill and real_fill > 0:
                exit_price = real_fill
            else:
                # Try DB-based fill price (actual filled exit order)
                exit_price = await self._lookup_exit_fill_from_db(sym)
                if exit_price is None:
                    # Get last known price for exit — never fall back to entry_price
                    # (that would create phantom 0-PnL trades).
                    feat_df = features_by_symbol.get(sym)
                    if feat_df is not None and len(feat_df) > 0:
                        exit_price = float(feat_df["close"].iloc[-1])
                    else:
                        # Try latest quote from streaming data provider
                        quote = self._data_client.get_latest_quote(sym)
                        bid = quote.get("bid")
                        ask = quote.get("ask")
                        if bid and ask and bid > 0 and ask > 0:
                            exit_price = (bid + ask) / 2.0
                            logger.info(
                                "Using quote midpoint for %s exit price: $%.2f "
                                "(no bar features available)",
                                sym, exit_price,
                            )
                        elif bid and bid > 0:
                            exit_price = bid
                        elif ask and ask > 0:
                            exit_price = ask

            if exit_price is None:
                logger.warning(
                    "Skipping trade record for %s — no exit price available "
                    "(features and quotes both missing). Entry was $%.2f",
                    sym, meta["entry_price"],
                )
                # Still clean up tracking state so we don't leak metadata
                self._exit_levels.pop(sym, None)
                self._pyramid_positions.pop(sym, None)
                self._ml_reversal_used.discard(sym)
                self._last_bar_times.pop(sym, None)
                continue

            direction = meta.get("direction", 1.0)
            shares = 0
            pyr = self._pyramid_positions.get(sym)
            if pyr and pyr.total_shares > 0:
                shares = pyr.total_shares
                # Use cost-weighted average entry from all pyramid legs
                # instead of stale first-fill price from metadata
                entry_price = pyr.avg_entry
            else:
                entry_price = meta["entry_price"]

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

            _is_exploration = meta.get("exploration", False)

            # Compute causal fields (improve7)
            _exit_lvl = self._exit_levels.get(sym)
            _mfe = 0.0
            _mae = 0.0
            _bars_held = 0
            _regime_at_entry = meta.get("regime_at_entry", "unknown")
            _regime_at_exit = self._last_regime if self._last_regime != "unknown" else getattr(self.regime_detector, "current_regime", "unknown")
            if _exit_lvl is not None:
                _bars_held = _exit_lvl.bars_held
                # MFE: max favorable excursion in dollars
                _highest = _exit_lvl.highest_favorable
                _mfe = (_highest - entry_price) * direction * shares
                # MAE: max adverse excursion (worst unrealized loss)
                # Use stop_loss distance as proxy for MAE (conservative)
                _stop_dist = abs(entry_price - _exit_lvl.stop_loss)
                _mae = _stop_dist * shares
            _entry_time = meta.get("entry_time", 0)
            _time_in_trade = self._time_fn() - _entry_time if _entry_time > 0 else 0.0

            _exit_reason = self._last_exit_reason.pop(sym, "live_close")
            # Tag reconciliation adjustments: position disappeared from
            # broker without a normal exit order.  These are cross-session
            # carryover cleanups or orphan metadata, not strategy trades.
            if _exit_reason == "live_close" and real_fill is None and _bars_held == 0:
                _exit_reason = "reconciliation_adjustment"
                logger.warning(
                    "Reconciliation adjustment: %s had stale entry metadata "
                    "(entry=$%.2f) with no broker position or exit fill — "
                    "tagging as non-strategy PnL",
                    sym, entry_price,
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
                exit_reason=_exit_reason,
                predicted_return=meta.get("predicted_return", 0),
                actual_return=actual_return,
                confidence=meta.get("confidence", 0),
                is_exploration=_is_exploration,
                entry_source=meta.get("entry_source", ""),
                regime_at_entry=_regime_at_entry,
                regime_at_exit=_regime_at_exit,
                mfe=round(_mfe, 2),
                mae=round(_mae, 2),
                bars_held_at_exit=_bars_held,
                time_in_trade_seconds=round(_time_in_trade, 1),
                closed_at=datetime.fromtimestamp(self._time_fn(), tz=UTC).isoformat() if self._time_fn() > 0 else "",
            )
            self._all_trades.append(trade)
            self.learner.record_trade(trade)

            # B1 (improve9): Canonical symbol trade count — increment
            # at the source so it stays consistent regardless of whether
            # evolution is frozen (B5) or running.
            self.evolved_params.symbol_trade_counts[sym] = (
                self.evolved_params.symbol_trade_counts.get(sym, 0) + 1
            )

            # v5 (improve8): Session-aware symbol loss gating
            if not _is_exploration:
                self._symbol_daily_pnl[sym] = self._symbol_daily_pnl.get(sym, 0.0) + pnl
                self._symbol_closed_today[sym] = self._symbol_closed_today.get(sym, 0) + 1
                if pnl <= 0:
                    self._symbol_consecutive_losses[sym] = (
                        self._symbol_consecutive_losses.get(sym, 0) + 1
                    )
                else:
                    self._symbol_consecutive_losses[sym] = 0
                    self._symbol_wins_today[sym] = self._symbol_wins_today.get(sym, 0) + 1

                # Track stop-loss exit timestamps for rolling 30-min window
                _exit_reason = trade.exit_reason
                if _exit_reason in ("stop_loss", "safety_net"):
                    if sym not in self._symbol_stop_loss_times:
                        self._symbol_stop_loss_times[sym] = []
                    self._symbol_stop_loss_times[sym].append(self._time_fn())

                # A3 (improve8): Session-aware ban conditions
                _equity = self._peak_equity if self._peak_equity > 0 else 100000.0
                _ban_pnl_threshold = -max(25.0, _equity * 0.0010)
                _sym_wins = self._symbol_wins_today.get(sym, 0)
                _sym_consec = self._symbol_consecutive_losses.get(sym, 0)
                _sym_pnl = self._symbol_daily_pnl.get(sym, 0.0)

                # Rolling 30-min stop-loss window
                _now_ts = self._time_fn()
                _sl_times = self._symbol_stop_loss_times.get(sym, [])
                _sl_times_30m = [t for t in _sl_times if _now_ts - t < 1800]
                self._symbol_stop_loss_times[sym] = _sl_times_30m

                if sym not in self._symbol_banned and (
                    (_sym_consec >= self._SYMBOL_BAN_CONSEC_LOSSES and _sym_wins == 0)
                    or _sym_pnl <= _ban_pnl_threshold
                    or len(_sl_times_30m) >= 2
                ):
                    self._symbol_banned.add(sym)
                    logger.warning(
                        "Symbol circuit breaker: %s BANNED for session "
                        "(daily_pnl=$%.2f, consec_losses=%d, wins=%d, "
                        "stop_losses_30m=%d, ban_threshold=$%.2f)",
                        sym, _sym_pnl, _sym_consec, _sym_wins,
                        len(_sl_times_30m), _ban_pnl_threshold,
                    )

            # C2 (improve8): Track per-exit-type cooldowns
            _exit_type = trade.exit_reason
            if _exit_type in ("stop_loss", "safety_net"):
                self._symbol_exit_type[sym] = "stop_loss"
            elif _exit_type == "ftf_loss" or (_exit_type == "ftf_chop" and pnl <= 0):
                self._symbol_exit_type[sym] = "ftf_loss"
            else:
                self._symbol_exit_type[sym] = _exit_type
            self._symbol_exit_tick[sym] = self._tick_count

            # Record for regime-stratified Kelly (skip exploration to prevent
            # micro-size trades from polluting main Kelly statistics)
            if not _is_exploration:
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
            self._last_bar_times.pop(sym, None)
            self._last_exit_reason.pop(sym, None)
            self._last_exit_fill_price.pop(sym, None)

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
                        prediction_horizon=PREDICTION_HORIZON,
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

    async def _lookup_exit_fill_from_db(self, symbol: str) -> float | None:
        """Look up actual exit fill price from DB for a recently closed position.

        Queries the most recent filled sell order for this symbol with
        organism source attribution.  Returns the avg_fill_price if found,
        or None if no DB session is available or no matching order exists.
        """
        if not self._sessionmaker:
            return None
        try:
            from sqlalchemy import select, text as sa_text
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                stmt = (
                    select(Order.avg_fill_price)
                    .where(
                        Order.symbol == symbol,
                        Order.side == "sell",
                        Order.status == "filled",
                        sa_text("attributes->>'source' = 'organism'"),
                    )
                    .order_by(Order.updated_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is not None and float(row) > 0:
                    price = float(row)
                    logger.info(
                        "DB fill price for %s exit: $%.2f", symbol, price,
                    )
                    return price
        except Exception as e:
            logger.debug("DB exit fill lookup failed for %s: %s", symbol, e)
        return None

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
                        prediction_horizon=PREDICTION_HORIZON,
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
                        prediction_horizon=PREDICTION_HORIZON,
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

        # improve9 B5: Freeze all self-evolution except symbol bookkeeping
        # until at least 300 clean post-reset trades. The adaptation space
        # (signal weights, exit params, regime scales, breakout weights, etc.)
        # is too wide for the sample size during bootstrap.
        _EVOLUTION_FREEZE_TRADES = 300
        recent_trades = self._all_trades[-200:]  # last 200 trades
        _total_trades = len(self._all_trades)

        if recent_trades and _total_trades >= _EVOLUTION_FREEZE_TRADES:
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
        elif _total_trades < _EVOLUTION_FREEZE_TRADES:
            logger.info(
                "Evolution frozen (%d/%d trades) — symbol bookkeeping only",
                _total_trades, _EVOLUTION_FREEZE_TRADES,
            )

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

    async def _persist_telemetry_to_db(self) -> None:
        """Write latest telemetry snapshot to DB (every 6th tick ≈ 1/min)."""
        if self._sessionmaker is None:
            return
        snap = self._telemetry.latest
        if snap is None:
            return
        try:
            from backend.infra.schemas import TickTelemetry
            from backend.infra.database import get_session_context

            # Top candidates summary (compact)
            top_cands = [
                {"sym": ad.symbol, "score": round(ad.composite_score, 4), "dir": ad.direction}
                for ad in snap.alpha_details[:5]
            ]
            # Exit decisions summary
            exit_decs = [
                {"sym": ed.symbol, "bars": ed.bars_held, "pnl": round(ed.pnl_pct, 4),
                 "nearest": ed.nearest_exit}
                for ed in snap.exit_details
            ]

            async with get_session_context() as session:
                row = TickTelemetry(
                    tick_number=snap.tick_number,
                    regime=snap.regime,
                    equity=snap.equity,
                    drawdown_pct=snap.drawdown_pct,
                    open_positions=snap.open_positions,
                    entries_blocked_reason=snap.filtering.entries_blocked_reason,
                    orders_submitted=snap.filtering.orders_submitted,
                    gate_rejections=snap.filtering.to_dict().get("rejections", {}),
                    top_candidates=top_cands,
                    exit_decisions=exit_decs,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.debug("Telemetry DB write skipped: %s", e)

    async def _cleanup_old_telemetry(self) -> None:
        """Delete telemetry rows older than 7 days."""
        if self._sessionmaker is None:
            return
        try:
            from backend.infra.schemas import TickTelemetry
            from backend.infra.database import get_session_context

            import sqlalchemy as sa
            cutoff = self._now_fn() - timedelta(days=7)
            async with get_session_context() as session:
                await session.execute(
                    sa.delete(TickTelemetry).where(TickTelemetry.timestamp < cutoff)
                )
                await session.commit()
            logger.info("Cleaned up telemetry rows older than 7 days")
        except Exception as e:
            logger.debug("Telemetry cleanup skipped: %s", e)

    def force_save_brain(self) -> dict:
        """Admin-only recovery path: persist the full brain bypassing the
        walk-forward gate.

        This method is the ONLY way to write ML joblibs + reference features
        + evolved params + fully synced manifest from the live process when
        the walk-forward gate has been blocking normal tick-driven saves.

        It deliberately does NOT:
          - submit orders
          - call walk_forward_gate
          - re-train any model
          - touch scheduler state

        It returns a verification dict with live gen/trades/best_sharpe/
        ml_is_trained/feature_count so callers (admin route) can confirm
        the save landed against the expected live object graph.
        """
        logger.warning(
            "FORCE SAVE requested at tick %d — bypassing walk-forward gate",
            self._tick_count,
        )
        try:
            # Mirror _save_brain: always persist exit_levels + entry_metadata
            exit_levels_snapshot = {
                sym: lvl.to_dict()
                for sym, lvl in self._exit_levels.items()
            }
            entry_metadata_snapshot = dict(self._entry_metadata)
            self._persist_exit_levels_standalone(
                exit_levels_snapshot, entry_metadata_snapshot
            )

            # Full save — bypass the gate, same kwargs block as _save_brain
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
                    "pending_entry": dict(self._pending_entry),
                },
                evolved_params=self.evolved_params.to_dict(),
                governance_controller=self.governance,
                regime_detector=self.regime_detector,
                force=True,
            )
            # C4 watchdog: truth-source update
            self._watchdog_last_brain_save_tick = self._tick_count

            best_sharpe = self.learner.state.best_sharpe
            if not np.isfinite(best_sharpe):
                best_sharpe = None
            return {
                "success": True,
                "forced": True,
                "tick": self._tick_count,
                "generation": self.learner.state.generation,
                "total_trades": self.learner.state.total_trades,
                "cumulative_pnl": self.learner.state.cumulative_pnl,
                "best_sharpe": best_sharpe,
                "ml_is_trained": getattr(self.signal_gen, "_is_trained", False),
                "feature_count": len(
                    getattr(self.signal_gen, "_feature_cols", []) or []
                ),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except Exception as e:
            logger.error("force_save_brain failed: %s", e, exc_info=True)
            return {
                "success": False,
                "forced": True,
                "error": str(e),
                "tick": self._tick_count,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def _save_brain(self) -> None:
        """Save full brain state to disk (with walk-forward gate)."""
        try:
            # F4 — forensic guard: detect unexpected object replacement
            if (
                id(self.signal_gen) != self._forensic_signal_gen_id
                or id(self.learner) != self._forensic_learner_id
            ):
                import traceback as _tb
                logger.critical(
                    "FORENSIC GUARD: live engine's learner/signal_gen object "
                    "identity changed since __init__. "
                    "signal_gen id=%d (was %d), learner id=%d (was %d). "
                    "Stack:\n%s",
                    id(self.signal_gen), self._forensic_signal_gen_id,
                    id(self.learner), self._forensic_learner_id,
                    "".join(_tb.format_stack()),
                )
                # Do not abort here — the guarded helper will block any
                # unsafe write. But the CRITICAL log captures the caller.

            # F4 — regression detection: if learner state regressed to
            # fresh while disk says trained, abort to preserve disk truth.
            _learner_state = getattr(self.learner, "state", None)
            if (
                _learner_state is not None
                and getattr(_learner_state, "total_trades", 0) == 0
            ):
                try:
                    from backend.organism.brain_persistence import (
                        _read_json, MANIFEST_FILE,
                    )
                    _disk = _read_json(self.brain.brain_dir / MANIFEST_FILE)
                    _disk_trades = _disk.get("total_trades", 0) or 0
                    if _disk_trades > 0:
                        import traceback as _tb2
                        logger.critical(
                            "FORENSIC GUARD: live learner.state.total_trades=0 "
                            "but disk manifest shows total_trades=%d. Learner "
                            "state regressed. Skipping save to avoid wiping "
                            "disk. Stack:\n%s",
                            _disk_trades,
                            "".join(_tb2.format_stack()),
                        )
                        return  # Abort save entirely
                except Exception:
                    pass  # If we can't read disk, let the guarded helper decide

            # CORE-013 fix: always persist exit_levels and entry_metadata
            # even when the walk-forward gate blocks the full brain save.
            # These are safety-critical (trailing stops, partial TP flags)
            # and must survive restarts regardless of Sharpe regression.
            exit_levels_snapshot = {
                sym: lvl.to_dict()
                for sym, lvl in self._exit_levels.items()
            }
            entry_metadata_snapshot = dict(self._entry_metadata)
            self._persist_exit_levels_standalone(
                exit_levels_snapshot, entry_metadata_snapshot
            )

            # Walk-forward gate: skip full save if regression detected
            should_save, reason = self.brain.walk_forward_gate(
                self._all_trades[-100:],  # evaluate on last 100 trades
                min_trades=10,
                regression_threshold=0.95,
                learner=self.learner,
            )
            if not should_save:
                logger.warning(
                    "Full brain save SKIPPED by walk-forward gate: %s "
                    "— persisting all runtime truth (ML models + evolved_params gated)",
                    reason,
                )
                self.brain.save_essential_state(
                    signal_gen=self.signal_gen,
                    learner=self.learner,
                    all_trades=self._all_trades,
                    equity_curve=self._equity_curve,
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
                        "pending_entry": dict(self._pending_entry),
                    },
                    governance_controller=self.governance,
                    regime_detector=self.regime_detector,
                )
                self._watchdog_last_brain_save_tick = self._tick_count
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
                    "pending_entry": dict(self._pending_entry),
                },
                evolved_params=self.evolved_params.to_dict(),
                governance_controller=self.governance,
                regime_detector=self.regime_detector,
            )
            # C4: Update brain save watchdog tick
            self._watchdog_last_brain_save_tick = self._tick_count
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

    def _persist_exit_levels_standalone(
        self,
        exit_levels: dict[str, Any],
        entry_metadata: dict[str, Any],
    ) -> None:
        """CORE-013: Persist exit_levels and entry_metadata independently.

        Called before the walk-forward gate so these safety-critical fields
        survive even when the gate blocks the full brain save.
        """
        import json
        try:
            ec_path = self.brain.brain_dir / "extra_counters.json"
            if ec_path.is_file():
                with open(ec_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {}
            data["exit_levels"] = exit_levels
            data["entry_metadata"] = entry_metadata
            data["pending_entry_order_ids"] = dict(getattr(self, "_pending_entry_order_ids", {}))
            with open(ec_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to persist exit_levels standalone: %s", e)

    async def _cancel_pending_entry_orders(self) -> None:
        """CORE-011: Cancel open entry orders at the broker on drawdown kill.

        Iterates ``_pending_entry_order_ids`` and calls
        ``_order_service.cancel_order()`` for each.  Failures are logged
        but never crash the tick loop.  Exit/reduce-only orders are not
        tracked here and are therefore never cancelled.
        """
        if not self._pending_entry and not self._pending_entry_order_ids:
            return

        cancelled = []
        failed = []
        for sym, order_id in list(self._pending_entry_order_ids.items()):
            try:
                await self._order_service.cancel_order(order_id)
                cancelled.append(sym)
            except Exception as e:
                failed.append(sym)
                logger.error(
                    "Drawdown kill: failed to cancel order %s for %s: %s",
                    order_id, sym, e,
                )

        # Always clear local bookkeeping regardless of cancel outcome
        cleared_symbols = list(self._pending_entry.keys())
        self._pending_entry.clear()
        self._pending_entry_order_ids.clear()

        if cancelled:
            logger.warning(
                "Drawdown kill: cancelled %d broker entry orders: %s",
                len(cancelled), cancelled,
            )
        if failed:
            logger.warning(
                "Drawdown kill: %d cancel attempts failed: %s "
                "(local bookkeeping still cleared)",
                len(failed), failed,
            )
        if cleared_symbols and not cancelled and not failed:
            logger.warning(
                "Drawdown kill: cleared %d pending entries (no order IDs to cancel): %s",
                len(cleared_symbols), cleared_symbols,
            )

    # ═════════════════════════════════════════════════════════════
    #  HELPERS
    # ═════════════════════════════════════════════════════════════

    async def _get_equity(self) -> float:
        """Get current portfolio equity from broker.

        Falls back to last-known-good equity if the broker returns zero
        or errors, bounded by a staleness window.
        """
        value = 0.0
        try:
            raw = await self._positions_service.get_total_portfolio_value()
            value = float(raw) if raw else 0.0
        except Exception:
            try:
                bp = await self._positions_service.get_buying_power()
                value = float(bp) if bp else 0.0
            except Exception:
                pass

        if value > 0:
            self._last_valid_equity = value
            self._last_valid_equity_tick = self._tick_count
            # C2: Reset fallback streak on fresh equity
            self._watchdog_equity_fallback_streak = 0
            return value

        # Fallback: use last-known-good equity within staleness window
        ticks_since = self._tick_count - self._last_valid_equity_tick
        if self._last_valid_equity > 0 and ticks_since <= self._EQUITY_FALLBACK_MAX_TICKS:
            # C2: Track equity fallback usage
            self._watchdog_equity_fallback_count += 1
            self._watchdog_equity_fallback_streak += 1
            if self._watchdog_equity_fallback_streak > 25:
                logger.critical(
                    "C2 WATCHDOG: Equity fallback streak=%d — broker API may be down",
                    self._watchdog_equity_fallback_streak,
                )
            elif self._watchdog_equity_fallback_streak > 10:
                logger.warning(
                    "C2 WATCHDOG: Equity fallback streak=%d — broker API returning zero",
                    self._watchdog_equity_fallback_streak,
                )
            logger.warning(
                "Broker returned zero equity — using last-known-good $%.2f "
                "(%d ticks stale, max %d)",
                self._last_valid_equity, ticks_since, self._EQUITY_FALLBACK_MAX_TICKS,
            )
            return self._last_valid_equity

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
            "current_equity": self._equity_curve[-1] if self._equity_curve else None,
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
            "data_stale": self._data_stale,
            "learning_mode": self._is_learning_mode,
            "watchdog": self.get_watchdog_state(),
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
            self.alpha_scanner = AlphaScanner(top_n=ALPHA_TOP_N)
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
            features_by_symbol, ml_signals, regime,
            ml_is_trained=self.signal_gen.is_trained,
            learning_mode=self._is_learning_mode,
        )

        signals = []
        now = datetime.now(UTC)
        for c in candidates:
            if LONG_ONLY and not self.evolved_params.shorts_enabled and c.direction < 0:
                continue
            # Learning mode: use composite_score (breakout+tension based,
            # no ML). Production: use ML confidence if available.
            if self._is_learning_mode:
                confidence = c.composite_score
            else:
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
