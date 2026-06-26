"""Momentum strategy — the live book, extracted onto the Strategy contract.

Phase 1 Section 5: pull the live direction logic out of alpha_scanner so it lives
behind the shared contract, with thresholds read from strategy_config (verbatim
values). Because ML is dropped from the live gate (DROP_ML_FROM_GATE=True), the
live entry DIRECTION is a pure function of (features, regime) — exactly the
contract shape — so this is a faithful, parity-checkable extraction.

PARITY (Section 9): `_direction()` reproduces alpha_scanner._observable_direction
bit-for-bit (proven exhaustively in tests). The live engine keeps using its own
path by default; this module only becomes the live path behind the framework
flag once engine-level parity (step 5) is proven.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# Reuse the SAME symmetric-short flag the live path uses, so the two never diverge.
from backend.organism.alpha_scanner import SYMMETRIC_SHORT_ENABLED
from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy
from backend.organism.strategies.registry import register


def _finite(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f and f not in (float("inf"), float("-inf")) else default


@register("momentum")
class MomentumStrategy(Strategy):
    """Live momentum book. Direction from observable momentum/breakout features."""

    def required_features(self) -> set[str]:
        return {"ret_5d", "ret_20d", "comp_breakout_readiness",
                "comp_squeeze_momentum", "trend_strength"}

    def eligible_regimes(self) -> set[str]:
        return set(self.config.get("eligible_regimes", []))

    def validate_config(self) -> None:
        required = (
            "breakout_readiness_threshold", "breakout_readiness_squeeze_threshold",
            "squeeze_momentum_threshold", "ret_5d_threshold", "ret_20d_threshold",
        )
        for k in required:
            if k not in self.config:
                raise ValueError(f"momentum config missing {k!r}")
            if not isinstance(self.config[k], (int, float)):
                raise ValueError(f"momentum config {k!r} must be numeric")

    # ── direction: a verbatim port of alpha_scanner._observable_direction ──
    def _direction(self, row: pd.Series) -> float:
        c = self.config
        ret_5d = _finite(row.get("ret_5d", 0.0))
        ret_20d = _finite(row.get("ret_20d", 0.0))
        readiness = _finite(row.get("comp_breakout_readiness", 0.0))
        squeeze = _finite(row.get("comp_squeeze_momentum", 0.0))
        trend = _finite(row.get("trend_strength", 0.0))

        bullish_breakout = (
            readiness > c["breakout_readiness_threshold"]
            or (readiness > c["breakout_readiness_squeeze_threshold"]
                and squeeze > c["squeeze_momentum_threshold"])
        )
        bullish_momentum = (
            ret_5d > c["ret_5d_threshold"]
            or (ret_20d > c["ret_20d_threshold"] and trend >= c["trend_strength_min"])
        )

        if SYMMETRIC_SHORT_ENABLED:
            bearish_breakdown = squeeze < c["bearish_squeeze_threshold"]
            bearish_momentum = (
                ret_5d < c["bearish_ret_5d_threshold"]
                or (ret_20d < c["bearish_ret_20d_threshold"]
                    and trend <= c["trend_strength_max"])
            ) and not bullish_breakout
            if bullish_breakout or bullish_momentum:
                return 1.0
            if bearish_breakdown or bearish_momentum:
                return -1.0
            return 0.0

        bearish_momentum = ret_5d < c["bearish_ret_5d_threshold"] and not bullish_breakout
        if bullish_breakout or bullish_momentum:
            return 1.0
        if bearish_momentum:
            return -1.0
        return 0.0

    def _confidence(self, row: pd.Series, direction: float) -> float:
        # Comparable [0,1] conviction: breakout readiness is the natural momentum
        # conviction axis; clamp to [0,1]. (Ranking/scoring parity with the live
        # composite is verified at the engine level in step 5.)
        return max(0.0, min(1.0, _finite(row.get("comp_breakout_readiness", 0.0))))

    def scan(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        out: list[Candidate] = []
        for sym, df in features.items():
            if df is None or len(df) == 0:
                continue
            row = df.iloc[-1]
            d = self._direction(row)
            if d == 0.0:
                continue
            out.append(Candidate(
                symbol=sym, direction=d, confidence=self._confidence(row, d),
                strategy_name=self.name, features_snapshot=row,
                extra={"regime": regime},
            ))
        return out
