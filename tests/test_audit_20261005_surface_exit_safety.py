"""Audit 2026-10-05 surface exit-safety fixes (C05-01, C05-02, C06-02).

C05-01  The broker-price safety nets read ``current_price`` from the position
        dicts, which the production PositionsService never supplied, so they
        could not fire live. ``_position_dict`` now carries ``current_price``
        (and ``qty_available``); a missing, zero, negative or non-finite price
        is 0.0 and every net skips it with a WARNING.
C05-02  After an exit that leaves shares open (partial take-profit,
        ml_reversal, a blocked or failed exit) the exit window skipped the hard
        stop and max-loss for about ten ticks. The window now runs those
        always-on risk exits every tick and sells only the shares that no exit
        of the window has claimed, so an exit in flight is never sent twice.
C06-02  The quote rung of the exit-price ladder called
        ``self._data_client.get_latest_quote``, which the production data client
        (AlpacaDataClient) does not have; the AttributeError aborted
        reconciliation and the rest of every tick. It now reads the streaming
        provider's cached quote; any failure there means "price unknown" and the
        close stays pending.

Review of 2026-10-05 (REQUEST_CHANGES on the first cut):
        the window's risk check runs on a copy of the exit levels, so window
        ticks never move the trailing anchor or the MFE/MAE tracking; a
        broker-price breach acts only in regular trading hours and, when the
        symbol has a fresh bar, only if the bar close also breaches.

Positions come from the REAL PositionsService over a fake Alpaca TradingClient
whose positions carry alpaca-py's string fields; exits go through the REAL
``_submit_exit_order`` into a recording OrderService mock. Every tick runs on a
pinned clock: the broker-price nets depend on the time of day.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from backend.services.positions_service import PositionsService, _position_dict
from backend.utils.market_hours import NYSE_EARLY_CLOSE

NOW = datetime(2026, 10, 1, 15, 0, 5, tzinfo=UTC)  # Thursday 11:00:05 ET
CYCLE_S = 15.7  # production tick cycle: 10 s sleep + tick time
_MISSING = object()
_ET = ZoneInfo("America/New_York")


def et(day, hms):
    """An ET wall-clock instant (``day`` a date or ISO string) as aware UTC."""
    return datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=_ET).astimezone(UTC)


# ── fakes and helpers ────────────────────────────────────────────────────────
class FakeTradingClient:
    """alpaca-py TradingClient stand-in: Position objects with string fields."""

    def __init__(self):
        self.positions: dict[str, SimpleNamespace] = {}

    def get_all_positions(self):
        return list(self.positions.values())

    def get_account(self):
        return SimpleNamespace(portfolio_value="100000", buying_power="100000")

    def hold(self, symbol, qty, avg_entry, price=_MISSING, qty_available=_MISSING):
        """Hold ``qty`` long. ``qty_available`` defaults to ``qty`` (no open order)."""
        fields = dict(
            symbol=symbol, qty=str(qty), side="long",
            market_value=str(qty * avg_entry), cost_basis=str(qty * avg_entry),
            unrealized_pl="0", avg_entry_price=str(avg_entry),
        )
        if price is not _MISSING:
            fields["current_price"] = price
        if qty_available is not _MISSING:
            fields["qty_available"] = qty_available
        elif qty:
            fields["qty_available"] = str(qty)
        if qty:
            self.positions[symbol] = SimpleNamespace(**fields)
        else:
            self.positions.pop(symbol, None)


def frame(now, last=100.0, start=100.0, n=60):
    closes = np.linspace(start, last, n)
    ts = pd.date_range(end=now - pd.Timedelta(minutes=1), periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "open": closes, "high": closes * 1.001,
                         "low": closes * 0.999, "close": closes, "volume": 50_000.0,
                         "_nan_missingness": 0.0})


def make_engine(tmp_path, client=None, *, positions_service=None, data_client=None,
                streaming_provider=None, universe=("AAPL", "MSFT", "GOOGL", "SPY"),
                sessionmaker=None):
    """Engine with every external dependency mocked, exits through the real path."""
    from backend.organism.live_engine import OrganismLiveEngine

    orders: list[dict] = []
    order_service = MagicMock()
    clock = {"now": NOW}

    async def submit_symbol_order(**kwargs):
        orders.append({"tick": engine._tick_count, "symbol": kwargs["symbol"],
                       "side": kwargs["side"], "qty": kwargs["qty"],
                       "reason": kwargs["attributes"]["reason"]})
        return {"order_id": f"o{len(orders)}", "symbol": kwargs["symbol"],
                "side": kwargs["side"], "qty": str(kwargs["qty"]), "status": "submitted"}

    order_service.submit_symbol_order = AsyncMock(side_effect=submit_symbol_order)
    if positions_service is None:
        positions_service = PositionsService(trading_client=client)
    with patch("backend.organism.brain_persistence.OrganismBrain.load", return_value=False), \
         patch("backend.organism.brain_persistence.OrganismBrain.exists",
               new_callable=lambda: property(lambda self: False)), \
         patch("backend.organism.live_engine.BackgroundTrainer") as bg_cls, \
         patch("backend.organism.live_engine.MarketScanner", return_value=MagicMock()):
        bg = MagicMock()
        bg.start = AsyncMock()
        bg.stop = AsyncMock()
        bg.is_training = False
        bg_cls.return_value = bg
        engine = OrganismLiveEngine(
            data_client=data_client if data_client is not None else MagicMock(),
            order_service=order_service, positions_service=positions_service,
            brain_dir=str(tmp_path / "brain"), universe=list(universe),
            streaming_provider=streaming_provider, sessionmaker=sessionmaker,
            timeframe="1Min",  # the production timeframe
        )
    engine._now_fn = lambda: clock["now"]
    engine._time_fn = lambda: clock["now"].timestamp()
    engine._get_equity = AsyncMock(return_value=100_000.0)
    engine._reconcile_fills = AsyncMock()
    engine._save_brain = MagicMock()
    engine._check_tick_invariants = MagicMock()
    engine._initialized = True
    return engine, orders, clock


def set_features(engine, clock, prices: dict):
    """Universe frames at 100; ``prices`` adds/overrides symbols (None drops one)."""
    feats = {s: frame(clock["now"]) for s in ("SPY", "MSFT", "GOOGL")}
    for sym, px in prices.items():
        if px is None:
            feats.pop(sym, None)
        else:
            feats[sym] = frame(clock["now"], last=px)
    engine._fetch_and_compute_features = AsyncMock(return_value=feats)


def arm_levels(engine, *, stop=99.0, partial_tp=103.0, take_profit=110.0):
    from backend.organism.adaptive_exits import ExitLevels
    from backend.organism.regime import RegimeState

    engine.regime_detector.detect = MagicMock(
        return_value=RegimeState(primary="trending_up", confidence=0.9))
    engine._exit_levels["AAPL"] = ExitLevels(
        symbol="AAPL", direction=1.0, entry_price=100.0, stop_loss=stop,
        take_profit=take_profit, trailing_stop=stop, atr_at_entry=1.0,
        regime_at_entry="trending_up", highest_favorable=100.0, bars_held=10,
        partial_tp_price=partial_tp, prediction_horizon=15, initial_risk_at_entry=1.0)


async def tick(engine, clock, i):
    clock["now"] = NOW + timedelta(seconds=CYCLE_S * i)
    with patch("backend.organism.live_engine.LONG_ONLY", True):
        return await engine.live_tick()


async def tick_at(engine, clock, when):
    """One tick at ``when``; call set_features after moving the clock there."""
    clock["now"] = when
    with patch("backend.organism.live_engine.LONG_ONLY", True):
        return await engine.live_tick()


def warnings_for(caplog, text):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and text in r.getMessage()]


# ── C05-01: the broker price reaches the safety nets ────────────────────────
def test_position_dict_carries_broker_price_and_free_quantity():
    position = SimpleNamespace(symbol="AAPL", qty="10", market_value="905", cost_basis="1000",
                               unrealized_pl="-95", avg_entry_price="100",
                               current_price="90.5", qty_available="7")
    out = _position_dict(position)
    assert out["current_price"] == 90.5 and out["qty_available"] == 7.0
    assert out["qty"] == 10.0 and out["avg_entry_price"] == 100.0 and out["side"] == "long"


@pytest.mark.parametrize("price", [_MISSING, None, "", "0", "-3", "nan", "inf", "-inf", "abc"])
@pytest.mark.parametrize("available", [_MISSING, None, "", "nan", "inf", "abc"])
def test_position_dict_bogus_values_fail_safe(price, available):
    fields = dict(symbol="AAPL", qty="10", market_value="1000", cost_basis="1000",
                  unrealized_pl="0", avg_entry_price="100")
    if price is not _MISSING:
        fields["current_price"] = price
    if available is not _MISSING:
        fields["qty_available"] = available
    out = _position_dict(SimpleNamespace(**fields))
    assert out["current_price"] == 0.0
    assert out["qty_available"] is None


def test_exit_loop_reads_only_keys_the_production_position_dict_produces():
    """Contract: every broker-position key the exit loop reads exists live."""
    from backend.organism.live_engine import OrganismLiveEngine

    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    start = src.index("# 5. CHECK EXITS on existing positions")
    end = src.index("result.trades_closed = exits_submitted", start)
    read = set(re.findall(r'pos_data(?:\.get\(|\[)"(\w+)"', src[start:end]))
    produced = set(_position_dict(SimpleNamespace(
        symbol="AAPL", qty="1", market_value="1", cost_basis="1", unrealized_pl="0",
        avg_entry_price="1", current_price="1", qty_available="1")))
    assert {"current_price", "qty_available", "avg_entry_price", "qty", "side"} <= read
    assert read <= produced, f"exit loop reads keys PositionsService never supplies: {read - produced}"


async def test_no_features_net_fires_on_real_broker_price(tmp_path):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="90")  # -10%, past the 8% max-loss
    engine, orders, clock = make_engine(tmp_path, client)
    set_features(engine, clock, {})  # AAPL has no features this tick
    await tick(engine, clock, 1)
    assert orders == [{"tick": 1, "symbol": "AAPL", "side": "sell", "qty": 10,
                       "reason": "safety_net_no_features"}]


@pytest.mark.parametrize("price", [_MISSING, None, "", "0", "-5", "nan", "inf", "abc"])
async def test_no_features_net_skips_bogus_broker_price_with_warning(tmp_path, caplog, price):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price=price)
    engine, orders, clock = make_engine(tmp_path, client)
    set_features(engine, clock, {})
    with caplog.at_level(logging.WARNING):
        await tick(engine, clock, 1)
    assert orders == []
    assert warnings_for(caplog, "No features AND no valid broker price for AAPL")


@pytest.mark.parametrize("bar, stale", [(None, False), (91.0, False), (100.0, True)],
                         ids=["no_bar", "fresh_bar_confirms", "stale_bar"])
async def test_window_max_loss_net_fires_on_real_broker_price(tmp_path, bar, stale):
    """DD2-1 is live: in regular hours the broker price fires the window net
    when the symbol has no fresh bar or its fresh bar also breaches. A bar the
    per-symbol staleness admission lists as stale cannot veto it."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="90")
    engine, orders, clock = make_engine(tmp_path, client)
    set_features(engine, clock, {"AAPL": bar})
    if stale:  # stage 0.5 writes this every tick while a streaming provider runs
        engine._stale_entry_symbols = frozenset({"AAPL"})
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    result = await tick(engine, clock, 1)
    assert orders == [{"tick": 1, "symbol": "AAPL", "side": "sell", "qty": 10,
                       "reason": "safety_net_pending_exit_breach"}]
    assert result.orders_submitted == 1


@pytest.mark.parametrize("price", [None, "nan", "0"])
async def test_window_net_skips_bogus_broker_price_with_warning(tmp_path, caplog, price):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price=price)
    engine, orders, clock = make_engine(tmp_path, client)
    set_features(engine, clock, {})
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    with caplog.at_level(logging.WARNING):
        await tick(engine, clock, 1)
    assert orders == []
    assert warnings_for(caplog, "Exit window for AAPL: no valid bar or broker price")


# ── C05-02: the exit window protects the remaining shares ───────────────────
def _partial_setup(engine, kind):
    """Tick-1 price, a window price that breaches the remainder's risk exit, the
    expected reason and the partial size (10-share position)."""
    if kind == "ml_reversal":
        from backend.organism.ml_signal import MLSignal

        engine.signal_gen._is_trained = True
        engine.signal_gen.predict = MagicMock(side_effect=lambda _df, sym, *a, **k: MLSignal(
            symbol=sym, direction=-1.0, confidence=0.9, predicted_return=-0.01,
            raw_confidence=0.9, effective_confidence=0.9, effective_predicted_return=-0.01))
        # 30% intraday partial at 100.2; then under the 99 stop.
        return 100.2, 98.5, "stop_loss", max(1, int(10 * engine._ml_reversal_partial_pct))
    # 3R partial (20% intraday); then -9%, past the 8% max-loss.
    return 103.5, 91.0, "max_loss_limit", max(1, int(10 * engine.exit_engine.partial_tp_pct))


@pytest.mark.parametrize("kind", ["ml_reversal", "partial_take_profit"])
@pytest.mark.parametrize("fill", ["filled", "open_reported", "open_unreported", "open_record_lost"])
async def test_remainder_of_partial_exit_is_risk_checked_on_next_tick(tmp_path, kind, fill):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="100")
    with patch("backend.organism.live_engine.OrganismLiveEngine._is_learning_mode",
               new_callable=PropertyMock, return_value=False):
        engine, orders, clock = make_engine(tmp_path, client)
        arm_levels(engine)
        first_px, breach_px, reason, partial = _partial_setup(engine, kind)
        set_features(engine, clock, {"AAPL": first_px})
        await tick(engine, clock, 1)
        assert [(o["tick"], o["qty"]) for o in orders] == [(1, partial)]
        remainder = 10 - partial
        if fill == "filled":
            client.hold("AAPL", remainder, 100.0, price=str(breach_px))
        elif fill in ("open_reported", "open_record_lost"):  # the partial is still open
            client.hold("AAPL", 10, 100.0, price=str(breach_px), qty_available=str(remainder))
            if fill == "open_record_lost":  # e.g. a restart restored the window
                engine._exit_unclaimed_qty.clear()
        else:  # still open and the broker reports no qty_available
            client.hold("AAPL", 10, 100.0, price=str(breach_px), qty_available=None)
        set_features(engine, clock, {"AAPL": breach_px})
        await tick(engine, clock, 2)
        assert orders[1:] == [{"tick": 2, "symbol": "AAPL", "side": "sell",
                               "qty": remainder, "reason": reason}]
        # Everything is claimed now: no further exit while the orders stay open
        # (the broker holds every remaining share for them).
        held_qty = remainder if fill == "filled" else 10
        client.hold("AAPL", held_qty, 100.0, price=str(breach_px),
                    qty_available=None if fill == "open_unreported" else "0")
        for i in range(3, 10):
            await tick(engine, clock, i)
        assert sum(o["qty"] for o in orders) == 10


@pytest.mark.parametrize("available", ["0", None, "10"])
async def test_no_duplicate_exit_while_full_exit_in_flight(tmp_path, available):
    """'10' is an exit still in the outbox: Alpaca has not seen it yet."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="98.5")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    set_features(engine, clock, {"AAPL": 98.5})  # under the 99 stop
    await tick(engine, clock, 1)
    assert [(o["qty"], o["reason"]) for o in orders] == [(10, "stop_loss")]
    client.hold("AAPL", 10, 100.0, price="97", qty_available=available)  # not filled yet
    set_features(engine, clock, {"AAPL": 97.0})
    for i in range(2, 10):  # the whole exit window
        await tick(engine, clock, i)
    assert len(orders) == 1


async def test_failed_exit_leaves_position_protected_from_next_tick(tmp_path):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="98.5")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    calls = {"n": 0}
    recording = engine._order_service.submit_symbol_order.side_effect

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("outbox unavailable")
        return await recording(**kwargs)
    engine._order_service.submit_symbol_order.side_effect = flaky
    set_features(engine, clock, {"AAPL": 98.5})
    first = await tick(engine, clock, 1)
    assert orders == [] and any("Exit order failed for AAPL" in e for e in first.errors)
    assert "AAPL" in engine._pending_exit  # the routine retry still waits
    await tick(engine, clock, 2)
    assert orders == [{"tick": 2, "symbol": "AAPL", "side": "sell", "qty": 10,
                       "reason": "stop_loss"}]


async def test_blocked_window_exit_is_not_counted_and_retries(tmp_path):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="100")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    first_px, breach_px, _, partial = _partial_setup(engine, "ml_reversal")
    set_features(engine, clock, {"AAPL": first_px})
    await tick(engine, clock, 1)
    assert [o["qty"] for o in orders] == [partial]
    blocked = AsyncMock(return_value={"status": "blocked", "reason": "zero_quantity"})
    engine._submit_exit_order = blocked
    client.hold("AAPL", 10 - partial, 100.0, price=str(breach_px))
    set_features(engine, clock, {"AAPL": breach_px})
    result = await tick(engine, clock, 2)
    assert blocked.await_count == 1
    assert result.orders_submitted == 0
    assert not [a for a in result.activity if (a.details or {}).get("exit_window")]
    await tick(engine, clock, 3)
    assert blocked.await_count == 2  # nothing was claimed: the next tick tries again


async def test_window_keeps_routine_exits_suspended(tmp_path):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="100")
    with patch("backend.organism.live_engine.OrganismLiveEngine._is_learning_mode",
               new_callable=PropertyMock, return_value=False):
        engine, orders, clock = make_engine(tmp_path, client)
        arm_levels(engine)
        engine._exit_levels["AAPL"].partial_tp_taken = True  # leave the full take-profit
        first_px, _, _, partial = _partial_setup(engine, "ml_reversal")
        set_features(engine, clock, {"AAPL": first_px})
        await tick(engine, clock, 1)
        client.hold("AAPL", 10 - partial, 100.0, price="120")
        set_features(engine, clock, {"AAPL": 120.0})  # past take-profit: a routine exit
        for i in range(2, 11):  # the window armed at tick 1 ends after tick 10
            await tick(engine, clock, i)
        assert [o["qty"] for o in orders] == [partial]
        await tick(engine, clock, 11)
    assert orders[1:] == [{"tick": 11, "symbol": "AAPL", "side": "sell",
                           "qty": 10 - partial, "reason": "take_profit"}]


async def test_exit_order_records_unclaimed_shares(tmp_path):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="100")
    engine, orders, clock = make_engine(tmp_path, client)
    held = {"AAPL": {"symbol": "AAPL", "qty": 10.0, "side": "long"}}
    with patch("backend.organism.live_engine.LONG_ONLY", True):
        await engine._submit_exit_order("AAPL", 3, "ml_reversal", broker_positions=held)
        assert engine._exit_unclaimed_qty["AAPL"] == 7
        engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
        await engine._submit_exit_order("AAPL", 7, "stop_loss", broker_positions=held)
        assert engine._exit_unclaimed_qty["AAPL"] == 0
        # A held exit claims nothing.
        engine._exit_unclaimed_qty.clear()
        engine._pending_exit.clear()
        engine._exit_cooldown.clear()
        out = await engine._submit_exit_order("AAPL", 5, "stop_loss", broker_positions={})
        assert out["status"] == "blocked" and "AAPL" not in engine._exit_unclaimed_qty
        # A raising submission claims nothing either.
        engine._order_service.submit_symbol_order.side_effect = RuntimeError("down")
        with pytest.raises(RuntimeError):
            await engine._submit_exit_order("AAPL", 5, "stop_loss", broker_positions=held)
        assert "AAPL" not in engine._exit_unclaimed_qty
    assert [o["qty"] for o in orders] == [3, 7]


# ── Review of 2026-10-05: the window is exactly max-loss + hard stop ────────
# The reviewer's price path: a window peak of 106, the partial take-profit at
# 103 on tick 10, then a slide to 100.1 (scratch probe_hf.py).
_REVIEW_PATH = [104.0, 106.0, 105.0, 104.5, 104.0, 103.5, 103.2, 103.1, 103.0, 103.0,
                102.8, 102.6, 102.4, 102.2, 102.0, 101.8, 101.6, 101.5, 101.4,
                101.3, 101.2, 100.9, 100.7, 100.4, 100.1]


async def test_window_ticks_leave_trailing_anchor_and_excursions_frozen(tmp_path):
    """Window ticks must not move ExitLevels tracking: before the fix the 106
    peak became the trailing anchor and a trailing_stop went out at tick 22
    (100.9 under a 101.0 trail). Like the base code: anchor 103, trail 100.0,
    no trailing exit through tick 25, and MAE tracked only on routine ticks."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="103.5")
    with patch("backend.organism.live_engine.OrganismLiveEngine._is_learning_mode",
               new_callable=PropertyMock, return_value=False):
        engine, orders, clock = make_engine(tmp_path, client)
        arm_levels(engine)
        levels = engine._exit_levels["AAPL"]
        # A prior exit armed the window this tick and left 8 shares unclaimed.
        engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
        engine._exit_unclaimed_qty = {"AAPL": 8}
        trace = {}
        for i, px in enumerate(_REVIEW_PATH, start=1):
            client.hold("AAPL", 10, 100.0, price=str(px))
            set_features(engine, clock, {"AAPL": px})
            await tick(engine, clock, i * 4)  # 4 cycles apart: every tick is a new bar
            trace[i] = (levels.highest_favorable, levels.worst_adverse)
    assert [(o["tick"], o["qty"], o["reason"]) for o in orders] == [
        (10, 2, "partial_take_profit")]
    assert all(trace[i] == (100.0, 0.0) for i in range(1, 10))  # window: untouched
    assert all(trace[i] == (103.0, 103.0) for i in range(10, 20))  # tick 10, then its window
    assert all(trace[i] == (103.0, _REVIEW_PATH[i - 1]) for i in range(20, 26))  # routine
    assert levels.trailing_active and levels.trailing_stop == pytest.approx(100.0)


@pytest.mark.parametrize("bar, expected", [(106.0, []), (98.5, [(1, 10, "stop_loss")])],
                         ids=["new_high", "stop_breach"])
async def test_window_risk_check_runs_on_a_copy_of_the_exit_levels(tmp_path, bar, expected):
    """A window tick at a new high, or under the stop (which still exits),
    leaves the position's ExitLevels exactly as they were."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price=str(bar))
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    before = dataclasses.asdict(engine._exit_levels["AAPL"])
    set_features(engine, clock, {"AAPL": bar})
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    await tick(engine, clock, 1)
    assert [(o["tick"], o["qty"], o["reason"]) for o in orders] == expected
    assert dataclasses.asdict(engine._exit_levels["AAPL"]) == before


# ── Review of 2026-10-05: a lone broker mark never sells ────────────────────
async def test_fresh_bar_that_disagrees_vetoes_a_broker_price_breach(tmp_path, caplog):
    """The reviewer's probe: the bar (99.5) is above the 99 stop, the broker
    mark (91.9) is 8.1% under entry. Before: a 10-share window exit."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="91.9")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    set_features(engine, clock, {"AAPL": 99.5})
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    with caplog.at_level(logging.WARNING):
        result = await tick(engine, clock, 1)
    assert orders == [] and result.orders_submitted == 0
    assert warnings_for(caplog, "Exit window for AAPL: broker-price breach at 91.90 not acted on")


_EARLY_CLOSE_DAY = max(NYSE_EARLY_CLOSE)  # 13:00 ET close; always in the module's calendar


@pytest.mark.parametrize("when", [
    et("2026-10-01", "09:28:30"),  # pre-open warm-up tick
    et("2026-10-01", "16:00:20"),  # the close (the scheduler ticks to 16:01)
    et(_EARLY_CLOSE_DAY, "13:30:00"),  # after an early close
], ids=["pre_open", "close", "early_close_afternoon"])
@pytest.mark.parametrize("net", ["no_features", "window"])
async def test_broker_price_nets_do_not_act_outside_regular_hours(tmp_path, caplog, when, net):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="90")  # -10%, no bar: the broker mark alone
    engine, orders, clock = make_engine(tmp_path, client)
    clock["now"] = when
    set_features(engine, clock, {})
    if net == "window":
        engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    with caplog.at_level(logging.WARNING):
        await tick_at(engine, clock, when)
    assert orders == []
    assert warnings_for(caplog, (
        "Exit window for AAPL: broker-price breach at 90.00 not acted on" if net == "window"
        else "SAFETY NET (no features) for AAPL: broker breach at 90.00 not acted on"))


@pytest.mark.parametrize("net, reason", [("no_features", "safety_net_no_features"),
                                         ("window", "safety_net_pending_exit_breach")])
async def test_broker_price_nets_act_from_the_open(tmp_path, net, reason):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="90")
    engine, orders, clock = make_engine(tmp_path, client)
    when = clock["now"] = et("2026-10-01", "09:30:05")
    set_features(engine, clock, {})
    if net == "window":
        engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    await tick_at(engine, clock, when)
    assert [(o["qty"], o["reason"]) for o in orders] == [(10, reason)]


# ── Review of 2026-10-05: non-blocking items and surviving mutants ──────────
async def test_negative_qty_available_on_a_long_frees_no_shares(tmp_path):
    """Like the outbox guard (max(0, min(qty, available))): an anomalous
    negative qty_available on a long means 0 free shares, not abs() = 2."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="99.5", qty_available="-2")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    set_features(engine, clock, {"AAPL": 98.0})  # under the 99 stop
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    await tick(engine, clock, 1)
    assert orders == []


async def test_window_exit_is_logged_with_its_real_reason(tmp_path, caplog):
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="98.5")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    set_features(engine, clock, {"AAPL": 98.5})
    engine._pending_exit["AAPL"] = engine._exit_cooldown["AAPL"] = engine._tick_count
    with caplog.at_level(logging.WARNING):
        await tick(engine, clock, 1)
    assert [o["reason"] for o in orders] == ["stop_loss"]
    assert warnings_for(caplog, "Exit window stop_loss exit: AAPL at 98.50")
    assert not warnings_for(caplog, "DD2-1")


@pytest.mark.parametrize("later_exit", ["eod_flatten", "overnight_force_exit"])
async def test_window_exit_rearms_pending_so_no_second_sell_in_the_same_tick(tmp_path, later_exit):
    """Mutant M12: a window exit must re-arm _pending_exit. EOD flatten and the
    overnight forced exit run later in the same tick and skip only pending
    symbols; without the re-arm each would sell the full position again."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="98.5")
    engine, orders, clock = make_engine(tmp_path, client)
    arm_levels(engine)
    if later_exit == "eod_flatten":
        when = clock["now"] = et("2026-10-01", "15:58:30")  # the flatten window
    else:
        when = clock["now"] = et("2026-10-01", "09:31:00")
        Path(engine.brain.brain_dir).mkdir(parents=True, exist_ok=True)
        engine._overnight_flag_path().write_text(
            json.dumps({"session_date": "2026-09-30", "symbols": ["AAPL"]}))
    set_features(engine, clock, {"AAPL": 98.5})  # under the 99 stop
    engine._tick_count = 20
    engine._exit_cooldown["AAPL"] = 16  # an earlier exit's window; its pending expired
    await tick_at(engine, clock, when)
    assert [(o["qty"], o["reason"]) for o in orders] == [(10, "stop_loss")]
    assert engine._pending_exit["AAPL"] == engine._tick_count


async def test_pending_only_window_from_the_pyramid_close_path(tmp_path):
    """Mutant M7: the pyramid close_partial path (live_engine step 6) arms
    _pending_exit without _exit_cooldown. That window still suspends routine
    exits and still runs the stop on the shares the pyramid sell left free."""
    client = FakeTradingClient()
    client.hold("AAPL", 10, 100.0, price="100")
    with patch("backend.organism.live_engine.OrganismLiveEngine._is_learning_mode",
               new_callable=PropertyMock, return_value=False):
        engine, orders, clock = make_engine(tmp_path, client)
        arm_levels(engine)
        engine._exit_levels["AAPL"].partial_tp_taken = True  # leave the full take-profit
        with patch("backend.organism.live_engine.LONG_ONLY", True):  # step 6's call
            await engine._submit_exit_order("AAPL", 3, reason="pyramid_cut", direction=1.0)
        engine._pending_exit["AAPL"] = engine._tick_count
        assert "AAPL" not in engine._exit_cooldown
        # The pyramid sell is still open: the broker holds 3 shares for it.
        client.hold("AAPL", 10, 100.0, price="120", qty_available="7")
        set_features(engine, clock, {"AAPL": 120.0})  # past take-profit: a routine exit
        await tick(engine, clock, 1)
        assert [o["reason"] for o in orders] == ["pyramid_cut"]  # routine exits suspended
        client.hold("AAPL", 10, 100.0, price="98.5", qty_available="7")
        set_features(engine, clock, {"AAPL": 98.5})  # under the 99 stop
        await tick(engine, clock, 2)
    assert [(o["qty"], o["reason"]) for o in orders] == [(3, "pyramid_cut"), (7, "stop_loss")]


# ── C06-02: the quote rung no longer aborts reconciliation or the tick ──────
def _orphan_engine(tmp_path, streaming_provider, held):
    from backend.integrations.alpaca_data import AlpacaDataClient
    from backend.organism import close_accounting

    broker = MagicMock()
    broker.get_all_positions = AsyncMock(side_effect=lambda: dict(held))
    engine, orders, clock = make_engine(
        tmp_path, positions_service=broker, universe=("SPY", "QQQ"),
        # The production data client has no quote method; a spec'd mock raises
        # AttributeError exactly like it if the engine ever calls one again.
        data_client=MagicMock(spec=AlpacaDataClient),
        streaming_provider=streaming_provider,
    )
    del engine._reconcile_fills  # the real method
    engine._daily_loss_date = close_accounting.session_date(NOW)
    return engine, clock


async def _adopt_then_close(engine, held):
    """Both held names are adopted as orphans (held names get features); then
    both close outside the engine and AAA, outside the universe, has no frame."""
    engine._tick_count = 100
    await engine._reconcile_fills({"AAA": frame(NOW, last=20.0), "ZZZ": frame(NOW, last=50.0)})
    assert {s: m["entry_source"] for s, m in engine._entry_metadata.items()} == {
        "AAA": "reconciliation_orphan", "ZZZ": "reconciliation_orphan"}
    held.clear()  # both closed outside the engine; no organism sell exists
    engine._tick_count += 5


def _held():
    return {"AAA": {"symbol": "AAA", "qty": 7.0, "side": "long", "avg_entry_price": 20.0},
            "ZZZ": {"symbol": "ZZZ", "qty": 3.0, "side": "long", "avg_entry_price": 50.0}}


async def test_quote_rung_prices_orphan_close_from_streaming_provider(tmp_path):
    held = _held()
    provider = SimpleNamespace(get_latest_quote=MagicMock(return_value={"bid": 19.9, "ask": 20.1}))
    engine, _ = _orphan_engine(tmp_path, provider, held)
    await _adopt_then_close(engine, held)
    await engine._reconcile_fills({"ZZZ": frame(NOW, last=50.0)})
    by_symbol = {t.symbol: t for t in engine._all_trades}
    assert by_symbol["AAA"].exit_price == pytest.approx(20.0)
    assert by_symbol["AAA"].price_source == "quote_mid"
    assert by_symbol["AAA"].is_reconciliation_artifact
    assert by_symbol["ZZZ"].price_source == "bar_close"
    provider.get_latest_quote.assert_called_with("AAA")
    assert engine._entry_metadata == {} and engine._accounting_error == ""


def _raising(_symbol):
    raise RuntimeError("quote cache unavailable")


@pytest.mark.parametrize("provider", [
    None,
    SimpleNamespace(),  # no quote method
    SimpleNamespace(get_latest_quote=_raising),
    SimpleNamespace(get_latest_quote=lambda _s: {}),
    SimpleNamespace(get_latest_quote=lambda _s: None),
    SimpleNamespace(get_latest_quote=lambda _s: {"bid": "abc", "ask": 20.1}),
    SimpleNamespace(get_latest_quote=lambda _s: {"bid": float("nan"), "ask": float("inf")}),
    SimpleNamespace(get_latest_quote=lambda _s: {"bid": -1.0, "ask": 0.0}),
], ids=["none", "no_method", "raises", "empty", "not_dict", "malformed", "non_finite", "non_positive"])
async def test_unpriced_orphan_close_stays_pending_without_aborting(tmp_path, provider):
    held = _held()
    engine, _ = _orphan_engine(tmp_path, provider, held)
    await _adopt_then_close(engine, held)
    for _ in range(2):
        await engine._reconcile_fills({"ZZZ": frame(NOW, last=50.0)})  # must not raise
    assert [t.symbol for t in engine._all_trades] == ["ZZZ"]  # the later close still commits
    assert engine._entry_metadata["AAA"]["pending_close"]
    assert engine.status()["close_accounting"]["unresolved"]["AAA"]["reason"] == "no_exit_price"
    assert engine._accounting_error == ""


async def test_full_tick_runs_past_an_unpriced_orphan_close(tmp_path):
    """The rest of the tick (pending-entry reconciliation, age tracking, the
    periodic brain save) runs on every tick while the close stays pending."""
    held = {"XYZ": {"symbol": "XYZ", "qty": 7.0, "side": "long", "avg_entry_price": 20.0,
                    "current_price": 20.5}}
    engine, clock = _orphan_engine(tmp_path, None, held)

    async def features():
        out = {s: frame(clock["now"]) for s in ("SPY", "QQQ")}
        out.update({s: frame(clock["now"], last=20.0) for s in held})
        return out
    engine._fetch_and_compute_features = AsyncMock(side_effect=features)
    real_recon, real_age = engine._reconcile_pending_entry_orders, engine._track_pending_entry_ages
    calls = {"recon": 0, "age": 0}

    async def recon_spy(*args, **kwargs):
        calls["recon"] += 1
        return await real_recon(*args, **kwargs)

    def age_spy(*args, **kwargs):
        calls["age"] += 1
        return real_age(*args, **kwargs)
    engine._reconcile_pending_entry_orders = recon_spy
    engine._track_pending_entry_ages = age_spy
    errors, saves = [], {}
    for i in range(1, 21):
        if i == 4:
            held.clear()  # closed by hand between ticks
        before = engine._save_brain.call_count
        errors += (await tick(engine, clock, i)).errors
        saves[i] = engine._save_brain.call_count - before
    assert engine._tick_count == 20
    assert not [e for e in errors if "Live tick error" in e], errors
    assert calls == {"recon": 20, "age": 20}
    assert saves[20] == saves[19] + 1  # step 12's every-20-ticks brain save ran
    assert engine._entry_metadata["XYZ"]["pending_close"]
    assert engine.status()["close_accounting"]["unresolved"]["XYZ"]["reason"] == "no_exit_price"
    assert engine._accounting_error == ""
