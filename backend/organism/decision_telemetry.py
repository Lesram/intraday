"""
Decision Telemetry — Full transparency into the organism's decision pipeline.

Captures per-tick snapshots of every indicator, threshold, and decision gate
so the frontend can render the full "why" behind every trade action.

This module provides an in-memory ring buffer (~360 ticks / ~1 hour).
A separate persistence path (TickTelemetry table via live_engine) writes
summarised snapshots to the database for longer-term analysis. This module
does not perform DB writes itself.
"""

from __future__ import annotations

import collections
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _f(v: Any) -> float:
    """Safely cast to native float (handles numpy.float64, int, etc.)."""
    x = float(v)
    return 0.0 if not math.isfinite(x) else x


def _b(v: Any) -> bool:
    """Safely cast to native bool (handles numpy.bool_)."""
    return bool(v)


@dataclass
class SymbolAlphaDetail:
    """Per-symbol 7-factor alpha breakdown."""
    symbol: str
    composite_score: float = 0.0
    ml_score: float = 0.0
    breakout_score: float = 0.0
    institutional_score: float = 0.0
    momentum_score: float = 0.0
    momentum_quality_score: float = 0.0
    vol_price_div_score: float = 0.0
    regime_score: float = 0.0
    direction: float = 0.0
    # Weights used
    weights: dict[str, float] = field(default_factory=dict)
    # Threshold proximity
    min_composite_threshold: float = 0.15
    distance_to_threshold: float = 0.0
    passed_threshold: bool = False
    # Fitness gate
    symbol_fitness: float = 0.5
    fitness_gate: float = 0.45
    passed_fitness: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "composite_score": round(_f(self.composite_score), 4),
            "factors": {
                "ml": round(_f(self.ml_score), 4),
                "breakout": round(_f(self.breakout_score), 4),
                "institutional": round(_f(self.institutional_score), 4),
                "momentum": round(_f(self.momentum_score), 4),
                "momentum_quality": round(_f(self.momentum_quality_score), 4),
                "vol_price_div": round(_f(self.vol_price_div_score), 4),
                "regime": round(_f(self.regime_score), 4),
            },
            "weights": {k: round(_f(v), 4) for k, v in self.weights.items()},
            "direction": _f(self.direction),
            "threshold": round(_f(self.min_composite_threshold), 4),
            "distance_to_threshold": round(_f(self.distance_to_threshold), 4),
            "passed_threshold": _b(self.passed_threshold),
            "symbol_fitness": round(_f(self.symbol_fitness), 4),
            "fitness_gate": round(_f(self.fitness_gate), 4),
            "passed_fitness": _b(self.passed_fitness),
        }


@dataclass
class SymbolBreakoutDetail:
    """Per-symbol 6-pattern breakout breakdown."""
    symbol: str
    composite_score: float = 0.0
    squeeze_score: float = 0.0
    volume_score: float = 0.0
    contraction_score: float = 0.0
    rs_score: float = 0.0
    pivot_score: float = 0.0
    flow_score: float = 0.0
    direction: float = 0.0
    squeeze_fired: bool = False
    volume_ratio: float = 0.0
    # Weights used
    weights: dict[str, float] = field(default_factory=dict)
    # Threshold proximity
    min_breakout_threshold: float = 0.20
    distance_to_threshold: float = 0.0
    passed_threshold: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "composite_score": round(_f(self.composite_score), 4),
            "factors": {
                "squeeze": round(_f(self.squeeze_score), 4),
                "volume": round(_f(self.volume_score), 4),
                "contraction": round(_f(self.contraction_score), 4),
                "rs": round(_f(self.rs_score), 4),
                "pivot": round(_f(self.pivot_score), 4),
                "flow": round(_f(self.flow_score), 4),
            },
            "weights": {k: round(_f(v), 4) for k, v in self.weights.items()},
            "direction": _f(self.direction),
            "squeeze_fired": _b(self.squeeze_fired),
            "volume_ratio": round(_f(self.volume_ratio), 2),
            "threshold": round(_f(self.min_breakout_threshold), 4),
            "distance_to_threshold": round(_f(self.distance_to_threshold), 4),
            "passed_threshold": _b(self.passed_threshold),
        }


@dataclass
class PositionExitDetail:
    """Per-position exit proximity breakdown."""
    symbol: str
    current_price: float = 0.0
    entry_price: float = 0.0
    direction: float = 1.0
    pnl_pct: float = 0.0
    # Exit levels
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: float = 0.0
    partial_tp_price: float = 0.0
    # Distances as percentage of current price
    stop_loss_distance_pct: float = 0.0
    take_profit_distance_pct: float = 0.0
    trailing_stop_distance_pct: float = 0.0
    partial_tp_distance_pct: float = 0.0
    # State
    trailing_active: bool = False
    partial_tp_taken: bool = False
    bars_held: int = 0
    max_bars: int = 0
    time_exit_distance_pct: float = 0.0
    # ATR info
    atr_at_entry: float = 0.0
    regime_at_entry: str = "unknown"
    highest_favorable: float = 0.0
    # Nearest exit condition
    nearest_exit: str = ""
    nearest_exit_distance_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_price": round(_f(self.current_price), 4),
            "entry_price": round(_f(self.entry_price), 4),
            "direction": _f(self.direction),
            "pnl_pct": round(_f(self.pnl_pct), 4),
            "exits": {
                "stop_loss": {
                    "level": round(_f(self.stop_loss), 4),
                    "distance_pct": round(_f(self.stop_loss_distance_pct), 2),
                },
                "take_profit": {
                    "level": round(_f(self.take_profit), 4),
                    "distance_pct": round(_f(self.take_profit_distance_pct), 2),
                },
                "trailing_stop": {
                    "level": round(_f(self.trailing_stop), 4),
                    "distance_pct": round(_f(self.trailing_stop_distance_pct), 2),
                    "active": _b(self.trailing_active),
                },
                "partial_tp": {
                    "level": round(_f(self.partial_tp_price), 4),
                    "distance_pct": round(_f(self.partial_tp_distance_pct), 2),
                    "taken": _b(self.partial_tp_taken),
                },
                "time": {
                    "bars_held": int(self.bars_held),
                    "max_bars": int(self.max_bars),
                    "distance_pct": round(_f(self.time_exit_distance_pct), 2),
                },
            },
            "atr_at_entry": round(_f(self.atr_at_entry), 4),
            "regime_at_entry": str(self.regime_at_entry),
            "highest_favorable": round(_f(self.highest_favorable), 4),
            "nearest_exit": str(self.nearest_exit),
            "nearest_exit_distance_pct": round(_f(self.nearest_exit_distance_pct), 2),
        }


@dataclass
class KellySizingDetail:
    """Per-candidate 8-stage Kelly pipeline."""
    symbol: str
    kelly_raw: float = 0.0
    kelly_half: float = 0.0
    drawdown_scale: float = 0.0
    vol_scale: float = 0.0
    regime_scale: float = 0.0
    confidence_scale: float = 0.0
    breakout_bonus: float = 0.0
    final_weight: float = 0.0
    position_cap: float = 0.12
    shares: int = 0
    notional: float = 0.0
    direction: float = 1.0
    ml_floor_applied: bool = False
    # improve8 additions
    regime_scale_source: str = "static_frozen"
    expected_return_source: str = "heuristic"
    dollar_risk_cap_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "pipeline": {
                "kelly_raw": round(_f(self.kelly_raw), 6),
                "kelly_half": round(_f(self.kelly_half), 6),
                "drawdown_scale": round(_f(self.drawdown_scale), 4),
                "vol_scale": round(_f(self.vol_scale), 4),
                "regime_scale": round(_f(self.regime_scale), 4),
                "confidence_scale": round(_f(self.confidence_scale), 4),
                "breakout_bonus": round(_f(self.breakout_bonus), 4),
                "final_weight": round(_f(self.final_weight), 6),
                "ml_floor_applied": _b(self.ml_floor_applied),
                "regime_scale_source": str(self.regime_scale_source),
                "expected_return_source": str(self.expected_return_source),
                "dollar_risk_cap_applied": _b(self.dollar_risk_cap_applied),
            },
            "position_cap": round(_f(self.position_cap), 4),
            "shares": int(self.shares),
            "notional": round(_f(self.notional), 2),
            "direction": _f(self.direction),
        }


@dataclass
class FilteringSummary:
    """How many symbols passed each gate."""
    total_universe: int = 0
    had_features: int = 0
    alpha_scored: int = 0
    above_alpha_threshold: int = 0
    breakout_scored: int = 0
    above_breakout_threshold: int = 0
    passed_sector_gate: int = 0
    passed_fitness_gate: int = 0
    passed_cooldown: int = 0
    passed_position_limit: int = 0
    live_candidates_pre_sizing: int = 0
    kelly_sized: int = 0
    orders_submitted: int = 0
    # Gate-level rejection counters
    rejected_by_open_position: int = 0
    rejected_by_exit_cooldown: int = 0
    rejected_by_pending_entry: int = 0
    rejected_by_entry_metadata: int = 0
    rejected_by_long_only: int = 0
    rejected_by_sector_gate: int = 0
    rejected_by_fitness_gate: int = 0
    rejected_by_liquidity: int = 0
    rejected_by_missingness: int = 0
    rejected_by_cost_gate: int = 0
    rejected_by_min_notional: int = 0
    rejected_by_direction_zero: int = 0
    rejected_by_below_main_conf: int = 0
    rejected_by_below_expl_conf: int = 0
    rejected_by_defensive_filter: int = 0
    rejected_by_sizer_invalid: int = 0
    entries_blocked_reason: str = ""
    no_order_reason: str = ""
    # M3: Learning mode throttle telemetry
    learning_mode: bool = False
    trading_phase: str = ""
    guarded_mode: bool = False
    ml_isolation_mode: bool = False
    fixed_risk_sizing: bool = False
    promotion_blockers: list[str] = field(default_factory=list)
    effective_max_entries_per_hour: int = 3
    # improve8 additions
    regime_scale_source: str = ""
    effective_fitness_gate: float = 0.45
    effective_confidence_gate: float = 0.30
    burst_cap_remaining: int = 4
    data_source_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_universe": self.total_universe,
            "had_features": self.had_features,
            "alpha_scored": self.alpha_scored,
            "above_alpha_threshold": self.above_alpha_threshold,
            "breakout_scored": self.breakout_scored,
            "above_breakout_threshold": self.above_breakout_threshold,
            "passed_sector_gate": self.passed_sector_gate,
            "passed_fitness_gate": self.passed_fitness_gate,
            "passed_cooldown": self.passed_cooldown,
            "passed_position_limit": self.passed_position_limit,
            "live_candidates_pre_sizing": self.live_candidates_pre_sizing,
            "kelly_sized": self.kelly_sized,
            "orders_submitted": self.orders_submitted,
            "rejections": {
                "open_position": self.rejected_by_open_position,
                "exit_cooldown": self.rejected_by_exit_cooldown,
                "pending_entry": self.rejected_by_pending_entry,
                "entry_metadata": self.rejected_by_entry_metadata,
                "long_only": self.rejected_by_long_only,
                "sector_gate": self.rejected_by_sector_gate,
                "fitness_gate": self.rejected_by_fitness_gate,
                "liquidity": self.rejected_by_liquidity,
                "missingness": self.rejected_by_missingness,
                "cost_gate": self.rejected_by_cost_gate,
                "min_notional": self.rejected_by_min_notional,
                "direction_zero": self.rejected_by_direction_zero,
                "below_main_conf": self.rejected_by_below_main_conf,
                "below_expl_conf": self.rejected_by_below_expl_conf,
                "defensive_filter": self.rejected_by_defensive_filter,
                "sizer_invalid": self.rejected_by_sizer_invalid,
                "no_order_reason": str(self.no_order_reason),
            },
            "entries_blocked_reason": self.entries_blocked_reason,
            "no_order_reason": str(self.no_order_reason),
            "learning_mode": _b(self.learning_mode),
            "trading_phase": str(self.trading_phase),
            "guarded_mode": _b(self.guarded_mode),
            "ml_isolation_mode": _b(self.ml_isolation_mode),
            "fixed_risk_sizing": _b(self.fixed_risk_sizing),
            "promotion_blockers": [str(x) for x in self.promotion_blockers],
            "effective_max_entries_per_hour": int(self.effective_max_entries_per_hour),
            "regime_scale_source": str(self.regime_scale_source),
            "effective_fitness_gate": round(_f(self.effective_fitness_gate), 2),
            "effective_confidence_gate": round(_f(self.effective_confidence_gate), 2),
            "burst_cap_remaining": int(self.burst_cap_remaining),
            "data_source_summary": str(self.data_source_summary),
        }


@dataclass
class DecisionSnapshot:
    """Complete tick state — the full picture for one tick."""
    tick_number: int = 0
    timestamp: str = ""
    duration_s: float = 0.0
    # Regime
    regime: str = "unknown"
    regime_probabilities: dict[str, float] = field(default_factory=dict)
    regime_confidence: float = 0.0
    regime_features: dict[str, float] = field(default_factory=dict)
    # Governance
    equity: float = 0.0
    peak_equity: float = 0.0
    drawdown_pct: float = 0.0
    is_halted: bool = False
    is_frozen: bool = False
    # Evolved params snapshot
    evolution_generation: int = 0
    evolved_params_summary: dict[str, Any] = field(default_factory=dict)
    # All scored symbols
    alpha_details: list[SymbolAlphaDetail] = field(default_factory=list)
    breakout_details: list[SymbolBreakoutDetail] = field(default_factory=list)
    # All position exits
    exit_details: list[PositionExitDetail] = field(default_factory=list)
    # Kelly sizing for candidates
    kelly_details: list[KellySizingDetail] = field(default_factory=list)
    # Filtering funnel
    filtering: FilteringSummary = field(default_factory=FilteringSummary)
    # Open positions count
    open_positions: int = 0
    max_positions: int = 15

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick_number": int(self.tick_number),
            "timestamp": str(self.timestamp),
            "duration_s": round(_f(self.duration_s), 3),
            "regime": {
                "primary": str(self.regime),
                "probabilities": {
                    str(k): round(_f(v), 4)
                    for k, v in self.regime_probabilities.items()
                },
                "confidence": round(_f(self.regime_confidence), 4),
                "features": {
                    str(k): round(_f(v), 6) if isinstance(v, (int, float)) else v
                    for k, v in self.regime_features.items()
                },
            },
            "governance": {
                "equity": round(_f(self.equity), 2),
                "peak_equity": round(_f(self.peak_equity), 2),
                "drawdown_pct": round(_f(self.drawdown_pct), 4),
                "is_halted": _b(self.is_halted),
                "is_frozen": _b(self.is_frozen),
            },
            "evolution": {
                "generation": int(self.evolution_generation),
                "params": self.evolved_params_summary,
            },
            "alpha_scores": [d.to_dict() for d in self.alpha_details],
            "breakout_scores": [d.to_dict() for d in self.breakout_details],
            "exit_proximity": [d.to_dict() for d in self.exit_details],
            "kelly_sizing": [d.to_dict() for d in self.kelly_details],
            "filtering": self.filtering.to_dict(),
            "open_positions": int(self.open_positions),
            "max_positions": int(self.max_positions),
        }


class DecisionTelemetryStore:
    """In-memory ring buffer for decision snapshots.

    Stores ~1 hour of snapshots at 10s ticks (360 entries).
    Thread-safe via deque's atomic append/popleft.
    """

    def __init__(self, maxlen: int = 360):
        self._buffer: collections.deque[DecisionSnapshot] = collections.deque(
            maxlen=maxlen
        )

    def append(self, snapshot: DecisionSnapshot) -> None:
        """Add a snapshot to the ring buffer."""
        self._buffer.append(snapshot)

    @property
    def latest(self) -> DecisionSnapshot | None:
        """Get the most recent snapshot."""
        if not self._buffer:
            return None
        return self._buffer[-1]

    def history(self, limit: int = 50) -> list[DecisionSnapshot]:
        """Get recent snapshots, newest first."""
        items = list(self._buffer)
        items.reverse()
        return items[:limit]

    def symbol_history(
        self, symbol: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get per-symbol alpha/breakout/exit data across recent ticks."""
        results: list[dict[str, Any]] = []
        for snap in reversed(self._buffer):
            entry: dict[str, Any] = {
                "tick_number": snap.tick_number,
                "timestamp": snap.timestamp,
                "regime": snap.regime,
            }
            # Find alpha detail for symbol
            for ad in snap.alpha_details:
                if ad.symbol == symbol:
                    entry["alpha"] = ad.to_dict()
                    break
            # Find breakout detail
            for bd in snap.breakout_details:
                if bd.symbol == symbol:
                    entry["breakout"] = bd.to_dict()
                    break
            # Find exit detail
            for ed in snap.exit_details:
                if ed.symbol == symbol:
                    entry["exit"] = ed.to_dict()
                    break
            # Find kelly detail
            for kd in snap.kelly_details:
                if kd.symbol == symbol:
                    entry["kelly"] = kd.to_dict()
                    break
            if any(k in entry for k in ("alpha", "breakout", "exit", "kelly")):
                results.append(entry)
            if len(results) >= limit:
                break
        return results

    def exits_snapshot(self) -> list[dict[str, Any]]:
        """Get current exit proximity for all positions from latest tick."""
        snap = self.latest
        if snap is None:
            return []
        return [ed.to_dict() for ed in snap.exit_details]

    def __len__(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()
