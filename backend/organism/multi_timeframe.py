"""
Phase 4.2 — Multi-Timeframe Features.

Derives higher-timeframe features from the bar stream so the organism can
incorporate multi-timeframe confluence into its ML decisions.

Supports both daily and intraday (e.g. 15Min) bar inputs:
  • Daily bars  → resample to weekly (5 bars) and monthly (21 bars)
  • 15Min bars  → resample to daily (26 bars) and weekly (130 bars)

Feature naming:  ``mtf_{timeframe}_{indicator}``
    e.g. ``mtf_w_rsi_14`` (weekly RSI) or ``mtf_m_sma_trend`` (monthly trend).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd


# ── Constants: bars per day for various intraday timeframes ──────
_BARS_PER_DAY = {
    "1min": 390, "5min": 78, "15min": 26, "30min": 13, "1hour": 7,
}


def _detect_resample_periods() -> tuple[int, int]:
    """Return (short_period, long_period) based on the timeframe env var.

    Daily bars  → (5,  21)   ≈ weekly / monthly
    15Min bars  → (26, 130)  ≈ daily  / weekly
    """
    tf = os.getenv("ORGANISM_LIVE_TIMEFRAME", "1Day").lower().replace(" ", "")
    for key, bpd in _BARS_PER_DAY.items():
        if key in tf:
            return bpd, bpd * 5  # 1 day, 1 week
    return 5, 21  # default daily bars → weekly / monthly


# ── Helper: resample daily → N-day OHLCV ────────────────────────

def _resample_ohlcv(df: pd.DataFrame, period: int) -> pd.DataFrame:
    """Rolling N-day aggregation (NOT calendar resample).

    Produces a row for every input row — the last ``period`` bars
    are aggregated into one virtual bar.  This avoids lookahead and
    works for any DataFrame that has sequential daily bars.
    """
    out = pd.DataFrame(index=df.index)
    c = df["close"]
    h = df["high"] if "high" in df.columns else c
    l = df["low"] if "low" in df.columns else c
    o = df["open"] if "open" in df.columns else c
    v = df["volume"] if "volume" in df.columns else pd.Series(0, index=df.index)

    out["open"] = o.shift(period - 1)
    out["high"] = h.rolling(period, min_periods=1).max()
    out["low"] = l.rolling(period, min_periods=1).min()
    out["close"] = c
    out["volume"] = v.rolling(period, min_periods=1).sum()
    return out


# ── Feature generators per timeframe ────────────────────────────

def _tf_features(ohlcv: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Compute a fixed set of indicators on a resampled OHLCV frame."""
    f = pd.DataFrame(index=ohlcv.index)
    c = ohlcv["close"]
    h = ohlcv["high"]
    l = ohlcv["low"]
    v = ohlcv["volume"]

    # 1. Returns
    f[f"{prefix}_ret"] = c.pct_change(1)
    f[f"{prefix}_ret_3"] = c.pct_change(3)

    # 2. Trend: close vs SMA(10) of resampled frame
    sma10 = c.rolling(10, min_periods=1).mean()
    f[f"{prefix}_sma_trend"] = (c - sma10) / sma10.replace(0, 1e-10)

    # 3. RSI-14 on the resampled series
    delta = c.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, 1e-10)
    f[f"{prefix}_rsi_14"] = 100.0 - 100.0 / (1.0 + rs)

    # 4. Volatility: ATR normalised by close
    tr = pd.concat(
        [h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1,
    ).max(axis=1)
    atr_14 = tr.rolling(14, min_periods=1).mean()
    f[f"{prefix}_atr_norm"] = atr_14 / c.replace(0, 1e-10)

    # 5. Bar range
    f[f"{prefix}_range_pct"] = (h - l) / c.replace(0, 1e-10)

    # 6. Volume momentum
    vol_sma = v.rolling(10, min_periods=1).mean()
    f[f"{prefix}_vol_mom"] = v / vol_sma.replace(0, 1e-10)

    # 7. Bollinger %B on weekly/monthly
    sma20 = c.rolling(20, min_periods=1).mean()
    std20 = c.rolling(20, min_periods=1).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    f[f"{prefix}_bb_pct"] = (c - lower) / (upper - lower).replace(0, 1e-10)

    # 8. Higher-TF momentum alignment (simple slope)
    slope_5 = c.diff(5) / c.shift(5).replace(0, 1e-10)
    f[f"{prefix}_slope_5"] = slope_5

    return f.fillna(0.0).clip(-10.0, 10.0)  # Clip extreme values from near-zero divisions


# ── Public API ───────────────────────────────────────────────────

# Column names: must match what _tf_features produces above
_SUFFIXES = [
    "_ret", "_ret_3", "_sma_trend", "_rsi_14", "_atr_norm",
    "_range_pct", "_vol_mom", "_bb_pct", "_slope_5",
]

MTF_FEATURE_COLUMNS: list[str] = sorted(
    [f"mtf_w{s}" for s in _SUFFIXES] + [f"mtf_m{s}" for s in _SUFFIXES]
)
"""Names of all 18 multi-timeframe features added by this module."""


def add_multi_timeframe_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add multi-timeframe features to a DataFrame.

    Automatically detects intraday vs daily via ORGANISM_LIVE_TIMEFRAME env var
    and adjusts resample periods accordingly:
      - Daily  → weekly (5 bars) + monthly (21 bars)
      - 15Min  → daily (26 bars) + weekly (130 bars)

    Parameters
    ----------
    df : Bar DataFrame with open, high, low, close, volume columns.

    Returns
    -------
    Same DataFrame with 18 new ``mtf_*`` columns appended.
    """
    short_period, long_period = _detect_resample_periods()
    min_bars = long_period + 1

    if len(df) < min_bars:
        # Not enough data for larger resample window
        for col in MTF_FEATURE_COLUMNS:
            df[col] = 0.0
        return df

    # Short timeframe (weekly for daily, daily for intraday)
    weekly = _resample_ohlcv(df, period=short_period)
    w_feats = _tf_features(weekly, prefix="mtf_w")

    # Long timeframe (monthly for daily, weekly for intraday)
    monthly = _resample_ohlcv(df, period=long_period)
    m_feats = _tf_features(monthly, prefix="mtf_m")

    # Merge into original frame
    for col in w_feats.columns:
        df[col] = w_feats[col].values
    for col in m_feats.columns:
        df[col] = m_feats[col].values

    return df
