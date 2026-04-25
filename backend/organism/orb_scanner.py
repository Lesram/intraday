"""ORB Stocks-in-Play Scanner.

Implements the Opening Range Breakout strategy from
Zarattini, Barbon, Aziz (2024) "A Profitable Day Trading Strategy For
The U.S. Equity Market" (SSRN 4729284).

Strategy in 5 lines:
1. After the first 5-min bar of regular trading hours (9:35 ET):
2. Compute relative volume (RV) = today's first 5-min vol / avg prior 14d's first 5-min vol
3. Rank symbols by RV; take top N "stocks in play"
4. Direction: long if first 5-min bar closed UP from open; short if DOWN
5. Entry trigger: price breaks above ORB high (long) or below ORB low (short) any time after 9:35 ET

This module is the *scanner* — it produces ORBCandidate objects that the live engine
can route through the same composite/Kelly/sizing pipeline as alpha+breakout candidates.

Initial deployment: SHADOW MODE. Scanner runs and logs candidates; no entries fire.
After 5 sessions of shadow data, decide whether to promote to live entry path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time as dtime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Strategy constants (paper defaults; tunable via constructor) ────

DEFAULT_OPENING_MINUTES = 5    # ORB window length
DEFAULT_TOP_N = 10             # number of stocks-in-play candidates
DEFAULT_RV_LOOKBACK_DAYS = 14  # historical days for RV baseline
DEFAULT_MIN_PRICE = 5.0        # paper: > $5/share
DEFAULT_MIN_RV_RATIO = 1.5     # require at least 1.5× normal volume
DEFAULT_STOP_ATR_MULT = 1.0    # paper: 1× ATR stop


# US Eastern: 9:30-9:35 = ORB window; entries allowed 9:35-15:55 ET
RTH_OPEN_HOUR_ET = 9
RTH_OPEN_MIN_ET = 30
ORB_DECISION_HOUR_ET = 9
ORB_DECISION_MIN_ET = 35
NO_NEW_ENTRY_HOUR_ET = 15
NO_NEW_ENTRY_MIN_ET = 55


@dataclass
class ORBCandidate:
    """One ORB Stocks-in-Play candidate for an entry decision."""
    symbol: str
    direction: float                 # +1.0 long, -1.0 short
    rv_ratio: float                  # relative volume vs prior 14d
    orb_high: float                  # high of opening 5-min range
    orb_low: float                   # low of opening 5-min range
    orb_close: float                 # close of 5-min ORB candle
    orb_open: float                  # open of 5-min ORB candle
    current_price: float
    breakout_triggered: bool         # True if current_price has broken ORB level
    suggested_stop: float            # ORB-anchored stop price
    atr_at_entry: float
    timestamp: str                   # ISO-8601 of decision time

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "rv_ratio": round(self.rv_ratio, 3),
            "orb_high": round(self.orb_high, 4),
            "orb_low": round(self.orb_low, 4),
            "orb_close": round(self.orb_close, 4),
            "orb_open": round(self.orb_open, 4),
            "current_price": round(self.current_price, 4),
            "breakout_triggered": self.breakout_triggered,
            "suggested_stop": round(self.suggested_stop, 4),
            "atr_at_entry": round(self.atr_at_entry, 4),
            "timestamp": self.timestamp,
        }


class ORBScanner:
    """Scanner for ORB Stocks-in-Play candidates.

    Stateful across ticks within a session: caches the per-symbol opening range
    once detected, doesn't recompute every tick.

    Resets daily — at the start of each session, all cached ORB ranges are
    invalidated and recomputed when the first post-9:30 bar arrives.
    """

    def __init__(
        self,
        opening_minutes: int = DEFAULT_OPENING_MINUTES,
        top_n: int = DEFAULT_TOP_N,
        rv_lookback_days: int = DEFAULT_RV_LOOKBACK_DAYS,
        min_price: float = DEFAULT_MIN_PRICE,
        min_rv_ratio: float = DEFAULT_MIN_RV_RATIO,
        stop_atr_mult: float = DEFAULT_STOP_ATR_MULT,
    ) -> None:
        self.opening_minutes = opening_minutes
        self.top_n = top_n
        self.rv_lookback_days = rv_lookback_days
        self.min_price = min_price
        self.min_rv_ratio = min_rv_ratio
        self.stop_atr_mult = stop_atr_mult

        # Per-session state (reset daily)
        # symbol -> dict with orb_high, orb_low, orb_open, orb_close, rv_ratio,
        #          atr_at_entry, computed_for_date
        self._orb_cache: dict[str, dict[str, float]] = {}
        # Date string of currently-cached session (YYYY-MM-DD)
        self._current_session_date: Optional[str] = None
        # Symbols that fired entries this session — don't re-fire
        self._fired_today: set[str] = set()

    def _reset_for_new_session(self, session_date: str) -> None:
        """Clear cached state at start of a new session."""
        self._orb_cache.clear()
        self._fired_today.clear()
        self._current_session_date = session_date
        logger.info("ORB scanner reset for session %s", session_date)

    @staticmethod
    def _is_in_orb_window(now_et: dtime) -> bool:
        """True iff time is within the 9:30-9:35 ET ORB window."""
        return (
            now_et >= dtime(RTH_OPEN_HOUR_ET, RTH_OPEN_MIN_ET)
            and now_et < dtime(ORB_DECISION_HOUR_ET, ORB_DECISION_MIN_ET)
        )

    @staticmethod
    def _is_after_orb_decision(now_et: dtime) -> bool:
        """True iff time is past the 9:35 ET decision point and before EOD entry block."""
        return (
            now_et >= dtime(ORB_DECISION_HOUR_ET, ORB_DECISION_MIN_ET)
            and now_et < dtime(NO_NEW_ENTRY_HOUR_ET, NO_NEW_ENTRY_MIN_ET)
        )

    @staticmethod
    def _et_time(now_dt: pd.Timestamp) -> dtime:
        """Convert a UTC timestamp to an ET dtime. Approximation for replay use:
        we don't track DST precisely; use UTC-4 (EDT) as a reasonable default
        for backtests covering most of the trading year. For LIVE use, the
        timestamps come from the live engine's clock which is ET-aware."""
        if now_dt.tzinfo is None:
            now_dt = now_dt.tz_localize("UTC")
        # Approximate ET as UTC-4 (EDT). Live engine handles DST properly via
        # Python datetime; this is a best-effort approximation for replay.
        et = now_dt.tz_convert("America/New_York") if hasattr(
            now_dt, "tz_convert"
        ) else now_dt - pd.Timedelta(hours=4)
        if hasattr(et, "time"):
            return et.time()
        return dtime(0, 0)

    def _compute_orb_range(
        self,
        symbol: str,
        df: pd.DataFrame,
        atr_at_entry: float,
    ) -> Optional[dict[str, float]]:
        """Compute the 5-min opening range from a feature DataFrame.

        df is expected to have at least the bars from market open today.
        Look at the FIRST `opening_minutes` bars of today's session.
        """
        if df is None or len(df) < self.opening_minutes:
            return None
        if "close" not in df.columns or "high" not in df.columns:
            return None

        # Take the most-recent 5 bars as the ORB. This assumes the live engine
        # calls scan() right at the 9:35 decision point, when the last 5 bars
        # ARE the opening range. For mid-session calls we'd need timestamp-based
        # filtering.
        orb_bars = df.iloc[-self.opening_minutes:]
        try:
            orb_high = float(orb_bars["high"].max())
            orb_low = float(orb_bars["low"].min())
            orb_open = float(orb_bars["open"].iloc[0]) if "open" in orb_bars.columns else float(orb_bars["close"].iloc[0])
            orb_close = float(orb_bars["close"].iloc[-1])
            orb_volume = float(orb_bars["volume"].sum()) if "volume" in orb_bars.columns else 0.0

            # Sanity checks
            if not all(
                np.isfinite(v) for v in (orb_high, orb_low, orb_open, orb_close)
            ):
                return None
            if orb_high <= orb_low:
                return None
            if orb_close < self.min_price:
                return None

            return {
                "orb_high": orb_high,
                "orb_low": orb_low,
                "orb_open": orb_open,
                "orb_close": orb_close,
                "orb_volume": orb_volume,
                "atr_at_entry": atr_at_entry,
            }
        except Exception as e:
            logger.debug("ORB compute failed for %s: %s", symbol, e)
            return None

    def _compute_relative_volume(
        self,
        df: pd.DataFrame,
        today_first_5min_volume: float,
    ) -> float:
        """Approximate relative volume ratio.

        Ideally: today's first-5-min volume / avg of prior 14 days' first-5-min volume.

        Approximation when full daily history isn't structured for that lookup:
        use a rolling-window proxy on bar volume around the ORB period.
        """
        if df is None or "volume" not in df.columns or len(df) < 50:
            return 1.0  # neutral default
        try:
            # Proxy: ratio of today's first-5-min volume to the median of any
            # prior 5-bar windows in the available history. This isn't the
            # paper's exact RV ratio but tracks the same intuition.
            volume = df["volume"].values
            if len(volume) < self.opening_minutes + 10:
                return 1.0
            # Rolling 5-bar volume sums across history
            rolling_5 = pd.Series(volume).rolling(self.opening_minutes).sum().dropna()
            # Exclude the most-recent (today's) value to avoid using today's number as denominator
            historical = rolling_5.iloc[:-1] if len(rolling_5) > 1 else rolling_5
            if len(historical) < 10:
                return 1.0
            baseline = float(historical.median())
            if baseline <= 0:
                return 1.0
            return today_first_5min_volume / baseline
        except Exception:
            return 1.0

    def scan(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        now_dt: Any,
        session_date: Optional[str] = None,
        atr_by_symbol: Optional[dict[str, float]] = None,
    ) -> list[ORBCandidate]:
        """Run the ORB scanner.

        Returns:
            List of ORBCandidate objects with breakout_triggered=True for entries
            that should fire RIGHT NOW. Candidates with breakout_triggered=False
            are tracked but not yet ready to enter.

        The caller (live_engine) decides whether to ACT on these or only LOG them
        (shadow mode).
        """
        # Determine session date
        ts = pd.Timestamp(now_dt) if not isinstance(now_dt, pd.Timestamp) else now_dt
        if session_date is None:
            session_date = ts.strftime("%Y-%m-%d")

        # Reset state at session boundary
        if self._current_session_date != session_date:
            self._reset_for_new_session(session_date)

        # Time-window gating
        et = self._et_time(ts)
        in_orb_window = self._is_in_orb_window(et)
        after_orb_decision = self._is_after_orb_decision(et)

        if not (in_orb_window or after_orb_decision):
            return []

        atr_by_symbol = atr_by_symbol or {}
        candidates: list[ORBCandidate] = []

        # Phase 1: if just past the 9:35 decision point, compute ORB ranges
        # for symbols that don't have them cached yet.
        for symbol, df in features_by_symbol.items():
            if symbol in self._orb_cache:
                continue  # already computed for this session
            if df is None or len(df) < self.opening_minutes:
                continue

            atr = atr_by_symbol.get(symbol, 0.0)
            if atr <= 0 and "atr_14" in df.columns:
                try:
                    atr_v = float(df["atr_14"].iloc[-1])
                    last_close = float(df["close"].iloc[-1])
                    atr = atr_v * last_close if atr_v < 1.0 else atr_v
                except Exception:
                    atr = 0.0

            orb = self._compute_orb_range(symbol, df, atr)
            if orb is None:
                continue

            rv_ratio = self._compute_relative_volume(df, orb["orb_volume"])
            orb["rv_ratio"] = rv_ratio
            self._orb_cache[symbol] = orb

        # Phase 2: rank by relative volume, take top N
        ranked = [
            (sym, info) for sym, info in self._orb_cache.items()
            if info.get("rv_ratio", 0.0) >= self.min_rv_ratio
        ]
        ranked.sort(key=lambda kv: kv[1]["rv_ratio"], reverse=True)
        top = ranked[:self.top_n]

        # Phase 3: for each top candidate, check current breakout status
        for symbol, info in top:
            if symbol in self._fired_today:
                continue  # already fired this session
            df = features_by_symbol.get(symbol)
            if df is None or len(df) < 1 or "close" not in df.columns:
                continue
            try:
                current_price = float(df["close"].iloc[-1])
            except Exception:
                continue

            # Direction: ORB closed UP from open → long; closed DOWN → short
            if info["orb_close"] > info["orb_open"]:
                direction = 1.0
                breakout_triggered = current_price > info["orb_high"]
                stop = info["orb_low"] - info["atr_at_entry"] * self.stop_atr_mult
            elif info["orb_close"] < info["orb_open"]:
                direction = -1.0
                breakout_triggered = current_price < info["orb_low"]
                stop = info["orb_high"] + info["atr_at_entry"] * self.stop_atr_mult
            else:
                # Doji ORB: ambiguous direction, skip
                continue

            cand = ORBCandidate(
                symbol=symbol,
                direction=direction,
                rv_ratio=info["rv_ratio"],
                orb_high=info["orb_high"],
                orb_low=info["orb_low"],
                orb_close=info["orb_close"],
                orb_open=info["orb_open"],
                current_price=current_price,
                breakout_triggered=breakout_triggered,
                suggested_stop=stop,
                atr_at_entry=info["atr_at_entry"],
                timestamp=ts.isoformat(),
            )
            candidates.append(cand)

        return candidates

    def mark_fired(self, symbol: str) -> None:
        """Record that we entered a position via ORB for this symbol today.
        Prevents re-firing on subsequent ticks."""
        self._fired_today.add(symbol)

    def reset(self) -> None:
        """Manual full reset — useful for testing."""
        self._orb_cache.clear()
        self._fired_today.clear()
        self._current_session_date = None

    @property
    def orb_cache_size(self) -> int:
        """Number of symbols currently in the ORB cache (for diagnostics)."""
        return len(self._orb_cache)
