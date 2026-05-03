"""
Organism Runner — the integrated tick that runs per live cycle.

Ties together all organism subsystems in a single coherent tick:
1. Regime detection
2. Drift check
3. Governance validation
4. Regime-conditioned weight blending
5. Strategy execution (via multi-strategy runner)
6. Attribution (fast, from recent signals)
7. Living policy update
8. Promotion evaluation

This replaces the disparate scheduler-level integrations with a
unified organism heartbeat.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from backend.organism.regime import RegimeDetector, RegimeConditionedEnsemble, DriftDetector
from backend.organism.governance import GovernanceController
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class OrganismRunner:
    """Unified organism tick coordinator.

    Created once at startup and stored in app.state.organism_runner.
    Called each time the multi-strategy runner fires.
    """

    def __init__(
        self,
        *,
        governance: GovernanceController | None = None,
        regime_detector: RegimeDetector | None = None,
        ensemble: RegimeConditionedEnsemble | None = None,
        drift_detector: DriftDetector | None = None,
        now_fn: Any = None,
    ) -> None:
        self.governance = governance or GovernanceController()
        self.regime = regime_detector or RegimeDetector()
        self.ensemble = ensemble or RegimeConditionedEnsemble()
        self.drift = drift_detector or DriftDetector()

        # V8 DD2-10 / Wave-35 (2026-05-03): inject a clock so replay sees
        # the replay clock instead of wall clock.  Default is the canonical
        # wall-clock for live; replay supplies a synthetic clock.
        from backend.utils.clock_injection import default_now_fn
        self._now_fn = now_fn or default_now_fn

        self._tick_count: int = 0
        self._last_regime: str = ""
        self._last_drift_check: datetime | None = None
        self._drift_interval_s = int(os.getenv("ORGANISM_DRIFT_CHECK_INTERVAL_S", "3600"))

    def pre_execution_hook(
        self,
        *,
        features_df: Any = None,
        base_weights: dict[str, float],
        reference_features: Any = None,
    ) -> dict[str, Any]:
        """Called BEFORE strategy execution.

        Returns:
          - final_weights: regime-conditioned weights to apply
          - regime: detected regime state
          - trading_allowed: whether execution should proceed
          - drift: drift report (if checked this tick)
        """
        self._tick_count += 1
        result: dict[str, Any] = {
            "final_weights": dict(base_weights),
            "regime": None,
            "trading_allowed": True,
            "drift": None,
            "governance": self.governance.to_dict(),
        }

        # Governance check
        if self.governance.is_trading_halted:
            result["trading_allowed"] = False
            logger.warning("Organism: trading halted by governance")
            return result

        # Regime detection
        if features_df is not None and hasattr(features_df, "empty") and not features_df.empty:
            regime_state = self.regime.detect(features_df)
            result["regime"] = regime_state.to_dict()
            self._last_regime = regime_state.primary

            # Regime-conditioned blending
            if not self.governance.is_frozen:
                blended = self.ensemble.blend(regime_state, base_weights)

                # Filter disabled strategies
                for src in list(blended.keys()):
                    if self.governance.is_strategy_disabled(src):
                        blended[src] = 0.0

                result["final_weights"] = blended

        # Drift check (periodic)
        # V8 DD2-10 / Wave-35: use injected clock for replay determinism.
        now = self._now_fn()
        if reference_features is not None and features_df is not None:
            should_check = (
                self._last_drift_check is None
                or (now - self._last_drift_check).total_seconds() >= self._drift_interval_s
            )
            if should_check:
                try:
                    drift_report = self.drift.check_drift(reference_features, features_df)
                    result["drift"] = drift_report.to_dict()
                    self._last_drift_check = now

                    if drift_report.drifted:
                        logger.warning(
                            "Feature drift detected",
                            extra={"score": drift_report.overall_score},
                        )
                except Exception as e:
                    logger.warning("Drift check failed", extra={"error": str(e)})

        return result

    def post_execution_hook(
        self,
        *,
        live_metrics: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Called AFTER strategy execution.

        Checks drawdown, turnover, etc. and potentially triggers governance actions.
        """
        result: dict[str, Any] = {"actions": []}

        if not live_metrics:
            return result

        # Drawdown kill switch — use governance's configured limit
        drawdown = live_metrics.get("drawdown", 0.0)
        dd_limit = self.governance._drawdown_limit
        if drawdown >= dd_limit:
            self.governance.trigger_drawdown_kill(drawdown)
            result["actions"].append("drawdown_kill_triggered")

        return result

    def status(self) -> dict[str, Any]:
        return {
            "tick_count": self._tick_count,
            "last_regime": self._last_regime,
            "governance": self.governance.to_dict(),
        }
