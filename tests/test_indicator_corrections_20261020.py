"""Audit 2026-10-20 indicator check — corrections to live decision inputs.

An independent numerical check of the live indicators (repo functions vs
TA-Lib and re-implementations of their stated formulas) found four defects
that change live entries. These tests pin the corrected behaviour:

1. BreakoutScanner's squeeze test compared the Bollinger HALF-width with the
   Keltner FULL width, so a 2σ band inside a 3·ATR channel counted as a
   squeeze. The textbook test is BB(2σ) inside KC(1.5·ATR), half-width vs
   half-width.
2. The pure-breakout path forced every signal LONG, buying breakdowns below
   the pivot low (direction -1) and directionless signals (0). Only upward
   signals are taken now (BreakoutStrategy and the live engine loop).
3. Breakout readiness compared an EMA-smoothed ADX (~1.4x Wilder) with
   Wilder's "ADX < 25" level. Readiness now uses Wilder's ADX; the
   ``adx_14`` ML feature is unchanged (the saved models were trained on it).
4. A price that does not move scored as a tight coil at resistance: 20
   identical bars gave readiness ~0.57 / squeeze ~0.58 and a buy direction.
   No movement now scores 0.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from backend.organism.alpha_scanner import AlphaScanner
from backend.organism.breakout_scanner import BreakoutScanner
from backend.organism.composite_indicators import (
    _adx_wilder,
    breakout_readiness_index,
    squeeze_momentum_composite,
)
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.ml_features import compute_ml_features


def _walk(n: int = 400, seed: int = 0, price: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.standard_normal(n) * 0.001))
    open_ = np.r_[price, close[:-1]]
    span = np.abs(rng.standard_normal(n)) * 0.0006 * close
    high = np.maximum(open_, close) + span * rng.random(n)
    low = np.minimum(open_, close) - span * rng.random(n)
    volume = np.round(1000 * np.exp(rng.standard_normal(n) * 0.5))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-10-19 13:30", periods=n, freq="1min", tz="UTC"),
        "open": open_, "high": high, "low": low, "close": close, "volume": volume,
    })


def _freeze_tail(df: pd.DataFrame, k: int) -> pd.DataFrame:
    d = df.copy()
    p = float(d.loc[len(d) - k - 1, "close"])
    d.loc[len(d) - k:, ["open", "high", "low", "close"]] = p
    d.loc[len(d) - k:, "volume"] = 1.0
    return d


# ── 1. Breakout squeeze: half-width vs half-width ───────────────────


def _textbook_squeeze_fired(sc: BreakoutScanner, close, high, low) -> bool:
    """Independent statement of the rule: 5 bars ago the Bollinger band
    (SMA ± 2σ) sat inside the Keltner channel (SMA ± 1.5·ATR), widths are
    expanding now, and the current width is in the bottom 35% of 120 bars."""
    period = sc.BB_PERIOD
    s = pd.Series(close)
    sma = s.rolling(period, min_periods=1).mean().to_numpy()
    std = s.rolling(period, min_periods=2).std().fillna(0.0).to_numpy()
    half_bb = 2 * std / (sma + 1e-10)
    atr = sc._rolling_atr(high, low, close, sc.ATR_SHORT)
    half_kc = 1.5 * atr / (sma + 1e-10)
    recent = half_bb[-min(120, len(half_bb)):]
    pct = np.sum(recent <= half_bb[-1]) / len(recent)
    return bool(half_bb[-5] < half_kc[-5] and half_bb[-1] > half_bb[-3] and pct < 0.35)


def test_squeeze_fires_only_when_bollinger_sits_inside_keltner():
    sc = BreakoutScanner(top_n=8)
    sc.BB_PERIOD, sc.ATR_SHORT = 10, 5  # the live (approved baseline) periods
    agree = fired = 0
    for seed in range(300):
        d = _walk(n=200, seed=seed)
        c, h, l = d["close"].to_numpy(), d["high"].to_numpy(), d["low"].to_numpy()
        _, got = sc._squeeze_detector(c, h, l)
        want = _textbook_squeeze_fired(sc, c, h, l)
        agree += got == want
        fired += got
    assert agree == 300
    assert fired > 0  # the test exercises the firing branch


def test_squeeze_keltner_side_is_half_width():
    src = inspect.getsource(BreakoutScanner._squeeze_detector)
    assert "kc_width = 1.5 * atr_arr / (sma + 1e-10)" in src
    assert "2.0 * 1.5 * atr_arr" not in src


# ── 2. Pure breakout takes only upward signals ──────────────────────


def test_live_pure_breakout_loop_skips_non_upward_signals():
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    guard = 'if float(getattr(bs, "direction", 1.0) or 0.0) <= 0.0:'
    assert guard in src
    # The guard sits inside the pure-breakout loop, after the 0.55 gate and
    # before the shared entry gates.
    loop = src.index("for bs in _breakout_iter:")
    gate = src.index("if bs.composite_score < 0.55:", loop)
    shared = src.index("_passes_entry_gates(", gate)
    assert loop < gate < src.index(guard, gate) < shared


# ── 3. Readiness uses Wilder's ADX ──────────────────────────────────


def _reference_wilder_adx(h, l, c, n=14) -> np.ndarray:
    """Textbook Wilder ADX with TA-Lib-style seeding (sums over the first
    period, then Wilder recursion). Written independently of the module."""
    h, l, c = map(np.asarray, (h, l, c))
    m = len(c)
    tr = np.zeros(m); pdm = np.zeros(m); mdm = np.zeros(m)
    for i in range(1, m):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(m, np.nan); sp = np.full(m, np.nan); sm = np.full(m, np.nan)
    atr[n] = tr[1:n + 1].sum(); sp[n] = pdm[1:n + 1].sum(); sm[n] = mdm[1:n + 1].sum()
    for i in range(n + 1, m):
        atr[i] = atr[i - 1] - atr[i - 1] / n + tr[i]
        sp[i] = sp[i - 1] - sp[i - 1] / n + pdm[i]
        sm[i] = sm[i - 1] - sm[i - 1] / n + mdm[i]
    pdi = 100 * sp / atr
    mdi = 100 * sm / atr
    with np.errstate(invalid="ignore", divide="ignore"):
        dx = np.where(pdi + mdi > 0, 100 * np.abs(pdi - mdi) / (pdi + mdi), 0.0)
    adx = np.full(m, np.nan)
    adx[2 * n - 1] = np.nanmean(dx[n:2 * n])
    for i in range(2 * n, m):
        adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx


def test_wilder_adx_matches_textbook_after_warmup():
    for seed in range(5):
        d = _walk(n=500, seed=seed)
        got = _adx_wilder(d["high"], d["low"], d["close"], 14).to_numpy()
        ref = _reference_wilder_adx(d["high"], d["low"], d["close"], 14)
        np.testing.assert_allclose(got[300:], ref[300:], rtol=0, atol=1e-6)


def test_wilder_adx_counts_equal_moves_as_no_directional_movement():
    # Every bar expands the range by the same amount up and down: no
    # directional movement, so ADX stays 0 (the old -DM rule credited ties
    # to -DM and manufactured a downtrend).
    n = 60
    mid = np.full(n, 100.0)
    half = 0.10 + 0.01 * np.arange(n)
    h, l = pd.Series(mid + half), pd.Series(mid - half)
    adx = _adx_wilder(h, l, pd.Series(mid), 14)
    assert float(adx.abs().max()) == 0.0


def test_readiness_ignores_the_ema_adx_feature_column():
    d = _walk(n=400, seed=11)
    plain = breakout_readiness_index(d)
    with_feature = d.assign(adx_14=99.0)  # an adx_14 column must no longer leak in
    pd.testing.assert_series_equal(plain, breakout_readiness_index(with_feature))


# ── 4. No movement, no signal ───────────────────────────────────────


@pytest.mark.parametrize("k", [5, 20, 39])
def test_unmoving_price_scores_zero_readiness(k):
    d = _freeze_tail(_walk(n=500, seed=3), k)
    assert float(breakout_readiness_index(d).iloc[-1]) == 0.0


def test_unmoving_price_scores_zero_squeeze_over_the_band_window():
    d = _freeze_tail(_walk(n=500, seed=3), 20)
    assert float(squeeze_momentum_composite(d).iloc[-1]) == 0.0


def test_unmoving_price_never_yields_a_buy_direction():
    for seed in (3, 5, 8):
        for k in (20, 39):
            d = _freeze_tail(_walk(n=500, seed=seed), k)
            row = compute_ml_features(d, bars_per_day=390).iloc[-1]
            assert row["comp_breakout_readiness"] == 0.0
            assert AlphaScanner()._observable_direction(row) == 0.0


def test_moving_price_still_scores():
    d = _walk(n=500, seed=4)
    r = breakout_readiness_index(d)
    q = squeeze_momentum_composite(d)
    assert float(r.iloc[200:].max()) > 0.0
    assert float(q.iloc[200:].min()) > 0.0
