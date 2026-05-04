"""Mean-Reversion Scanner — intraday extreme-fade strategy.

Premise: in a universe of always-liquid leaders (SPY, QQQ, large-cap stocks,
sector ETFs), large intraday displacements from session VWAP without a fresh
fundamental catalyst tend to mean-revert. This is a structural property of
liquid markets driven by dealer/MM fading + ubiquitous mean-reversion HFT.

Signal:
  When current_price has displaced more than N × ATR from session VWAP,
  fire a candidate in the OPPOSITE direction (revert toward VWAP). Target a
  partial retracement to VWAP; stop on continued displacement.

Why this is independent edge from the predict-and-trade engine (alpha+breakout):
  - Doesn't require predicting next-bar direction (which our ML can't reliably do)
  - Bets on a measurable statistical regularity (mean reversion in liquid names)
  - Asymmetric R:R is structural (target distance > stop distance by design)
  - Universe of always-liquid leaders is the right shape for this strategy
    (deep books, narrow spreads, no anomalous-spike requirement)

Initial deployment: SHADOW MODE only (this module produces candidates and logs
them; no live wiring in this commit). Promote via ORGANISM_MEAN_REVERSION_LIVE_ENABLED
after 5+ shadow sessions show ≥3 candidates/day with simulated PnL > current alpha.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Strategy constants (Cliff-Asness / classic intraday-MR style; tunable) ──

DEFAULT_ENTRY_HOUR_ET = 9
DEFAULT_ENTRY_MIN_ET = 45        # let opening volatility settle (skip 9:30-9:45)
DEFAULT_NO_NEW_HOUR_ET = 15
DEFAULT_NO_NEW_MIN_ET = 30       # don't enter inside the EOD-flatten approach
# Default tightened from 1.5 → 4.0 based on Day-1 production data: shadow
# avg displacement was 5.46 ATR (skewed higher than replay's 2.5–4 range).
# 4.0 ATR cuts shadow volume ~60% while keeping the strongest signals.
DEFAULT_MIN_DISPLACEMENT_ATR = 4.0
# Default raised from 0.65 → 0.8 to match the env-default in live_engine.py
# (set via ORGANISM_MR_TARGET_RETRACEMENT, replay-validated). Audit-B
# finding 17 (2026-05-01): the mismatch was a calibration land-mine for
# tests/replay code that bypassed live_engine's construction path.
DEFAULT_TARGET_RETRACEMENT = 0.8    # exit at 80% retracement to VWAP
# Default raised from 0.5 → 1.0 (replay: best config used 1.0×ATR stop;
# 0.5 was getting noise-stopped on 1-min bars too easily).
DEFAULT_STOP_EXTENSION_ATR = 1.0
# Day-1 production showed R:R values up to 1,021 — micro-stop edge case
# when ATR is microscopic on low-vol low-priced names (SH/PSQ at $20-30).
# Floor stop_distance at 5 bps (0.05%) of price to keep R:R math sane.
DEFAULT_MIN_STOP_BPS = 5.0
DEFAULT_COOLDOWN_MINUTES = 60       # don't re-fire same symbol within 60 min
DEFAULT_MIN_PRICE = 5.0
DEFAULT_MIN_VWAP_BARS = 10           # need at least 10 bars for stable VWAP
DEFAULT_TOP_N = 5
DEFAULT_LONG_ONLY = True             # only fire oversold (price < VWAP) by default


@dataclass
class MeanReversionCandidate:
    """One mean-reversion entry candidate."""
    symbol: str
    direction: float              # +1.0 long (oversold), -1.0 short (overbought)
    current_price: float
    vwap: float
    distance_atr: float           # signed: positive = above VWAP, negative = below
    abs_distance_atr: float       # |distance_atr| — the signal-strength scalar
    target_price: float           # exit target (toward VWAP)
    stop_price: float             # invalidation (continued displacement)
    expected_r_r: float           # (target-entry) / (entry-stop)
    atr_at_entry: float
    session_high: float
    session_low: float
    n_bars_in_session: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "current_price": round(self.current_price, 4),
            "vwap": round(self.vwap, 4),
            "distance_atr": round(self.distance_atr, 3),
            "abs_distance_atr": round(self.abs_distance_atr, 3),
            "target_price": round(self.target_price, 4),
            "stop_price": round(self.stop_price, 4),
            "expected_r_r": round(self.expected_r_r, 3),
            "atr_at_entry": round(self.atr_at_entry, 4),
            "session_high": round(self.session_high, 4),
            "session_low": round(self.session_low, 4),
            "n_bars_in_session": self.n_bars_in_session,
            "timestamp": self.timestamp,
        }


class MeanReversionScanner:
    """Scan for intraday mean-reversion candidates against session VWAP.

    Stateful across ticks within a session: tracks per-symbol cooldown so the
    same symbol doesn't refire within `cooldown_minutes`.

    Resets on session-date change.
    """

    def __init__(
        self,
        entry_hour_et: int = DEFAULT_ENTRY_HOUR_ET,
        entry_min_et: int = DEFAULT_ENTRY_MIN_ET,
        no_new_hour_et: int = DEFAULT_NO_NEW_HOUR_ET,
        no_new_min_et: int = DEFAULT_NO_NEW_MIN_ET,
        min_displacement_atr: float = DEFAULT_MIN_DISPLACEMENT_ATR,
        target_retracement: float = DEFAULT_TARGET_RETRACEMENT,
        stop_extension_atr: float = DEFAULT_STOP_EXTENSION_ATR,
        min_stop_bps: float = DEFAULT_MIN_STOP_BPS,
        cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
        min_price: float = DEFAULT_MIN_PRICE,
        min_vwap_bars: int = DEFAULT_MIN_VWAP_BARS,
        top_n: int = DEFAULT_TOP_N,
        long_only: bool = DEFAULT_LONG_ONLY,
    ) -> None:
        self.entry_hour_et = entry_hour_et
        self.entry_min_et = entry_min_et
        self.no_new_hour_et = no_new_hour_et
        self.no_new_min_et = no_new_min_et
        self.min_displacement_atr = min_displacement_atr
        self.target_retracement = target_retracement
        self.stop_extension_atr = stop_extension_atr
        self.min_stop_bps = min_stop_bps
        self.cooldown_minutes = cooldown_minutes
        self.min_price = min_price
        self.min_vwap_bars = min_vwap_bars
        self.top_n = top_n
        self.long_only = long_only

        # symbol -> last-fire timestamp (UTC pd.Timestamp)
        self._fired_recently: dict[str, pd.Timestamp] = {}
        self._current_session_date: Optional[str] = None

    # ── Time helpers ───────────────────────────────────────────────

    def _is_in_entry_window(self, et_time: dtime) -> bool:
        entry = dtime(self.entry_hour_et, self.entry_min_et)
        cutoff = dtime(self.no_new_hour_et, self.no_new_min_et)
        return entry <= et_time < cutoff

    @staticmethod
    def _et_time(now_dt: pd.Timestamp) -> dtime:
        if now_dt.tzinfo is None:
            now_dt = now_dt.tz_localize("UTC")
        try:
            et = now_dt.tz_convert("America/New_York")
            return et.time()
        except Exception:
            return (now_dt - pd.Timedelta(hours=4)).time()

    def _reset_for_new_session(self, session_date: str) -> None:
        self._fired_recently.clear()
        self._current_session_date = session_date
        logger.info("MeanReversion scanner reset for session %s", session_date)

    def _is_in_cooldown(self, symbol: str, now_ts: pd.Timestamp) -> bool:
        last = self._fired_recently.get(symbol)
        if last is None:
            return False
        try:
            delta_seconds = (now_ts - last).total_seconds()
        except Exception:
            return False
        return delta_seconds < self.cooldown_minutes * 60

    # ── Math helpers ───────────────────────────────────────────────

    @staticmethod
    def _compute_session_vwap(
        df: pd.DataFrame, ts_et: pd.Series
    ) -> Optional[tuple[float, int, float, float]]:
        """Compute session-anchored VWAP from today's bars.

        Returns (vwap, n_today_bars, session_high, session_low) or None if
        insufficient data.
        """
        if df is None or len(df) < 2:
            return None
        for col in ("high", "low", "close", "volume"):
            if col not in df.columns:
                return None

        try:
            last_date = ts_et.iloc[-1].date()
        except Exception:
            return None
        try:
            dates = ts_et.dt.date
        except Exception:
            return None
        today_mask = (dates == last_date).values
        if not today_mask.any():
            return None

        today = df[today_mask]
        if len(today) < 1:
            return None

        hi = today["high"].astype(float).values
        lo = today["low"].astype(float).values
        cl = today["close"].astype(float).values
        vol = today["volume"].astype(float).values

        if not np.all(np.isfinite(hi)) or not np.all(np.isfinite(lo)):
            return None
        if not np.all(np.isfinite(cl)) or not np.all(np.isfinite(vol)):
            return None

        total_vol = float(vol.sum())
        if total_vol <= 0:
            return None

        typical = (hi + lo + cl) / 3.0
        vwap = float((typical * vol).sum() / total_vol)
        if not np.isfinite(vwap) or vwap <= 0:
            return None

        return vwap, int(len(today)), float(hi.max()), float(lo.min())

    @staticmethod
    def _extract_atr(df: pd.DataFrame, current_price: float) -> float:
        """Return ATR in price units. Mirrors EOD scanner: handles both
        normalized (atr/close in [0,1]) and absolute (price-units) forms."""
        if df is None or "atr_14" not in df.columns:
            return 0.0
        try:
            atr_v = float(df["atr_14"].iloc[-1])
            if not np.isfinite(atr_v):
                return 0.0
            if 0 < atr_v < 1.0:
                return atr_v * current_price
            return atr_v
        except Exception:
            return 0.0

    @staticmethod
    def _extract_ts_et(df: pd.DataFrame) -> Optional[pd.Series]:
        if "timestamp" in df.columns:
            ts_raw = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        elif df.index.dtype.kind == "M":
            ts_raw = pd.to_datetime(pd.Series(df.index), utc=True)
        else:
            return None
        if ts_raw.isna().all():
            return None
        try:
            return pd.Series(ts_raw).dt.tz_convert("America/New_York")
        except Exception:
            return None

    # ── Main scan ──────────────────────────────────────────────────

    def scan(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        now_dt: Any,
        session_date: Optional[str] = None,
    ) -> list[MeanReversionCandidate]:
        """Run the mean-reversion scanner.

        Returns candidates ranked by absolute displacement (strongest first),
        capped at `top_n`. Empty list if outside entry window.
        """
        ts = pd.Timestamp(now_dt) if not isinstance(now_dt, pd.Timestamp) else now_dt
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        if session_date is None:
            session_date = ts.strftime("%Y-%m-%d")

        if self._current_session_date != session_date:
            self._reset_for_new_session(session_date)

        et = self._et_time(ts)
        if not self._is_in_entry_window(et):
            return []

        candidates: list[MeanReversionCandidate] = []

        for symbol, df in features_by_symbol.items():
            if self._is_in_cooldown(symbol, ts):
                continue
            if df is None or len(df) < self.min_vwap_bars:
                continue

            ts_et = self._extract_ts_et(df)
            if ts_et is None:
                continue

            vwap_data = self._compute_session_vwap(df, ts_et)
            if vwap_data is None:
                continue
            vwap, n_bars, session_high, session_low = vwap_data
            if n_bars < self.min_vwap_bars:
                continue

            try:
                current_price = float(df["close"].iloc[-1])
            except Exception:
                continue
            if not np.isfinite(current_price) or current_price < self.min_price:
                continue

            atr = self._extract_atr(df, current_price)
            if atr <= 0:
                continue

            displacement = current_price - vwap
            distance_atr = displacement / atr
            abs_distance_atr = abs(distance_atr)

            if abs_distance_atr < self.min_displacement_atr:
                continue

            # Direction: revert toward VWAP.
            # price > vwap → overbought → SHORT (direction = -1)
            # price < vwap → oversold   → LONG  (direction = +1)
            direction = -1.0 if displacement > 0 else 1.0
            if self.long_only and direction < 0:
                continue

            abs_displacement = abs(displacement)
            target_price = current_price + direction * (
                self.target_retracement * abs_displacement
            )
            # Floor the stop distance at min_stop_bps × price / 10000.
            # Prevents pathological R:R when ATR is microscopic on low-vol
            # low-priced names (Day-1 prod showed R:R up to 1,021 from
            # micro-ATR cases).
            atr_stop_distance = self.stop_extension_atr * atr
            min_stop_distance = self.min_stop_bps * current_price / 10000.0
            actual_stop_distance = max(atr_stop_distance, min_stop_distance)
            stop_price = current_price - direction * actual_stop_distance

            target_distance = abs(target_price - current_price)
            stop_distance = abs(current_price - stop_price)
            expected_r_r = (
                target_distance / stop_distance if stop_distance > 0 else 0.0
            )

            cand = MeanReversionCandidate(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                vwap=vwap,
                distance_atr=distance_atr,
                abs_distance_atr=abs_distance_atr,
                target_price=target_price,
                stop_price=stop_price,
                expected_r_r=expected_r_r,
                atr_at_entry=atr,
                session_high=session_high,
                session_low=session_low,
                n_bars_in_session=n_bars,
                timestamp=ts.isoformat(),
            )
            candidates.append(cand)

        candidates.sort(key=lambda c: c.abs_distance_atr, reverse=True)
        return candidates[: self.top_n]

    def mark_fired(self, symbol: str, now_ts: Any) -> None:
        ts = pd.Timestamp(now_ts) if not isinstance(now_ts, pd.Timestamp) else now_ts
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        self._fired_recently[symbol] = ts

    def reset(self) -> None:
        self._fired_recently.clear()
        self._current_session_date = None
