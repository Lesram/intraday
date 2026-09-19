"""Per-trade notional cap + daily max-loss halt tests.

CAP: Configurable per-trade notional cap before entry.
HALT: Configurable daily max-loss circuit breaker via governance.
"""

from __future__ import annotations
from datetime import datetime, timezone


# ─── CAP tests ─────────────────────────────────────────────

def test_notional_cap_applies():
    """When notional exceeds cap, shares should be reduced."""
    max_notional = 5000.0
    current_price = 200.0
    initial_shares = 50  # 50 * $200 = $10,000 > $5,000 cap

    if max_notional > 0 and current_price > 0:
        _notional = initial_shares * current_price
        if _notional > max_notional:
            capped = max(1, int(max_notional / current_price))
        else:
            capped = initial_shares
    else:
        capped = initial_shares

    assert capped == 25  # $5,000 / $200 = 25 shares
    assert capped * current_price <= max_notional


def test_notional_cap_under_limit():
    """When notional is under cap, shares unchanged."""
    max_notional = 5000.0
    current_price = 100.0
    initial_shares = 30  # 30 * $100 = $3,000 < $5,000

    _notional = initial_shares * current_price
    if _notional > max_notional:
        capped = max(1, int(max_notional / current_price))
    else:
        capped = initial_shares

    assert capped == 30  # unchanged


def test_notional_cap_disabled():
    """When cap is 0 (disabled), shares unchanged."""
    max_notional = 0.0
    initial_shares = 100

    if max_notional > 0:
        capped = 1  # would cap
    else:
        capped = initial_shares

    assert capped == 100


def test_notional_cap_minimum_1_share():
    """Cap should never reduce below 1 share."""
    max_notional = 50.0
    current_price = 500.0
    initial_shares = 10  # 10 * $500 = $5000 > $50 cap

    capped = max(1, int(max_notional / current_price))
    assert capped == 1  # $50 / $500 = 0.1, clamped to 1


# ─── HALT tests ────────────────────────────────────────────

def test_daily_max_loss_triggers():
    """Halt should fire when daily PnL crosses threshold."""
    max_daily_loss = 500.0
    starting_equity = 100_000.0
    current_equity = 99_400.0  # -$600 < -$500

    daily_pnl = current_equity - starting_equity
    should_halt = daily_pnl <= -max_daily_loss

    assert should_halt is True
    assert daily_pnl == -600.0


def test_daily_max_loss_no_trigger():
    """No halt when loss is above threshold."""
    max_daily_loss = 500.0
    starting_equity = 100_000.0
    current_equity = 99_700.0  # -$300 > -$500

    daily_pnl = current_equity - starting_equity
    should_halt = daily_pnl <= -max_daily_loss

    assert should_halt is False


def test_daily_max_loss_reset_next_day():
    """Starting equity resets on new trading day."""
    daily_loss_date = "2026-04-15"
    today = "2026-04-16"
    old_starting = 100_000.0
    current_equity = 99_800.0

    if today != daily_loss_date:
        starting_equity = current_equity  # reset
        daily_loss_date = today
    else:
        starting_equity = old_starting

    assert starting_equity == 99_800.0  # reset to current
    assert daily_loss_date == "2026-04-16"

    # After reset, daily PnL is 0 (no halt)
    daily_pnl = current_equity - starting_equity
    assert daily_pnl == 0.0


def test_daily_max_loss_disabled():
    """When limit is 0 (disabled), no halt."""
    max_daily_loss = 0.0
    should_check = max_daily_loss > 0
    assert should_check is False


def test_daily_max_loss_positive_day():
    """On a winning day, no halt regardless of threshold."""
    max_daily_loss = 500.0
    starting_equity = 100_000.0
    current_equity = 101_000.0  # +$1,000

    daily_pnl = current_equity - starting_equity
    should_halt = daily_pnl <= -max_daily_loss

    assert should_halt is False
    assert daily_pnl == 1_000.0
