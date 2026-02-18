"""
Phase 4 — Training Orchestrator.

Schedules and runs nightly/weekly training jobs:
1. Fetch recent market data for the training universe.
2. Compute versioned features via FeatureStore.
3. Run attribution to get reward signals from fills.
4. Produce candidate policy weights (from attribution + regime analysis).
5. Run walk-forward evaluation on the candidate vs current baseline.
6. If candidate passes gates → write to Policy Registry for promotion.
7. If candidate fails → log and keep current policy.

Can run as:
- A scheduled background job (via APScheduler or asyncio loop)
- A manual trigger via API endpoint
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from backend.organism.attribution import AttributionService
from backend.organism.feature_store import VersionedFeatureStore
from backend.organism.walk_forward import WalkForwardEvaluator, AcceptanceGates
from backend.organism.governance import GovernanceController
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrainingCandidate:
    """A candidate policy produced by training."""
    id: str
    weights: dict[str, float]
    regime_weights: dict[str, dict[str, float]]  # {regime_label: {source: weight}}
    parameters: dict[str, Any]
    source: str  # "nightly" | "weekly" | "manual"
    created_at: str
    attribution_window: str = ""
    feature_config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "weights": self.weights,
            "regime_weights": self.regime_weights,
            "parameters": self.parameters,
            "source": self.source,
            "created_at": self.created_at,
            "attribution_window": self.attribution_window,
            "feature_config_hash": self.feature_config_hash,
        }


@dataclass
class TrainingRunResult:
    """Result of a full training run."""
    run_id: str
    candidate: TrainingCandidate | None = None
    walk_forward_accepted: bool = False
    walk_forward_report: dict[str, Any] = field(default_factory=dict)
    promoted: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "walk_forward_accepted": self.walk_forward_accepted,
            "promoted": self.promoted,
            "rejection_reasons": self.rejection_reasons,
            "duration_s": round(self.duration_s, 2),
            "created_at": self.created_at,
        }


class TrainingOrchestrator:
    """Nightly/weekly training job that produces, evaluates, and promotes candidates.

    This is the organism's "slow brain" — it runs off-line relative to the
    live trading loop and produces improvements that are staged for promotion.
    """

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        governance: GovernanceController,
        data_fetcher: Any = None,  # callable(symbol, lookback, timeframe) -> DataFrame
        train_window_days: int = 60,
        test_window_days: int = 10,
        step_days: int = 5,
        attribution_lookback_days: int = 7,
        universe: list[str] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._governance = governance
        self._data_fetcher = data_fetcher
        self._attribution = AttributionService(sessionmaker)
        self._feature_store = VersionedFeatureStore(sessionmaker=sessionmaker)
        self._evaluator = WalkForwardEvaluator(
            train_window_days=train_window_days,
            test_window_days=test_window_days,
            step_days=step_days,
        )

        self._universe = universe or self._default_universe()
        self._attribution_lookback = attribution_lookback_days

        # These are env-configurable
        self._score_alpha = float(os.getenv("ORGANISM_TRAINING_SCORE_ALPHA", "0.3"))
        self._regime_boost = float(os.getenv("ORGANISM_TRAINING_REGIME_BOOST", "0.05"))

    @staticmethod
    def _default_universe() -> list[str]:
        csv = os.getenv(
            "ORGANISM_TRAINING_UNIVERSE",
            "AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,SPY,QQQ,IWM",
        )
        return [s.strip().upper() for s in csv.split(",") if s.strip()]

    async def run_training(
        self,
        *,
        source: str = "nightly",
        current_weights: dict[str, float] | None = None,
    ) -> TrainingRunResult:
        """Full training pipeline."""
        run_id = str(uuid.uuid4())[:12]
        start_time = datetime.now(UTC)
        result = TrainingRunResult(run_id=run_id, created_at=start_time.isoformat())

        # 1. Governance check
        if self._governance.is_frozen:
            result.rejection_reasons.append("Organism adaptation is frozen")
            return result

        if not self._governance.can_change():
            result.rejection_reasons.append("Daily change budget exhausted")
            return result

        try:
            # 2. Run attribution on recent fills
            attr_end = datetime.now(UTC)
            attr_start = attr_end - timedelta(days=self._attribution_lookback)
            attribution = await self._attribution.compute_attribution(
                window_start=attr_start,
                window_end=attr_end,
                persist=True,
            )

            # 3. Produce candidate weights from attribution
            candidate = self._produce_candidate(
                attribution_rewards=attribution.reward_signals,
                current_weights=current_weights or {},
                source=source,
            )
            result.candidate = candidate

            # 4. Fetch price data for walk-forward
            price_data = await self._fetch_price_data()
            if not price_data:
                result.rejection_reasons.append("No price data available for walk-forward")
                return result

            # 5. Run walk-forward evaluation
            baseline_weights = current_weights or {s: 1.0 for s in candidate.weights}
            wf_report = await self._evaluator.evaluate(
                price_data=price_data,
                candidate_weights=candidate.weights,
                baseline_weights=baseline_weights,
                candidate_id=candidate.id,
                baseline_id="current",
            )

            result.walk_forward_report = wf_report.to_dict()
            result.walk_forward_accepted = wf_report.accepted
            result.rejection_reasons.extend(wf_report.rejection_reasons)

            # 6. Register candidate if accepted
            if wf_report.accepted:
                await self._register_candidate(candidate, wf_report.to_dict())
                result.promoted = True  # promoted to registry; promotion controller handles staging
                self._governance.record_change()
                logger.info(
                    "Training candidate accepted and registered",
                    extra={"candidate_id": candidate.id, "sharpe": wf_report.mean_sharpe},
                )
            else:
                logger.info(
                    "Training candidate rejected",
                    extra={
                        "candidate_id": candidate.id,
                        "reasons": wf_report.rejection_reasons,
                    },
                )

        except Exception as e:
            result.rejection_reasons.append(f"Training error: {str(e)}")
            logger.exception("Training run failed", extra={"run_id": run_id})

        result.duration_s = (datetime.now(UTC) - start_time).total_seconds()
        return result

    def _produce_candidate(
        self,
        *,
        attribution_rewards: dict[str, float],
        current_weights: dict[str, float],
        source: str,
    ) -> TrainingCandidate:
        """Generate candidate weights from attribution rewards + current policy.

        Uses a simple update rule:
            new_w = current_w * (1 + alpha * reward)
        Then normalizes so mean weight == 1.0.
        """
        all_sources = set(current_weights.keys()) | set(attribution_rewards.keys())
        if not all_sources:
            all_sources = {"momentum", "mean_reversion", "stat_arb", "regime_momentum", "breakout"}

        raw: dict[str, float] = {}
        for src in all_sources:
            cw = current_weights.get(src, 1.0)
            reward = attribution_rewards.get(src, 0.0)
            raw[src] = cw * (1.0 + self._score_alpha * reward)

        # Normalize
        mean_w = sum(raw.values()) / len(raw) if raw else 1.0
        if mean_w > 0:
            weights = {k: v / mean_w for k, v in raw.items()}
        else:
            weights = {k: 1.0 for k in raw}

        # Clamp
        weights = {k: max(0.10, min(2.50, v)) for k, v in weights.items()}

        # Regime-specific weight variants — labels MUST match RegimeLabel constants
        from backend.organism.regime import RegimeLabel
        regime_weights = {
            RegimeLabel.TRENDING_UP: {k: v * (1.05 if k in ("momentum", "regime_momentum", "breakout") else 0.95) for k, v in weights.items()},
            RegimeLabel.TRENDING_DOWN: {k: v * (0.95 if k in ("momentum", "breakout") else 1.05) for k, v in weights.items()},
            RegimeLabel.CHOP: {k: v * (1.05 if k in ("mean_reversion", "stat_arb") else 0.95) for k, v in weights.items()},
            RegimeLabel.HIGH_VOL: {k: v * (0.90 if k == "breakout" else 1.0) for k, v in weights.items()},
            RegimeLabel.LOW_VOL: {k: v * 1.0 for k, v in weights.items()},
            RegimeLabel.STRESS: {k: v * (0.80 if k in ("momentum", "breakout") else 0.90) for k, v in weights.items()},
        }

        return TrainingCandidate(
            id=f"{source}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            weights=weights,
            regime_weights=regime_weights,
            parameters={},
            source=source,
            created_at=datetime.now(UTC).isoformat(),
            feature_config_hash=self._feature_store.config_hash,
        )

    async def _fetch_price_data(self) -> dict[str, pd.DataFrame]:
        """Fetch recent price data for the training universe."""
        price_data: dict[str, pd.DataFrame] = {}

        if self._data_fetcher is None:
            try:
                from backend.data.alpaca_client import AlpacaClient
                import os as _os
                api_key = _os.getenv("ALPACA_API_KEY_ID", "") or _os.getenv("ALPACA_API_KEY", "")
                secret_key = _os.getenv("ALPACA_API_SECRET_KEY", "") or _os.getenv("ALPACA_SECRET_KEY", "")
                paper = _os.getenv("ALPACA_PAPER", "true").lower() in ("1", "true")
                if not api_key or not secret_key:
                    logger.warning(
                        "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not set — "
                        "cannot create data client for training"
                    )
                    return {}
                client = AlpacaClient(
                    api_key=api_key,
                    secret_key=secret_key,
                    paper=paper,
                )
                self._data_fetcher = client
            except Exception as e:
                logger.warning("Cannot create data client for training", extra={"error": str(e)})
                return {}

        import asyncio as _asyncio

        for symbol in self._universe:
            try:
                if hasattr(self._data_fetcher, "get_historical_bars_df"):
                    method = self._data_fetcher.get_historical_bars_df
                    if _asyncio.iscoroutinefunction(method):
                        df = await method(symbol, lookback=200, timeframe="1Day")
                    else:
                        df = await _asyncio.to_thread(
                            method, symbol, lookback=200, timeframe="1Day",
                        )
                elif hasattr(self._data_fetcher, "get_historical_data"):
                    method = self._data_fetcher.get_historical_data
                    if _asyncio.iscoroutinefunction(method):
                        df = await method(symbol, timeframe="1Day", limit=200)
                    else:
                        df = await _asyncio.to_thread(
                            method, symbol, timeframe="1Day", limit=200,
                        )
                else:
                    continue

                if df is not None and not df.empty:
                    # Normalize columns
                    col_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
                    df = df.rename(columns=col_map)
                    if "timestamp" not in df.columns:
                        df = df.reset_index().rename(columns={"index": "timestamp"})
                    price_data[symbol] = df
            except Exception as e:
                logger.warning(f"Failed to fetch data for {symbol}", extra={"error": str(e)})

        return price_data

    async def _register_candidate(
        self, candidate: TrainingCandidate, wf_report: dict[str, Any]
    ) -> None:
        """Write accepted candidate to the policy registry in DB."""
        from backend.infra.schemas import ModelLifecycleEvent

        try:
            async with self._sessionmaker() as session:
                session.add(
                    ModelLifecycleEvent(
                        model_id=None,
                        model_name="policy_registry",
                        model_version=candidate.id,
                        event_type="candidate_registered",
                        payload={
                            "candidate": candidate.to_dict(),
                            "walk_forward_summary": {
                                k: v
                                for k, v in wf_report.items()
                                if k != "windows"
                            },
                        },
                        created_at=datetime.now(UTC),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.warning("Failed to register candidate", extra={"error": str(e)})
