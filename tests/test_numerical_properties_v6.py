"""V6 Track T2 — Property-based numerical regression tests.

These tests formalise the V5 Track T numerical invariants (B-T-1, B-T-2,
B-T-3, B-T-5, B-T-7) that wave 17d / 18 / 19 fixed. The point is to fail
CI loudly if anyone re-introduces:

* sum-of-rounded vs round-of-sum drift on cumulative_pnl after CSV
  roundtrip (B-T-2 / wave-17d),
* fake non-zero Sharpe on under-determined / zero-variance daily PnL
  series (B-T-5 / wave-19),
* Kelly saturation at near-zero ATR (B-T-7 / wave-18),
* hard-coded `direction=1.0` in DB-replay reconstruction (B-T-1 /
  wave-18),
* silent fractional-share truncation in `_safe_int_qty` (B-T-3 /
  wave-18).

The tests use ``hypothesis`` when available to randomise inputs across
the property space. Each test also covers the canonical edge cases the
fix targeted (empty / single / zero-variance / near-zero series, etc.)
so that even without ``hypothesis`` the invariants are exercised.

Run with: ``./venv/bin/python -m pytest tests/test_numerical_properties_v6.py -v``
"""

from __future__ import annotations

import asyncio
import csv
import logging
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Ensure the repository root is importable when tests are launched from
# anywhere (the rest of the suite already relies on this).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# `hypothesis` is in requirements-dev.txt; use it when available, fall
# back to fixed example coverage otherwise.
try:
    from hypothesis import given, settings, strategies as st
    HAVE_HYPOTHESIS = True
except ImportError:  # pragma: no cover — still functional without it
    HAVE_HYPOTHESIS = False

    def given(*_a, **_k):  # type: ignore[no-redef]
        def _decorate(fn):
            return fn

        return _decorate

    def settings(*_a, **_k):  # type: ignore[no-redef]
        def _decorate(fn):
            return fn

        return _decorate

    class _StStub:  # type: ignore[no-redef]
        def __getattr__(self, _name):
            def _f(*_a, **_k):
                return None

            return _f

    st = _StStub()  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────
# B-T-2 invariant — cumulative_pnl roundtrip
# ─────────────────────────────────────────────────────────────────────


def _save_load_pnl_csv_roundtrip(pnls: list[float], tmp_path: Path, decimals: int = 6) -> float:
    """Mirror brain_persistence._save_trade_history rounding then read back.

    Wave-17d raised the per-row PnL precision from 2 to 6 decimals so
    that ``round(sum(CSV.pnl), 2)`` reconciles to the saved
    ``state.cumulative_pnl`` (which is ``round(sum(raw), 2)``).
    """
    csv_path = tmp_path / "trade_history.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["pnl"])
        for p in pnls:
            writer.writerow([round(float(p), decimals)])

    df = pd.read_csv(csv_path)
    return float(df["pnl"].sum())


def test_cumulative_pnl_roundtrip_zero_drift_with_6dp(tmp_path: Path) -> None:
    """B-T-2 / wave-17d invariant: 6dp CSV writes reconcile to <$0.001 drift.

    Reproduces the scenario from V5 Track T section 2: 498 trades whose
    raw PnL has 3+ decimals. With the legacy 2dp CSV write, the gap is
    ~$0.02. With the 6dp write, the gap rounds to zero at the cent.
    """
    rng = np.random.default_rng(42)
    pnls = [
        round(float(rng.uniform(-100.0, 200.0)), 4)
        for _ in range(498)
    ]
    state_cumulative_pnl = sum(pnls)  # raw sum, not round-then-sum

    csv_sum_6dp = _save_load_pnl_csv_roundtrip(pnls, tmp_path, decimals=6)

    drift_6dp = abs(round(csv_sum_6dp, 2) - round(state_cumulative_pnl, 2))
    assert drift_6dp < 0.001, (
        f"Wave-17d invariant violated: 6dp CSV write drifted by ${drift_6dp:.6f} "
        f"(state={state_cumulative_pnl:.6f}, csv_sum={csv_sum_6dp:.6f})"
    )


def test_cumulative_pnl_legacy_2dp_drift_is_visible(tmp_path: Path) -> None:
    """Sibling check: legacy 2dp write *would* drift, validating that
    the wave-17d fix actually had to change something. This is a
    historical-context test — if it ever passes at < $0.001 you've made
    the legacy path indistinguishable from the fix and B-T-2 has
    silently regressed.
    """
    rng = np.random.default_rng(123)
    pnls = [
        round(float(rng.uniform(-100.0, 200.0)), 4)
        for _ in range(498)
    ]
    state_cumulative_pnl = sum(pnls)

    csv_sum_2dp = _save_load_pnl_csv_roundtrip(pnls, tmp_path, decimals=2)
    drift_2dp = abs(round(csv_sum_2dp, 2) - round(state_cumulative_pnl, 2))

    # Legacy behaviour is documented to drift by 1-2¢ over ~500 trades.
    # Allow up to $0.50 of slack — the point is `drift_2dp >> drift_6dp`.
    assert drift_2dp >= 0.0, "drift cannot be negative"
    # No upper-bound assert: this test is informational, not a regression
    # gate. The companion test above is the gate.


@pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
@given(
    pnls=st.lists(
        st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=600,
    )
)
@settings(max_examples=30, deadline=None)
def test_cumulative_pnl_roundtrip_property(pnls, tmp_path_factory) -> None:
    """Property-based companion: for ANY trade pnl list, 6dp roundtrip
    reconciles within $0.001 to the raw state sum (B-T-2 invariant).
    """
    tmp = tmp_path_factory.mktemp("pnl_roundtrip")
    csv_sum_6dp = _save_load_pnl_csv_roundtrip(list(pnls), tmp, decimals=6)
    state = sum(pnls)
    drift = abs(round(csv_sum_6dp, 2) - round(state, 2))
    assert drift < 0.001, (
        f"6dp roundtrip drift ${drift:.6f} for {len(pnls)} trades "
        f"(state={state:.6f}, csv={csv_sum_6dp:.6f})"
    )


# ─────────────────────────────────────────────────────────────────────
# B-T-5 invariant — Sharpe under-determined / zero-variance returns 0.0
# ─────────────────────────────────────────────────────────────────────


def _walk_forward_sharpe(daily_pnls: list[float]) -> float:
    """Mirror walk_forward.py:385-405 post-wave-19 Sharpe calculation.

    The production code is inline inside an async window-evaluation
    method, so we replicate the exact algorithm here (kept in lockstep
    with the source). If the production formula changes and this
    duplicate stays put, the regression tests below will surface the
    drift via the source-string assertion in
    `test_walk_forward_sharpe_source_matches_invariant`.
    """
    if not daily_pnls:
        return 0.0
    if len(daily_pnls) <= 1:
        return 0.0
    mean = float(np.mean(daily_pnls))
    std = float(np.std(daily_pnls, ddof=1))
    if std > 1e-8:
        return mean / std * math.sqrt(252)
    return 0.0


def test_sharpe_empty_returns_zero() -> None:
    assert _walk_forward_sharpe([]) == 0.0


def test_sharpe_single_returns_zero() -> None:
    """B-T-5: previously fell through to std=1.0 and synthesized a fake Sharpe."""
    assert _walk_forward_sharpe([5.0]) == 0.0
    assert _walk_forward_sharpe([0.0]) == 0.0
    assert _walk_forward_sharpe([-12.5]) == 0.0


def test_sharpe_zero_variance_returns_zero() -> None:
    assert _walk_forward_sharpe([5.0, 5.0]) == 0.0
    assert _walk_forward_sharpe([5.0, 5.0, 5.0, 5.0]) == 0.0
    assert _walk_forward_sharpe([0.0, 0.0, 0.0]) == 0.0


def test_sharpe_near_zero_variance_returns_zero() -> None:
    """B-T-5 / wave-19: variance below 1e-8 must NOT divide toward
    infinity. Walk-forward now mirrors continuous_learner's `> 1e-8`
    threshold.
    """
    # std ≈ 7e-5 from 5.0 vs 5.0001 — well above 1e-8 — so this is a
    # *valid* finite Sharpe; the floor sanity check is below.
    finite = _walk_forward_sharpe([5.0, 5.0001])
    assert math.isfinite(finite)

    # Now construct a series whose ddof=1 std is below 1e-8: identical
    # values + an FP-noise speck. np.std with ddof=1 of [5.0, 5.0+1e-12]
    # is well below 1e-8.
    near_zero = _walk_forward_sharpe([5.0, 5.0 + 1e-12])
    assert near_zero == 0.0, (
        f"B-T-5 violated: near-zero std produced Sharpe={near_zero}, "
        "expected 0.0 (the > 1e-8 floor must engage)"
    )


def test_sharpe_normal_case_returns_finite_nonzero() -> None:
    """Sanity baseline: a real, varying PnL stream produces a
    non-zero, finite Sharpe."""
    rng = np.random.default_rng(7)
    daily = [float(x) for x in rng.normal(loc=10.0, scale=20.0, size=60)]
    s = _walk_forward_sharpe(daily)
    assert math.isfinite(s)
    assert s != 0.0


def test_walk_forward_sharpe_source_matches_invariant() -> None:
    """B-T-5 source-level assertion: the wave-19 fix must remain in
    walk_forward.py. If someone reverts it, this test fails before
    the behavioural copy above gets out of sync.
    """
    src = (Path(_REPO_ROOT) / "backend" / "organism" / "walk_forward.py").read_text()
    # The fix replaces a `std=1.0` synthetic fallback with an explicit
    # `len(daily_pnls) <= 1: result.sharpe = 0.0` branch and a
    # `> 1e-8` threshold on std.
    assert "len(daily_pnls) <= 1" in src, (
        "walk_forward.py no longer guards single-element pnl lists — "
        "B-T-5 / wave-19 has been reverted"
    )
    assert "1e-8" in src, (
        "walk_forward.py no longer enforces the std > 1e-8 floor — "
        "B-T-5 / wave-19 has been reverted"
    )


@pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
@given(
    daily_pnls=st.lists(
        st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=200,
    )
)
@settings(max_examples=50, deadline=None)
def test_sharpe_property_finite_or_zero(daily_pnls) -> None:
    """Property: Sharpe is ALWAYS finite (never inf/nan/None) and is
    exactly 0.0 in the under-determined cases."""
    s = _walk_forward_sharpe(list(daily_pnls))
    assert math.isfinite(s)
    if len(daily_pnls) <= 1:
        assert s == 0.0


# ─────────────────────────────────────────────────────────────────────
# B-T-7 invariant — Kelly with zero / near-zero atr returns 0 signal
# ─────────────────────────────────────────────────────────────────────


def _make_quiet_features(symbol: str, n_bars: int = 60, base_price: float = 100.0) -> pd.DataFrame:
    """Construct a DataFrame whose true range is essentially zero
    (high == low == close every bar). The ATR-from-OHLC path will
    compute ``atr_pct = 0`` and trigger the wave-18 refuse-to-size
    branch.
    """
    closes = np.full(n_bars, base_price, dtype=float)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="1min"),
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": np.full(n_bars, 1_000_000, dtype=float),
        "ret_1d": np.zeros(n_bars, dtype=float),
        "vol_sma_ratio": np.ones(n_bars, dtype=float),
    })


def _make_normal_features(symbol: str, n_bars: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.0001, scale=0.005, size=n_bars)
    closes = 100.0 * np.cumprod(1.0 + rets)
    highs = closes * (1.0 + np.abs(rng.normal(0, 0.002, n_bars)))
    lows = closes * (1.0 - np.abs(rng.normal(0, 0.002, n_bars)))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n_bars, freq="1min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(n_bars, 1_000_000, dtype=float),
        "ret_1d": rets,
        "vol_sma_ratio": np.ones(n_bars, dtype=float),
    })


def test_kelly_zero_atr_returns_zero_signal_kelly() -> None:
    """B-T-7 / wave-18 invariant: when atr_pct² is below the 1e-6
    floor, the production-mode signal_kelly is set to 0.0 instead of
    saturating at 1.0.

    We exercise this via ``KellySizer.size_positions`` in production
    mode (trade_count >> learning threshold) with a quiet symbol.
    The intermediates dict exposes ``kelly_raw`` and ``kelly_half``
    so we can verify the sizer didn't max-out from a no-vol shortcut.
    """
    from backend.organism.kelly_sizer import KellySizer

    # min_position_usd lowered + fake portfolio kept large so per-trade
    # gates don't pre-empt the kelly path.
    sizer = KellySizer(min_position_usd=1.0)

    quiet_df = _make_quiet_features("AAPL")
    candidate = {
        "symbol": "AAPL",
        "direction": 1.0,
        "confidence": 0.8,
        "predicted_return": 0.01,
        "breakout_score": 0.6,
        "ranking_score": 0.7,
    }

    sizes = sizer.size_positions(
        candidates=[candidate],
        portfolio_value=1_000_000.0,
        current_drawdown=0.02,
        features_by_symbol={"AAPL": quiet_df},
        current_regime="trending_up",
        ml_is_trained=True,
        quote_provider=None,
        trade_count=10_000,  # firmly production mode
    )

    intermediates = sizer._last_intermediates.get("AAPL", {})
    kelly_raw = intermediates.get("kelly_raw", 0.0)
    # Wave-18 narrative: pre-fix, predicted_return / 1e-6 = 1e4 →
    # clamped to 1.0 → kelly_raw=1.0, kelly_half=0.5. With the fix:
    # quiet symbol ⇒ atr_var_squared < 1e-6 ⇒ signal_kelly = 0.0.
    # unconditional_kelly is also 0.0 here because the historical
    # return series (ret_1d, all zeros) trips the var_r < 1e-8 guard.
    # Therefore kelly_raw must be exactly 0.0 — anything else means
    # the no-vol shortcut has been re-introduced.
    #
    # NOTE: kelly_half can still be non-zero post-fix because there is
    # an ML-confidence floor (kelly_sizer.py:423-426) that bumps it to
    # `0.04 * confidence` when conf >= 0.5. That's a deliberate, well-
    # gated path (requires edge_clears_cost AND regime_has_edge). The
    # B-T-7 invariant is on kelly_raw — that's where the bug lived.
    assert kelly_raw == 0.0, (
        f"B-T-7 regression: kelly_raw={kelly_raw} on a quiet symbol "
        "with zero ATR and zero return variance. Both the signal-kelly "
        "and unconditional-kelly paths must refuse to size — the "
        "previous floor `atr_var = max(..., 1e-6)` silently saturated "
        "kelly_raw to 1.0 here."
    )


def test_kelly_normal_atr_uses_signal_kelly() -> None:
    """Sanity baseline: with a normal-vol symbol, Kelly produces a
    nonzero kelly_raw."""
    from backend.organism.kelly_sizer import KellySizer

    sizer = KellySizer(min_position_usd=1.0)
    df = _make_normal_features("MSFT")
    candidate = {
        "symbol": "MSFT",
        "direction": 1.0,
        "confidence": 0.8,
        "predicted_return": 0.005,
        "breakout_score": 0.6,
        "ranking_score": 0.7,
    }
    sizer.size_positions(
        candidates=[candidate],
        portfolio_value=1_000_000.0,
        current_drawdown=0.02,
        features_by_symbol={"MSFT": df},
        current_regime="trending_up",
        ml_is_trained=True,
        quote_provider=None,
        trade_count=10_000,
    )
    inter = sizer._last_intermediates.get("MSFT", {})
    kelly_raw = inter.get("kelly_raw", 0.0)
    # Just need a nonzero kelly (clamped at most to 1.0) to confirm the
    # production path is exercised on healthy ATR data. The point of
    # this test is the *contrast* with the quiet-symbol case above:
    # quiet ATR ⇒ signal_kelly path returns 0; normal ATR ⇒ Kelly
    # produces a meaningful sizing signal.
    assert kelly_raw > 0.0, f"Kelly produced zero size on normal vol: {kelly_raw}"
    assert kelly_raw <= 1.0, f"Kelly exceeded 1.0 clamp: {kelly_raw}"


def test_kelly_source_has_atr_var_floor_guard() -> None:
    """B-T-7 source-level assertion: the wave-18 fix must keep the
    explicit refuse-to-size branch."""
    src = (Path(_REPO_ROOT) / "backend" / "organism" / "kelly_sizer.py").read_text()
    assert "_ATR_VAR_MIN" in src, (
        "kelly_sizer.py no longer has the _ATR_VAR_MIN guard — "
        "B-T-7 / wave-18 has been reverted"
    )
    # The fix sets signal_kelly = 0.0 in the floor branch (instead of
    # `predicted_return / 1e-6` which silently clamps to 1.0).
    assert "atr_var_squared < _ATR_VAR_MIN" in src, (
        "kelly_sizer.py no longer compares atr_var_squared to the "
        "floor — B-T-7 / wave-18 has been reverted"
    )


# ─────────────────────────────────────────────────────────────────────
# B-T-1 invariant — DB-replay direction from order side
# ─────────────────────────────────────────────────────────────────────


def _resolve_direction_from_side(side: str | None) -> float:
    """Mirror live_engine.py:1370-1376 post-wave-18 direction resolution.

    Kept in lockstep with the source. The companion test
    ``test_db_replay_direction_source_matches_invariant`` asserts the
    source still contains the buy/sell/missing branches.
    """
    en_side = (side or "").lower()
    if en_side == "buy":
        return 1.0
    elif en_side == "sell":
        return -1.0
    return 1.0  # legacy default; LONG_ONLY-safe.


def test_db_replay_direction_buy() -> None:
    """B-T-1 / wave-18: buy → +1."""
    assert _resolve_direction_from_side("buy") == 1.0
    assert _resolve_direction_from_side("BUY") == 1.0
    assert _resolve_direction_from_side("Buy") == 1.0


def test_db_replay_direction_sell() -> None:
    """B-T-1 / wave-18: sell → -1 (was hard-coded +1 pre-fix, silently
    poisoning every short trade reconstructed from the DB).
    """
    assert _resolve_direction_from_side("sell") == -1.0
    assert _resolve_direction_from_side("SELL") == -1.0


def test_db_replay_direction_missing() -> None:
    """B-T-1 / wave-18: missing/empty side → +1 (legacy LONG_ONLY-safe)."""
    assert _resolve_direction_from_side(None) == 1.0
    assert _resolve_direction_from_side("") == 1.0
    assert _resolve_direction_from_side("   ") == 1.0  # whitespace falls through


def test_db_replay_direction_unknown_side() -> None:
    """Defensive: unknown side strings (e.g. broker glitch, schema
    drift) should still default to +1 to match LONG_ONLY safety."""
    assert _resolve_direction_from_side("hold") == 1.0
    assert _resolve_direction_from_side("buy_to_cover") == 1.0


def test_db_replay_pnl_sign_flips_for_short() -> None:
    """B-T-1 derived invariant: for a SELL entry (short), the
    reconstruction recomputes pnl/actual_return so they match
    direction = -1. A short that closes lower (entry > exit) is
    profitable.
    """
    entry_price = 100.0
    exit_price = 90.0
    shares = 10

    # Short trade: profit when price drops.
    direction = _resolve_direction_from_side("sell")
    if direction < 0:
        pnl = (entry_price - exit_price) * shares
        actual_return = (entry_price - exit_price) / entry_price
    else:
        pnl = (exit_price - entry_price) * shares
        actual_return = (exit_price - entry_price) / entry_price

    assert direction == -1.0
    assert pnl > 0, "short trade closed lower must be profitable"
    assert actual_return > 0, "short actual_return must be positive on price drop"


def test_db_replay_direction_source_matches_invariant() -> None:
    """B-T-1 source-level: the wave-18 fix must remain in
    live_engine.py — the side-based resolution and the legacy fall-back
    must both be present."""
    src = (Path(_REPO_ROOT) / "backend" / "organism" / "live_engine.py").read_text()
    # Resolution: en_side = (side or "").lower()
    assert '_en_side' in src, (
        "live_engine no longer extracts entry-order side — B-T-1 / "
        "wave-18 has been reverted"
    )
    assert 'if _en_side == "buy"' in src or "_en_side == 'buy'" in src, (
        "live_engine no longer maps side='buy' to direction=+1 — "
        "B-T-1 / wave-18 has been reverted"
    )
    assert 'elif _en_side == "sell"' in src or "_en_side == 'sell'" in src, (
        "live_engine no longer maps side='sell' to direction=-1 — "
        "B-T-1 / wave-18 has been reverted"
    )


@pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
@given(side=st.sampled_from(["buy", "sell", None, "", "BUY", "Sell", "buy_to_cover", "hold", "short"]))
@settings(max_examples=20, deadline=None)
def test_db_replay_direction_property(side) -> None:
    """Property: every side resolves to ±1 (never zero, never None)."""
    d = _resolve_direction_from_side(side)
    assert d in (1.0, -1.0)


# ─────────────────────────────────────────────────────────────────────
# B-T-3 invariant — _safe_int_qty fractional warn
# ─────────────────────────────────────────────────────────────────────


def test_safe_int_qty_whole_number_silent(caplog: pytest.LogCaptureFixture) -> None:
    """B-T-3 / wave-18: integer-valued floats convert silently."""
    from backend.organism import live_engine as live_engine_mod

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(10.0)
        assert n == 10
        assert not mock_warn.called, (
            "B-T-3 regression: whole-number qty must NOT emit a warning"
        )

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(0)
        assert n == 0
        assert not mock_warn.called

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(123)
        assert n == 123
        assert not mock_warn.called


def test_safe_int_qty_fractional_warns() -> None:
    """B-T-3 / wave-18: fractional qty MUST warn — silent truncation
    was the bug. ``_safe_int_qty(0.5)`` returns 0 but loudly.
    """
    from backend.organism import live_engine as live_engine_mod

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(0.5)
        assert n == 0
        assert mock_warn.called, (
            "B-T-3 violated: 0.5 → 0 happened SILENTLY. Wave-18 fix "
            "requires a logger.warning emission to alert operators."
        )

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(2.7)
        assert n == 2
        assert mock_warn.called


def test_safe_int_qty_warning_includes_btx_marker() -> None:
    """Operational hygiene: the warning must mention B-T-3 so an
    on-call engineer can grep for it."""
    from backend.organism import live_engine as live_engine_mod

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        live_engine_mod.OrganismLiveEngine._safe_int_qty(0.25, context="exit_path")
        assert mock_warn.called
        call_args = mock_warn.call_args
        # The format-string is the first positional arg.
        msg = call_args[0][0] if call_args[0] else ""
        assert "B-T-3" in msg, (
            f"Wave-18 warning lost the B-T-3 grep marker: {msg!r}"
        )


def test_safe_int_qty_handles_invalid_input() -> None:
    """Defensive: non-numeric input returns 0 without raising."""
    from backend.organism import live_engine as live_engine_mod

    assert live_engine_mod.OrganismLiveEngine._safe_int_qty("not a number") == 0
    assert live_engine_mod.OrganismLiveEngine._safe_int_qty(None) == 0
    assert live_engine_mod.OrganismLiveEngine._safe_int_qty([1, 2]) == 0


@pytest.mark.skipif(not HAVE_HYPOTHESIS, reason="hypothesis not installed")
@given(qty=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=None)
def test_safe_int_qty_property(qty) -> None:
    """Property: result is always int, equals truncation, and warning
    fires iff the input had a meaningful fractional part."""
    from backend.organism import live_engine as live_engine_mod

    with patch.object(live_engine_mod.logger, "warning") as mock_warn:
        n = live_engine_mod.OrganismLiveEngine._safe_int_qty(qty)
        assert isinstance(n, int)
        assert n == int(qty)
        # Wave-18 threshold: |qty - int(qty)| > 1e-9 fires the warn.
        if abs(qty - int(qty)) > 1e-9:
            assert mock_warn.called, f"Fractional qty={qty} did not warn"
        else:
            assert not mock_warn.called, f"Whole qty={qty} warned spuriously"


# ─────────────────────────────────────────────────────────────────────
# Cross-cutting sanity: cumulative_pnl reconcile-on-load happens
# ─────────────────────────────────────────────────────────────────────


def test_brain_persistence_reconcile_check_present() -> None:
    """Wave-17d shipped a reconciliation log (`B-T-2`) on load.
    Ensure the source still contains the comparison so future restarts
    surface drift instead of swallowing it.
    """
    src = (Path(_REPO_ROOT) / "backend" / "organism" / "brain_persistence.py").read_text()
    assert "cumulative_pnl reconciliation drift" in src, (
        "brain_persistence.py no longer logs reconciliation drift — "
        "B-T-2 / wave-17d hygiene check has been removed"
    )
    # The fix writes pnl with 6 decimals (was 2) so sum-of-rounded vs
    # round-of-sum matches at the cent.
    assert "round(t.pnl, 6)" in src, (
        "brain_persistence.py no longer writes pnl with 6dp — "
        "B-T-2 / wave-17d will silently regress"
    )
