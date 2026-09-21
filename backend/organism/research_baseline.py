"""Fail closed when a configured paper restart restores another policy baseline.

Only fingerprints already loaded model objects for identity; it never deserializes
or rewrites a model. The deployment supplies the approved JSON from its immutable
image. Absence of configuration is reported as unverified, never as acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pickle
from typing import Any

from backend.organism import research_policy
from backend.organism.model_fingerprint import is_random_forest, random_forest_fingerprint

BASELINE_ENV = "ORGANISM_APPROVED_POLICY_BASELINE"
COMPONENT_FIELDS = {
    "alpha_scanner": ("WEIGHT_ML", "WEIGHT_VOLUME", "WEIGHT_MOMENTUM", "WEIGHT_BREAKOUT", "WEIGHT_REGIME"),
    "breakout_scanner": ("W_SQUEEZE", "W_VOLUME", "W_CONTRACTION", "W_RS", "W_PIVOT", "W_FLOW",
                         "BB_PERIOD", "ATR_SHORT", "ATR_LONG", "PIVOT_LOOKBACK", "VOL_AVG_PERIOD", "RS_PERIOD"),
    "kelly_sizer": ("_evolved_regime_scales",),
    "exit_engine": ("atr_multiplier", "trailing_start_atr", "trailing_distance_atr", "partial_tp_r", "partial_tp_pct"),
}


def _fingerprint(value: Any) -> str:
    if value is None:
        raise RuntimeError("Approved research baseline requires all retained models/caches")
    if is_random_forest(value):
        return random_forest_fingerprint(value)
    return hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def runtime_identity(engine: Any) -> dict:
    """Prediction-relevant restored state, excluding outcome bookkeeping."""
    signal = engine.signal_gen
    ensemble = signal._ensemble
    models = {
        "ml_classifier.joblib": _fingerprint(signal._clf),
        "ml_regressor.joblib": _fingerprint(signal._reg),
    }
    weights = []
    for classifier, regressor, name, weight in ensemble._models:
        if f"ensemble_{name}_clf.joblib" in models:
            raise RuntimeError("Duplicate approved ensemble model identity")
        models[f"ensemble_{name}_clf.joblib"] = _fingerprint(classifier)
        models[f"ensemble_{name}_reg.joblib"] = _fingerprint(regressor)
        weights.append({"name": name, "weight": float(weight)})
    for attr in ("_last_val_X", "_last_val_y_dir", "_last_val_y_ret"):
        models[f"ml_{attr.lstrip('_')}.joblib"] = _fingerprint(getattr(signal, attr, None))
    identity = {
        "effective_policy_hash": research_policy.effective_policy_hash(engine.evolved_params),
        "applied_components": {
            component: {field: getattr(getattr(engine, component), field) for field in fields}
            for component, fields in COMPONENT_FIELDS.items()
        },
        "models": models,
        "model_generation": signal.generation,
        "trained": bool(signal.is_trained),
        "ensemble_trained": bool(ensemble._is_trained),
        "ensemble_weights": weights,
        "feature_columns": list(signal._feature_cols),
        "direction_threshold_buy": signal._direction_threshold_buy,
        "direction_threshold_sell": signal._direction_threshold_sell,
        "evolved_feature_weights": getattr(signal, "_evolved_feature_weights", {}),
        "xgb_parameters": dict(signal._xgb_params),
        "calibration_map": signal.calibration_to_dict()["map"],
    }
    return json.loads(json.dumps(identity, sort_keys=True, allow_nan=False))


def verify_configured_baseline(engine: Any, *, brain_loaded: bool) -> dict:
    """Verify restored memory before engine reconstruction, training or ticks."""
    configured = os.environ.get(BASELINE_ENV, "")
    if not configured:
        return {"configured": False, "verified": False, "reason": "baseline_not_configured"}
    try:
        if not brain_loaded or not research_policy.RESEARCH_POLICY_LOCKED:
            raise ValueError("retained brain and research lock required")
        path = Path(configured)
        if not path.is_absolute():
            raise ValueError("approved baseline path must be absolute")
        raw = path.read_bytes()
        baseline = json.loads(raw)
        if type(baseline.get("schema_version")) is not int or baseline["schema_version"] != 1:
            raise ValueError("unsupported approved baseline schema")
        if baseline.get("policy_id") != research_policy.RESEARCH_POLICY_ID:
            raise ValueError("approved baseline policy mismatch")
        params_hash = research_policy.effective_policy_hash(baseline["effective_policy_params"])
        if params_hash != baseline["effective_policy_hash"]:
            raise ValueError("approved baseline parameter hash mismatch")
        actual = runtime_identity(engine)
        if actual["effective_policy_hash"] != params_hash or actual != baseline["runtime_identity"]:
            raise ValueError("restored prediction baseline mismatch")
        if not actual["trained"] or not actual["ensemble_trained"]:
            raise ValueError("approved retained models must be trained")
        return {
            "configured": True, "verified": True, "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "runtime_identity_sha256": hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        }
    except Exception as exc:
        # Never echo arbitrary JSON/model contents or configuration values.
        raise RuntimeError("Approved research baseline verification failed; startup held") from exc
