"""Opening-Range-Breakout (ORB) strategy — stocks-in-play, onto the Strategy contract.

Phase 1 step 9 (BUILD, not extract: ORB had a scanner but was never a first-class
strategy). Wraps the unchanged `ORBScanner` (verbatim config) and emits the live
ORB ENTRY decision: signals whose breakout has TRIGGERED right now, with the
scanner's direction. live_routing:false (Rule A — untested; prove OOS at t>=2 via
the backtester + the dynamic in-play universe feed before any flip).

`now` for the opening-range window is read from the feature frames' latest bar
timestamp (contract convention: a FeatureFrame is as-of-now); no timestamp ⇒
stand down. Confidence uses ORB's natural conviction axis — relative-volume
intensity `min(rv_ratio/4, 1)` (the "_orb_tension" term of the live composite);
the full ML-blended composite is deferred to step 5b (and ORB's ML corr≈0.056 is
noise anyway, so the RV-intensity axis is the honest conviction signal).
"""
from __future__ import annotations

import pandas as pd

from backend.organism.orb_scanner import ORBScanner
from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy
from backend.organism.strategies.registry import register


@register("orb")
class ORBStrategy(Strategy):
    """Opening-range breakout on in-play (high relative-volume) names."""

    def __init__(self, config, scanner=None) -> None:
        super().__init__(config)
        c = config
        # 5c: an injected scanner shares STATE (orb cache, mark_fired cooldowns)
        # with the engine — mandatory when this strategy routes live, otherwise
        # duplicate instances double-fire. Default self-built for backtests.
        self._scanner = scanner if scanner is not None else ORBScanner(
            opening_minutes=int(c["opening_minutes"]),
            top_n=int(c["top_n"]),
            rv_lookback_days=int(c["rv_lookback_days"]),
            min_price=c["min_price"],
            min_rv_ratio=c["min_rv_ratio"],
            stop_atr_mult=c["stop_atr_mult"],
        )

    def required_features(self) -> set[str]:
        return {"open", "high", "low", "close", "volume"}

    def eligible_regimes(self) -> set[str]:
        return set(self.config.get("eligible_regimes", []))

    def validate_config(self) -> None:
        required = (
            "opening_minutes", "top_n", "rv_lookback_days", "min_price",
            "min_rv_ratio", "stop_atr_mult",
        )
        for k in required:
            if k not in self.config:
                raise ValueError(f"orb config missing {k!r}")
            if not isinstance(self.config[k], (int, float)):
                raise ValueError(f"orb config {k!r} must be numeric")

    @staticmethod
    def _now_from_features(features: FeatureFrame):
        latest = None
        for df in features.values():
            if df is None or len(df) == 0:
                continue
            ts = None
            if isinstance(df.index, pd.DatetimeIndex):
                ts = df.index[-1]
            elif "timestamp" in df.columns:
                try:
                    ts = pd.Timestamp(df["timestamp"].iloc[-1])
                except (TypeError, ValueError):
                    ts = None
            if ts is not None and (latest is None or ts > latest):
                latest = ts
        return latest

    @staticmethod
    def _confidence(rv_ratio: float) -> float:
        # ORB's natural conviction axis: relative-volume intensity (the live
        # _orb_tension term). Full ML composite deferred to 5b.
        return max(0.0, min(1.0, rv_ratio / 4.0))

    def scan(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        now = self._now_from_features(features)
        if now is None:
            return []
        data = {s: df for s, df in features.items() if df is not None and len(df) > 0}
        orb_cands = self._scanner.scan(data, now)

        out: list[Candidate] = []
        for oc in orb_cands:
            if not oc.breakout_triggered:   # only entries ready to fire NOW
                continue
            if oc.direction == 0.0:
                continue
            out.append(Candidate(
                symbol=oc.symbol,
                direction=oc.direction,
                confidence=self._confidence(oc.rv_ratio),
                strategy_name=self.name,
                extra={
                    "regime": regime, "rv_ratio": oc.rv_ratio,
                    "orb_high": oc.orb_high, "orb_low": oc.orb_low,
                    "suggested_stop": oc.suggested_stop,
                    "atr_at_entry": oc.atr_at_entry,
                    # 5c: raw scanner candidate so the engine adapter can
                    # replicate the inline cand_dict field-for-field.
                    "raw": oc,
                },
            ))
        return out
