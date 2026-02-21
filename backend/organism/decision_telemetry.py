"""
Decision Telemetry — Full transparency into the organism's decision pipeline.

Captures per-tick snapshots of every indicator, threshold, and decision gate
so the frontend can render the full "why" behind every trade action.

In-memory ring buffer only — no DB storage. Ephemeral diagnostic data.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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
    fitness_gate: float = 0.35
    passed_fitness: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "composite_score": round(self.composite_score, 4),
            "factors": {
                "ml": round(self.ml_score, 4),
                "breakout": round(self.breakout_score, 4),
                "institutional": round(self.institutional_score, 4),
                "momentum": round(self.momentum_score, 4),
                "momentum_quality": round(self.momentum_quality_score, 4),
                "vol_price_div": round(self.vol_price_div_score, 4),
                "regime": round(self.regime_score, 4),
            },
            "weights": self.weights,
            "direction": self.direction,
            "threshold": round(self.min_composite_threshold, 4),
            "distance_to_threshold": round(self.distance_to_threshold, 4),
            "passed_threshold": self.passed_threshold,
            "symbol_fitness": round(self.symbol_fitness, 4),
            "fitness_gate": round(self.fitness_gate, 4),
            "passed_fitness": self.passed_fitness,
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
            "composite_score": round(self.composite_score, 4),
            "factors": {
                "squeeze": round(self.squeeze_score, 4),
                "volume": round(self.volume_score, 4),
                "contraction": round(self.contraction_score, 4),
                "rs": round(self.rs_score, 4),
                "pivot": round(self.pivot_score, 4),
                "flow": round(self.flow_score, 4),
            },
            "weights": self.weights,
            "direction": self.direction,
            "squeeze_fired": self.squeeze_fired,
            "volume_ratio": round(self.volume_ratio, 2),
            "threshold": round(self.min_breakout_threshold, 4),
            "distance_to_threshold": round(self.distance_to_threshold, 4),
            "passed_threshold": self.passed_threshold,
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
    regime_at_entry: str = "normal"
    highest_favorable: float = 0.0
    # Nearest exit condition
    nearest_exit: str = ""
    nearest_exit_distance_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_price": round(self.current_price, 4),
            "entry_price": round(self.entry_price, 4),
            "direction": self.direction,
            "pnl_pct": round(self.pnl_pct, 4),
            "exits": {
                "stop_loss": {
                    "level": round(self.stop_loss, 4),
                    "distance_pct": round(self.stop_loss_distance_pct, 2),
                },
                "take_profit": {
                    "level": round(self.take_profit, 4),
                    "distance_pct": round(self.take_profit_distance_pct, 2),
                },
                "trailing_stop": {
                    "level": round(self.trailing_stop, 4),
                    "distance_pct": round(self.trailing_stop_distance_pct, 2),
                    "active": self.trailing_active,
                },
                "partial_tp": {
                    "level": round(self.partial_tp_price, 4),
                    "distance_pct": round(self.partial_tp_distance_pct, 2),
                    "taken": self.partial_tp_taken,
                },
                "time": {
                    "bars_held": self.bars_held,
                    "max_bars": self.max_bars,
                    "distance_pct": round(self.time_exit_distance_pct, 2),
                },
            },
            "atr_at_entry": round(self.atr_at_entry, 4),
            "regime_at_entry": self.regime_at_entry,
            "highest_favorable": round(self.highest_favorable, 4),
            "nearest_exit": self.nearest_exit,
            "nearest_exit_distance_pct": round(self.nearest_exit_distance_pct, 2),
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "pipeline": {
                "kelly_raw": round(self.kelly_raw, 6),
                "kelly_half": round(self.kelly_half, 6),
                "drawdown_scale": round(self.drawdown_scale, 4),
                "vol_scale": round(self.vol_scale, 4),
                "regime_scale": round(self.regime_scale, 4),
                "confidence_scale": round(self.confidence_scale, 4),
                "breakout_bonus": round(self.breakout_bonus, 4),
                "final_weight": round(self.final_weight, 6),
            },
            "position_cap": round(self.position_cap, 4),
            "shares": self.shares,
            "notional": round(self.notional, 2),
            "direction": self.direction,
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
    kelly_sized: int = 0
    orders_submitted: int = 0

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
            "kelly_sized": self.kelly_sized,
            "orders_submitted": self.orders_submitted,
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
            "tick_number": self.tick_number,
            "timestamp": self.timestamp,
            "duration_s": round(self.duration_s, 3),
            "regime": {
                "primary": self.regime,
                "probabilities": {
                    k: round(v, 4)
                    for k, v in self.regime_probabilities.items()
                },
                "confidence": round(self.regime_confidence, 4),
                "features": {
                    k: round(v, 6)
                    for k, v in self.regime_features.items()
                },
            },
            "governance": {
                "equity": round(self.equity, 2),
                "peak_equity": round(self.peak_equity, 2),
                "drawdown_pct": round(self.drawdown_pct, 4),
                "is_halted": self.is_halted,
                "is_frozen": self.is_frozen,
            },
            "evolution": {
                "generation": self.evolution_generation,
                "params": self.evolved_params_summary,
            },
            "alpha_scores": [d.to_dict() for d in self.alpha_details],
            "breakout_scores": [d.to_dict() for d in self.breakout_details],
            "exit_proximity": [d.to_dict() for d in self.exit_details],
            "kelly_sizing": [d.to_dict() for d in self.kelly_details],
            "filtering": self.filtering.to_dict(),
            "open_positions": self.open_positions,
            "max_positions": self.max_positions,
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
