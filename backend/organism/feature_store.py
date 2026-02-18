"""
Phase 2 — Versioned Feature Store.

Provides online/offline feature parity:
- Feature configs are versioned (hash of pipeline config).
- Feature snapshots are stored for each bar window for training reproducibility.
- QA gates reject bad data before training or policy updates.

The feature store wraps the existing FeatureEngineer but adds:
1. Config versioning
2. Snapshot persistence
3. Data QA checks
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.features.feature_engineering import FeatureEngineer
from backend.infra.schemas import ModelLifecycleEvent
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Default feature pipeline configuration
DEFAULT_FEATURE_CONFIG: dict[str, Any] = {
    "feature_mode": "realtime_light",
    "enable_heavy_features": False,
    "enable_autocorr_features": False,
    "feature_groups": [
        "trend",       # SMA/EMA slopes, breakout distance
        "mean_reversion",  # z-scores, Bollinger position/width
        "volatility",  # ATR, realized vol
        "liquidity",   # volume anomalies
        "regime",      # trend strength + volatility regime
    ],
}


@dataclass
class FeatureQAReport:
    """Results of data quality checks on a feature set."""
    passed: bool
    missing_bar_pct: float = 0.0
    nan_pct: float = 0.0
    outlier_count: int = 0
    row_count: int = 0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "missing_bar_pct": round(self.missing_bar_pct, 4),
            "nan_pct": round(self.nan_pct, 4),
            "outlier_count": self.outlier_count,
            "row_count": self.row_count,
            "issues": self.issues,
        }


@dataclass
class FeatureSnapshot:
    """A versioned snapshot of features for audit/training reproducibility."""
    version_id: str
    config_hash: str
    symbol: str
    timeframe: str
    window_start: str
    window_end: str
    feature_columns: list[str]
    row_count: int
    qa: FeatureQAReport
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "config_hash": self.config_hash,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "feature_columns": self.feature_columns,
            "row_count": self.row_count,
            "qa": self.qa.to_dict(),
            "created_at": self.created_at,
        }


class VersionedFeatureStore:
    """Feature store that wraps FeatureEngineer with config versioning + QA."""

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._config = config or dict(DEFAULT_FEATURE_CONFIG)
        self._sessionmaker = sessionmaker
        self._config_hash = self._hash_config(self._config)
        self._engineer = FeatureEngineer(config=self._config)

    @property
    def config_hash(self) -> str:
        return self._config_hash

    @staticmethod
    def _hash_config(config: dict[str, Any]) -> str:
        blob = json.dumps(config, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]

    def compute_features(
        self,
        price_df: pd.DataFrame,
        *,
        symbol: str = "",
        timeframe: str = "1Day",
    ) -> tuple[pd.DataFrame, FeatureSnapshot]:
        """Compute features and return both the DataFrame and a snapshot for audit.

        This is the ~single~ entry point for both live and backtest feature computation,
        ensuring online/offline parity.
        """
        features_df = self._engineer.compute_technical_indicators(price_df)

        # QA
        qa = self._qa_check(price_df, features_df)

        now = datetime.now(UTC)
        window_start = ""
        window_end = ""
        if "timestamp" in price_df.columns and len(price_df) > 0:
            window_start = str(price_df["timestamp"].iloc[0])
            window_end = str(price_df["timestamp"].iloc[-1])

        snapshot = FeatureSnapshot(
            version_id=f"{self._config_hash}_{symbol}_{now.strftime('%Y%m%d%H%M%S')}",
            config_hash=self._config_hash,
            symbol=symbol,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
            feature_columns=list(features_df.columns),
            row_count=len(features_df),
            qa=qa,
            created_at=now.isoformat(),
        )

        return features_df, snapshot

    def _qa_check(self, price_df: pd.DataFrame, features_df: pd.DataFrame) -> FeatureQAReport:
        """Run data quality gates."""
        issues: list[str] = []
        row_count = len(features_df)

        # Missing bars (gaps in timestamp sequence)
        missing_bar_pct = 0.0
        if "timestamp" in price_df.columns and len(price_df) > 1:
            try:
                ts = pd.to_datetime(price_df["timestamp"])
                diffs = ts.diff().dropna()
                if len(diffs) > 0:
                    median_diff = diffs.median()
                    gaps = (diffs > median_diff * 2).sum()
                    missing_bar_pct = float(gaps) / len(diffs) if len(diffs) > 0 else 0.0
                    if missing_bar_pct > 0.10:
                        issues.append(f"High missing bar rate: {missing_bar_pct:.2%}")
            except Exception as e:
                logger.warning("QA: missing-bar check failed", extra={"error": str(e)})

        # NaN percentage in features
        nan_pct = 0.0
        if row_count > 0:
            total_cells = features_df.size
            nan_cells = int(features_df.isna().sum().sum())
            nan_pct = nan_cells / total_cells if total_cells > 0 else 0.0
            if nan_pct > 0.20:
                issues.append(f"High NaN rate in features: {nan_pct:.2%}")

        # Outlier detection (simple: values > 10 std from mean)
        outlier_count = 0
        try:
            numeric_cols = features_df.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                series = features_df[col].dropna()
                if len(series) < 10:
                    continue
                mean = series.mean()
                std = series.std()
                if std > 0:
                    outliers = ((series - mean).abs() > 10 * std).sum()
                    outlier_count += int(outliers)
        except Exception as e:
            logger.warning("QA: outlier check failed", extra={"error": str(e)})

        if outlier_count > 5:
            issues.append(f"Detected {outlier_count} extreme outliers")

        passed = len(issues) == 0

        return FeatureQAReport(
            passed=passed,
            missing_bar_pct=missing_bar_pct,
            nan_pct=nan_pct,
            outlier_count=outlier_count,
            row_count=row_count,
            issues=issues,
        )

    async def persist_snapshot(self, snapshot: FeatureSnapshot) -> None:
        """Store the feature snapshot for audit/training reproducibility."""
        if not self._sessionmaker:
            return
        try:
            async with self._sessionmaker() as session:
                session.add(
                    ModelLifecycleEvent(
                        model_id=None,
                        model_name="feature_store",
                        model_version=snapshot.config_hash,
                        event_type="feature_snapshot",
                        payload=snapshot.to_dict(),
                        created_at=datetime.now(UTC),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.warning("Feature snapshot persist failed", extra={"error": str(e)})

    async def get_latest_snapshot(self, symbol: str = "") -> FeatureSnapshot | None:
        """Load the most recent feature snapshot for a symbol."""
        if not self._sessionmaker:
            return None
        try:
            async with self._sessionmaker() as session:
                q = (
                    select(ModelLifecycleEvent)
                    .where(
                        ModelLifecycleEvent.event_type == "feature_snapshot",
                        ModelLifecycleEvent.model_name == "feature_store",
                    )
                    .order_by(desc(ModelLifecycleEvent.created_at))
                    .limit(1)
                )
                row = await session.execute(q)
                evt = row.scalars().first()
                if not evt:
                    return None
                p = evt.payload or {}
                qa_d = p.get("qa", {})
                return FeatureSnapshot(
                    version_id=p.get("version_id", ""),
                    config_hash=p.get("config_hash", ""),
                    symbol=p.get("symbol", ""),
                    timeframe=p.get("timeframe", ""),
                    window_start=p.get("window_start", ""),
                    window_end=p.get("window_end", ""),
                    feature_columns=p.get("feature_columns", []),
                    row_count=p.get("row_count", 0),
                    qa=FeatureQAReport(
                        passed=qa_d.get("passed", True),
                        missing_bar_pct=qa_d.get("missing_bar_pct", 0.0),
                        nan_pct=qa_d.get("nan_pct", 0.0),
                        outlier_count=qa_d.get("outlier_count", 0),
                        row_count=qa_d.get("row_count", 0),
                        issues=qa_d.get("issues", []),
                    ),
                    created_at=p.get("created_at", ""),
                )
        except Exception as e:
            logger.warning("Feature snapshot load failed", extra={"error": str(e)})
            return None
