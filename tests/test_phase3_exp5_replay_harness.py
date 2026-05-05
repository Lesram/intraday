"""Phase 3 Exp 5 replay harness tests.

The Exp 5 script is a research instrument, not live trading logic. These
tests keep it honest: dynamic seed counts, strategy-exit bucketing, explicit
promotion criteria, and no leaked monkeypatch of the live exit table.
"""
from __future__ import annotations

import pytest


def test_phase3_exp5_parse_variants_rejects_empty_or_nonpositive():
    from scripts.backtest_exp5_stop_atr import parse_variants

    assert parse_variants("2.5, 3.0,3.5") == [2.5, 3.0, 3.5]

    with pytest.raises(ValueError):
        parse_variants("")
    with pytest.raises(ValueError):
        parse_variants("2.5,0")


def test_phase3_exp5_seed_copy_uses_dynamic_trade_count(tmp_path):
    from scripts.backtest_exp5_stop_atr import (
        prepare_seed_dir,
        read_new_trade_rows,
    )

    source = tmp_path / "seed"
    source.mkdir()
    (source / "trade_history.csv").write_text(
        "symbol,pnl,exit_reason\n"
        "AAPL,1.0,max_holding_period\n"
        "MSFT,-2.0,stop_loss\n"
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    target, seed_count = prepare_seed_dir(source, out_dir, "atr2_5")

    assert seed_count == 2
    assert target != source
    with (target / "trade_history.csv").open("a") as fh:
        fh.write("NVDA,3.0,trailing_stop\n")
    assert read_new_trade_rows(target, seed_count) == [{
        "symbol": "NVDA",
        "pnl": "3.0",
        "exit_reason": "trailing_stop",
    }]


def test_phase3_exp5_comparison_enforces_shadow_promotion_gate():
    from scripts.backtest_exp5_stop_atr import build_comparison

    baseline = {
        "label": "atr2_5",
        "chop_stop_atr": 2.5,
        "trades_in_brain_history_during_replay": 10,
        "total_pnl_broker": -10.0,
        "win_rate_broker": 0.2,
        "max_drawdown": 0.010,
        "exit_reason_mix": {
            "stop_loss": 4,
            "pyramid_cut_full_at_-1.2R": 4,
            "max_holding_period": 2,
        },
    }
    good_variant = {
        "label": "atr3_0",
        "chop_stop_atr": 3.0,
        "trades_in_brain_history_during_replay": 10,
        "total_pnl_broker": -4.0,
        "win_rate_broker": 0.3,
        "max_drawdown": 0.012,
        "exit_reason_mix": {
            "stop_loss": 2,
            "pyramid_cut_full_at_-1.2R": 4,
            "max_holding_period": 4,
        },
    }
    bad_pyramid_variant = {
        "label": "atr3_5",
        "chop_stop_atr": 3.5,
        "trades_in_brain_history_during_replay": 10,
        "total_pnl_broker": 0.0,
        "win_rate_broker": 0.4,
        "max_drawdown": 0.012,
        "exit_reason_mix": {
            "stop_loss": 1,
            "pyramid_cut_full_at_-1.2R": 7,
            "max_holding_period": 2,
        },
    }

    comparison = build_comparison([baseline, good_variant, bad_pyramid_variant])

    variants = {v["label"]: v for v in comparison["variants"]}
    assert variants["atr2_5"]["passes_exp5_gate"] is False
    assert variants["atr3_0"]["passes_exp5_gate"] is True
    assert variants["atr3_5"]["passes_exp5_gate"] is False
    assert comparison["recommendation"] == "shadow_candidate"
    assert comparison["criteria"]["replay_scope"] == "relative_delta_only"


@pytest.mark.asyncio
async def test_phase3_exp5_run_one_restores_exit_table_after_failure(tmp_path):
    from backend.organism.adaptive_exits import AdaptiveExitEngine
    from scripts.backtest_exp5_stop_atr import run_one

    source = tmp_path / "seed"
    source.mkdir()
    (source / "trade_history.csv").write_text("symbol,pnl,exit_reason\n")
    original = AdaptiveExitEngine.REGIME_STOP_ATR.copy()

    with pytest.raises(FileNotFoundError):
        await run_one(
            9.9,
            "failing",
            cache_dir=tmp_path / "missing_cache",
            seed_source=source,
            out_dir=tmp_path / "out",
            max_ticks=1,
        )

    assert AdaptiveExitEngine.REGIME_STOP_ATR == original
