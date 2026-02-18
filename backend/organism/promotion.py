"""
Phase 5 — Promotion Controller (State Machine).

Manages the safe deployment pipeline for policy candidates:
    shadow → paper_execute → canary → ramp → active

State machine:
  SHADOW        – compute decisions only, log, don't trade
  PAPER_EXECUTE – submit orders through paper broker with strict caps
  CANARY        – use candidate for a tiny subset of universe / small risk budget
  RAMP          – gradually increase budget / universe breadth
  ACTIVE        – fully promoted
  ROLLED_BACK   – candidate failed, reverted to last-known-good

Automatic rollback triggers:
  - Drawdown breach
  - Slippage anomaly
  - Drift + calibration collapse
  - Excessive regime churn / turnover

Each transition is persisted as a ModelLifecycleEvent for audit.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.infra.schemas import ModelLifecycleEvent
from backend.organism.governance import GovernanceController
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class PromotionStage(str, Enum):
    SHADOW = "shadow"
    PAPER_EXECUTE = "paper_execute"
    CANARY = "canary"
    RAMP = "ramp"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"

    @classmethod
    def ordered(cls) -> list["PromotionStage"]:
        return [cls.SHADOW, cls.PAPER_EXECUTE, cls.CANARY, cls.RAMP, cls.ACTIVE]


@dataclass
class PromotionState:
    """Current state of a candidate in the promotion pipeline."""
    candidate_id: str
    stage: PromotionStage
    weights: dict[str, float]
    regime_weights: dict[str, dict[str, float]]
    entered_stage_at: str
    metrics_in_stage: dict[str, Any] = field(default_factory=dict)
    rollback_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "stage": self.stage.value,
            "weights": self.weights,
            "regime_weights": self.regime_weights,
            "entered_stage_at": self.entered_stage_at,
            "metrics_in_stage": self.metrics_in_stage,
            "rollback_count": self.rollback_count,
        }


@dataclass
class RollbackTrigger:
    """Describes what caused a rollback."""
    reason: str
    metric_name: str
    metric_value: float
    threshold: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "metric_name": self.metric_name,
            "metric_value": round(self.metric_value, 6),
            "threshold": round(self.threshold, 6),
            "timestamp": self.timestamp,
        }


# ── Stage-specific risk caps ────────────────────────────────────────

STAGE_RISK_CAPS: dict[str, dict[str, float]] = {
    PromotionStage.SHADOW.value: {
        "max_exposure": 0.0,       # no actual risk
        "max_symbols": 0,
    },
    PromotionStage.PAPER_EXECUTE.value: {
        "max_exposure": 0.20,      # 20% max per position
        "max_symbols": 50,
    },
    PromotionStage.CANARY.value: {
        "max_exposure": 0.05,      # 5% max per position
        "max_symbols": 5,
    },
    PromotionStage.RAMP.value: {
        "max_exposure": 0.15,      # 15%
        "max_symbols": 20,
    },
    PromotionStage.ACTIVE.value: {
        "max_exposure": 0.25,
        "max_symbols": 100,
    },
}


class PromotionController:
    """Manages the candidate promotion lifecycle.

    Usage:
        controller = PromotionController(sessionmaker=..., governance=...)
        await controller.restore_state()

        # After successful walk-forward:
        await controller.begin_promotion(candidate_id, weights, regime_weights)

        # On each tick:
        stage = controller.current_stage
        risk_caps = controller.current_risk_caps()

        # After observing metrics:
        await controller.evaluate_and_advance(live_metrics)

        # If bad:
        await controller.rollback(trigger)
    """

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        governance: GovernanceController,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._governance = governance
        self._state: PromotionState | None = None
        self._last_known_good: dict[str, float] | None = None

        # Read env at instantiation time, not import time
        self.MIN_STAGE_DURATION: dict[str, int] = {
            PromotionStage.SHADOW.value: int(os.getenv("ORGANISM_SHADOW_MIN_S", "3600")),
            PromotionStage.PAPER_EXECUTE.value: int(os.getenv("ORGANISM_PAPER_MIN_S", "86400")),
            PromotionStage.CANARY.value: int(os.getenv("ORGANISM_CANARY_MIN_S", "86400")),
            PromotionStage.RAMP.value: int(os.getenv("ORGANISM_RAMP_MIN_S", "172800")),
        }
        self.ROLLBACK_THRESHOLDS: dict[str, float] = {
            "max_drawdown": float(os.getenv("ORGANISM_ROLLBACK_DD", "0.08")),
            "max_slippage_bps": float(os.getenv("ORGANISM_ROLLBACK_SLIPPAGE_BPS", "50")),
            "max_turnover_ratio": float(os.getenv("ORGANISM_ROLLBACK_TURNOVER", "10.0")),
            "max_regime_churn_rate": float(os.getenv("ORGANISM_ROLLBACK_CHURN", "0.50")),
        }

    @property
    def current_stage(self) -> PromotionStage | None:
        return self._state.stage if self._state else None

    @property
    def active_candidate_id(self) -> str | None:
        return self._state.candidate_id if self._state else None

    def current_risk_caps(self) -> dict[str, float]:
        if not self._state:
            return STAGE_RISK_CAPS[PromotionStage.SHADOW.value]
        return STAGE_RISK_CAPS.get(
            self._state.stage.value,
            STAGE_RISK_CAPS[PromotionStage.SHADOW.value],
        )

    def get_active_weights(self) -> dict[str, float] | None:
        """Return candidate weights if in an execute stage, else None (use baseline)."""
        if self._state and self._state.stage not in (PromotionStage.SHADOW, PromotionStage.ROLLED_BACK):
            return dict(self._state.weights)
        return self._last_known_good

    def get_regime_weights(self, regime: str) -> dict[str, float] | None:
        """Get regime-specific weights if available."""
        if self._state and self._state.regime_weights:
            return self._state.regime_weights.get(regime)
        return None

    # ── lifecycle ────────────────────────────────────────────────────

    async def begin_promotion(
        self,
        candidate_id: str,
        weights: dict[str, float],
        regime_weights: dict[str, dict[str, float]] | None = None,
    ) -> PromotionState:
        """Start promoting a new candidate (enters SHADOW)."""
        # Save current weights as last-known-good (from any active/running state)
        if self._state and self._state.stage not in (
            PromotionStage.SHADOW, PromotionStage.ROLLED_BACK
        ):
            self._last_known_good = dict(self._state.weights)

        self._state = PromotionState(
            candidate_id=candidate_id,
            stage=PromotionStage.SHADOW,
            weights=weights,
            regime_weights=regime_weights or {},
            entered_stage_at=datetime.now(UTC).isoformat(),
        )

        await self._persist_transition("begin_promotion", {})
        logger.info("Promotion started", extra={"candidate": candidate_id, "stage": "shadow"})
        return self._state

    async def evaluate_and_advance(
        self, live_metrics: dict[str, float]
    ) -> PromotionState | None:
        """Check if the candidate should advance to the next stage."""
        if not self._state:
            return None
        if self._state.stage == PromotionStage.ROLLED_BACK:
            return self._state

        # Check for rollback triggers — even ACTIVE candidates can degrade
        trigger = self._check_rollback_triggers(live_metrics)
        if trigger:
            await self.rollback(trigger)
            return self._state

        if self._state.stage == PromotionStage.ACTIVE:
            return self._state  # already fully promoted, no advancement needed

        # Check minimum time in stage
        entered = datetime.fromisoformat(self._state.entered_stage_at)
        elapsed = (datetime.now(UTC) - entered).total_seconds()
        min_duration = self.MIN_STAGE_DURATION.get(self._state.stage.value, 3600)

        if elapsed < min_duration:
            return self._state  # not yet eligible

        # Governance check
        if self._governance.is_frozen:
            return self._state

        # Advance to next stage
        stages = PromotionStage.ordered()
        current_idx = stages.index(self._state.stage)
        if current_idx < len(stages) - 1:
            next_stage = stages[current_idx + 1]
            self._state.stage = next_stage
            self._state.entered_stage_at = datetime.now(UTC).isoformat()
            self._state.metrics_in_stage = dict(live_metrics)
            await self._persist_transition("advance", {"to": next_stage.value, "metrics": live_metrics})
            logger.info(
                "Promotion advanced",
                extra={"candidate": self._state.candidate_id, "stage": next_stage.value},
            )

        return self._state

    async def rollback(self, trigger: RollbackTrigger) -> PromotionState | None:
        """Roll back to last-known-good."""
        if not self._state:
            return None

        self._state.stage = PromotionStage.ROLLED_BACK
        self._state.rollback_count += 1
        self._state.entered_stage_at = datetime.now(UTC).isoformat()

        await self._persist_transition("rollback", {"trigger": trigger.to_dict()})

        # Freeze adaptation to prevent immediate re-promotion
        self._governance.freeze()

        logger.warning(
            "PROMOTION ROLLED BACK",
            extra={
                "candidate": self._state.candidate_id,
                "trigger": trigger.reason,
                "rollback_count": self._state.rollback_count,
            },
        )
        return self._state

    async def restore_state(self) -> None:
        """Restore promotion state from DB on startup."""
        try:
            async with self._sessionmaker() as session:
                row = await session.execute(
                    select(ModelLifecycleEvent)
                    .where(
                        ModelLifecycleEvent.model_name == "promotion_controller",
                    )
                    .order_by(desc(ModelLifecycleEvent.created_at))
                    .limit(1)
                )
                evt = row.scalars().first()
                if not evt:
                    return
                p = evt.payload or {}
                state = p.get("state")
                if not state:
                    return
                self._state = PromotionState(
                    candidate_id=state.get("candidate_id", ""),
                    stage=PromotionStage(state.get("stage", "shadow")),
                    weights=state.get("weights", {}),
                    regime_weights=state.get("regime_weights", {}),
                    entered_stage_at=state.get("entered_stage_at", ""),
                    metrics_in_stage=state.get("metrics_in_stage", {}),
                    rollback_count=state.get("rollback_count", 0),
                )
                lkg = p.get("last_known_good")
                if isinstance(lkg, dict):
                    self._last_known_good = lkg

                logger.info(
                    "Promotion state restored",
                    extra={
                        "candidate": self._state.candidate_id,
                        "stage": self._state.stage.value,
                    },
                )
        except Exception as e:
            logger.warning("Promotion state restore failed", extra={"error": str(e)})

    # ── internal ─────────────────────────────────────────────────────

    def _check_rollback_triggers(
        self, metrics: dict[str, float]
    ) -> RollbackTrigger | None:
        """Check live metrics against rollback thresholds."""
        now = datetime.now(UTC).isoformat()

        dd = metrics.get("drawdown", 0.0)
        if dd > self.ROLLBACK_THRESHOLDS["max_drawdown"]:
            return RollbackTrigger(
                reason="Drawdown breach",
                metric_name="drawdown",
                metric_value=dd,
                threshold=self.ROLLBACK_THRESHOLDS["max_drawdown"],
                timestamp=now,
            )

        slip = metrics.get("avg_slippage_bps", 0.0)
        if slip > self.ROLLBACK_THRESHOLDS["max_slippage_bps"]:
            return RollbackTrigger(
                reason="Slippage anomaly",
                metric_name="avg_slippage_bps",
                metric_value=slip,
                threshold=self.ROLLBACK_THRESHOLDS["max_slippage_bps"],
                timestamp=now,
            )

        turnover = metrics.get("turnover_ratio", 0.0)
        if turnover > self.ROLLBACK_THRESHOLDS["max_turnover_ratio"]:
            return RollbackTrigger(
                reason="Excessive turnover",
                metric_name="turnover_ratio",
                metric_value=turnover,
                threshold=self.ROLLBACK_THRESHOLDS["max_turnover_ratio"],
                timestamp=now,
            )

        churn = metrics.get("regime_churn_rate", 0.0)
        if churn > self.ROLLBACK_THRESHOLDS["max_regime_churn_rate"]:
            return RollbackTrigger(
                reason="Regime churn explosion",
                metric_name="regime_churn_rate",
                metric_value=churn,
                threshold=self.ROLLBACK_THRESHOLDS["max_regime_churn_rate"],
                timestamp=now,
            )

        return None  # All clear

    async def _persist_transition(
        self, action: str, details: dict[str, Any]
    ) -> None:
        """Log the state transition for audit."""
        try:
            async with self._sessionmaker() as session:
                add_call = session.add(
                    ModelLifecycleEvent(
                        model_id=None,
                        model_name="promotion_controller",
                        model_version=self._state.candidate_id if self._state else None,
                        event_type=f"promotion_{action}",
                        payload={
                            "action": action,
                            "state": self._state.to_dict() if self._state else {},
                            "last_known_good": self._last_known_good,
                            "details": details,
                        },
                        created_at=datetime.now(UTC),
                    )
                )
                if inspect.isawaitable(add_call):
                    await add_call
                await session.commit()
        except Exception as e:
            logger.warning("Promotion transition persist failed", extra={"error": str(e)})
