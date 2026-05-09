"""Strategy authorization and promotion guardrails.

This governor is deliberately side-effect free in Phase 9A.  It gives live
and replay paths a shared answer to: "is this strategy allowed to risk
capital?"  Wiring it into order placement is a later controlled slice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from backend.organism.schema.candidate_signal import CandidateSignal


@dataclass(frozen=True)
class StrategyPolicy:
    strategy_id: str
    enabled: bool = True
    live_enabled: bool = False
    min_live_tier: int = 2
    max_risk_budget_bps: float = 0.0
    allow_pyramiding: bool = False
    allowed_regimes: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    strategy_id: str
    evidence_tier: int
    live_intent: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "strategy_id": self.strategy_id,
            "evidence_tier": self.evidence_tier,
            "live_intent": self.live_intent,
        }


DEFAULT_STRATEGY_POLICIES: tuple[StrategyPolicy, ...] = (
    StrategyPolicy(
        strategy_id="alpha_baseline",
        enabled=True,
        live_enabled=True,
        min_live_tier=0,
        max_risk_budget_bps=25.0,
        notes="Current guarded alpha/breakout baseline; not a new promotion.",
    ),
    StrategyPolicy(strategy_id="orb_sip_current", notes="Current ORB remains shadow/research."),
    StrategyPolicy(strategy_id="eod_momentum_current", notes="Current EOD remains shadow/research."),
    StrategyPolicy(strategy_id="mean_reversion_current", notes="Current MR remains shadow/research."),
    StrategyPolicy(strategy_id="etf_intraday_momentum", notes="Phase 9B top research lane."),
    StrategyPolicy(strategy_id="gamma_flow_momentum", notes="Phase 9B volatility/gamma overlay lane."),
    StrategyPolicy(strategy_id="orb_sip_v2", notes="Redesigned stocks-in-play ORB lane."),
    StrategyPolicy(strategy_id="residual_mean_reversion", notes="Residual/sector-neutral MR lane."),
    StrategyPolicy(strategy_id="pairs_stat_arb", notes="Medium-term residual pairs lane."),
    StrategyPolicy(strategy_id="eod_reversal_shadow", notes="Experimental EOD single-name reversal."),
    StrategyPolicy(strategy_id="inverse_index_hedge", notes="Intraday hedge overlay only."),
    StrategyPolicy(strategy_id="catalyst_continuation", notes="Catalyst/news continuation lane."),
    StrategyPolicy(strategy_id="reconciliation_artifact", enabled=False, notes="Bookkeeping only."),
)


@dataclass
class StrategyGovernor:
    """Read-only strategy gate for shadow/replay/live authorization checks."""

    policies: Iterable[StrategyPolicy] = field(default_factory=lambda: DEFAULT_STRATEGY_POLICIES)

    def __post_init__(self) -> None:
        self._policies = {p.strategy_id: p for p in self.policies}

    @property
    def known_strategy_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))

    def policy_for(self, strategy_id: str) -> StrategyPolicy | None:
        return self._policies.get(str(strategy_id or "").strip().lower())

    def authorize_signal(
        self,
        signal: CandidateSignal,
        *,
        live_intent: bool,
        pyramiding: bool = False,
    ) -> AuthorizationDecision:
        policy = self.policy_for(signal.strategy_id)
        if policy is None:
            return AuthorizationDecision(
                False,
                "unknown_strategy_id",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if not policy.enabled:
            return AuthorizationDecision(
                False,
                "strategy_disabled",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if pyramiding and not policy.allow_pyramiding:
            return AuthorizationDecision(
                False,
                "pyramiding_not_allowed",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if policy.allowed_regimes and signal.regime not in policy.allowed_regimes:
            return AuthorizationDecision(
                False,
                "regime_not_allowed",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if not live_intent:
            return AuthorizationDecision(
                True,
                "shadow_authorized",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if signal.shadow_only:
            return AuthorizationDecision(
                False,
                "signal_shadow_only",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if not policy.live_enabled:
            return AuthorizationDecision(
                False,
                "strategy_live_disabled",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if signal.evidence_tier < policy.min_live_tier:
            return AuthorizationDecision(
                False,
                "insufficient_evidence_tier",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        if signal.risk_budget_bps > policy.max_risk_budget_bps:
            return AuthorizationDecision(
                False,
                "risk_budget_exceeds_policy",
                signal.strategy_id,
                signal.evidence_tier,
                live_intent,
            )
        return AuthorizationDecision(
            True,
            "live_authorized",
            signal.strategy_id,
            signal.evidence_tier,
            live_intent,
        )
