"""
Module B — Momentum Pyramider.

Adds to winning positions at continuation breakout levels.
The key insight: winners tend to keep winning. Adding on strength
with strict risk rules turns $250 average wins into $1,000+.

Rules:
    1. Initial entry = 60% of target size
    2. At +1.5R: add 30% more, move all stops to breakeven
    3. At +3.0R: add final 10%, trail tightly
    4. NEVER average down — only add to winners
    5. Each add reduces total risk as stops tighten

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §3 Module B
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class PyramidLevel:
    """One layer of a pyramided position."""
    shares: int
    entry_price: float
    bar_added: int
    level: int  # 0=initial, 1=first add, 2=second add

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price


@dataclass
class PyramidPosition:
    """A position with multiple pyramid layers."""
    symbol: str
    direction: float           # +1 long, -1 short
    layers: list[PyramidLevel] = field(default_factory=list)
    target_total_shares: int = 0  # Full target position size
    atr_at_entry: float = 0.0
    initial_stop: float = 0.0
    current_stop: float = 0.0
    highest_price: float = 0.0   # Highest favorable price
    lowest_price: float = float('inf')  # Lowest favorable price (inf = uninitialized)
    breakout_score: float = 0.0  # Original breakout score

    @property
    def total_shares(self) -> int:
        return sum(lay.shares for lay in self.layers)

    @property
    def avg_entry(self) -> float:
        total_cost = sum(lay.cost_basis for lay in self.layers)
        total_shares = self.total_shares
        return total_cost / total_shares if total_shares > 0 else 0

    @property
    def layer_count(self) -> int:
        return len(self.layers)

    @property
    def r_multiple(self) -> float:
        """Current R-multiple from initial entry."""
        if not self.layers or self.atr_at_entry < 1e-6:
            return 0.0
        entry = self.layers[0].entry_price
        if self.direction > 0:
            return (self.highest_price - entry) / self.atr_at_entry
        else:
            if self.lowest_price == float('inf'):
                return 0.0  # not yet initialized
            return (entry - self.lowest_price) / self.atr_at_entry

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L at current price."""
        pnl = 0.0
        for lay in self.layers:
            if self.direction > 0:
                pnl += (current_price - lay.entry_price) * lay.shares
            else:
                pnl += (lay.entry_price - current_price) * lay.shares
        return pnl

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "layers": self.layer_count,
            "total_shares": self.total_shares,
            "avg_entry": round(self.avg_entry, 2),
            "current_stop": round(self.current_stop, 2),
            "r_multiple": round(self.r_multiple, 2),
        }


@dataclass
class PyramidAction:
    """Action recommended by the pyramider."""
    action: str             # "add", "tighten_stop", "close_partial", "none"
    shares_to_add: int = 0
    new_stop: float = 0.0
    reason: str = ""


class MomentumPyramider:
    """Add to winning positions at breakout continuation levels.

    The pyramid structure:
        Layer 0: 60% of target size at initial breakout
        Layer 1: 30% at +1.5R (confirmation)
        Layer 2: 10% at +3.0R (parabolic move)

    Risk management:
        - After Layer 1: move ALL stops to breakeven
        - After Layer 2: trail at 2× ATR from highest
        - Max 3 layers per position
        - Anti-pyramid: -0.7R → cut 50%, -1R → cut 100%
    """

    LAYER_0_PCT = 0.60   # Initial entry: 60% of target
    LAYER_1_PCT = 0.30   # First add: 30%
    LAYER_2_PCT = 0.10   # Second add: 10%

    ADD_1_THRESHOLD = 1.5  # Add at +1.5R
    ADD_2_THRESHOLD = 3.0  # Add at +3.0R

    CUT_PARTIAL = -0.7    # Cut 50% at -0.7R
    CUT_FULL = -1.0       # Cut 100% at -1.0R

    MAX_LAYERS = 3

    def __init__(self):
        self._pyramid_count = 0
        self._max_layers_reached = 0

    def initial_shares(self, target_shares: int) -> int:
        """Calculate initial entry size (Layer 0)."""
        return max(1, int(target_shares * self.LAYER_0_PCT))

    def check_pyramid(
        self,
        position: PyramidPosition,
        current_price: float,
    ) -> PyramidAction:
        """Check if we should add, tighten stop, or cut.

        Parameters
        ----------
        position : current PyramidPosition
        current_price : latest price

        Returns
        -------
        PyramidAction with recommended action.
        """
        if not position.layers:
            return PyramidAction(action="none")

        # G3: guard against NaN/Inf current_price. If streaming data
        # is stale or corrupt, current_price can be NaN, which would
        # silently disable all pyramid actions (NaN comparisons are
        # always False). Catch early and return safely.
        import math
        if not math.isfinite(current_price) or current_price <= 0:
            return PyramidAction(action="none")

        entry = position.layers[0].entry_price
        atr = position.atr_at_entry
        if atr < 1e-6:
            return PyramidAction(action="none")

        # Update highest/lowest favorable price
        if position.direction > 0:
            position.highest_price = max(position.highest_price, current_price)
            r_current = (current_price - entry) / atr
        else:
            if position.lowest_price == float('inf'):
                position.lowest_price = current_price
            position.lowest_price = min(position.lowest_price, current_price)
            r_current = (entry - current_price) / atr

        # ── Anti-pyramid: cut losers ─────────────────────
        if r_current <= self.CUT_FULL:
            return PyramidAction(
                action="close_partial",
                shares_to_add=-position.total_shares,  # Close all
                reason=f"cut_full_at_{r_current:.1f}R",
            )

        if r_current <= self.CUT_PARTIAL and position.layer_count == 1:
            cut_shares = max(1, position.total_shares // 2)
            return PyramidAction(
                action="close_partial",
                shares_to_add=-cut_shares,
                reason=f"cut_partial_at_{r_current:.1f}R",
            )

        # ── Pyramid: add to winners ──────────────────────
        if position.layer_count >= self.MAX_LAYERS:
            # Already at max layers — just tighten stop
            if r_current > self.ADD_2_THRESHOLD:
                # Trail at 2× ATR from high
                if position.direction > 0:
                    new_stop = position.highest_price - 2 * atr
                else:
                    new_stop = position.lowest_price + 2 * atr
                if self._is_tighter_stop(position, new_stop):
                    return PyramidAction(
                        action="tighten_stop",
                        new_stop=new_stop,
                        reason="trail_at_3R_plus",
                    )
            return PyramidAction(action="none")

        # Layer 1: add at +1.5R
        if position.layer_count == 1 and r_current >= self.ADD_1_THRESHOLD:
            add_shares = max(1, int(position.target_total_shares * self.LAYER_1_PCT))
            # Move stop to breakeven
            new_stop = entry  # Breakeven
            if position.direction < 0:
                new_stop = entry  # Same for shorts

            self._pyramid_count += 1
            return PyramidAction(
                action="add",
                shares_to_add=add_shares,
                new_stop=new_stop,
                reason=f"pyramid_L1_at_{r_current:.1f}R",
            )

        # Layer 2: add at +3.0R
        if position.layer_count == 2 and r_current >= self.ADD_2_THRESHOLD:
            add_shares = max(1, int(position.target_total_shares * self.LAYER_2_PCT))
            # Trail at 1.5× ATR from current
            if position.direction > 0:
                new_stop = current_price - 1.5 * atr
            else:
                new_stop = current_price + 1.5 * atr

            self._pyramid_count += 1
            self._max_layers_reached += 1
            return PyramidAction(
                action="add",
                shares_to_add=add_shares,
                new_stop=new_stop,
                reason=f"pyramid_L2_at_{r_current:.1f}R",
            )

        # ── Tighten stop on profit ───────────────────────
        if r_current > 2.0 and position.layer_count >= 2:
            if position.direction > 0:
                new_stop = position.highest_price - 2.5 * atr
            else:
                new_stop = position.lowest_price + 2.5 * atr
            if self._is_tighter_stop(position, new_stop):
                return PyramidAction(
                    action="tighten_stop",
                    new_stop=new_stop,
                    reason=f"trail_at_{r_current:.1f}R",
                )

        return PyramidAction(action="none")

    def _is_tighter_stop(self, pos: PyramidPosition, new_stop: float) -> bool:
        """Check if new stop is tighter (more protective) than current."""
        if pos.direction > 0:
            return new_stop > pos.current_stop
        else:
            return new_stop < pos.current_stop
