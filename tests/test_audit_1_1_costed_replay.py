"""Audit 2026-06-09 plan 1.1 — costed replay fills.

The replay harness previously defaulted to same-bar close fills with flat
slippage only (no spread, no commission) — optimistic fills that overstate
every strategy's performance. Verifies:

1. Half-spread model: per-symbol-class resolution (ETF/megacap/other),
   flat float, per-symbol dict, and legacy None=0.
2. Costs move fills against the trader on both sides.
3. Commission is debited from cash and tracked.
4. cost_profile="realistic" flips on next-bar-open fills + auto spread +
   >=1bp slippage in one flag; "legacy" and None preserve old behavior.
5. Backward compat: zero-cost defaults unchanged for existing tests.
"""

import pytest

from backend.organism.replay_simulator import ReplayEngine, SimulatedBroker


# ── 1. Half-spread resolution ────────────────────────────────────────


def test_half_spread_auto_classification():
    b = SimulatedBroker(half_spread_bps="auto")
    assert b._half_spread_for("SPY") == 0.5
    assert b._half_spread_for("XLK") == 0.5
    assert b._half_spread_for("NVDA") == 1.0
    assert b._half_spread_for("ZZZUNKNOWN") == 2.5


def test_half_spread_flat_and_dict_and_none():
    assert SimulatedBroker(half_spread_bps=3.0)._half_spread_for("SPY") == 3.0
    d = SimulatedBroker(half_spread_bps={"SPY": 0.25})
    assert d._half_spread_for("SPY") == 0.25
    assert d._half_spread_for("NVDA") == 1.0  # dict miss → auto
    assert SimulatedBroker()._half_spread_for("SPY") == 0.0  # legacy default


# ── 2–3. Costs against the trader + commission ───────────────────────


@pytest.mark.asyncio
async def test_buy_fills_above_and_sell_below_price():
    b = SimulatedBroker(initial_cash=100_000, slippage_bps=1.0,
                        half_spread_bps=2.0)
    b.set_price("ABC", 100.0)
    buy = await b.submit_symbol_order(symbol="ABC", side="buy", qty=10)
    assert float(buy["avg_fill_price"]) == pytest.approx(100.0 * 1.0003)
    sell = await b.submit_symbol_order(symbol="ABC", side="sell", qty=10)
    assert float(sell["avg_fill_price"]) == pytest.approx(100.0 * 0.9997)


@pytest.mark.asyncio
async def test_commission_debited_and_tracked():
    b = SimulatedBroker(initial_cash=100_000, commission_per_share=0.005)
    b.set_price("ABC", 100.0)
    await b.submit_symbol_order(symbol="ABC", side="buy", qty=100)
    await b.submit_symbol_order(symbol="ABC", side="sell", qty=100)
    assert b.total_commission == pytest.approx(1.0)  # 200 shares * $0.005
    # Round trip at flat price: cash down by exactly the commission.
    assert b.cash == pytest.approx(100_000 - 1.0)


# ── 4. cost_profile semantics ────────────────────────────────────────


def _bars():
    import pandas as pd

    return {"ABC": pd.DataFrame({
        "open": [100.0] * 50, "high": [101.0] * 50,
        "low": [99.0] * 50, "close": [100.0] * 50,
        "volume": [1e6] * 50,
    })}


def test_realistic_profile_flips_fills_spread_slippage():
    e = ReplayEngine(bars_by_symbol=_bars(), cost_profile="realistic",
                     slippage_bps=0)
    assert e.delay_fill is True
    assert e.half_spread_bps == "auto"
    assert e.slippage_bps >= 1.0


def test_legacy_and_default_profiles_unchanged():
    e_none = ReplayEngine(bars_by_symbol=_bars())
    assert e_none.delay_fill is False
    assert e_none.half_spread_bps is None
    e_legacy = ReplayEngine(bars_by_symbol=_bars(), cost_profile="legacy")
    assert e_legacy.delay_fill is False


def test_unknown_profile_rejected():
    with pytest.raises(ValueError, match="cost_profile"):
        ReplayEngine(bars_by_symbol=_bars(), cost_profile="bananas")


# ── 5. Backward compat: zero-cost default math intact ────────────────


@pytest.mark.asyncio
async def test_legacy_default_broker_is_zero_cost():
    b = SimulatedBroker(initial_cash=100_000)
    b.set_price("ABC", 100.0)
    buy = await b.submit_symbol_order(symbol="ABC", side="buy", qty=10)
    assert float(buy["avg_fill_price"]) == pytest.approx(100.0)
    assert b.total_commission == 0.0
