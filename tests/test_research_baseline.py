"""Approved restart baseline must match actual restored prediction state."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.organism import research_baseline as baseline, research_policy as policy


def engine():
    signal = SimpleNamespace(
        _clf={"weight": 1}, _reg={"weight": 2},
        _ensemble=SimpleNamespace(_models=[({"weight": 3}, {"weight": 4}, "rf", 0.4)], _is_trained=True),
        _last_val_X=[1, 2], _last_val_y_dir=[1], _last_val_y_ret=[0.1],
        generation=389, is_trained=True, _feature_cols=["ret", "vol"],
        _direction_threshold_buy=0.7, _direction_threshold_sell=0.3,
        _evolved_feature_weights={"ret": 0.5},
        _xgb_params={"max_depth": 3},
        calibration_to_dict=Mock(return_value={"map": [0.1, 0.3, 0.5, 0.7, 0.9], "counts": [[1, 2]] * 5}),
    )
    components = {name: SimpleNamespace(**{field: 1.0 for field in fields})
                  for name, fields in baseline.COMPONENT_FIELDS.items()}
    return SimpleNamespace(signal_gen=signal, evolved_params=SimpleNamespace(stop_atr_scale=0.985, symbol_trade_counts={"SPY": 2}), **components)


def approve(tmp_path, monkeypatch, obj):
    value = {"schema_version": 1, "policy_id": policy.RESEARCH_POLICY_ID,
             "effective_policy_params": policy.effective_policy_params(obj.evolved_params),
             "effective_policy_hash": policy.effective_policy_hash(obj.evolved_params),
             "runtime_identity": baseline.runtime_identity(obj)}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(value))
    monkeypatch.setenv(baseline.BASELINE_ENV, str(path))
    return path


def test_unconfigured_is_explicitly_unverified(monkeypatch):
    monkeypatch.delenv(baseline.BASELINE_ENV, raising=False)
    assert baseline.verify_configured_baseline(None, brain_loaded=False) == {
        "configured": False, "verified": False, "reason": "baseline_not_configured"}


def test_verified_restore_preserves_files_and_ignores_outcome_counts(tmp_path, monkeypatch):
    obj = engine(); path = approve(tmp_path, monkeypatch, obj); before = path.read_bytes()
    obj.evolved_params.symbol_trade_counts["SPY"] += 1
    obj.signal_gen.calibration_to_dict.return_value["counts"][0][0] += 4
    observed = baseline.verify_configured_baseline(obj, brain_loaded=True)
    assert observed["configured"] and observed["verified"]
    assert len(observed["sha256"]) == 64
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["model", "ensemble", "weight", "feature_columns", "threshold", "feature_weight", "calibration_map", "params", "untrained", "cache", "generation", "exit_component", "scanner_component", "kelly_component", "breakout_component", "xgb_config"])
def test_changed_prediction_context_fails_closed(tmp_path, monkeypatch, mutation):
    obj = engine(); path = approve(tmp_path, monkeypatch, obj); before = path.read_bytes()
    s = obj.signal_gen
    if mutation == "model": s._clf["weight"] = 9
    elif mutation == "ensemble": s._ensemble._models[0][0]["weight"] = 9
    elif mutation == "weight": s._ensemble._models[0] = (*s._ensemble._models[0][:3], 0.9)
    elif mutation == "feature_columns": s._feature_cols.reverse()
    elif mutation == "threshold": s._direction_threshold_buy = 0.8
    elif mutation == "feature_weight": s._evolved_feature_weights["ret"] = 0.8
    elif mutation == "calibration_map": s.calibration_to_dict.return_value["map"][0] = 0.8
    elif mutation == "params": obj.evolved_params.stop_atr_scale = 1.5
    elif mutation == "untrained": s.is_trained = False
    elif mutation == "cache": s._last_val_X = None
    elif mutation == "generation": s.generation += 1
    elif mutation == "exit_component": obj.exit_engine.atr_multiplier = 9
    elif mutation == "scanner_component": obj.alpha_scanner.WEIGHT_VOLUME = 9
    elif mutation == "kelly_component": obj.kelly_sizer._evolved_regime_scales = {"chop": 9}
    elif mutation == "breakout_component": obj.breakout_scanner.BB_PERIOD = 99
    elif mutation == "xgb_config": s._xgb_params["max_depth"] = 9
    with pytest.raises(RuntimeError, match="startup held"):
        baseline.verify_configured_baseline(obj, brain_loaded=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["missing", "corrupt", "schema", "policy", "hash", "no_brain", "unlocked"])
def test_invalid_baseline_cannot_certify_startup(tmp_path, monkeypatch, failure):
    obj = engine(); path = approve(tmp_path, monkeypatch, obj)
    if failure == "missing": path.unlink()
    elif failure == "corrupt": path.write_text("not json")
    elif failure in ("schema", "policy", "hash"):
        data = json.loads(path.read_text())
        data[{"schema": "schema_version", "policy": "policy_id", "hash": "effective_policy_hash"}[failure]] = "invalid"
        path.write_text(json.dumps(data))
    elif failure == "unlocked": monkeypatch.setattr(policy, "RESEARCH_POLICY_LOCKED", False)
    with pytest.raises(RuntimeError, match="startup held"):
        baseline.verify_configured_baseline(obj, brain_loaded=failure != "no_brain")
