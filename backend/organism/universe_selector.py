"""
Phase 4.1 — Dynamic Universe Selection.

The organism adds / removes symbols from its active trading universe
based on learned fitness scores, fresh liquidity data, and sector
momentum.  The fixed env-var list becomes a *seed* universe that is
periodically refreshed by this module.

Core rules:
    1. Never drop below ``MIN_UNIVERSE`` symbols (stability floor).
    2. Symbols with open positions are NEVER removed mid-trade.
    3. New symbols come from a *candidate pool* that is broader than the
       seed (e.g. top-100 liquid US equities).
    4. Fitness = blend of PnL, win-rate, and volume quality.
    5. Universe rotates on a configurable cadence (daily by default).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Configuration constants (env-overridable) ────────────────────
MIN_UNIVERSE = int(os.getenv("UNIVERSE_MIN_SIZE", "15"))
MAX_UNIVERSE = int(os.getenv("UNIVERSE_MAX_SIZE", "80"))
TOP_ADD = int(os.getenv("UNIVERSE_TOP_ADD", "10"))
TOP_DROP = int(os.getenv("UNIVERSE_TOP_DROP", "5"))
MIN_OBSERVATIONS = int(os.getenv("UNIVERSE_MIN_OBSERVATIONS", "3"))
FITNESS_DECAY = float(os.getenv("UNIVERSE_FITNESS_DECAY", "0.95"))
DEFAULT_FITNESS = 0.50     # Starting fitness for brand-new symbols


@dataclass
class SymbolFitness:
    """Aggregated fitness metrics for one symbol."""

    symbol: str
    fitness: float = DEFAULT_FITNESS
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_volume_quality: float = 0.5
    last_rotated_gen: int = 0
    rotations_observed: int = 0

    def to_dict(self) -> dict[str, Any]:
        # Audit-I finding I-4 (2026-05-02): native-type casts for JSON safety.
        return {
            "symbol": str(self.symbol),
            "fitness": round(float(self.fitness), 4),
            "total_trades": int(self.total_trades),
            "win_rate": round(float(self.win_rate), 4),
            "avg_pnl": round(float(self.avg_pnl), 2),
            "avg_volume_quality": round(float(self.avg_volume_quality), 4),
            "last_rotated_gen": int(self.last_rotated_gen),
            "rotations_observed": int(self.rotations_observed),
        }


class DynamicUniverseSelector:
    """Selects and rotates the active trading universe.

    Called once per rotation cadence (typically daily or per-epoch).
    Maintains a fitness table keyed by symbol.

    Usage::

        selector = DynamicUniverseSelector(seed_symbols=["AAPL", "MSFT", ...])
        new_universe = selector.rotate(
            trades=recent_trades,
            candidate_pool=["AAPL", "MSFT", ...],
            open_positions={"AAPL", "MSFT"},
            generation=42,
        )
    """

    def __init__(
        self,
        seed_symbols: list[str],
        min_universe: int = MIN_UNIVERSE,
        max_universe: int = MAX_UNIVERSE,
        protected_symbols: set[str] | None = None,
    ) -> None:
        self._min = min_universe
        self._max = max_universe
        self._protected: set[str] = set(protected_symbols) if protected_symbols else set()

        # Initialise fitness table from seed
        self._fitness: dict[str, SymbolFitness] = {}
        for sym in seed_symbols:
            self._fitness[sym] = SymbolFitness(symbol=sym)

        self._active: list[str] = list(seed_symbols)
        self._rotation_count = 0

    # ── Properties ───────────────────────────────────────────────

    @property
    def active_universe(self) -> list[str]:
        return list(self._active)

    @property
    def fitness_table(self) -> dict[str, SymbolFitness]:
        return dict(self._fitness)

    # ── Core rotation ────────────────────────────────────────────

    def rotate(
        self,
        trades: list[Any],
        candidate_pool: list[str] | None = None,
        open_positions: set[str] | None = None,
        generation: int = 0,
    ) -> list[str]:
        """Perform one universe rotation.

        Parameters
        ----------
        trades : Recent TradeRecords (must have .symbol, .pnl, .confidence)
        candidate_pool : Broader set of eligible symbols (superset of active).
                         If ``None``, only existing fitness table is used.
        open_positions : Symbols with open positions (protected from removal).
        generation : Current organism generation (for logging).

        Returns
        -------
        Updated active universe list.
        """
        self._rotation_count += 1
        open_positions = open_positions or set()

        # 0. Increment observation counter for ALL tracked symbols
        for sf in self._fitness.values():
            sf.rotations_observed += 1

        # 1. Update fitness from trade evidence
        self._update_fitness_from_trades(trades)

        # 2. Decay unseen symbols toward default
        self._decay_fitness()

        # 3. Ensure candidate pool symbols have entries
        if candidate_pool:
            for sym in candidate_pool:
                if sym not in self._fitness:
                    self._fitness[sym] = SymbolFitness(
                        symbol=sym, last_rotated_gen=generation,
                    )

        # 4. Rank all known symbols by fitness
        ranked = sorted(
            self._fitness.values(),
            key=lambda sf: sf.fitness,
            reverse=True,
        )

        # 5. Determine drops — lowest-fitness active symbols
        drops: list[str] = []
        active_set = set(self._active)
        for sf in reversed(ranked):
            if len(drops) >= TOP_DROP:
                break
            if sf.symbol not in active_set:
                continue
            if sf.symbol in open_positions:
                continue  # never drop a symbol with open position
            if sf.symbol in self._protected:
                continue  # never drop a protected symbol (e.g. inverse ETFs)
            if sf.total_trades < MIN_OBSERVATIONS:
                continue  # not enough data to judge
            if sf.fitness < DEFAULT_FITNESS - 0.1:
                drops.append(sf.symbol)

        # 6. Determine adds — highest-fitness inactive symbols
        #    Threshold is DEFAULT_FITNESS (not higher) so new candidates
        #    that haven't been traded yet can enter and accumulate evidence.
        #    Observation gate: new symbols must be observed for MIN_OBSERVATIONS
        #    rotations before they can be added (prevents untested symbols
        #    from immediately trading).
        adds: list[str] = []
        for sf in ranked:
            if len(adds) >= TOP_ADD:
                break
            if sf.symbol in active_set:
                continue
            if sf.fitness >= DEFAULT_FITNESS:
                # Observation gate: require enough rotations unless it's a
                # seed symbol (total_trades == 0 and was in initial list —
                # these already have rotations_observed from being tracked).
                if sf.rotations_observed < MIN_OBSERVATIONS and sf.total_trades == 0:
                    continue
                adds.append(sf.symbol)
                sf.last_rotated_gen = generation

        # 7. Apply changes
        new_active = [s for s in self._active if s not in drops]
        new_active.extend(adds)

        # 8. Enforce bounds
        if len(new_active) < self._min:
            # Pad with top candidates not yet active
            for sf in ranked:
                if len(new_active) >= self._min:
                    break
                if sf.symbol not in new_active:
                    new_active.append(sf.symbol)

        if len(new_active) > self._max:
            # Trim lowest-fitness
            scored = [
                (s, self._fitness.get(s, SymbolFitness(symbol=s)).fitness)
                for s in new_active
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            # Keep top _max but protect open positions
            kept: list[str] = []
            for s, _f in scored:
                if s in open_positions or len(kept) < self._max:
                    kept.append(s)
            # Ensure open-position symbols are never dropped, even if
            # they pushed us above _max — but cap remaining at _max.
            new_active = kept

        self._active = new_active

        if drops or adds:
            logger.info(
                "Universe rotation #%d: added %s, dropped %s → %d symbols",
                self._rotation_count,
                adds or "[]",
                drops or "[]",
                len(self._active),
            )

        return list(self._active)

    # ── Fitness updates ──────────────────────────────────────────

    def _update_fitness_from_trades(self, trades: list[Any]) -> None:
        """Update per-symbol fitness from recent trade outcomes."""
        by_symbol: dict[str, list[Any]] = {}
        for t in trades:
            sym = getattr(t, "symbol", None)
            if sym:
                by_symbol.setdefault(sym, []).append(t)

        for sym, sym_trades in by_symbol.items():
            if sym not in self._fitness:
                self._fitness[sym] = SymbolFitness(symbol=sym)

            sf = self._fitness[sym]
            pnl_list = [t.pnl for t in sym_trades]
            wins = sum(1 for p in pnl_list if p > 0)

            # EMA-blend new evidence into existing fitness
            new_wr = wins / max(len(pnl_list), 1)
            new_avg_pnl = float(np.mean(pnl_list)) if pnl_list else 0.0

            alpha = 0.3  # blend factor for new evidence
            sf.win_rate = (1 - alpha) * sf.win_rate + alpha * new_wr
            sf.avg_pnl = (1 - alpha) * sf.avg_pnl + alpha * new_avg_pnl
            sf.total_trades += len(sym_trades)

            # Composite fitness: 60% win-rate, 40% normalised PnL
            pnl_norm = min(max(new_avg_pnl / 100.0, -1.0), 1.0)  # normalise
            raw_fitness = 0.6 * sf.win_rate + 0.4 * (0.5 + pnl_norm / 2)
            sf.fitness = (1 - alpha) * sf.fitness + alpha * raw_fitness

    def _decay_fitness(self) -> None:
        """Pull all fitness scores toward DEFAULT_FITNESS over time."""
        for sf in self._fitness.values():
            sf.fitness = FITNESS_DECAY * sf.fitness + (1 - FITNESS_DECAY) * DEFAULT_FITNESS

    # ── Persistence ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "rotation_count": self._rotation_count,
            "protected_symbols": sorted(self._protected),
            "fitness": {
                sym: sf.to_dict() for sym, sf in self._fitness.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        seed_symbols: list[str] | None = None,
        protected_symbols: set[str] | None = None,
    ) -> "DynamicUniverseSelector":
        """Restore from brain persistence."""
        active = d.get("active", seed_symbols or [])
        # Restore protected symbols: prefer caller arg, fall back to persisted
        if protected_symbols is None:
            persisted = d.get("protected_symbols")
            if persisted:
                protected_symbols = set(persisted)
        selector = cls(seed_symbols=active, protected_symbols=protected_symbols)
        selector._rotation_count = d.get("rotation_count", 0)

        for sym, sf_dict in d.get("fitness", {}).items():
            sf = SymbolFitness(symbol=sym)
            for k in ("fitness", "total_trades", "win_rate", "avg_pnl",
                       "avg_volume_quality", "last_rotated_gen",
                       "rotations_observed"):
                if k in sf_dict:
                    setattr(sf, k, sf_dict[k])
            selector._fitness[sym] = sf

        # Ensure active list is populated
        if not selector._active and seed_symbols:
            selector._active = list(seed_symbols)

        # Merge missing protected symbols into active universe.
        # Protection prevents future removal, but if the brain was saved
        # before protection existed, the symbols may already be absent.
        if selector._protected:
            active_set = set(selector._active)
            merged = []
            for sym in sorted(selector._protected):
                if sym not in active_set:
                    selector._active.append(sym)
                    merged.append(sym)
                    # Ensure fitness entry exists so the symbol is tradeable
                    if sym not in selector._fitness:
                        selector._fitness[sym] = SymbolFitness(symbol=sym)
            if merged:
                logger.info(
                    "Protected symbols merged into active universe on restore: %s",
                    merged,
                )

        return selector
