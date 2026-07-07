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

    def scan_all(self, features: FeatureFrame, regime: str) -> dict[str, dict]:
        """Phase 3 Task 3 (5c): one scan pass over EVERY registered strategy,
        returning per-strategy results tagged with their Rule-A routing status:

            {name: {"candidates": [Candidate...], "routed": bool}}

        - ``routed`` is this selector's `_eligible` (mode + regime + live_routing):
          in live mode only routed strategies may convert to capital candidates;
          un-routed strategies are returned anyway as SHADOW/ATTRIBUTION data
          (Task 4: measured, never sized). live_routing gates capital, not data.
        - Strategies scan regardless of eligibility (backtest semantics for the
          measurement half) — a scan error in one strategy never poisons the
          others (fail-closed to an empty list, matching stand-down).
        """
        out: dict[str, dict] = {}
        for s in self.strategies:
            try:
                cands = s.scan(features, regime)
            except Exception:  # noqa: BLE001 — fail-closed BY DESIGN:
                # any strategy error becomes stand-down for that strategy
                # only; never poisons the others' scan.
                cands = []
            cands.sort(key=lambda c: c.confidence, reverse=True)
            out[s.name] = {"candidates": cands, "routed": self._eligible(s, regime)}
        return out

    def select_policy_ranked(self, features: FeatureFrame, regime: str,
                             policy: dict[str, list[str]] | None = None,
                             scan_res: dict | None = None) -> list[Candidate]:
        """Phase 3 Task 4: policy-ordered capital candidates for one regime.

        Under the 5b verdict (FLAT ships — no confidence model beat flat OOS),
        candidate ranking carries no information, so ORDER IS POLICY: the
        declarative REGIME_POLICY list is the ranking authority; within one
        strategy, native scan order is preserved. A strategy contributes only
        if it is BOTH routed (Rule A via scan_all) AND named in the policy for
        this regime — the policy can only narrow live routing, never widen it.

        Absent/empty policy entry ⇒ [] ⇒ EXPLICIT STAND-DOWN.
        ``scan_res`` lets the caller reuse an existing scan_all() pass (the
        engine's per-tick memoized result) instead of scanning again.
        """
        if policy is None:
            from backend.organism.strategies.strategy_config import regime_policy
            policy = regime_policy()
        order = policy.get(regime, [])
        if not order:
            return []                      # stand down
        res = scan_res if scan_res is not None else self.scan_all(features, regime)
        out: list[Candidate] = []
        for name in order:
            entry = res.get(name) or {}
            if entry.get("routed"):
                out.extend(entry.get("candidates", []))
        return out

    @classmethod
    def from_config(cls, mode: str = LIVE, only: Iterable[str] | None = None,
                    scanner_overrides: dict | None = None) -> "StrategySelector":
        """Build the selector from the registry + strategy_config.

        Imports the strategy modules so they self-register, then instantiates
        each configured (non-parked) strategy with its config block. `only`
        restricts to a subset (e.g. {"momentum"} for the parity path).
        `scanner_overrides` maps strategy name -> a live scanner INSTANCE to
        inject (5c: the engine passes its own stateful scanners so mark_fired/
        cooldown/cache state stays single-source)."""
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
        overrides = scanner_overrides or {}
        strategies = []
        for name in names:
            try:
                strategies.append(
                    build_strategy(name, all_configs()[name],
                                   scanner=overrides.get(name)))
            except KeyError:
                # configured but not yet registered (e.g. mean_reversion/orb
                # before steps 7/9) — skip cleanly; they join as they're built.
                continue
        return cls(strategies, mode=mode)
