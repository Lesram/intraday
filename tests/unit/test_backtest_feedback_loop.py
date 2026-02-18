import json
from pathlib import Path

import pytest

from scripts import backtest_feedback_loop as loop


def test_propose_overlays_enables_kill_switch_when_dd_exceeds_target():
    metrics = {"max_drawdown_pct": 30.0}
    daily_returns = [0.01, -0.01, 0.02]
    updates, notes = loop._propose_overlays(
        metrics=metrics,
        daily_returns=daily_returns,
        max_dd_target_pct=25.0,
        current_params={},
    )

    assert updates["overlay_kill_switch"] == 1
    assert any("kill-switch" in note for note in notes)


def test_propose_overlays_enables_vol_targeting_when_vol_high():
    metrics = {"max_drawdown_pct": 5.0}
    daily_returns = [0.05, -0.05, 0.04, -0.04]
    updates, _ = loop._propose_overlays(
        metrics=metrics,
        daily_returns=daily_returns,
        max_dd_target_pct=25.0,
        current_params={},
    )

    assert updates["overlay_vol_enabled"] == 1


def test_propose_overlays_enables_gap_guard_on_large_daily_drop():
    metrics = {"max_drawdown_pct": 5.0}
    daily_returns = [0.01, -0.05, 0.02]
    updates, _ = loop._propose_overlays(
        metrics=metrics,
        daily_returns=daily_returns,
        max_dd_target_pct=25.0,
        current_params={},
    )

    assert updates["overlay_gap_enabled"] == 1


def test_propose_overlays_no_changes_when_within_target():
    metrics = {"max_drawdown_pct": 15.0}
    daily_returns = [0.001, -0.001, 0.001]
    updates, notes = loop._propose_overlays(
        metrics=metrics,
        daily_returns=daily_returns,
        max_dd_target_pct=25.0,
        current_params={},
    )

    assert updates == {}
    assert any("No overlay changes proposed" in note for note in notes)


def test_propose_overlays_does_not_loosen_existing_kill_dd():
    metrics = {"max_drawdown_pct": 30.0}
    daily_returns = [0.01, -0.01, 0.02]
    updates, _ = loop._propose_overlays(
        metrics=metrics,
        daily_returns=daily_returns,
        max_dd_target_pct=25.0,
        current_params={"overlay_kill_dd_pct": 0.15},
    )

    assert updates["overlay_kill_dd_pct"] == 0.15


def test_score_calmar_calculation():
    assert loop._score({"cagr_pct": 20.0, "max_drawdown_pct": 10.0}) == 2.0
    assert loop._score({"cagr_pct": 20.0, "max_drawdown_pct": 0.05}) == 200.0


def test_load_config_valid_json(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"symbols": ["AAPL"]}), encoding="utf-8")
    payload = loop._load_config(config_path)
    assert payload["symbols"] == ["AAPL"]


def test_load_config_invalid_json(tmp_path: Path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{bad json}", encoding="utf-8")
    with pytest.raises(SystemExit):
        loop._load_config(config_path)


def test_load_config_missing_file(tmp_path: Path):
    config_path = tmp_path / "missing.json"
    with pytest.raises(SystemExit):
        loop._load_config(config_path)


def test_resolve_window_explicit_args():
    payload = {}
    start, end = loop._resolve_window(payload, "2024-01-01", "2024-12-31")
    assert start == "2024-01-01"
    assert end == "2024-12-31"


def test_resolve_window_from_holdout():
    payload = {"holdout": {"start": "2024-01-01", "end": "2024-12-31"}}
    start, end = loop._resolve_window(payload, None, None)
    assert start == "2024-01-01"
    assert end == "2024-12-31"


def test_resolve_window_from_range():
    payload = {"range": {"start": "2023-01-01", "end": "2023-12-31"}}
    start, end = loop._resolve_window(payload, None, None)
    assert start == "2023-01-01"
    assert end == "2023-12-31"


def test_resolve_window_missing_raises():
    with pytest.raises(SystemExit):
        loop._resolve_window({}, None, None)


def test_get_params_variations():
    assert loop._get_params({"params": {"a": 1}}) == {"a": 1}
    assert loop._get_params({"parameters": {"b": 2}}) == {"b": 2}
    assert loop._get_params({"params": "bad"}) == {}
    assert loop._get_params({}) == {}


def test_get_symbols_variations():
    assert loop._get_symbols({"symbols": ["AAPL", " ", "MSFT"]}) == ["AAPL", "MSFT"]
    assert loop._get_symbols({"symbols": []}) == []
    assert loop._get_symbols({"symbols": "AAPL"}) == []


def test_build_costs_variations():
    costs = loop._build_costs({"costs": {"slippage_bps": 4.0, "commission_per_trade": 0.2}})
    assert costs.slippage_bps == 4.0
    assert costs.commission_per_trade == 0.2

    costs = loop._build_costs({})
    assert costs.slippage_bps == 0.0
    assert costs.commission_per_trade == 0.0

    costs = loop._build_costs({"costs": {"slippage_bps": 3.0}})
    assert costs.slippage_bps == 3.0
    assert costs.commission_per_trade == 0.0
