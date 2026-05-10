"""Gamma/volatility proxy for intraday momentum research.

This is a bar-derived proxy, not a true options-gamma model.  Phase 9B uses it
only to classify whether ETF/index momentum candidates were observed on
high-volatility, high-volume, trend-confirmed days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class GammaVolState:
    symbol: str
    realized_vol_z: float
    volume_z: float
    opening_gap_pct: float
    first_hour_trend_bps: float
    rest_of_day_trend_bps: float
    high_vol_trend_day: bool
    direction: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "realized_vol_z": round(self.realized_vol_z, 4),
            "volume_z": round(self.volume_z, 4),
            "opening_gap_pct": round(self.opening_gap_pct, 4),
            "first_hour_trend_bps": round(self.first_hour_trend_bps, 4),
            "rest_of_day_trend_bps": round(self.rest_of_day_trend_bps, 4),
            "high_vol_trend_day": self.high_vol_trend_day,
            "direction": self.direction,
        }


class GammaVolProxy:
    """Estimate high-volatility trend conditions from 1-minute OHLCV bars."""

    def __init__(
        self,
        *,
        vol_z_threshold: float = 0.75,
        volume_z_threshold: float = 0.50,
        trend_bps_threshold: float = 20.0,
        lookback_bars: int = 390,
    ) -> None:
        self.vol_z_threshold = vol_z_threshold
        self.volume_z_threshold = volume_z_threshold
        self.trend_bps_threshold = trend_bps_threshold
        self.lookback_bars = lookback_bars

    def evaluate(self, symbol: str, bars: pd.DataFrame, now: Any | None = None) -> GammaVolState | None:
        prepared = _prepare_bars(bars)
        if prepared is None or len(prepared) < 70:
            return None
        session = _session_bars(prepared, now)
        if len(session) < 70:
            return None

        close = session["close"].astype(float)
        volume = session["volume"].astype(float) if "volume" in session.columns else pd.Series(dtype=float)
        returns = close.pct_change().dropna()
        if len(returns) < 20:
            return None

        current_vol = float(returns.tail(30).std(ddof=0) or 0.0)
        hist_returns = prepared["close"].astype(float).pct_change().dropna().tail(self.lookback_bars)
        hist_vol = hist_returns.rolling(30).std(ddof=0).dropna()
        realized_vol_z = _zscore(current_vol, hist_vol.tolist())

        current_volume = float(volume.tail(30).mean()) if len(volume) >= 30 else 0.0
        hist_volume = (
            prepared["volume"].astype(float).rolling(30).mean().dropna().tail(self.lookback_bars)
            if "volume" in prepared.columns
            else pd.Series(dtype=float)
        )
        volume_z = _zscore(current_volume, hist_volume.tolist())

        first_open = float(session["open"].iloc[0])
        prev_close = _previous_close(prepared, session)
        first_hour_close = float(session["close"].iloc[min(len(session) - 1, 59)])
        latest_close = float(session["close"].iloc[-1])
        if first_open <= 0 or prev_close is None or prev_close <= 0:
            return None

        opening_gap_pct = (first_open - prev_close) / prev_close * 100.0
        first_hour_trend_bps = (first_hour_close - prev_close) / prev_close * 10000.0
        rest_of_day_trend_bps = (latest_close - prev_close) / prev_close * 10000.0
        direction = 1 if rest_of_day_trend_bps > 0 else -1 if rest_of_day_trend_bps < 0 else 0
        high_vol_trend_day = (
            realized_vol_z >= self.vol_z_threshold
            and volume_z >= self.volume_z_threshold
            and abs(rest_of_day_trend_bps) >= self.trend_bps_threshold
        )

        return GammaVolState(
            symbol=symbol.upper(),
            realized_vol_z=realized_vol_z,
            volume_z=volume_z,
            opening_gap_pct=opening_gap_pct,
            first_hour_trend_bps=first_hour_trend_bps,
            rest_of_day_trend_bps=rest_of_day_trend_bps,
            high_vol_trend_day=high_vol_trend_day,
            direction=direction,
        )


def _zscore(value: float, history: list[float]) -> float:
    values = [float(v) for v in history if math.isfinite(float(v))]
    if len(values) < 5:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std <= 0:
        return 0.0
    return (float(value) - mean) / std


def _prepare_bars(bars: pd.DataFrame | None) -> pd.DataFrame | None:
    if bars is None or len(bars) == 0:
        return None
    required = {"open", "close"}
    if not required.issubset(set(bars.columns)):
        return None
    df = bars.copy()
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        if ts.isna().all():
            return None
        df = df.assign(_ts=ts).sort_values("_ts")
    elif df.index.dtype.kind == "M":
        ts = pd.to_datetime(pd.Series(df.index), utc=True)
        df = df.assign(_ts=ts.values).sort_values("_ts")
    else:
        return None
    return df.reset_index(drop=True)


def _session_bars(df: pd.DataFrame, now: Any | None = None) -> pd.DataFrame:
    ts_et = pd.to_datetime(df["_ts"], utc=True).dt.tz_convert("America/New_York")
    if now is None:
        session_date = ts_et.iloc[-1].date()
    else:
        now_ts = pd.Timestamp(now)
        if now_ts.tzinfo is None:
            now_ts = now_ts.tz_localize("UTC")
        session_date = now_ts.tz_convert("America/New_York").date()
    mask = ts_et.dt.date == session_date
    return df[mask].reset_index(drop=True)


def _previous_close(df: pd.DataFrame, session: pd.DataFrame) -> float | None:
    if session.empty:
        return None
    first_ts = session["_ts"].iloc[0]
    prev = df[df["_ts"] < first_ts]
    if prev.empty:
        return None
    try:
        return float(prev["close"].iloc[-1])
    except (TypeError, ValueError):
        return None
