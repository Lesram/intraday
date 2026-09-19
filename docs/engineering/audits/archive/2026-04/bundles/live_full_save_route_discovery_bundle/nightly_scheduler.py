"""
Organism Nightly Scheduler.

Runs the "slow brain" training loop on a schedule:
1. Attribution from recent fills
2. Candidate production (weights from rewards)
3. Walk-forward evaluation
4. Registration to policy registry (if accepted)
5. Promotion start (shadow stage)

Triggered via:
  - ORGANISM_NIGHTLY_ENABLED=1
  - ORGANISM_NIGHTLY_INTERVAL_S (default 86400 = 24h)
  - or manually via API
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Backoff configuration ────────────────────────────────────────
_BASE_BACKOFF_S = 60            # first retry wait
_MAX_BACKOFF_S = 3600           # cap at 1 hour
_JITTER_FRACTION = 0.25         # ±25 % randomness


async def _run_nightly_tick(app) -> dict:
    """Execute one nightly training cycle."""
    from backend.organism.training import TrainingOrchestrator
    from backend.organism.governance import GovernanceController
    from backend.organism.promotion import PromotionController

    governance: GovernanceController | None = getattr(app.state, "organism_governance", None)
    if governance is None:
        msg = "Nightly tick: no governance controller on app.state"
        logger.warning(msg)
        raise RuntimeError(msg)

    sessionmaker = getattr(app.state, "sessionmaker", None)
    if not sessionmaker:
        msg = "Nightly tick: no sessionmaker available"
        logger.warning(msg)
        raise RuntimeError(msg)

    # Get current weights from living policy
    policy = getattr(app.state, "living_policy", None)
    current_weights = policy.get_weights() if policy else {}

    orchestrator = TrainingOrchestrator(
        sessionmaker=sessionmaker,
        governance=governance,
    )

    result = await orchestrator.run_training(
        source="nightly",
        current_weights=current_weights,
    )

    # If candidate was accepted and registered, start promotion to shadow
    if result.promoted and result.candidate:
        promotion: PromotionController | None = getattr(app.state, "organism_promotion", None)
        if promotion:
            await promotion.begin_promotion(
                candidate_id=result.candidate.id,
                weights=result.candidate.weights,
                regime_weights=result.candidate.regime_weights,
            )

    logger.info(
        "Nightly training tick completed",
        extra={
            "run_id": result.run_id,
            "promoted": result.promoted,
            "accepted": result.walk_forward_accepted,
            "duration_s": result.duration_s,
        },
    )

    return result.to_dict()


async def _nightly_loop(app) -> None:
    """Background loop for nightly training with exponential backoff.

    On consecutive failures the wait shortens to
    ``min(_BASE_BACKOFF_S * 2^failures, _MAX_BACKOFF_S) ± jitter``
    so we don't hammer a broken dependency.  A single success resets
    the counter back to the normal interval.
    """
    interval = int(os.getenv("ORGANISM_NIGHTLY_INTERVAL_S", "86400"))
    logger.info("Organism nightly scheduler started (interval=%ds)", interval)

    consecutive_errors = 0

    while True:
        try:
            await _run_nightly_tick(app)
            consecutive_errors = 0        # success → reset
        except asyncio.CancelledError:
            logger.info("Organism nightly scheduler cancelled")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.exception(
                "Organism nightly tick failed (streak=%d)",
                consecutive_errors,
                extra={"error": str(e)},
            )

        # Compute wait time
        if consecutive_errors > 0:
            raw = min(
                _BASE_BACKOFF_S * (2 ** (consecutive_errors - 1)),
                _MAX_BACKOFF_S,
            )
            jitter = raw * _JITTER_FRACTION * (random.random() * 2 - 1)
            wait = max(raw + jitter, _BASE_BACKOFF_S)
            logger.info(
                "Nightly scheduler backing off for %.0fs "
                "(consecutive_errors=%d)",
                wait,
                consecutive_errors,
            )
        else:
            wait = interval

        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            logger.info("Organism nightly scheduler cancelled during sleep")
            break


async def start_organism_nightly_scheduler(app) -> bool:
    """Start the nightly training scheduler as a background task.

    Called from the factory lifespan.
    """
    enabled = os.getenv("ORGANISM_NIGHTLY_ENABLED", "0").lower() in ("1", "true", "yes")
    if not enabled:
        return False

    task = asyncio.create_task(_nightly_loop(app))
    app.state.organism_nightly_task = task

    # Register for cleanup
    registry = getattr(app.state, "task_registry", None)
    if registry and hasattr(registry, "add"):
        registry.add(task)

    return True
