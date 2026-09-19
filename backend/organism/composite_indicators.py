"""
Proprietary Composite Trading Indicators.

Combines multiple base indicators into higher-conviction composite signals
that the ML model and alpha scanner use for trade decisions.

Each composite indicator fuses 3-5 base indicators into a single
normalized score [0, 1] representing a specific market condition.

Composites:
    1. Squeeze Momentum Composite   — volatility compression + directional energy
    2. Volume-Price Divergence       — smart money vs dumb money flow
    3. Trend Alignment Score         — multi-timeframe trend consensus
    4. Institutional Accumulation    — large block flow detection
    5. Mean Reversion Extremity      — multi-indicator oversold/overbought
    6. Breakout Readiness Index      — pre-breakout tension scoring
    7. Momentum Quality Score        — sustainable vs fading momentum
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────

def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise division that survives zero denominators.

    V7 DD-1 / Wave-24 (2026-05-03): the previous implementation
    `a / b.replace(0, 1e-10)` collapsed `0/0` to `0`. Combined with
    `(1 - _safe_div(...)).clip(0, 1)`, this produced a SATURATED
    score (1.0) on flat-price / warmup / halted bars — the platform
    manufactured synthetic "high breakout score" out of zero signal.
    Now: when BOTH a and b are ~0 at the same index, the result is
    NaN, which downstream `.fillna(0.0)` converts to a clean 0
    (no signal → no score). Non-zero numerator over zero denominator
    still uses the 1e-10 epsilon (same legacy semantics for those).
    """
    a_zero = a.abs() < 1e-12
    b_zero = b.abs() < 1e-12
    raw = a / b.replace(0, 1e-10)
    # Mark 0/0 explicitly as NaN so callers don't propagate phantom values.
    return raw.where(~(a_zero & b_zero), other=float("nan"))


def _norm_01(s: pd.Series) -> pd.Series:
    """Normalize to [0, 1] using rolling percentile rank (60-bar window)."""
    return s.rolling(60, min_periods=10).rank(pct=True).fillna(0.5)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=1).mean()


# ═══════════════════════════════════════════════════════════════════
# 1. SQUEEZE MOMENTUM COMPOSITE
# ═══════════════════════════════════════════════════════════════════

def squeeze_momentum_composite(df: pd.DataFrame) -> pd.Series:
    """Bollinger squeeze + Keltner Channel + momentum direction.

    Detects compressed volatility with building directional energy.
    High score = squeeze active with strong directional momentum.

    Combines:
    - BB width percentile (squeeze tightness)
    - BB inside Keltner (true squeeze)
    - Linear regression slope of close (momentum direction)
    - Volume expansion during squeeze
    """
    c, h, l = df["close"], df["high"], df["low"]

    # Bollinger Bands
    bb_mid = _sma(c, 20)
    bb_std = c.rolling(20, min_periods=1).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = _safe_div(bb_upper - bb_lower, bb_mid)

    # Keltner Channel (ATR-based)
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / 20, adjust=False).mean()
    kc_upper = _ema(c, 20) + 1.5 * atr
    kc_lower = _ema(c, 20) - 1.5 * atr

    # Squeeze active: BB inside KC
    squeeze_on = ((bb_lower > kc_lower) & (bb_upper < kc_upper)).astype(float)

    # BB width tightness (lower percentile = tighter = higher score)
    tightness = 1.0 - bb_width.rolling(120, min_periods=20).rank(pct=True).fillna(0.5)

    # Momentum: deviation from midline (Donchian-BB midline)
    dc_mid = (h.rolling(20).max() + l.rolling(20).min()) / 2
    overall_mid = (dc_mid + bb_mid) / 2
    momentum = _safe_div(c - overall_mid, atr)

    # Directional energy: abs momentum normalized
    energy = momentum.abs().rolling(10, min_periods=1).mean()
    energy_score = (energy / energy.rolling(60, min_periods=10).max().replace(0, 1e-10)).clip(0, 1)

    # Volume during squeeze
    v = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)
    vol_sma = _sma(v, 20)
    vol_surge = _safe_div(v, vol_sma).clip(0, 5)
    vol_score = ((vol_surge - 1) / 4).clip(0, 1)

    composite = (
        0.30 * squeeze_on
        + 0.25 * tightness
        + 0.25 * energy_score
        + 0.20 * vol_score
    ).clip(0, 1)

    return composite.fillna(0.0)


# ═══════════════════════════════════════════════════════════════════
# 2. VOLUME-PRICE DIVERGENCE
# ═══════════════════════════════════════════════════════════════════

def volume_price_divergence(df: pd.DataFrame) -> pd.Series:
    """Detect divergence between price direction and volume flow.

    Positive = bullish divergence (price flat/down but volume accumulating)
    Negative = bearish divergence (price up but volume distributing)

    Combines:
    - OBV slope vs price slope divergence
    - MFI divergence from price trend
    - Chaikin Money Flow direction vs price
    - Volume-weighted price vs equal-weighted price gap
    """
    c, h, l = df["close"], df["high"], df["low"]
    v = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)

    # OBV slope (10-bar)
    obv = (v * np.sign(c.diff())).cumsum()
    obv_slope = _safe_div(obv - _sma(obv, 10), obv.rolling(10, min_periods=1).std())
    price_slope = _safe_div(c - _sma(c, 10), c.rolling(10, min_periods=1).std())
    obv_div = (obv_slope - price_slope).clip(-3, 3) / 6 + 0.5  # normalize [0,1]

    # Money Flow Index divergence
    tp = (h + l + c) / 3
    raw_mf = tp * v
    pos_mf = raw_mf.where(tp > tp.shift(1), 0).rolling(14, min_periods=1).sum()
    neg_mf = raw_mf.where(tp < tp.shift(1), 0).rolling(14, min_periods=1).sum()
    mfi = 100 - _safe_div(100, 1 + _safe_div(pos_mf, neg_mf))
    mfi_norm = mfi / 100.0
    # MFI rising while price falling = bullish divergence
    mfi_slope = mfi_norm - mfi_norm.shift(5)
    price_ret5 = c.pct_change(5)
    mfi_div = (mfi_slope - price_ret5 * 10).clip(-2, 2) / 4 + 0.5

    # Chaikin Money Flow
    mf_mult = _safe_div((c - l) - (h - c), h - l)
    mf_vol = mf_mult * v
    cmf = _safe_div(mf_vol.rolling(20, min_periods=1).sum(), v.rolling(20, min_periods=1).sum())
    cmf_direction = (cmf > 0).astype(float)
    price_direction = (c.pct_change(5) > 0).astype(float)
    cmf_div = (cmf_direction != price_direction).astype(float) * 0.5 + cmf.abs().clip(0, 0.5)

    # VWAP gap: volume-weighted price vs simple average
    vwap_20 = _safe_div((c * v).rolling(20, min_periods=1).sum(), v.rolling(20, min_periods=1).sum())
    sma_20 = _sma(c, 20)
    vwap_gap = _safe_div(vwap_20 - sma_20, sma_20).clip(-0.05, 0.05) * 10 + 0.5

    composite = (
        0.30 * obv_div.fillna(0.5)
        + 0.25 * mfi_div.fillna(0.5)
        + 0.25 * cmf_div.fillna(0.5)
        + 0.20 * vwap_gap.fillna(0.5)
    ).clip(0, 1)

    return composite.fillna(0.5)


# ═══════════════════════════════════════════════════════════════════
# 3. TREND ALIGNMENT SCORE
# ═══════════════════════════════════════════════════════════════════

def trend_alignment_score(df: pd.DataFrame) -> pd.Series:
    """Multi-timeframe trend consensus.

    Measures alignment across 5/10/20/50 period moving averages.
    1.0 = perfectly aligned uptrend (5>10>20>50 and price above all)
    0.0 = perfectly aligned downtrend
    0.5 = mixed/choppy

    Combines:
    - SMA alignment (golden cross stack)
    - ADX trend strength
    - Price position relative to MAs
    - MACD confirmation
    """
    c = df["close"]

    sma5 = _sma(c, 5)
    sma10 = _sma(c, 10)
    sma20 = _sma(c, 20)
    sma50 = _sma(c, 50)

    # SMA stack alignment: how many are in order?
    bull_align = (
        (sma5 > sma10).astype(float)
        + (sma10 > sma20).astype(float)
        + (sma20 > sma50).astype(float)
        + (c > sma5).astype(float)
    ) / 4.0

    bear_align = (
        (sma5 < sma10).astype(float)
        + (sma10 < sma20).astype(float)
        + (sma20 < sma50).astype(float)
        + (c < sma5).astype(float)
    ) / 4.0

    # 1.0 = full bull alignment, 0.0 = full bear alignment
    alignment = bull_align * 0.5 + 0.5 - bear_align * 0.5

    # ADX strength: higher ADX = more confidence in alignment
    if "adx_14" in df.columns:
        adx = df["adx_14"]
    else:
        # Compute ADX inline
        h, l = df["high"], df["low"]
        plus_dm = h.diff().where((h.diff() > -l.diff()) & (h.diff() > 0), 0.0)
        minus_dm = (-l.diff()).where((-l.diff() > h.diff()) & (-l.diff() > 0), 0.0)
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = _safe_div(100 * _ema(plus_dm, 14), atr14)
        minus_di = _safe_div(100 * _ema(minus_dm, 14), atr14)
        dx = _safe_div(100 * (plus_di - minus_di).abs(), plus_di + minus_di)
        adx = _ema(dx, 14)

    adx_strength = (adx / 100.0).clip(0, 1)

    # MACD confirmation
    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    macd_line = ema12 - ema26
    macd_signal = _ema(macd_line, 9)
    macd_hist = macd_line - macd_signal
    macd_bull = (macd_hist > 0).astype(float)

    # Weighted composite
    composite = (
        0.35 * alignment
        + 0.25 * adx_strength
        + 0.20 * macd_bull
        + 0.20 * (c > sma20).astype(float)
    ).clip(0, 1)

    return composite.fillna(0.5)


# ═══════════════════════════════════════════════════════════════════
# 4. INSTITUTIONAL ACCUMULATION DETECTOR
# ═══════════════════════════════════════════════════════════════════

def institutional_accumulation(df: pd.DataFrame) -> pd.Series:
    """Detect institutional buying patterns.

    Institutional buying shows as:
    - Large volume bars with small price impact (stealth accumulation)
    - Positive money flow on down bars (buying the dip)
    - Rising OBV while price consolidates
    - Close consistently near highs on high-volume bars

    Score: 0 = distribution, 0.5 = neutral, 1.0 = heavy accumulation
    """
    c, h, l = df["close"], df["high"], df["low"]
    v = df["volume"] if "volume" in df.columns else pd.Series(1e6, index=df.index)

    # 1. Stealth accumulation: high volume but low price impact
    price_impact = c.pct_change().abs()
    log_vol = np.log1p(v)
    impact_ratio = _safe_div(price_impact, log_vol)
    # Low impact ratio on high volume = accumulation
    vol_pctile = v.rolling(20, min_periods=1).rank(pct=True)
    stealth = ((vol_pctile > 0.7) & (impact_ratio < impact_ratio.rolling(20).median())).astype(float)

    # 2. Positive money flow on down bars
    is_down_bar = (c < c.shift(1)).astype(float)
    close_in_range = _safe_div(c - l, h - l)  # [0,1] where 1 = close at high
    buying_dip = (is_down_bar * close_in_range).rolling(10, min_periods=1).mean()

    # 3. OBV trend vs price trend
    obv = (v * np.sign(c.diff())).cumsum()
    obv_rising = (obv > obv.shift(10)).astype(float)
    price_flat = (c.pct_change(10).abs() < 0.02).astype(float)
    obv_diverge = obv_rising * price_flat

    # 4. Close near highs on big volume days
    close_near_high = (close_in_range > 0.7).astype(float)
    big_vol = (vol_pctile > 0.8).astype(float)
    bullish_close = (close_near_high * big_vol).rolling(10, min_periods=1).mean()

    composite = (
        0.25 * stealth
        + 0.25 * buying_dip
        + 0.25 * obv_diverge
        + 0.25 * bullish_close
    ).clip(0, 1)

    return composite.fillna(0.5)


# ═══════════════════════════════════════════════════════════════════
# 5. MEAN REVERSION EXTREMITY
# ═══════════════════════════════════════════════════════════════════

def mean_reversion_extremity(df: pd.DataFrame) -> pd.Series:
    """Multi-indicator oversold/overbought score.

    -1.0 = extreme oversold (buy signal)
    +1.0 = extreme overbought (sell signal)
     0.0 = neutral

    Combines RSI, Stochastic, BB position, z-score, Williams %R.
    More extreme readings across more indicators = higher conviction.
    """
    c, h, l = df["close"], df["high"], df["low"]

    # RSI
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = _safe_div(gain, loss)
    rsi = 100 - _safe_div(100, 1 + rs)
    rsi_score = (rsi - 50) / 50  # [-1, 1]

    # Stochastic
    low14 = l.rolling(14, min_periods=1).min()
    high14 = h.rolling(14, min_periods=1).max()
    stoch = _safe_div(c - low14, high14 - low14) * 100
    stoch_score = (stoch - 50) / 50

    # Bollinger Band position
    bb_mid = _sma(c, 20)
    bb_std = c.rolling(20, min_periods=1).std()
    bb_pos = _safe_div(c - (bb_mid - 2 * bb_std), 4 * bb_std)
    bb_score = (bb_pos - 0.5) * 2

    # Z-score
    z20 = _safe_div(c - _sma(c, 20), c.rolling(20, min_periods=1).std())
    z_score = (z20 / 3).clip(-1, 1)

    # Williams %R
    wr = _safe_div(high14 - c, high14 - low14) * -100
    wr_score = (wr + 50) / 50  # [-1, 1]

    # Composite: average of all mean-reversion indicators
    composite = (
        0.25 * rsi_score
        + 0.20 * stoch_score
        + 0.20 * bb_score
        + 0.20 * z_score
        + 0.15 * wr_score
    ).clip(-1, 1)

    return composite.fillna(0.0)


# ═══════════════════════════════════════════════════════════════════
# 6. BREAKOUT READINESS INDEX
# ═══════════════════════════════════════════════════════════════════

def breakout_readiness_index(df: pd.DataFrame) -> pd.Series:
    """Pre-breakout tension scoring.

    Measures how "ready" a stock is to break out based on:
    - Bollinger squeeze tightness (volatility compression)
    - Price coiling near resistance
    - Rising volume on tests of resistance
    - ADX declining then starting to rise (energy building)

    Score: 0 = not ready, 1.0 = imminent breakout
    """
    c, h, l = df["close"], df["high"], df["low"]
    v = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)

    # 1. Volatility compression: ATR contracting
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_short = tr.rolling(5, min_periods=1).mean()
    atr_long = tr.rolling(40, min_periods=5).mean()
    compression = (1 - _safe_div(atr_short, atr_long)).clip(0, 1)

    # 2. Price coiling near resistance (within 1 ATR of 20-bar high)
    resistance = h.rolling(20, min_periods=5).max()
    dist_to_res = _safe_div(resistance - c, atr_long)
    near_resistance = (1 - dist_to_res.clip(0, 3) / 3).clip(0, 1)

    # 3. Rising volume on approach to resistance
    vol_sma = _sma(v, 20)
    vol_ratio = _safe_div(v, vol_sma)
    vol_near_res = vol_ratio * (dist_to_res < 1).astype(float)
    vol_buildup = vol_near_res.rolling(5, min_periods=1).mean().clip(0, 3) / 3

    # 4. ADX turning up (energy building after consolidation)
    if "adx_14" in df.columns:
        adx = df["adx_14"]
    else:
        plus_dm = h.diff().where((h.diff() > -l.diff()) & (h.diff() > 0), 0.0)
        minus_dm = (-l.diff()).where((-l.diff() > h.diff()) & (-l.diff() > 0), 0.0)
        atr14 = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = _safe_div(100 * _ema(plus_dm, 14), atr14)
        minus_di = _safe_div(100 * _ema(minus_dm, 14), atr14)
        dx = _safe_div(100 * (plus_di - minus_di).abs(), plus_di + minus_di)
        adx = _ema(dx, 14)

    adx_slope = adx - adx.shift(3)
    adx_turning = ((adx < 25) & (adx_slope > 0)).astype(float)

    composite = (
        0.30 * compression
        + 0.25 * near_resistance
        + 0.25 * vol_buildup
        + 0.20 * adx_turning
    ).clip(0, 1)

    return composite.fillna(0.0)


# ═══════════════════════════════════════════════════════════════════
# 7. MOMENTUM QUALITY SCORE
# ═══════════════════════════════════════════════════════════════════

def momentum_quality_score(df: pd.DataFrame) -> pd.Series:
    """Distinguish sustainable momentum from fading/exhausted moves.

    High quality momentum has:
    - Increasing volume on trend bars
    - Decreasing volume on pullbacks
    - Price making higher highs/lows
    - MACD histogram expanding
    - RSI not yet overbought

    Score: 0 = fading/exhausted, 1.0 = fresh high-quality momentum
    """
    c, h, l = df["close"], df["high"], df["low"]
    v = df["volume"] if "volume" in df.columns else pd.Series(1.0, index=df.index)

    # 1. Volume confirmation: volume expands on up bars
    up_bar = (c > c.shift(1)).astype(float)
    vol_on_up = (v * up_bar).rolling(10, min_periods=1).sum()
    vol_on_dn = (v * (1 - up_bar)).rolling(10, min_periods=1).sum()
    vol_confirm = _safe_div(vol_on_up, vol_on_up + vol_on_dn).clip(0, 1)

    # 2. Higher highs and higher lows
    hh = (h > h.rolling(5, min_periods=1).max().shift(1)).astype(float)
    hl = (l > l.rolling(5, min_periods=1).min().shift(1)).astype(float)
    trend_structure = (hh + hl) / 2

    # 3. MACD histogram expanding
    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    macd = ema12 - ema26
    macd_signal = _ema(macd, 9)
    hist = macd - macd_signal
    hist_expanding = (hist.abs() > hist.abs().shift(1)).astype(float)
    hist_positive = (hist > 0).astype(float)
    macd_quality = hist_expanding * 0.5 + hist_positive * 0.5

    # 4. RSI sweet spot (40-70 = sustainable, >80 = exhausted)
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rsi = 100 - _safe_div(100, 1 + _safe_div(gain, loss))
    rsi_quality = pd.Series(0.0, index=df.index)
    rsi_quality = rsi_quality.where(~((rsi >= 40) & (rsi <= 70)), 1.0)
    rsi_quality = rsi_quality.where(~((rsi > 70) & (rsi <= 80)), 0.5)
    # >80 or <30 = exhausted
    rsi_quality = rsi_quality.where(~(rsi > 80), 0.1)

    composite = (
        0.30 * vol_confirm
        + 0.25 * trend_structure.rolling(5, min_periods=1).mean()
        + 0.25 * macd_quality
        + 0.20 * rsi_quality
    ).clip(0, 1)

    return composite.fillna(0.5)


# ═══════════════════════════════════════════════════════════════════
# MASTER FUNCTION — compute all composites
# ═══════════════════════════════════════════════════════════════════

def compute_composite_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all 7 composite indicator columns to the DataFrame.

    Expects OHLCV columns: open, high, low, close, volume.

    Returns the same DataFrame with new columns:
        comp_squeeze_momentum
        comp_vol_price_div
        comp_trend_alignment
        comp_institutional_acc
        comp_mean_rev_extreme
        comp_breakout_readiness
        comp_momentum_quality
    """
    out = df.copy()

    if len(df) < 20:
        for col in COMPOSITE_COLUMNS:
            out[col] = 0.0
        return out

    out["comp_squeeze_momentum"] = squeeze_momentum_composite(df)
    out["comp_vol_price_div"] = volume_price_divergence(df)
    out["comp_trend_alignment"] = trend_alignment_score(df)
    out["comp_institutional_acc"] = institutional_accumulation(df)
    out["comp_mean_rev_extreme"] = mean_reversion_extremity(df)
    out["comp_breakout_readiness"] = breakout_readiness_index(df)
    out["comp_momentum_quality"] = momentum_quality_score(df)

    # Replace inf/nan
    for col in COMPOSITE_COLUMNS:
        out[col] = out[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    return out


# Canonical list of composite feature column names
COMPOSITE_COLUMNS: list[str] = [
    "comp_squeeze_momentum",
    "comp_vol_price_div",
    "comp_trend_alignment",
    "comp_institutional_acc",
    "comp_mean_rev_extreme",
    "comp_breakout_readiness",
    "comp_momentum_quality",
]
