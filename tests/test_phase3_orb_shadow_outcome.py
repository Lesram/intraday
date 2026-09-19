"""Tests for the Phase 3 ORB shadow outcome simulator."""
from __future__ import annotations

import pandas as pd

from scripts.phase3_orb_shadow_outcome import (
    SimulationConfig,
    normalize_bars,
    run_orb_simulation,
    summarize_outcomes,
)


def _bars(rows: list[tuple[str, float, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )


def test_orb_outcome_sim_finds_next_open_eod_win():
    raw = {
        "TEST": _bars([
            ("2026-04-20T13:30:00Z", 100.0, 100.4, 99.8, 100.2, 1000),
            ("2026-04-20T13:31:00Z", 100.2, 100.5, 100.0, 100.4, 1000),
            ("2026-04-20T13:32:00Z", 100.4, 100.8, 100.3, 100.7, 1000),
            ("2026-04-20T13:33:00Z", 100.7, 100.9, 100.5, 100.8, 1000),
            ("2026-04-20T13:34:00Z", 100.8, 101.0, 100.6, 101.0, 1000),
            ("2026-04-20T13:35:00Z", 101.0, 101.4, 100.9, 101.3, 1000),
            ("2026-04-20T13:36:00Z", 101.4, 102.0, 101.3, 101.8, 1000),
            ("2026-04-20T13:37:00Z", 101.8, 102.5, 101.7, 102.2, 1000),
            ("2026-04-20T13:38:00Z", 102.2, 103.0, 102.1, 102.8, 1000),
        ])
    }
    bars = normalize_bars(raw, ["TEST"])

    outcomes = run_orb_simulation(
        bars,
        SimulationConfig(
            symbols=["TEST"],
            min_rv_ratio=0.0,
            slippage_bps=0.0,
            max_stale_minutes=0.0,
            min_trades_for_signal=1,
        ),
    )
    summary = summarize_outcomes(
        outcomes,
        SimulationConfig(min_rv_ratio=0.0, slippage_bps=0.0, min_trades_for_signal=1),
    )

    assert len(outcomes) == 1
    assert outcomes[0].exit_reason == "eod"
    assert outcomes[0].entry_open == 101.4
    assert outcomes[0].pnl_per_share > 0
    assert summary["recommendation"] == "continue_shadow_review"


def test_orb_outcome_sim_records_stop_loss():
    raw = {
        "TEST": _bars([
            ("2026-04-20T13:30:00Z", 100.0, 100.4, 99.8, 100.2, 1000),
            ("2026-04-20T13:31:00Z", 100.2, 100.5, 100.0, 100.4, 1000),
            ("2026-04-20T13:32:00Z", 100.4, 100.8, 100.3, 100.7, 1000),
            ("2026-04-20T13:33:00Z", 100.7, 100.9, 100.5, 100.8, 1000),
            ("2026-04-20T13:34:00Z", 100.8, 101.0, 100.6, 101.0, 1000),
            ("2026-04-20T13:35:00Z", 101.0, 101.4, 100.9, 101.3, 1000),
            ("2026-04-20T13:36:00Z", 101.4, 101.6, 99.0, 99.5, 1000),
            ("2026-04-20T13:37:00Z", 99.5, 100.0, 99.0, 99.8, 1000),
        ])
    }
    bars = normalize_bars(raw, ["TEST"])

    outcomes = run_orb_simulation(
        bars,
        SimulationConfig(
            symbols=["TEST"],
            min_rv_ratio=0.0,
            slippage_bps=0.0,
            max_stale_minutes=0.0,
        ),
    )

    assert len(outcomes) == 1
    assert outcomes[0].exit_reason == "stop"
    assert outcomes[0].pnl_per_share < 0


def test_orb_summary_rejects_negative_sample():
    config = SimulationConfig(min_trades_for_signal=2)
    raw = {
        "TEST": _bars([
            ("2026-04-20T13:30:00Z", 100.0, 100.4, 99.8, 100.2, 1000),
            ("2026-04-20T13:31:00Z", 100.2, 100.5, 100.0, 100.4, 1000),
            ("2026-04-20T13:32:00Z", 100.4, 100.8, 100.3, 100.7, 1000),
            ("2026-04-20T13:33:00Z", 100.7, 100.9, 100.5, 100.8, 1000),
            ("2026-04-20T13:34:00Z", 100.8, 101.0, 100.6, 101.0, 1000),
            ("2026-04-20T13:35:00Z", 101.0, 101.4, 100.9, 101.3, 1000),
            ("2026-04-20T13:36:00Z", 101.4, 101.6, 99.0, 99.5, 1000),
        ])
    }
    outcomes = run_orb_simulation(
        normalize_bars(raw, ["TEST"]),
        SimulationConfig(
            symbols=["TEST"],
            min_rv_ratio=0.0,
            slippage_bps=0.0,
            max_stale_minutes=0.0,
        ),
    )

    summary = summarize_outcomes(outcomes, config)

    assert summary["total_trades"] == 1
    assert summary["gross_pnl_per_share"] < 0
    assert summary["recommendation"] == "insufficient_negative_sample"
