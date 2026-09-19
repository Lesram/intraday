"""Tests for Phase 3 alternative-timeframe scout tooling."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.phase3_timeframe_scout import (
    build_comparison,
    parse_symbols,
    parse_timeframes,
    resample_bars,
    select_and_limit_bars,
    summarize_exit_mix,
)


def _bars(rows: int = 10) -> pd.DataFrame:
    ts = pd.date_range("2026-05-04T14:00:00Z", periods=rows, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": [stamp.isoformat().replace("+00:00", "Z") for stamp in ts],
        "open": [100.0 + i for i in range(rows)],
        "high": [101.0 + i for i in range(rows)],
        "low": [99.0 + i for i in range(rows)],
        "close": [100.5 + i for i in range(rows)],
        "volume": [1000.0 + i for i in range(rows)],
    })


def test_parse_symbols_and_timeframes_validate_inputs():
    assert parse_symbols("aapl, MSFT") == ["AAPL", "MSFT"]
    assert parse_timeframes("1Min,5Min") == ["1Min", "5Min"]

    with pytest.raises(ValueError):
        parse_timeframes("5Min")
    with pytest.raises(ValueError):
        parse_timeframes("1Min,15Min")
    with pytest.raises(ValueError):
        parse_symbols(" , ")


def test_select_and_limit_bars_normalizes_and_rejects_missing_symbols():
    raw = {"AAPL": _bars(5), "MSFT": _bars(5)}

    selected = select_and_limit_bars(raw, symbols=["MSFT"], bar_limit=3)

    assert list(selected) == ["MSFT"]
    assert len(selected["MSFT"]) == 3
    assert str(selected["MSFT"]["timestamp"].dtype).startswith("datetime64")

    with pytest.raises(ValueError):
        select_and_limit_bars(raw, symbols=["NVDA"], bar_limit=3)
    with pytest.raises(ValueError):
        select_and_limit_bars(raw, symbols=["AAPL"], bar_limit=0)


def test_resample_bars_builds_ohlcv_5min_bars():
    raw = {"AAPL": _bars(10)}
    selected = select_and_limit_bars(raw, symbols=["AAPL"], bar_limit=None)

    resampled = resample_bars(selected, "5Min")

    out = resampled["AAPL"]
    assert len(out) == 2
    assert out["open"].tolist() == [100.0, 105.0]
    assert out["high"].tolist() == [105.0, 110.0]
    assert out["low"].tolist() == [99.0, 104.0]
    assert out["close"].tolist() == [104.5, 109.5]
    assert out["volume"].tolist() == [5010.0, 5035.0]


def test_build_comparison_requires_sample_before_shadow_gate():
    baseline = {
        "timeframe": "1Min",
        "ticks": 80,
        "orders": 4,
        "brain_trades": 4,
        "broker_trades": 4,
        "total_pnl_broker": -4.0,
        "expectancy_per_trade": -1.0,
        "win_rate_broker": 0.25,
        "max_drawdown": 0.01,
        "sharpe": -1.0,
    }
    good_5min = {
        "timeframe": "5Min",
        "ticks": 80,
        "orders": 4,
        "brain_trades": 4,
        "broker_trades": 4,
        "total_pnl_broker": 0.0,
        "expectancy_per_trade": 0.0,
        "win_rate_broker": 0.5,
        "max_drawdown": 0.012,
        "sharpe": 0.0,
    }
    thin_5min = {
        **good_5min,
        "timeframe": "5Min",
        "ticks": 20,
        "brain_trades": 1,
        "broker_trades": 1,
    }

    comparison = build_comparison([baseline, good_5min])
    variants = {row["timeframe"]: row for row in comparison["variants"]}
    assert variants["5Min"]["passes_shadow_gate"] is True
    assert comparison["recommendation"] == "shadow_candidate_needs_full_replay"

    thin = build_comparison([baseline, thin_5min])
    assert thin["variants"][1]["sufficient_sample"] is False
    assert thin["recommendation"] == "do_not_promote_from_scout"


def test_summarize_exit_mix_buckets_reasons():
    summary = summarize_exit_mix([
        {"exit_reason": "pyramid_cut_full_at_-1.2R"},
        {"exit_reason": "stop_loss"},
        {"exit_reason": "max_holding_period"},
    ])

    assert summary["total"] == 3
    assert summary["buckets"]["pyramid_cut"] == 1
    assert summary["shares"]["stop_loss"] == pytest.approx(1 / 3)
