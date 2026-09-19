"""Breakout strategy — the live pure-breakout book, onto the Strategy contract.

Phase 1 step 6 decision: KEEP DISTINCT (not folded into momentum). Breakout is a
separate multi-factor generator (squeeze / volume / contraction / relative-
strength / pivot / institutional-flow) that independently flags symbols momentum's
_observable_direction never does. So it becomes its own Strategy.

Faithful extraction (thin-seam discipline, same as momentum step 5): this adapter
wraps the existing, unchanged `BreakoutScanner` — the single source of the
composite — and reproduces only the live ENTRY decision: the pure-breakout path
(`live_engine` ~4302-4371) takes scanner signals with `composite >= 0.55`, forces
LONG (`direction=1.0`), and routes them. Selector-level concerns (dedup vs the
momentum candidates, the per-tick cap of 2, ranking interplay) are NOT the
strategy's job — they belong to the selector/engine routing step (deferred,
named in docs/architecture/intra_2.0_phase1.md). Confidence ownership for live
sizing is likewise deferred (step 5b); here `confidence = min(composite, 1.0)`
mirrors the live `_bo_conf` exactly, but is not yet wired to Kelly.
"""
from __future__ import annotations

from backend.organism.breakout_scanner import BreakoutScanner
from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy
from backend.organism.strategies.registry import register


@register("breakout")
class BreakoutStrategy(Strategy):
    """Live pure-breakout book. Long entries on high-composite breakout signals."""

    def __init__(self, config, scanner=None) -> None:
        super().__init__(config)
        # 5c: injected scanner = the engine's own instance (exactness by
        # identity, not by config replication). Default: build VERBATIM from
        # the config block so it matches the live scanner bit-for-bit.
        if scanner is not None:
            self._scanner = scanner
            return
        c = config
        scanner = BreakoutScanner(top_n=int(c["top_n"]))
        scanner.W_SQUEEZE = c["w_squeeze"]
        scanner.W_VOLUME = c["w_volume"]
        scanner.W_CONTRACTION = c["w_contraction"]
        scanner.W_RS = c["w_rs"]
        scanner.W_PIVOT = c["w_pivot"]
        scanner.W_FLOW = c["w_flow"]
        scanner.MIN_BREAKOUT_SCORE = c["min_breakout_score"]
        scanner.BB_PERIOD = int(c["bb_period"])
        scanner.ATR_SHORT = int(c["atr_short"])
        scanner.ATR_LONG = int(c["atr_long"])
        scanner.VOL_AVG_PERIOD = int(c["vol_avg_period"])
        self._scanner = scanner

    def required_features(self) -> set[str]:
        # The scanner computes its indicators from raw OHLCV bars.
        return {"open", "high", "low", "close", "volume"}

    def eligible_regimes(self) -> set[str]:
        return set(self.config.get("eligible_regimes", []))

    def validate_config(self) -> None:
        required = (
            "top_n", "w_squeeze", "w_volume", "w_contraction", "w_rs", "w_pivot",
            "w_flow", "min_breakout_score", "bb_period", "atr_short", "atr_long",
            "vol_avg_period", "entry_composite_threshold", "max_pure_breakout",
        )
        for k in required:
            if k not in self.config:
                raise ValueError(f"breakout config missing {k!r}")
            if not isinstance(self.config[k], (int, float)):
                raise ValueError(f"breakout config {k!r} must be numeric")

    def scan(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        threshold = self.config["entry_composite_threshold"]
        long_only = bool(self.config.get("long_only", True))
        data = {s: df for s, df in features.items() if df is not None and len(df) > 0}
        spy = features.get("SPY")
        signals = self._scanner.scan(data, spy)

        out: list[Candidate] = []
        for sig in signals:
            if sig.composite_score < threshold:
                continue
            # Live entry path forces LONG regardless of the scanner's direction.
            direction = 1.0 if long_only else sig.direction
            if direction == 0.0:
                continue
            out.append(Candidate(
                symbol=sig.symbol,
                direction=direction,
                confidence=max(0.0, min(1.0, sig.composite_score)),
                strategy_name=self.name,
                extra={"regime": regime, "composite_score": sig.composite_score,
                       # 5c: raw signal for the engine adapter.
                       "raw": sig},
            ))
        return out
