"""Mean-reversion strategy — VWAP-displacement fade, onto the Strategy contract.

Phase 1 step 7. Mean-reversion is REGISTERED but `live_routing:false` (Rule A):
it is evidence-NEGATIVE after costs (gross bounce ~1.7-2.2bps < ~4bps round-trip
cost; net-negative in every sweep, residual variant included). It exists as a
backtest/shadow BENCHMARK only — the step-8 OOS bar (net exp>0 at t>=2, costed)
plus a human flip is what would ever route it.

Because it never routes capital, there is no live-parity obligation here (unlike
momentum step 5 / breakout step 6). This adapter wraps the unchanged
`MeanReversionScanner` (configured verbatim) so the backtester measures the REAL
MR signal. Confidence mirrors the live MR composite exactly
(min(1, 0.30 + 0.15*abs_distance_atr), live_engine ~4770) so a future router and
the backtester score it on the same axis.

`now` for the time-of-day entry window + causal VWAP is read from the feature
frames' latest bar timestamp (contract convention: a FeatureFrame is as-of-now).
If frames carry no timestamp, the strategy stands down (can't place the window).
"""
from __future__ import annotations

import pandas as pd

from backend.organism.mean_reversion_scanner import MeanReversionScanner
from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy
from backend.organism.strategies.registry import register


@register("mean_reversion")
class MeanReversionStrategy(Strategy):
    """VWAP-displacement fade. Benchmark only (live_routing:false)."""

    def __init__(self, config, scanner=None) -> None:
        super().__init__(config)
        c = config
        # 5c: injected scanner shares mark_fired/cooldown state with the engine
        # (mandatory for live routing); default self-built for backtests.
        if scanner is not None:
            self._scanner = scanner
            return
        self._scanner = MeanReversionScanner(
            entry_hour_et=int(c["entry_hour_et"]), entry_min_et=int(c["entry_min_et"]),
            no_new_hour_et=int(c["no_new_hour_et"]), no_new_min_et=int(c["no_new_min_et"]),
            min_displacement_atr=c["min_displacement_atr"],
            target_retracement=c["target_retracement"],
            stop_extension_atr=c["stop_extension_atr"],
            min_stop_bps=c["min_stop_bps"],
            cooldown_minutes=int(c["cooldown_minutes"]),
            min_price=c["min_price"],
            min_vwap_bars=int(c["min_vwap_bars"]),
            top_n=int(c["top_n"]),
            long_only=bool(c["long_only"]),
        )

    def required_features(self) -> set[str]:
        return {"open", "high", "low", "close", "volume"}

    def eligible_regimes(self) -> set[str]:
        return set(self.config.get("eligible_regimes", []))

    def validate_config(self) -> None:
        required = (
            "min_displacement_atr", "target_retracement", "stop_extension_atr",
            "min_stop_bps", "min_price", "cooldown_minutes", "top_n",
            "min_vwap_bars", "entry_hour_et", "entry_min_et", "no_new_hour_et",
            "no_new_min_et",
        )
        for k in required:
            if k not in self.config:
                raise ValueError(f"mean_reversion config missing {k!r}")
            if not isinstance(self.config[k], (int, float)):
                raise ValueError(f"mean_reversion config {k!r} must be numeric")

    @staticmethod
    def _now_from_features(features: FeatureFrame):
        """Latest bar timestamp across the frames, or None if untimestamped."""
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
    def _confidence(abs_distance_atr: float) -> float:
        # Faithful to the live MR composite (live_engine ~4770): distance-only,
        # no ML (MR is a statistical signal, not a directional prediction).
        return min(1.0, 0.30 + 0.15 * abs_distance_atr)

    def scan(self, features: FeatureFrame, regime: str) -> list[Candidate]:
        now = self._now_from_features(features)
        if now is None:
            return []  # no timestamp -> can't place the entry window -> stand down
        data = {s: df for s, df in features.items() if df is not None and len(df) > 0}
        mr_cands = self._scanner.scan(data, now)

        out: list[Candidate] = []
        for mrc in mr_cands:
            out.append(Candidate(
                symbol=mrc.symbol,
                direction=mrc.direction,
                confidence=self._confidence(mrc.abs_distance_atr),
                strategy_name=self.name,
                extra={
                    "regime": regime,
                    "vwap": mrc.vwap,
                    "distance_atr": mrc.distance_atr,
                    "abs_distance_atr": mrc.abs_distance_atr,
                    "target_price": mrc.target_price,
                    "stop_price": mrc.stop_price,
                    "expected_r_r": mrc.expected_r_r,
                    "atr_at_entry": mrc.atr_at_entry,
                    # 5c: raw scanner candidate for the engine adapter.
                    "raw": mrc,
                },
            ))
        return out
