from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd


def _feature_frame(**overrides):
    rows = 60
    base = {
        "close": np.linspace(100.0, 105.0, rows),
        "ret_1d": [0.001] * rows,
        "ret_5d": [0.020] * rows,
        "ret_20d": [0.030] * rows,
        "comp_breakout_readiness": [0.80] * rows,
        "comp_squeeze_momentum": [0.70] * rows,
        "comp_institutional_acc": [0.50] * rows,
        "comp_momentum_quality": [0.50] * rows,
        "comp_vol_price_div": [0.50] * rows,
        "vol_sma_ratio": [2.00] * rows,
        "trend_strength": [0.50] * rows,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_alpha_scanner_derives_direction_when_ml_is_dropped_from_gate():
    from backend.organism.alpha_scanner import AlphaScanner

    ml_hold = SimpleNamespace(
        symbol="AAPL",
        direction=0.0,
        confidence=0.99,
        effective_confidence=0.99,
        predicted_return=0.05,
    )

    candidates = AlphaScanner(top_n=1).scan(
        {"AAPL": _feature_frame()},
        {"AAPL": ml_hold},
        current_regime="chop",
        ml_is_trained=True,
        learning_mode=False,
        derive_direction_from_observables=True,
    )

    assert candidates
    assert candidates[0].direction == 1.0
    assert candidates[0].ml_signal is None
    assert candidates[0].expected_return_source == "heuristic"


def test_kelly_sizer_records_invalid_direction_rejection():
    from backend.organism.kelly_sizer import KellySizer

    sizer = KellySizer(min_position_usd=1.0)
    sizes = sizer.size_positions(
        [
            {
                "symbol": "AAPL",
                "direction": 0.0,
                "confidence": 0.9,
                "predicted_return": 0.01,
                "breakout_score": 0.8,
            }
        ],
        portfolio_value=100_000.0,
        current_drawdown=0.0,
        features_by_symbol={"AAPL": _feature_frame()},
        current_regime="chop",
    )

    assert sizes == []
    assert sizer._exploration_rejects[0]["reason"] == "invalid_direction"


def test_filtering_summary_exposes_no_trade_diagnostics():
    from backend.organism.decision_telemetry import FilteringSummary

    payload = FilteringSummary(
        live_candidates_pre_sizing=2,
        rejected_by_direction_zero=2,
        rejected_by_defensive_filter=3,
        rejected_by_sizer_invalid=1,
        no_order_reason="direction_zero",
    ).to_dict()

    assert payload["live_candidates_pre_sizing"] == 2
    assert payload["no_order_reason"] == "direction_zero"
    assert payload["rejections"]["direction_zero"] == 2
    assert payload["rejections"]["defensive_filter"] == 3
    assert payload["rejections"]["sizer_invalid"] == 1
    assert payload["rejections"]["no_order_reason"] == "direction_zero"


def test_live_engine_records_directionless_candidate_as_rejected():
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    rejected = []
    candidate = {
        "symbol": "AAPL",
        "direction": 0.0,
        "confidence": 0.8,
        "effective_confidence": 0.8,
        "breakout_score": 0.7,
    }

    assert engine._record_directionless_candidate(candidate, rejected) is True
    assert rejected == [
        {
            **candidate,
            "live_pipeline_candidate": False,
            "defensive_filter_reason": "direction_zero",
        }
    ]


def test_live_engine_infers_direction_zero_no_order_reason():
    from backend.organism.live_engine import LiveTickResult, OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._last_entries_blocked_reason = ""
    engine._last_gate_rejections = {"direction_zero": 2}
    engine._last_live_candidates_pre_sizing = 0
    engine._last_kelly_sizes = []

    result = LiveTickResult(timestamp="2026-05-12T13:30:00+00:00")

    assert engine._infer_no_order_reason(result) == "direction_zero"
