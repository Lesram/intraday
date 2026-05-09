"""Candidate-filter shadow telemetry helpers.

Records candidate slices that Phase 3 wants to watch before any no-entry gate
is promoted. This module is observability-only; it does not decide, size, or
submit trades.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.organism.regime import is_inverse_etf
from backend.organism.schema.candidate_signal import infer_strategy_id


ALPHA_BREAKOUT_WATCH_REGIMES = frozenset({"chop", "trending_down"})


def _finite_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def infer_entry_source(candidate: dict[str, Any]) -> str:
    override = str(candidate.get("entry_source_override") or "").strip()
    if override:
        return override
    breakout_score = _finite_float(candidate.get("breakout_score"))
    predicted_return = abs(_finite_float(candidate.get("predicted_return")))
    if breakout_score >= 0.55 and predicted_return < 0.003:
        return "breakout"
    if breakout_score >= 0.4:
        return "alpha+breakout"
    return "alpha"


def candidate_filter_tags(candidate: dict[str, Any], regime: str) -> list[str]:
    symbol = str(candidate.get("symbol") or "").upper()
    regime_label = str(regime)
    confidence = _finite_float(candidate.get("confidence"))
    entry_source = infer_entry_source(candidate)
    tags: list[str] = []
    if 0.45 <= confidence < 0.55:
        tags.append("conf_45_55")
    if 0.55 <= confidence < 0.65:
        tags.append("conf_55_65")
    if entry_source == "alpha+breakout":
        if regime_label == "chop":
            tags.append("alpha_breakout_chop")
        if regime_label == "trending_down":
            tags.append("alpha_breakout_trending_down")
        if regime_label in ALPHA_BREAKOUT_WATCH_REGIMES:
            tags.append("alpha_breakout_chop_or_trending_down")
        if is_inverse_etf(symbol):
            tags.append("inverse_etf_alpha_breakout")
            if regime_label == "trending_down":
                tags.append("inverse_etf_alpha_breakout_trending_down")
            if regime_label in ALPHA_BREAKOUT_WATCH_REGIMES:
                tags.append("inverse_etf_alpha_breakout_chop_or_trending_down")
    return tags


@dataclass(frozen=True)
class CandidateShadowEvent:
    tick: int
    timestamp: str
    symbol: str
    regime: str
    direction: float
    confidence: float
    effective_confidence: float
    breakout_score: float
    predicted_return: float
    ranking_score: float
    entry_source: str
    strategy_id: str
    matched_filters: list[str]
    live_pipeline_candidate: bool = True
    defensive_filter_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        row = {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "regime": self.regime,
            "direction": round(self.direction, 4),
            "confidence": round(self.confidence, 4),
            "effective_confidence": round(self.effective_confidence, 4),
            "breakout_score": round(self.breakout_score, 4),
            "predicted_return": round(self.predicted_return, 6),
            "ranking_score": round(self.ranking_score, 6),
            "entry_source": self.entry_source,
            "strategy_id": self.strategy_id,
            "matched_filters": list(self.matched_filters),
            "live_pipeline_candidate": self.live_pipeline_candidate,
        }
        if self.defensive_filter_reason:
            row["defensive_filter_reason"] = self.defensive_filter_reason
        return row


def build_candidate_shadow_events(
    candidates: Iterable[dict[str, Any]],
    *,
    regime: str,
    tick: int,
    timestamp: str,
    record_all_candidates: bool = False,
) -> list[CandidateShadowEvent]:
    events: list[CandidateShadowEvent] = []
    for candidate in candidates:
        tags = candidate_filter_tags(candidate, regime)
        if not tags and not record_all_candidates:
            continue
        entry_source = infer_entry_source(candidate)
        events.append(
            CandidateShadowEvent(
                tick=int(tick),
                timestamp=str(timestamp),
                symbol=str(candidate.get("symbol") or ""),
                regime=str(regime),
                direction=_finite_float(candidate.get("direction")),
                confidence=_finite_float(candidate.get("confidence")),
                effective_confidence=_finite_float(
                    candidate.get("effective_confidence"),
                    _finite_float(candidate.get("confidence")),
                ),
                breakout_score=_finite_float(candidate.get("breakout_score")),
                predicted_return=_finite_float(candidate.get("predicted_return")),
                ranking_score=_finite_float(candidate.get("ranking_score")),
                entry_source=entry_source,
                strategy_id=infer_strategy_id(
                    entry_source,
                    candidate.get("strategy_id", ""),
                ),
                matched_filters=tags,
                live_pipeline_candidate=bool(
                    candidate.get("live_pipeline_candidate", True)
                ),
                defensive_filter_reason=str(
                    candidate.get("defensive_filter_reason") or ""
                ),
            )
        )
    return events


class CandidateShadowTelemetryRecorder:
    """Append-only JSONL writer for candidate shadow evidence events."""

    def __init__(
        self,
        path: str | Path,
        *,
        record_all_candidates: bool = False,
    ) -> None:
        self.path = Path(path)
        self.record_all_candidates = record_all_candidates

    def record_candidates(
        self,
        candidates: Iterable[dict[str, Any]],
        *,
        regime: str,
        tick: int,
        timestamp: str,
    ) -> int:
        events = build_candidate_shadow_events(
            candidates,
            regime=regime,
            tick=tick,
            timestamp=timestamp,
            record_all_candidates=self.record_all_candidates,
        )
        if not events:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            for event in events:
                fh.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
        return len(events)
