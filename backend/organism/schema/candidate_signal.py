"""Canonical strategy signal contract.

Phase 9A introduces a first-class strategy identity before ranking, sizing,
orders, replay, and promotion.  This module is intentionally lightweight and
side-effect free so it can be used by shadow engines, replay scripts, and live
gatekeeping without importing the large live engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast


_STRATEGY_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_VALID_SIDES = {"long", "short"}


ENTRY_SOURCE_STRATEGY_MAP: dict[str, str] = {
    "": "alpha_baseline",
    "alpha": "alpha_baseline",
    "breakout": "alpha_baseline",
    "alpha+breakout": "alpha_baseline",
    "orb_sip": "orb_sip_current",
    "orb_sip_inverse": "orb_sip_current",
    "eod_momentum": "eod_momentum_current",
    "eod_momentum_inverse": "eod_momentum_current",
    "mean_reversion": "mean_reversion_current",
    "reconciliation_orphan": "reconciliation_artifact",
}


def infer_strategy_id(entry_source: Any, explicit: Any = None) -> str:
    """Return the canonical strategy id for current and legacy metadata."""
    explicit_text = str(explicit or "").strip().lower()
    if explicit_text:
        return explicit_text
    source = str(entry_source or "").strip().lower()
    return ENTRY_SOURCE_STRATEGY_MAP.get(source, "alpha_baseline")


def _parse_dt(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    else:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_bool(value: Any, *, default: bool = True) -> bool:
    """Parse persisted boolean-ish values without treating "false" as truthy."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, int | float):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class CandidateSignal:
    """One strategy-born candidate before portfolio ranking and sizing."""

    signal_id: str
    strategy_id: str
    engine_version: str
    symbol: str
    side: str
    timeframe: str
    created_at: datetime | str | None
    intended_horizon_bars: int
    regime: str
    evidence_tier: int
    shadow_only: bool
    expected_edge_bps: float | None = None
    confidence: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    risk_budget_bps: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        strategy_id = str(self.strategy_id or "").strip().lower()
        symbol = str(self.symbol or "").strip().upper()
        side = str(self.side or "").strip().lower()
        timeframe = str(self.timeframe or "").strip()
        engine_version = str(self.engine_version or "").strip()
        signal_id = str(self.signal_id or "").strip()
        regime = str(self.regime or "unknown").strip().lower() or "unknown"
        created_at = _parse_dt(self.created_at)

        if not signal_id:
            raise ValueError("CandidateSignal.signal_id is required")
        if not _STRATEGY_ID_RE.match(strategy_id):
            raise ValueError(f"Invalid strategy_id: {self.strategy_id!r}")
        if not engine_version:
            raise ValueError("CandidateSignal.engine_version is required")
        if not symbol:
            raise ValueError("CandidateSignal.symbol is required")
        if side not in _VALID_SIDES:
            raise ValueError("CandidateSignal.side must be 'long' or 'short'")
        if not timeframe:
            raise ValueError("CandidateSignal.timeframe is required")
        if int(self.intended_horizon_bars) <= 0:
            raise ValueError("CandidateSignal.intended_horizon_bars must be > 0")
        if not 0 <= int(self.evidence_tier) <= 4:
            raise ValueError("CandidateSignal.evidence_tier must be in [0, 4]")
        if float(self.risk_budget_bps) < 0:
            raise ValueError("CandidateSignal.risk_budget_bps must be >= 0")
        if self.features is None or not isinstance(self.features, dict):
            raise ValueError("CandidateSignal.features must be a dict")

        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "engine_version", engine_version)
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "regime", regime)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "intended_horizon_bars", int(self.intended_horizon_bars))
        object.__setattr__(self, "evidence_tier", int(self.evidence_tier))
        object.__setattr__(self, "shadow_only", parse_bool(self.shadow_only, default=True))
        object.__setattr__(self, "risk_budget_bps", float(self.risk_budget_bps))
        object.__setattr__(self, "features", dict(self.features))

    @property
    def direction(self) -> float:
        return 1.0 if self.side == "long" else -1.0

    @property
    def created_at_datetime(self) -> datetime:
        return cast(datetime, self.created_at)

    @property
    def created_at_iso(self) -> str:
        return self.created_at_datetime.isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "engine_version": self.engine_version,
            "symbol": self.symbol,
            "side": self.side,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "created_at": self.created_at_iso,
            "intended_horizon_bars": self.intended_horizon_bars,
            "regime": self.regime,
            "evidence_tier": self.evidence_tier,
            "shadow_only": bool(self.shadow_only),
            "expected_edge_bps": self.expected_edge_bps,
            "confidence": self.confidence,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "risk_budget_bps": self.risk_budget_bps,
            "features": dict(self.features),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateSignal":
        return cls(
            signal_id=payload["signal_id"],
            strategy_id=payload["strategy_id"],
            engine_version=payload["engine_version"],
            symbol=payload["symbol"],
            side=payload["side"],
            timeframe=payload["timeframe"],
            created_at=payload.get("created_at"),
            intended_horizon_bars=payload["intended_horizon_bars"],
            regime=payload.get("regime", "unknown"),
            evidence_tier=payload.get("evidence_tier", 0),
            shadow_only=parse_bool(payload.get("shadow_only"), default=True),
            expected_edge_bps=payload.get("expected_edge_bps"),
            confidence=payload.get("confidence"),
            stop_price=payload.get("stop_price"),
            target_price=payload.get("target_price"),
            risk_budget_bps=payload.get("risk_budget_bps", 0.0),
            features=payload.get("features") or {},
        )
