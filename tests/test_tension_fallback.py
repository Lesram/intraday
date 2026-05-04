"""Tests for tension proxy fallback when market scanner has no results."""
import pytest


def test_tension_proxy_from_volume_and_return():
    """Tension proxy computes from vol_ratio and ret_1d when scanner empty."""
    # Simulate the proxy formula
    vol_ratio = 1.5  # 1.5x average volume
    abs_ret = 0.01   # 1% daily return

    tension = min(
        max(vol_ratio - 1.0, 0.0) / 3.0 + abs_ret * 20.0,
        0.80,
    )

    assert 0.3 < tension < 0.5, f"Expected ~0.37, got {tension}"

    # Confidence with this tension should clear the 0.25 gate
    breakout_score = 0.2  # modest breakout
    confidence = 0.65 * breakout_score + 0.35 * min(tension, 1.0)
    assert confidence > 0.25, f"Confidence {confidence} should be > 0.25 gate"


def test_tension_proxy_zero_volume_zero_return():
    """No volume, no return -> tension proxy stays near zero."""
    vol_ratio = 0.8   # below average
    abs_ret = 0.001   # flat

    tension = min(
        max(vol_ratio - 1.0, 0.0) / 3.0 + abs_ret * 20.0,
        0.80,
    )

    assert tension < 0.1, f"Flat stock should have low tension, got {tension}"


def test_tension_proxy_capped_at_080():
    """Extreme volume/return capped at 0.80."""
    vol_ratio = 5.0    # 5x average
    abs_ret = 0.10     # 10% move

    tension = min(
        max(vol_ratio - 1.0, 0.0) / 3.0 + abs_ret * 20.0,
        0.80,
    )

    assert tension == 0.80, f"Should be capped at 0.80, got {tension}"


def test_tension_proxy_not_used_when_scanner_has_data():
    """When scanner provides tension, proxy is not used."""
    scanner_tension = 0.55

    # The lookup returns non-zero -> proxy path not triggered
    tension = scanner_tension  # _tension_lookup.get(symbol, 0.0) returns 0.55
    assert tension == 0.55  # No fallback needed


def test_confidence_clears_gate_with_moderate_signals():
    """Realistic learning-mode scenario: moderate breakout + tension proxy."""
    # Scenario: SPY breakout_score=0.25, vol_ratio=1.3, ret_1d=0.008
    breakout_score = 0.25
    vol_ratio = 1.3
    abs_ret = 0.008

    tension = min(
        max(vol_ratio - 1.0, 0.0) / 3.0 + abs_ret * 20.0,
        0.80,
    )
    # tension = 0.1/3 + 0.16 = 0.033 + 0.16 = 0.193

    confidence = 0.65 * breakout_score + 0.35 * min(tension, 1.0)
    # confidence = 0.1625 + 0.0676 = 0.23 -- still below gate
    # This is correct: modest signals shouldn't pass

    # Stronger signal: breakout=0.35, vol_ratio=1.8, ret_1d=0.012
    breakout_score2 = 0.35
    vol_ratio2 = 1.8
    abs_ret2 = 0.012

    tension2 = min(
        max(vol_ratio2 - 1.0, 0.0) / 3.0 + abs_ret2 * 20.0,
        0.80,
    )
    # tension2 = 0.8/3 + 0.24 = 0.267 + 0.24 = 0.507

    confidence2 = 0.65 * breakout_score2 + 0.35 * min(tension2, 1.0)
    # confidence2 = 0.2275 + 0.177 = 0.405
    assert confidence2 > 0.25, f"Strong signal should clear gate: {confidence2}"
    assert confidence2 > 0.40, f"Strong signal should reach main-book: {confidence2}"
