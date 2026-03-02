"""
Module 1 — ML Feature Engine.

Computes 70+ features per symbol per bar for the self-learning organism.
No lookahead bias — every feature uses only past data.

Ref: docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md §3.1
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


# ─── Helpers ────────────────────────────────────────────────────────

def _safe(series: pd.Series, default: float = 0.0) -> pd.Series:
    return series.fillna(default)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period, min_periods=1).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100.0 - 100.0 / (1.0 + rs)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_c = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1
    ).max(axis=1)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return _true_range(high, low, close).rolling(period, min_periods=1).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr = _atr(high, low, close, period)
    plus_di = 100 * _ema(plus_dm, period) / atr.replace(0, 1e-10)
    minus_di = 100 * _ema(minus_dm, period) / atr.replace(0, 1e-10)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    return _ema(dx, period)


# ─── Main Feature Computation ──────────────────────────────────────

def compute_ml_features(
    df: pd.DataFrame,
    spy_df: pd.DataFrame | None = None,
    bars_per_day: int = 1,
) -> pd.DataFrame:
    """Compute 70+ ML features.  No lookahead.

    Parameters
    ----------
    df : DataFrame with columns [open, high, low, close, volume, timestamp].
    spy_df : Optional SPY DataFrame for cross-asset features.

    Returns
    -------
    DataFrame with all original columns + new feature columns.
    """
    f = df.copy()
    c, h, l, o, v = f["close"], f["high"], f["low"], f["open"], f["volume"]
    _ann_factor = math.sqrt(252 * bars_per_day)

    # ═══════════════════════════════════════════════════════
    # PRICE ACTION (15)
    # ═══════════════════════════════════════════════════════
    f["ret_1d"] = c.pct_change(1)
    f["ret_2d"] = c.pct_change(2)
    f["ret_3d"] = c.pct_change(3)
    f["ret_5d"] = c.pct_change(5)
    f["ret_10d"] = c.pct_change(10)
    f["ret_20d"] = c.pct_change(20)
    f["log_ret_1d"] = np.log(c / c.shift(1))
    f["momentum_accel"] = f["ret_1d"] - f["ret_1d"].shift(1)

    f["close_to_high"] = (c - l) / (h - l).replace(0, 1e-10)
    f["close_to_low"] = (h - c) / (h - l).replace(0, 1e-10)
    f["range_pct"] = (h - l) / c.replace(0, 1e-10)

    f["gap_pct"] = (o - c.shift(1)) / c.shift(1).replace(0, 1e-10)
    body = (c - o).abs()
    total = (h - l).replace(0, 1e-10)
    f["body_ratio"] = body / total
    f["upper_shadow"] = (h - pd.concat([c, o], axis=1).max(axis=1)) / total
    f["lower_shadow"] = (pd.concat([c, o], axis=1).min(axis=1) - l) / total

    # ═══════════════════════════════════════════════════════
    # TREND (10)
    # ═══════════════════════════════════════════════════════
    f["sma_5"] = _sma(c, 5) / c
    f["sma_10"] = _sma(c, 10) / c
    f["sma_20"] = _sma(c, 20) / c
    f["sma_50"] = _sma(c, 50) / c
    f["ema_12"] = _ema(c, 12)
    f["ema_26"] = _ema(c, 26)
    f["macd"] = f["ema_12"] - f["ema_26"]
    f["macd_signal"] = _ema(f["macd"], 9)
    f["macd_hist"] = f["macd"] - f["macd_signal"]
    f["adx_14"] = _adx(h, l, c, 14)

    # Normalize MACD/signal to price scale
    f["macd"] = f["macd"] / c.replace(0, 1e-10)
    f["macd_signal"] = f["macd_signal"] / c.replace(0, 1e-10)
    f["macd_hist"] = f["macd_hist"] / c.replace(0, 1e-10)

    # ═══════════════════════════════════════════════════════
    # MEAN REVERSION (8)
    # ═══════════════════════════════════════════════════════
    f["rsi_14"] = _rsi(c, 14) / 100.0  # Normalize [0,1]
    f["rsi_5"] = _rsi(c, 5) / 100.0

    bb_mid = _sma(c, 20)
    bb_std = c.rolling(20, min_periods=1).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    f["bb_position"] = (c - bb_lower) / (bb_upper - bb_lower).replace(0, 1e-10)
    f["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, 1e-10)

    f["z_score_20"] = (c - _sma(c, 20)) / c.rolling(20, min_periods=1).std().replace(0, 1e-10).fillna(1e-10)
    f["z_score_50"] = (c - _sma(c, 50)) / c.rolling(50, min_periods=1).std().replace(0, 1e-10).fillna(1e-10)

    # Stochastic
    low14 = l.rolling(14, min_periods=1).min()
    high14 = h.rolling(14, min_periods=1).max()
    f["stoch_k"] = (c - low14) / (high14 - low14).replace(0, 1e-10)
    f["stoch_d"] = f["stoch_k"].rolling(3, min_periods=1).mean()

    # ═══════════════════════════════════════════════════════
    # VOLATILITY (10)
    # ═══════════════════════════════════════════════════════
    f["atr_14"] = _atr(h, l, c, 14) / c.replace(0, 1e-10)
    f["atr_ratio"] = _atr(h, l, c, 5) / _atr(h, l, c, 20).replace(0, 1e-10)

    log_ret = np.log(c / c.shift(1))
    f["realized_vol_5"] = log_ret.rolling(5, min_periods=1).std() * _ann_factor
    f["realized_vol_20"] = log_ret.rolling(20, min_periods=1).std() * _ann_factor
    f["vol_ratio_5_20"] = f["realized_vol_5"] / f["realized_vol_20"].replace(0, 1e-10)

    # Parkinson volatility: uses high-low range
    f["parkinson_vol"] = (
        np.log(h / l.replace(0, 1e-10)) ** 2 / (4 * math.log(2))
    ).rolling(20, min_periods=1).mean().apply(lambda x: math.sqrt(max(x, 0)) * _ann_factor)

    # Garman-Klass volatility
    log_hl = np.log(h / l.replace(0, 1e-10))
    log_co = np.log(c / o.replace(0, 1e-10))
    gk_var = 0.5 * log_hl**2 - (2 * math.log(2) - 1) * log_co**2
    f["garman_klass_vol"] = gk_var.rolling(20, min_periods=1).mean().apply(
        lambda x: math.sqrt(max(x, 0)) * _ann_factor
    )

    # Volatility regime: low/normal/high based on percentile
    vol_pctile = f["realized_vol_20"].rolling(60, min_periods=20).rank(pct=True)
    f["vol_regime"] = pd.cut(vol_pctile, bins=[-0.01, 0.33, 0.67, 1.01], labels=[0, 1, 2]).astype(float)

    # Bollinger squeeze: BB width percentile (low = squeeze)
    f["bb_squeeze"] = f["bb_width"].rolling(60, min_periods=10).rank(pct=True)

    # Volatility expansion signal
    f["vol_expansion"] = (f["realized_vol_5"] / f["realized_vol_5"].shift(5).replace(0, 1e-10) - 1).clip(-2, 2)

    # ═══════════════════════════════════════════════════════
    # VOLUME (8)
    # ═══════════════════════════════════════════════════════
    vol_sma20 = _sma(v, 20)
    f["vol_sma_ratio"] = v / vol_sma20.replace(0, 1e-10)
    f["obv_slope"] = (v * np.sign(c - c.shift(1))).cumsum()
    f["obv_slope"] = (f["obv_slope"] - _sma(f["obv_slope"], 10)) / f["obv_slope"].rolling(10, min_periods=1).std().replace(0, 1e-10).fillna(1e-10)
    f["vol_momentum_5"] = v.pct_change(5)
    f["vol_momentum_10"] = v.pct_change(10)

    # Money Flow Index
    tp = (h + l + c) / 3
    raw_mf = tp * v
    pos_mf = raw_mf.where(tp > tp.shift(1), 0).rolling(14, min_periods=1).sum()
    neg_mf = raw_mf.where(tp < tp.shift(1), 0).rolling(14, min_periods=1).sum()
    f["mfi_14"] = (100 - 100 / (1 + pos_mf / neg_mf.replace(0, 1e-10))) / 100.0

    # VWAP distance (rolling 20-bar VWAP to avoid cumulative staleness)
    vwap_window = min(20, len(c))
    roll_vol = v.rolling(vwap_window, min_periods=1).sum()
    roll_vp = (c * v).rolling(vwap_window, min_periods=1).sum()
    vwap = roll_vp / roll_vol.replace(0, 1e-10)
    f["vwap_distance"] = (c - vwap) / vwap.replace(0, 1e-10)

    f["volume_breakout"] = (v > 2 * vol_sma20).astype(float)

    # Price-volume divergence: price up but volume down = bearish divergence
    price_dir = np.sign(f["ret_5d"])
    vol_dir = np.sign(f["vol_momentum_5"])
    f["pv_divergence"] = (price_dir != vol_dir).astype(float) * price_dir

    # ═══════════════════════════════════════════════════════
    # CROSS-SECTIONAL (5) — relative to SPY/market
    # ═══════════════════════════════════════════════════════
    if spy_df is not None and "close" in spy_df.columns and len(spy_df) >= len(df):
        spy_c = spy_df["close"].iloc[-len(df):].values
        spy_ret = pd.Series(spy_c).pct_change().values

        # Relative strength vs SPY
        stock_ret_20 = f["ret_20d"].values
        spy_ret_20 = pd.Series(spy_c).pct_change(20).values[-len(df):]
        f["rel_strength_spy"] = pd.Series(
            stock_ret_20 - spy_ret_20, index=f.index
        )

        # Beta (rolling 20-day)
        stock_rets = f["ret_1d"].values
        betas = []
        for i in range(len(stock_rets)):
            if i < 20:
                betas.append(1.0)
            else:
                sr = stock_rets[i-20:i]
                mr = spy_ret[max(0, len(spy_ret)-len(stock_rets)+i-20):max(0, len(spy_ret)-len(stock_rets)+i)]
                if (
                    len(mr) >= 20
                    and np.std(mr) > 0
                    and not np.any(np.isnan(sr))
                    and not np.any(np.isnan(mr[-20:]))
                ):
                    val = float(np.corrcoef(sr, mr[-20:])[0, 1] * np.std(sr) / np.std(mr[-20:]))
                    betas.append(val if np.isfinite(val) else 1.0)
                else:
                    betas.append(1.0)
        f["beta_20d"] = betas

        # Correlation to market
        corrs = []
        for i in range(len(stock_rets)):
            if i < 20:
                corrs.append(0.0)
            else:
                sr = stock_rets[i-20:i]
                mr = spy_ret[max(0, len(spy_ret)-len(stock_rets)+i-20):max(0, len(spy_ret)-len(stock_rets)+i)]
                if (
                    len(mr) >= 20
                    and np.std(sr) > 0
                    and np.std(mr) > 0
                    and not np.any(np.isnan(sr))
                    and not np.any(np.isnan(mr[-20:]))
                ):
                    val = float(np.corrcoef(sr, mr[-20:])[0, 1])
                    corrs.append(val if np.isfinite(val) else 0.0)
                else:
                    corrs.append(0.0)
        f["corr_to_market"] = corrs

        # Idiosyncratic vol
        f["idio_vol"] = f["realized_vol_20"] * (1 - pd.Series(corrs, index=f.index).abs())
    else:
        f["rel_strength_spy"] = 0.0
        f["beta_20d"] = 1.0
        f["corr_to_market"] = 0.0
        f["idio_vol"] = f["realized_vol_20"]

    # Sector momentum proxy (use own 20d vs 5d as rough sector)
    f["sector_momentum"] = f["ret_20d"] - f["ret_5d"]

    # ═══════════════════════════════════════════════════════
    # MICROSTRUCTURE (5)
    # ═══════════════════════════════════════════════════════
    f["spread_proxy"] = 2 * (h - l) / (h + l).replace(0, 1e-10)
    f["price_impact"] = f["ret_1d"].abs() / (np.log1p(v)).replace(0, 1e-10)
    f["tick_direction"] = np.sign(c - c.shift(1)).rolling(10, min_periods=1).mean()
    f["close_location"] = (c - l) / (h - l).replace(0, 1e-10)
    f["true_range_pct"] = _true_range(h, l, c) / c.replace(0, 1e-10)

    # ═══════════════════════════════════════════════════════
    # TEMPORAL (4)
    # ═══════════════════════════════════════════════════════
    if "timestamp" in f.columns:
        ts = pd.to_datetime(f["timestamp"])
        f["day_of_week"] = ts.dt.dayofweek / 4.0  # Normalize [0,1]
        f["month_sin"] = np.sin(2 * math.pi * ts.dt.month / 12)
        f["month_cos"] = np.cos(2 * math.pi * ts.dt.month / 12)
    else:
        f["day_of_week"] = 0.0
        f["month_sin"] = 0.0
        f["month_cos"] = 0.0

    # Session/52-week high/low (uses session window for intraday, 252 for daily)
    _hl_window = min(len(h), bars_per_day) if bars_per_day > 1 else 252
    high_52w = h.rolling(_hl_window, min_periods=min(20, _hl_window)).max()
    low_52w = l.rolling(_hl_window, min_periods=min(20, _hl_window)).min()
    f["pct_from_52w_high"] = (c - high_52w) / high_52w.replace(0, 1e-10)
    f["pct_from_52w_low"] = (c - low_52w) / low_52w.replace(0, 1e-10)

    # ═══════════════════════════════════════════════════════
    # REGIME (4)
    # ═══════════════════════════════════════════════════════
    f["trend_strength"] = f["adx_14"] / 100.0

    # Choppiness index: log(sum(ATR14) / (highest-lowest)) / log(14)
    atr_sum = _true_range(h, l, c).rolling(14, min_periods=1).sum()
    hh = h.rolling(14, min_periods=1).max()
    ll = l.rolling(14, min_periods=1).min()
    ci_denom = (hh - ll).replace(0, 1e-10)
    f["choppiness"] = np.log10(atr_sum / ci_denom) / math.log10(14)

    # Hurst exponent approximation (rescaled range on 50 bars)
    def _hurst_approx(series: pd.Series, window: int = 50) -> pd.Series:
        result = pd.Series(0.5, index=series.index)
        vals = series.values
        for i in range(window, len(vals)):
            seg = vals[i-window:i]
            mean = np.mean(seg)
            std = np.std(seg)
            if std < 1e-10:
                continue
            cumdev = np.cumsum(seg - mean)
            r = np.max(cumdev) - np.min(cumdev)
            result.iloc[i] = math.log(max(r / std, 1e-10)) / math.log(window)
        return result

    f["hurst"] = _hurst_approx(log_ret, 50)

    # Regime label encoded: 0=chop, 1=trending, 2=high_vol
    f["regime_encoded"] = 0.0
    f.loc[f["adx_14"] > 25, "regime_encoded"] = 1.0
    f.loc[f["vol_regime"] == 2, "regime_encoded"] = 2.0

    # ═══════════════════════════════════════════════════════
    # MOMENTUM PERSISTENCE (4)
    # ═══════════════════════════════════════════════════════
    _ret_1d = f["ret_1d"]
    for _lag in (1, 5, 10):
        f[f"ret_autocorr_{_lag}"] = _ret_1d.rolling(
            window=max(30, _lag * 3), min_periods=max(15, _lag + 2),
        ).apply(
            lambda s, __lag=_lag: float(s.autocorr(lag=__lag))
            if len(s) > __lag else 0.0,
            raw=False,
        )

    # Hurst exponent on returns (rescaled-range, separate from price hurst)
    def _hurst_ret(series: pd.Series, window: int = 50) -> pd.Series:
        result = pd.Series(0.5, index=series.index)
        vals = series.values
        for i in range(window, len(vals)):
            seg = vals[i - window : i]
            mean_val = np.mean(seg)
            std_val = np.std(seg)
            if std_val < 1e-10:
                continue
            cumdev = np.cumsum(seg - mean_val)
            r = np.max(cumdev) - np.min(cumdev)
            result.iloc[i] = math.log(max(r / std_val, 1e-10)) / math.log(window)
        return result

    f["hurst_exponent"] = _hurst_ret(_ret_1d, 50)

    # ═══════════════════════════════════════════════════════
    # COMPOSITE INDICATORS (7)
    # ═══════════════════════════════════════════════════════
    try:
        from backend.organism.composite_indicators import (
            compute_composite_indicators,
            COMPOSITE_COLUMNS,
        )
        f = compute_composite_indicators(f)
    except Exception:
        # Graceful fallback — composites are not critical
        for col_name in [
            "comp_squeeze_momentum", "comp_vol_price_div",
            "comp_trend_alignment", "comp_institutional_acc",
            "comp_mean_rev_extreme", "comp_breakout_readiness",
            "comp_momentum_quality",
        ]:
            f[col_name] = 0.0

    # ═══════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════
    # Drop intermediate columns that are not features
    for col in ["ema_12", "ema_26"]:
        if col in f.columns:
            f.drop(columns=[col], inplace=True)

    # Replace inf/nan — but first measure missingness so callers can gate
    f.replace([np.inf, -np.inf], np.nan, inplace=True)
    last_row_nans = int(f.iloc[-1].isna().sum()) if len(f) > 0 else 0
    total_cols = len(f.columns)
    missingness_ratio = last_row_nans / total_cols if total_cols > 0 else 0.0
    f.fillna(0.0, inplace=True)

    # Store missingness as a feature so the engine can gate entries
    f["_nan_missingness"] = missingness_ratio  # constant per call

    return f


# ─── Feature Metadata ──────────────────────────────────────────────

FEATURE_COLUMNS: list[str] = [
    # Price Action
    "ret_1d", "ret_2d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "log_ret_1d", "momentum_accel",
    "close_to_high", "close_to_low", "range_pct",
    "gap_pct", "body_ratio", "upper_shadow", "lower_shadow",
    # Trend
    "sma_5", "sma_10", "sma_20", "sma_50",
    "macd", "macd_signal", "macd_hist", "adx_14",
    # Mean Reversion
    "rsi_14", "rsi_5", "bb_position", "bb_width",
    "z_score_20", "z_score_50", "stoch_k", "stoch_d",
    # Volatility
    "atr_14", "atr_ratio",
    "realized_vol_5", "realized_vol_20", "vol_ratio_5_20",
    "parkinson_vol", "garman_klass_vol",
    "vol_regime", "bb_squeeze", "vol_expansion",
    # Volume
    "vol_sma_ratio", "obv_slope", "vol_momentum_5", "vol_momentum_10",
    "mfi_14", "vwap_distance", "volume_breakout", "pv_divergence",
    # Cross-sectional
    "rel_strength_spy", "sector_momentum", "corr_to_market",
    "beta_20d", "idio_vol",
    # Microstructure
    "spread_proxy", "price_impact", "tick_direction",
    "close_location", "true_range_pct",
    # Temporal
    "day_of_week", "month_sin", "month_cos",
    "pct_from_52w_high", "pct_from_52w_low",
    # Regime
    "trend_strength", "choppiness", "hurst", "regime_encoded",
    # Momentum persistence
    "ret_autocorr_1", "ret_autocorr_5", "ret_autocorr_10", "hurst_exponent",
    # Composite indicators (proprietary)
    "comp_squeeze_momentum", "comp_vol_price_div",
    "comp_trend_alignment", "comp_institutional_acc",
    "comp_mean_rev_extreme", "comp_breakout_readiness",
    "comp_momentum_quality",
]
"""All 79 feature column names produced by compute_ml_features()."""
