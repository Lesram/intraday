"""EOD Momentum Scanner — late-day continuation trades.

Inspired by Heston, Korajczyk, Sadka (2017) "Market Intraday Momentum"
which documented that the first half-hour return predicts the last
half-hour return on US equity index ETFs (out-of-sample R² ≈ 1.4-2.0%).

This module implements a simpler, robust variant: at 15:30 ET (when
~30 min of trading remain), if the day's cumulative return is large
enough (positive or negative), enter in the SAME direction. EOD flatten
(handled by existing live_engine logic at 15:58 ET) closes the trade.

Why this is independent edge from alpha+breakout+ORB:
  - Different time-of-day (alpha runs all day; ORB at 9:35 onwards;
    EOD at 15:30 onwards)
  - Different signal (cumulative-day-return continuation, not
    intra-bar pattern)
  - Different exit (forced EOD flatten, not stops/targets/timeout)
  - Different turnover (1 trade per active day max, vs many ORB/alpha
    intraday)

Initial deployment: SHADOW MODE (logs candidates, no entries fire).
Promote via ORGANISM_EOD_LIVE_ENABLED=true after 5 sessions of evidence
(per the same Phase A-E framework as ORB; see ORB_PROMOTION_CRITERIA.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time as dtime
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Strategy constants (Heston-Korajczyk-Sadka inspired; tunable)
DEFAULT_DECISION_HOUR_ET = 15
DEFAULT_DECISION_MIN_ET = 30          # 15:30 ET = 30 min before close
DEFAULT_NO_NEW_HOUR_ET = 15
DEFAULT_NO_NEW_MIN_ET = 50            # don't enter after 15:50 (8 min before EOD flatten at 15:58)
DEFAULT_MIN_DAY_RETURN_PCT = 0.30     # require >= 0.30% day return to enter (long)
DEFAULT_MIN_PRICE = 5.0
DEFAULT_TOP_N = 5                     # max EOD candidates per session (low turnover)
# Audit-A finding 9 (2026-05-01): same shape as the share-count liquidity
# gate bug. `max(atr, 0.10)` floors stop at $0.10 absolute regardless of
# price. For $5 stock = 2% (huge); for $1000 stock = 0.01% (irrelevant).
# Switch to bps-based floor matching mean_reversion_scanner.py's pattern.
DEFAULT_MIN_STOP_BPS = 5.0           # 5 bps = 0.05% of price minimum


@dataclass
class EODCandidate:
    """One EOD momentum candidate."""
    symbol: str
    direction: float          # +1.0 long, -1.0 short
    day_return_pct: float     # cumulative return from open to current
    open_price: float
    current_price: float
    suggested_stop: float     # ATR-based or open-anchored stop
    atr_at_entry: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "day_return_pct": round(self.day_return_pct, 4),
            "open_price": round(self.open_price, 4),
            "current_price": round(self.current_price, 4),
            "suggested_stop": round(self.suggested_stop, 4),
            "atr_at_entry": round(self.atr_at_entry, 4),
            "timestamp": self.timestamp,
        }


class EODMomentumScanner:
    """Scan for end-of-day momentum continuation candidates.

    At 15:30 ET each session, examine the day's cumulative return for
    each universe symbol. If |return| >= threshold, produce a candidate
    in the same direction.

    Stateful per session — mark_fired prevents re-firing same symbol
    same day.
    """

    def __init__(
        self,
        decision_hour_et: int = DEFAULT_DECISION_HOUR_ET,
        decision_min_et: int = DEFAULT_DECISION_MIN_ET,
        no_new_hour_et: int = DEFAULT_NO_NEW_HOUR_ET,
        no_new_min_et: int = DEFAULT_NO_NEW_MIN_ET,
        min_day_return_pct: float = DEFAULT_MIN_DAY_RETURN_PCT,
        min_price: float = DEFAULT_MIN_PRICE,
        min_stop_bps: float = DEFAULT_MIN_STOP_BPS,
        top_n: int = DEFAULT_TOP_N,
    ) -> None:
        self.decision_hour_et = decision_hour_et
        self.decision_min_et = decision_min_et
        self.no_new_hour_et = no_new_hour_et
        self.no_new_min_et = no_new_min_et
        self.min_day_return_pct = min_day_return_pct
        self.min_price = min_price
        self.min_stop_bps = min_stop_bps
        self.top_n = top_n

        self._fired_today: set[str] = set()
        self._current_session_date: Optional[str] = None

    def _is_in_decision_window(self, now_et: dtime) -> bool:
        """True iff time is in [15:30, 15:50) ET — the EOD entry window."""
        decision = dtime(self.decision_hour_et, self.decision_min_et)
        no_new = dtime(self.no_new_hour_et, self.no_new_min_et)
        return decision <= now_et < no_new

    @staticmethod
    def _et_time(now_dt: pd.Timestamp) -> dtime:
        if now_dt.tzinfo is None:
            now_dt = now_dt.tz_localize("UTC")
        try:
            et = now_dt.tz_convert("America/New_York")
            return et.time()
        except Exception:
            # Crude EDT approx fallback
            return (now_dt - pd.Timedelta(hours=4)).time()

    def _reset_for_new_session(self, session_date: str) -> None:
        self._fired_today.clear()
        self._current_session_date = session_date
        logger.info("EOD scanner reset for session %s", session_date)

    @staticmethod
    def _known_bars(df: pd.DataFrame, now_ts: pd.Timestamp) -> pd.DataFrame:
        """Return only bars observable at ``now_ts`` for causal shadow scans."""
        if df is None or len(df) == 0:
            return df
        if now_ts.tzinfo is None:
            now_ts = now_ts.tz_localize("UTC")
        else:
            now_ts = now_ts.tz_convert("UTC")
        try:
            if "timestamp" in df.columns:
                ts_raw = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                mask = ts_raw <= now_ts
                return df.loc[mask.values].reset_index(drop=True)
            if df.index.dtype.kind == "M":
                idx_ts = pd.to_datetime(pd.Series(df.index), errors="coerce", utc=True)
                mask = idx_ts <= now_ts
                return df.loc[mask.values].reset_index(drop=True)
        except (AttributeError, KeyError, TypeError, ValueError):
            return df
        return df

    @staticmethod
    def _compute_day_return(df: pd.DataFrame, ts_et: pd.Series) -> Optional[tuple[float, float, float]]:
        """Return (open_price, current_price, day_return_pct) using today's
        first bar's open and the most-recent close.

        Returns None if the day's first bar can't be identified.
        """
        if df is None or len(df) < 2 or "close" not in df.columns:
            return None

        # Identify today's bars — those with ET date == last bar's ET date
        try:
            last_date = ts_et.iloc[-1].date()
        except Exception:
            return None

        # Mask: bars where ET date == today
        try:
            dates = ts_et.dt.date
        except Exception:
            return None
        today_mask = (dates == last_date).values

        if not today_mask.any():
            return None

        today_bars = df[today_mask]
        if len(today_bars) < 2 or "open" not in today_bars.columns:
            return None

        try:
            open_price = float(today_bars["open"].iloc[0])
            current_price = float(today_bars["close"].iloc[-1])
        except Exception:
            return None

        if open_price <= 0 or not np.isfinite(open_price):
            return None
        day_return = (current_price - open_price) / open_price
        return open_price, current_price, day_return

    @staticmethod
    def _extract_atr(df: pd.DataFrame, current_price: float) -> float:
        if df is None or "atr_14" not in df.columns:
            return 0.0
        try:
            atr_v = float(df["atr_14"].iloc[-1])
            # atr_14 in our features may be normalized (atr/close); detect
            if 0 < atr_v < 1.0:
                return atr_v * current_price
            return atr_v
        except Exception:
            return 0.0

    def scan(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        now_dt: Any,
        session_date: Optional[str] = None,
    ) -> list[EODCandidate]:
        """Run the EOD momentum scanner.

        Returns candidates whose absolute day-return exceeds the threshold.
        Caller decides whether to enter (live) or just log (shadow).
        """
        ts = pd.Timestamp(now_dt) if not isinstance(now_dt, pd.Timestamp) else now_dt
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        if session_date is None:
            session_date = ts.strftime("%Y-%m-%d")

        if self._current_session_date != session_date:
            self._reset_for_new_session(session_date)

        et = self._et_time(ts)
        if not self._is_in_decision_window(et):
            return []

        candidates: list[EODCandidate] = []

        for symbol, df in features_by_symbol.items():
            if symbol in self._fired_today:
                continue
            known_df = self._known_bars(df, ts)
            if known_df is None or len(known_df) < 30:
                continue

            # Need timestamps to identify today's open
            if "timestamp" in known_df.columns:
                ts_raw = pd.to_datetime(known_df["timestamp"], errors="coerce", utc=True)
            elif known_df.index.dtype.kind == "M":
                ts_raw = pd.to_datetime(pd.Series(known_df.index), utc=True)
            else:
                continue

            if ts_raw.isna().all():
                continue

            try:
                ts_et = pd.Series(ts_raw).dt.tz_convert("America/New_York")
            except Exception:
                continue

            day_data = self._compute_day_return(known_df, ts_et)
            if day_data is None:
                continue
            open_price, current_price, day_return = day_data

            if current_price < self.min_price:
                continue

            # Apply threshold
            if abs(day_return) * 100 < self.min_day_return_pct:
                continue

            direction = 1.0 if day_return > 0 else -1.0
            atr = self._extract_atr(known_df, current_price)

            # ATR-based stop, anchored such that it's ~1×ATR adverse.
            # Audit-A finding 9 (2026-05-01): replaced the absolute $0.10
            # floor with a bps-based floor. For low-vol micro-ATR cases
            # the bps floor dominates; for normal cases ATR dominates.
            atr_distance = max(atr, 0.0)
            min_stop_distance = self.min_stop_bps * current_price / 10000.0
            actual_stop_distance = max(atr_distance, min_stop_distance)
            if direction > 0:
                stop = current_price - actual_stop_distance
            else:
                stop = current_price + actual_stop_distance

            cand = EODCandidate(
                symbol=symbol,
                direction=direction,
                day_return_pct=day_return * 100,
                open_price=open_price,
                current_price=current_price,
                suggested_stop=stop,
                atr_at_entry=atr,
                timestamp=ts.isoformat(),
            )
            candidates.append(cand)

        # Sort by absolute day-return descending (strongest signal first), top-N
        candidates.sort(key=lambda c: abs(c.day_return_pct), reverse=True)
        return candidates[:self.top_n]

    def mark_fired(self, symbol: str) -> None:
        self._fired_today.add(symbol)

    def reset(self) -> None:
        self._fired_today.clear()
        self._current_session_date = None
