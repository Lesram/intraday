"""The shared Strategy contract — the heart of Intra 2.0 Phase 1.

Every strategy implements this one ABC and emits the strategy-agnostic
``Candidate``, so the engine ranks heterogeneous candidates on a single axis and
the backtester runs any strategy through the identical candidate -> gate -> size
-> exit -> record path. Extracting a strategy onto this contract must PRESERVE
its output (parity, Section 9): the contract is behavior-defining, not
behavior-changing.

``scan()`` must be a deterministic, side-effect-free function of (features,
regime) — no order placement, no I/O — which is what makes backtests reproducible
and live/replay parity checkable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# symbol -> features DataFrame (newest row last). The one input shape every
# strategy scans over.
FeatureFrame = dict[str, pd.DataFrame]


@dataclass
class Candidate:
    """A strategy-agnostic trade candidate.

    ``confidence`` is the ONE comparable ranking axis across all strategies:
    a [0.0, 1.0] conviction score (higher = stronger). Every strategy MUST map
    its internal scoring onto this scale so heterogeneous candidates from
    different strategies are rankable on a single axis. Anything strategy-
    specific (sub-scores, thresholds hit) goes in ``extra``; fields the live
    engine already consumes (ml_signal, expected_return_source) are carried
    explicitly so a module can round-trip to the engine's native type with
    bit-for-bit parity.
    """

    symbol: str
    direction: float          # +1 long, -1 short, 0 = no directional view
    confidence: float         # [0.0, 1.0] comparable conviction across strategies
    strategy_name: str
    features_snapshot: Any = None        # ref to the feature row/frame for the trade record
    expected_return_source: str = "heuristic"  # "ml" | "calibrated_breakout" | "heuristic"
    ml_signal: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize direction to a clean sign; keep 0 as "no view".
        d = float(self.direction)
        self.direction = 1.0 if d > 0 else (-1.0 if d < 0 else 0.0)
        self.confidence = float(self.confidence)


class Strategy(ABC):
    """One contract for every strategy.

    Subclasses set ``name`` (via @register) and implement the abstract methods.
    ``__init__`` stores the strategy's own config block and validates it
    fail-closed, so a misconfigured strategy refuses to load rather than trade
    blindly.
    """

    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None):
        # Receives its OWN section of strategy_config.py and stores it. A
        # strategy MUST read every tunable from here — never from a hardcoded
        # constant elsewhere (Section 4 / Rule: externalized config).
        self.config: dict[str, Any] = dict(config or {})
        self.validate_config()

    # ── advisory routing metadata ────────────────────────────────────────
    @property
    def live_routing(self) -> bool:
        """Whether config authorizes this strategy to influence LIVE capital.

        Rule A: this gates CAPITAL, not measurement. Default False — a strategy
        is a backtest/shadow benchmark until it has passed the Section-8 bar and
        config is deliberately flipped to true.
        """
        return bool(self.config.get("live_routing", False))

    # ── the contract ─────────────────────────────────────────────────────
    @abstractmethod
    def required_features(self) -> set[str]:
        """Feature columns this strategy needs (e.g. {"ret_5d", "ret_20d"}).
        Lets the engine/backtester guarantee inputs exist before scanning."""

    @abstractmethod
    def scan(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        """Pure, side-effect-free (features, regime) -> 0..n Candidates."""

    @abstractmethod
    def eligible_regimes(self) -> set[str]:
        """Regimes this strategy is DESIGNED for (advisory to the selector).
        Declaring a regime does NOT authorize live routing (Rule A)."""

    @abstractmethod
    def validate_config(self) -> None:
        """Raise on insane params (e.g. negative thresholds). Fail-closed."""
