"""Phase 2 strategy attribution coverage.

These tests keep the first Phase 2 step behavioral: compute real segment
payloads from trades, persist them in the brain manifest, and expose them
through the live strategy-health route.  No order-path behavior changes.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_phase2_attribution_collapses_drag_segments_and_flags_inversion():
    from backend.organism.strategy_attribution import compute_from_trades

    trades = []
    for _ in range(6):
        trades.append({
            "pnl": -4.0,
            "exit_reason": "stop_loss",
            "entry_source": "alpha",
            "regime_at_entry": "chop",
            "confidence": 0.75,
        })
    for _ in range(6):
        trades.append({
            "pnl": 2.0,
            "exit_reason": "max_holding_period",
            "entry_source": "breakout",
            "regime_at_entry": "chop",
            "confidence": 0.55,
        })
    trades.append({
        "pnl": -1.0,
        "exit_reason": "pyramid_cut_full_at_-1.3R",
        "entry_source": "",
        "regime_at_entry": "",
        "confidence": 0.35,
    })

    out = compute_from_trades(trades)

    assert out["n_trades"] == 13
    assert out["total_pnl"] == pytest.approx(-13.0)
    assert out["segments"]["exit_reason"][0]["value"] == "stop_loss"
    assert out["segments"]["exit_reason"][0]["total_pnl"] == pytest.approx(-24.0)
    assert any(
        seg["value"] == "pyramid_cut"
        for seg in out["segments"]["exit_reason"]
    )
    assert out["confidence_inversion"]["flag"] is True
    assert (
        out["confidence_inversion"]["buckets"][">=0.7"]["mean_pnl"]
        < out["confidence_inversion"]["buckets"]["0.5-0.6"]["mean_pnl"]
    )


def test_phase2_manifest_writes_attribution_and_dispatches_strategy_alert(tmp_path: Path):
    from backend.organism.brain_persistence import OrganismBrain

    class _State:
        generation = 1
        total_trades = 60
        cumulative_pnl = -40.0
        best_sharpe = -1.0

    class _Trade:
        def __init__(self, pnl: float):
            self.pnl = pnl
            self.exit_reason = "stop_loss" if pnl < 0 else "max_holding_period"
            self.entry_source = "alpha"
            self.regime_at_entry = "chop"
            self.confidence = 0.7 if pnl < 0 else 0.55

    class _Learner:
        state = _State()
        trade_history = [_Trade(-1.0) for _ in range(50)] + [
            _Trade(1.0) for _ in range(10)
        ]

    class _SignalGen:
        _is_trained = True
        _feature_cols = ["a", "b"]

    brain = OrganismBrain.__new__(OrganismBrain)
    brain.brain_dir = tmp_path
    brain._manifest = {}
    brain.trade_history = []

    dispatched = []

    def _fake_alert(payload):
        dispatched.append(payload)
        return True

    manifest: dict = {}
    with patch(
        "backend.organism.strategy_alerts.maybe_dispatch_low_win_rate_alert",
        _fake_alert,
    ):
        brain._apply_live_manifest_fields(manifest, _SignalGen(), _Learner())

    assert manifest["strategy_expectancy"]["n_trades"] == 60
    assert manifest["strategy_expectancy"]["last_50_win_rate"] == pytest.approx(0.2)
    assert manifest["strategy_attribution"]["windows"]["last_50"]["n_trades"] == 50
    assert (
        manifest["strategy_attribution"]["segments"]["exit_reason"][0]["value"]
        == "stop_loss"
    )
    assert len(dispatched) == 1
    assert dispatched[0] == manifest["strategy_expectancy"]


def test_phase2_strategy_health_detail_reads_manifest_attribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    attribution = {
        "n_trades": 50,
        "total_pnl": -25.0,
        "segments": {
            "exit_reason": [
                {"value": "trailing_stop", "n_trades": 5, "total_pnl": -10.0}
            ],
        },
        "windows": {
            "last_50": {
                "n_trades": 50,
                "total_pnl": -25.0,
                "segments": {
                    "exit_reason": [
                        {"value": "trailing_stop", "n_trades": 5, "total_pnl": -10.0}
                    ],
                },
            },
        },
    }
    (brain_dir / "manifest.json").write_text(json.dumps({
        "strategy_expectancy": {
            "n_trades": 50,
            "total_pnl": -25.0,
            "last_50_win_rate": 0.2,
        },
        "strategy_attribution": attribution,
    }))
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(brain_dir))

    from backend.api.routes.strategy_health import strategy_health

    payload = asyncio.run(strategy_health(detail="attribution"))
    assert payload["strategy_attribution"] == attribution

    slim = asyncio.run(strategy_health(window="last_50", detail="attribution"))
    assert slim["window"] == "last_50"
    assert slim["strategy_attribution"]["segments"]["exit_reason"][0]["value"] == (
        "trailing_stop"
    )


def test_phase2_strategy_health_detail_recomputes_attribution_from_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    (brain_dir / "manifest.json").write_text(json.dumps({
        "strategy_expectancy": {
            "n_trades": 2,
            "total_pnl": -3.0,
            "last_50_win_rate": 0.0,
        },
    }))
    (brain_dir / "trade_history.csv").write_text(
        "pnl,exit_reason,entry_source,regime_at_entry,confidence\n"
        "-5.0,stop_loss,alpha,chop,0.72\n"
        "2.0,max_holding_period,breakout,chop,0.55\n"
    )
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(brain_dir))

    from backend.api.routes.strategy_health import strategy_health

    payload = asyncio.run(strategy_health(detail="attribution"))
    attr = payload["strategy_attribution"]
    assert attr["n_trades"] == 2
    assert attr["segments"]["exit_reason"][0]["value"] == "stop_loss"
    assert attr["segments"]["exit_reason"][0]["total_pnl"] == pytest.approx(-5.0)
