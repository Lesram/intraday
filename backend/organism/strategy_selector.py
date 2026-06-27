"""Regime-adaptive strategy selector (Phase 1 Section 6).

The single layer the engine talks to: it reads the current regime, aggregates
candidates from the ELIGIBLE strategies, and hands back one ranked list (or
none). It does NOT pick a single "best" strategy per tick — that arbiter is a
Phase-2 empirical question; Phase 1 needs correct plumbing + gating.

Routing policy (Rule A lives here):
- live mode: a strategy influences capital in regime R only if
  R in eligible_regimes AND live_routing is True. Today that set is effectively
  {momentum} (still unproven).
- backtest/shadow mode: run ALL registered strategies regardless of live_routing
  — the whole point there is MEASUREMENT. live_routing gates capital, not data.
- no eligible strategy for the regime -> emit nothing -> STAND DOWN (the correct,
  tested default).
"""
from __future__ import annotations

from typing import Iterable

from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy

LIVE = "live"
BACKTEST = "backtest"


class StrategySelector:
    def __init__(self, strategies: Iterable[Strategy], mode: str = LIVE):
        if mode not in (LIVE, BACKTEST):
            raise ValueError(f"mode must be {LIVE!r} or {BACKTEST!r}, got {mode!r}")
        self.strategies: list[Strategy] = list(strategies)
        self.mode = mode

    def _eligible(self, s: Strategy, regime: str) -> bool:
        if regime not in s.eligible_regimes():
            return False
        if self.mode == LIVE:
            return s.live_routing  # capital gated (Rule A)
        return True  # backtest/shadow: measure every registered strategy

    def eligible_strategies(self, regime: str) -> list[Strategy]:
        return [s for s in self.strategies if self._eligible(s, regime)]

    def select(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        """Aggregate candidates from eligible strategies, ranked by the single
        comparable axis (confidence desc). Empty list == stand down."""
        cands: list[Candidate] = []
        for s in self.eligible_strategies(regime):
            cands.extend(s.scan(features, regime))
        cands.sort(key=lambda c: c.confidence, reverse=True)
        return cands

    @classmethod
    def from_config(cls, mode: str = LIVE, only: Iterable[str] | None = None) -> "StrategySelector":
        """Build the selector from the registry + strategy_config.

        Imports the strategy modules so they self-register, then instantiates
        each configured (non-parked) strategy with its config block. `only`
        restricts to a subset (e.g. {"momentum"} for the parity path)."""
        # Import for registration side effects (parked EOD is intentionally absent).
        import backend.organism.strategies.breakout  # noqa: F401
        import backend.organism.strategies.mean_reversion  # noqa: F401
        import backend.organism.strategies.momentum  # noqa: F401
        import backend.organism.strategies.orb  # noqa: F401
        from backend.organism.strategies.registry import build_strategy
        from backend.organism.strategies.strategy_config import all_configs

        names = list(all_configs())
        if only is not None:
            only = set(only)
            names = [n for n in names if n in only]
        strategies = []
        for name in names:
            try:
                strategies.append(build_strategy(name, all_configs()[name]))
            except KeyError:
                # configured but not yet registered (e.g. mean_reversion/orb
                # before steps 7/9) — skip cleanly; they join as they're built.
                continue
        return cls(strategies, mode=mode)
