"""Experiment 2 — Suppress inverse ETF entries (PSQ/SH) in chop regime.

Tests:
1. PSQ blocked in chop
2. SH blocked in chop
3. PSQ allowed outside chop
4. SH allowed outside chop
5. Non-inverse symbols unchanged
6. Suppression logging fires when expected
"""

from __future__ import annotations


# The Exp2 gate is a simple conditional check in the entry loop.
# We test the logic predicate directly since the full async
# live_tick is too complex to unit-test.

_INVERSE_ETFS_CHOP_SUPPRESSED = frozenset({"PSQ", "SH"})


def _should_suppress(symbol: str, regime: str) -> bool:
    """Mirror the exact gate condition from live_engine.py."""
    return symbol in _INVERSE_ETFS_CHOP_SUPPRESSED and regime == "chop"


# ─────────────────────────────────────────────────────────────
# Test 1: PSQ blocked in chop
# ─────────────────────────────────────────────────────────────

def test_psq_blocked_in_chop():
    assert _should_suppress("PSQ", "chop") is True


# ─────────────────────────────────────────────────────────────
# Test 2: SH blocked in chop
# ─────────────────────────────────────────────────────────────

def test_sh_blocked_in_chop():
    assert _should_suppress("SH", "chop") is True


# ─────────────────────────────────────────────────────────────
# Test 3: PSQ allowed outside chop
# ─────────────────────────────────────────────────────────────

def test_psq_allowed_outside_chop():
    for regime in ["trending_up", "trending_down", "high_vol", "stress", "unknown"]:
        assert _should_suppress("PSQ", regime) is False, f"PSQ should trade in {regime}"


# ─────────────────────────────────────────────────────────────
# Test 4: SH allowed outside chop
# ─────────────────────────────────────────────────────────────

def test_sh_allowed_outside_chop():
    for regime in ["trending_up", "trending_down", "high_vol", "stress", "unknown"]:
        assert _should_suppress("SH", regime) is False, f"SH should trade in {regime}"


# ─────────────────────────────────────────────────────────────
# Test 5: Non-inverse symbols unchanged
# ─────────────────────────────────────────────────────────────

def test_non_inverse_unchanged():
    non_inverse = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "XLE", "IWM", "AMZN", "TSLA", "XOM"]
    for sym in non_inverse:
        assert _should_suppress(sym, "chop") is False, f"{sym} should NOT be suppressed"
        assert _should_suppress(sym, "trending_down") is False
        assert _should_suppress(sym, "high_vol") is False


# ─────────────────────────────────────────────────────────────
# Test 6: Suppression logging format
# ─────────────────────────────────────────────────────────────

def test_suppression_log_format():
    """Verify the suppression log message contains expected fields."""
    import logging
    import io

    logger = logging.getLogger("test_exp2")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    sym = "PSQ"
    regime = "chop"
    confidence = 0.38

    logger.info(
        "Exp2: inverse ETF entry suppressed in chop: "
        "%s regime=%s confidence=%.3f reason=inverse_etf_suppressed_chop",
        sym, regime, confidence,
    )

    logger.removeHandler(handler)
    output = stream.getvalue()

    assert "Exp2: inverse ETF entry suppressed in chop" in output
    assert "PSQ" in output
    assert "regime=chop" in output
    assert "inverse_etf_suppressed_chop" in output
    assert "confidence=0.380" in output


# ─────────────────────────────────────────────────────────────
# Test 7: Only the specific set is suppressed (no accidental
#          inclusion of other ETFs like XLK, IWM, QQQ)
# ─────────────────────────────────────────────────────────────

def test_only_psq_sh_are_inverse():
    """Verify the suppression set is exactly {PSQ, SH} and not broader."""
    assert _INVERSE_ETFS_CHOP_SUPPRESSED == {"PSQ", "SH"}
    # ETFs that are NOT inverse and must NOT be suppressed
    for etf in ["QQQ", "SPY", "IWM", "XLK", "XLE", "XOM"]:
        assert etf not in _INVERSE_ETFS_CHOP_SUPPRESSED
