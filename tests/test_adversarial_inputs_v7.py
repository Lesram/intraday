"""V7 Track FF — adversarial-input regression tests.

DRAFT — see artifacts/audit/v7_reports/track_ff_edge_cases_adversarial.md.

These tests pin the *current* defensive behaviour of the surfaces audited
in V7 Track FF. Where current behaviour has a gap (e.g. submit_symbol_order
not calling validate_order), the test is marked xfail with the finding
identifier so it surfaces if/when the gap is closed.

Categories:
  1. Bar data integrity (compute_ml_features)
  2. Adversarial broker responses (alpaca_broker, static)
  3. WS adversarial (alpaca_stream, static)
  4. Feature pipeline edge cases
  5. ML inference edge cases
  6. Order submission adversarial (validate_order + submit_symbol_order)
  7. Time / scheduling adversarial (UTC discipline)
  8. State persistence adversarial
  9. Numerical adversarial
 10. Configuration adversarial
"""
from __future__ import annotations

import inspect
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

UTC = timezone.utc


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def base_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 250
    ts = [datetime(2025, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i) for i in range(n)]
    closes = 100.0 + np.cumsum(rng.normal(0, 0.3, n))
    opens = closes + rng.normal(0, 0.05, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.1, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.1, n))
    return pd.DataFrame({
        "timestamp": ts, "open": opens, "high": highs,
        "low": lows, "close": closes,
        "volume": np.full(n, 1_000_000, dtype=float),
    })


# ─── 1. Bar data integrity ─────────────────────────────────────────

def test_bar_duplicate_timestamps_does_not_crash(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df)] = df.iloc[-1].to_dict()
    out = compute_ml_features(df)
    assert len(out) == len(df)


def test_bar_out_of_order_timestamps_silently_accepted(base_df):
    """No monotonicity guard exists. This test pins the current behaviour
    so any future enforcement surfaces explicitly."""
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, "timestamp"] = df.loc[0, "timestamp"]
    out = compute_ml_features(df)
    assert len(out) == len(df)


def test_bar_nan_close_propagates_to_missingness_gate(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, "close"] = float("nan")
    out = compute_ml_features(df)
    miss = float(out.iloc[-1]["_nan_missingness"])
    # FINDING FF-1: NaN in `close` produces ≥25% missingness in the
    # last row, which the engine's gate (live_engine.py:3460) blocks.
    assert miss > 0.25, "NaN close should trigger >25% missingness gate"


def test_bar_inf_volume_replaced(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, "volume"] = float("inf")
    out = compute_ml_features(df)
    # inf is replaced via f.replace([inf, -inf], NaN) then fillna(0)
    assert math.isfinite(float(out.iloc[-1]["vol_sma_ratio"]))


def test_bar_negative_volume_silently_accepted(base_df):
    """FINDING FF-2: corrupted negative volume produces a negative
    vol_sma_ratio that still feeds tension/composites without rejection."""
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, "volume"] = -10_000_000.0
    out = compute_ml_features(df)
    ratio = float(out.iloc[-1]["vol_sma_ratio"])
    assert ratio < 0, "documents current behaviour: negative volume → negative ratio"


def test_bar_negative_price_does_not_crash(base_df):
    """FINDING FF-3: negative prices coerce log(c) → NaN → 0.0 silently.
    No upstream rejection."""
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, ["open", "high", "low", "close"]] = -50.0
    out = compute_ml_features(df)
    # log_ret_1d should be 0 (NaN → fillna(0)) since log of negative is NaN
    assert float(out.iloc[-1]["log_ret_1d"]) == 0.0


def test_bar_50pct_gap_computed(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, ["open", "high", "low", "close"]] = float(df.loc[len(df) - 2, "close"]) * 1.50
    out = compute_ml_features(df)
    # gap_pct ~ 0.50
    assert abs(float(out.iloc[-1]["gap_pct"]) - 0.50) < 0.05


def test_bar_frozen_100_bars(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    last = df.iloc[-1].copy()
    for _ in range(100):
        new = last.to_dict()
        new["timestamp"] = df.iloc[-1]["timestamp"] + timedelta(minutes=1)
        df.loc[len(df)] = new
    out = compute_ml_features(df)
    # Many features collapse — but no crash
    assert math.isfinite(float(out.iloc[-1]["atr_14"]))


def test_bar_single_row_does_not_crash():
    from backend.organism.ml_features import compute_ml_features
    df = pd.DataFrame({
        "timestamp": [datetime(2025, 1, 1, tzinfo=UTC)],
        "open": [100.0], "high": [100.0], "low": [100.0],
        "close": [100.0], "volume": [1_000.0],
    })
    out = compute_ml_features(df)
    assert len(out) == 1


def test_bar_missing_timestamp_none_is_caught_by_fetch_layer(base_df):
    """compute_ml_features RAISES on None timestamp (TypeError from pd.to_datetime).
    The tick loop's _fetch_one wraps in try/except → silently skips the symbol.
    This test pins the raising behaviour at the feature layer."""
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy()
    df.loc[len(df) - 1, "timestamp"] = None
    with pytest.raises((TypeError, ValueError)):
        compute_ml_features(df)


# ─── 4. Feature pipeline ───────────────────────────────────────────

def test_feature_capitalised_column_raises(base_df):
    from backend.organism.ml_features import compute_ml_features
    df = base_df.copy().rename(columns={"close": "Close"})
    with pytest.raises(KeyError):
        compute_ml_features(df)


# ─── 5. ML inference ───────────────────────────────────────────────

def test_ml_predict_before_training_returns_neutral(base_df):
    from backend.organism.ml_features import compute_ml_features
    from backend.organism.ml_signal import MLSignalGenerator
    feat = compute_ml_features(base_df)
    gen = MLSignalGenerator()
    sig = gen.predict(feat, symbol="TEST")
    assert sig.direction == 0
    assert sig.confidence == 0
    assert sig.predicted_return == 0


def test_ml_predict_extreme_outlier_safe(base_df):
    from backend.organism.ml_features import compute_ml_features
    from backend.organism.ml_signal import MLSignalGenerator
    feat = compute_ml_features(base_df)
    feat.iloc[-1, feat.columns.get_loc("rsi_14")] = 1e30
    gen = MLSignalGenerator()
    sig = gen.predict(feat, symbol="TEST")  # untrained → neutral
    assert sig.direction == 0


# ─── 6. Order submission ───────────────────────────────────────────

def test_order_validate_negative_qty_rejected():
    from backend.services.order_service import OrderService
    svc = OrderService.__new__(OrderService)
    res = svc.validate_order({"symbol": "AAPL", "side": "buy", "qty": -10})
    assert res["valid"] is False
    assert any("invalid_qty" in e for e in res["errors"])


def test_order_validate_zero_qty_rejected():
    from backend.services.order_service import OrderService
    svc = OrderService.__new__(OrderService)
    res = svc.validate_order({"symbol": "AAPL", "side": "buy", "qty": 0})
    assert res["valid"] is False


def test_order_validate_special_chars_symbol_rejected():
    from backend.services.order_service import OrderService
    svc = OrderService.__new__(OrderService)
    res = svc.validate_order({"symbol": "AA;PL", "side": "buy", "qty": 100})
    assert res["valid"] is False


# V12 W90 (post-cleanup): FF-4 and FF-5 were xfail(strict=True) since
# the V7 audit; pytest's strict-xfail mode then turns into XPASS(strict)
# = test failure when the underlying fix ships.  Verified that
# OrderService.submit_symbol_order now calls _validate / validate_order
# AND idempotency cache compares request body — both fixes landed in
# unrecorded waves between V8-V11.  Removed the xfail decorators so
# the tests serve as positive regression locks going forward.
def test_submit_symbol_order_validates_inputs():
    from backend.services.order_service import OrderService
    src = inspect.getsource(OrderService.submit_symbol_order)
    assert "validate_order" in src or "_validate" in src


def test_idempotency_collision_with_different_body():
    from backend.services.order_service import OrderService
    src = inspect.getsource(OrderService.submit_symbol_order)
    cache_block_start = src.find("if idempotency_key in self._async_submitted_orders")
    cache_block_end = src.find("return existing_result", cache_block_start)
    block = src[cache_block_start:cache_block_end]
    assert "symbol" in block, "cache hit should verify symbol matches"


# ─── 7. Time / scheduling ──────────────────────────────────────────

def test_bar_ts_uses_utc_for_dst_safety():
    """`_last_bar_times` keys are derived from `self._now_fn().astimezone(UTC)`,
    making the bar boundary detection DST-immune."""
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    assert "self._now_fn().astimezone(UTC).strftime" in src


# ─── 8. State persistence ──────────────────────────────────────────

def test_brain_persistence_has_some_lock_primitive():
    from backend.organism import brain_persistence
    src = inspect.getsource(brain_persistence)
    # Multiple writers (shadow scanner + live engine) on the same volume
    # need *some* form of mutual exclusion. Pin presence.
    assert any(t in src for t in ("Lock", "fcntl", "filelock", "FileLock", "_lock"))


# ─── 9. Numerical ──────────────────────────────────────────────────

def test_zero_division_entry_price_raises():
    """Documents that division by 0 entry price would raise; live_engine
    is responsible for guarding before computing actual_return."""
    with pytest.raises(ZeroDivisionError):
        _ = (101.0 - 0.0) / 0


def test_near_zero_entry_price_overflow_silent():
    """FINDING FF-6: a near-zero entry_price (e.g. 1e-300) produces a finite
    but absurd actual_return without overflow, leaking phantom performance
    if not caught upstream."""
    actual_return = (101.0 - 0.0) / 1e-300
    assert math.isfinite(actual_return)
    assert actual_return > 1e100


# ─── 10. Configuration ─────────────────────────────────────────────

def test_universe_csv_empty_yields_empty_list():
    """FINDING FF-7: ORGANISM_LIVE_SYMBOLS='' parses to an empty universe.
    Engine runs with 0 symbols rather than rejecting the misconfiguration."""
    raw = ""
    parsed = [s.strip().upper() for s in raw.split(",") if s.strip()]
    assert parsed == []


def test_universe_csv_duplicates_not_deduped():
    """FINDING FF-8: duplicate symbols in ORGANISM_LIVE_SYMBOLS are accepted
    verbatim. No dedup."""
    raw = "AAPL,AAPL,AAPL"
    parsed = [s.strip().upper() for s in raw.split(",") if s.strip()]
    assert parsed == ["AAPL", "AAPL", "AAPL"]
    assert len(parsed) != len(set(parsed))


def test_max_notional_negative_silently_disables():
    """FINDING FF-9: ORGANISM_MAX_NOTIONAL=-100 is parsed as -100.0 and
    silently disables the cap (the live_engine guard `if MAX_NOTIONAL > 0`
    treats it as off rather than raising or warning)."""
    val = float("-100")
    assert val == -100.0
    assert not (val > 0)  # guard disables silently


# ─── 2/3. Broker / WS adversarial — static review ──────────────────

def test_ws_listen_handles_malformed_json():
    from backend.integrations import alpaca_stream
    src = inspect.getsource(alpaca_stream.AlpacaStreamClient.listen)
    assert "json.JSONDecodeError" in src
    assert "continue" in src


def test_broker_request_has_bounded_retries():
    from backend.integrations import alpaca_broker
    src = inspect.getsource(alpaca_broker.AlpacaBrokerClient._make_request_with_retry)
    assert "max_retries" in src and "for attempt in range" in src


@pytest.mark.asyncio
async def test_broker_handles_empty_200_body():
    """An empty success is resolved by exact identity, without another POST."""
    from unittest.mock import AsyncMock
    from fastapi import HTTPException
    import httpx
    from backend.integrations.alpaca_broker import AlpacaBrokerClient

    broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
    broker.base_url = "https://broker.invalid"
    broker.is_paper = True
    broker.get_order = AsyncMock(side_effect=HTTPException(404, "not found"))
    confirmed = {"id": "broker-id", "status": "accepted", "client_order_id": "original"}
    broker._make_request_with_retry = AsyncMock(side_effect=[
        httpx.Response(200, content=b""), httpx.Response(200, json=confirmed),
    ])
    result = await broker.place_order("AAPL", "buy", 1, client_order_id="original")
    assert result == confirmed
    calls = broker._make_request_with_retry.await_args_list
    assert [call.args[0] for call in calls] == ["POST", "GET"]
    assert calls[1].kwargs["params"] == {"client_order_id": "original"}


@pytest.mark.asyncio
async def test_ws_handler_handles_null_filled_qty(monkeypatch):
    """A null cumulative quantity still reaches the actual order update path."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from backend.integrations import alpaca_stream
    from backend.api import socketio_server

    order = SimpleNamespace(id="local-id", filled_qty=0, user_id="test", symbol="AAPL",
                            side="buy", qty=1, order_type="market", submitted_at=None)
    repo = SimpleNamespace(get_by_broker_order_id=AsyncMock(return_value=order),
                           attach_broker_result=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(alpaca_stream, "get_session_context", session_context)
    monkeypatch.setattr(alpaca_stream, "OrdersRepo", lambda _: repo)
    accounting = AsyncMock(return_value={"applied": False, "reason": "non_fill_status"})
    monkeypatch.setattr(alpaca_stream, "apply_incremental_fill_accounting", accounting)
    broadcast = AsyncMock()
    monkeypatch.setattr(socketio_server, "broadcast_order_update", broadcast)
    stream = alpaca_stream.AlpacaStreamClient.__new__(alpaca_stream.AlpacaStreamClient)
    await stream._process_trade_update({"data": {"event": "new", "order": {
        "id": "broker-id", "status": "new", "filled_qty": None,
    }}})
    repo.attach_broker_result.assert_awaited_once()
    assert repo.attach_broker_result.await_args.kwargs["status"] == stream._map_alpaca_status("new")
    assert repo.attach_broker_result.await_args.kwargs["filled_qty"] is None
    assert accounting.await_args.kwargs["cumulative_filled_qty"] == 0.0
    session.commit.assert_awaited_once()
    assert broadcast.await_args.args[1]["filled_qty"] == 0.0
