"""V8 / Wave-38 (2026-05-03): tests for ml/mlops/brokers cleanup.

Locks the regressions for:
- NN-MED-1: backend/mlops/ (10 files, ~5k LOC) entirely orphan; only
  __init__.py re-exported from backend.ml.model_manager. Deleted.
- NN-MED-2: 8 of 14 backend/ml/ modules orphan (data_processing,
  ensemble_framework, model_management, pipeline, prediction_service,
  sentiment, staleness_detector, validation). Deleted.
- NN-MED-3: backend/optimization/portfolio_optimizer.py orphan. Deleted.
- NN-MED-4: backend/brokers/{alpaca_production, broker_failover}.py
  orphan; live broker path is backend/integrations/alpaca_broker.py.
  Deleted.
- Cascade: backend/risk/{advanced_risk_manager, advanced_risk}.py were
  only referenced by orphan portfolio_optimizer. Deleted.

Run with: ./venv/bin/python -m pytest tests/test_wave38_fixes.py -v
"""
from __future__ import annotations

import os

import pytest


@pytest.mark.parametrize("path", [
    "backend/mlops",
    "backend/ml/data_processing.py",
    "backend/ml/ensemble_framework.py",
    "backend/ml/model_management.py",
    "backend/ml/pipeline.py",
    "backend/ml/prediction_service.py",
    "backend/ml/sentiment.py",
    "backend/ml/staleness_detector.py",
    "backend/ml/validation.py",
    "backend/brokers/alpaca_production.py",
    "backend/brokers/broker_failover.py",
    "backend/optimization/portfolio_optimizer.py",
    "backend/risk/advanced_risk_manager.py",
    "backend/risk/advanced_risk.py",
])
def test_wave38_orphan_path_deleted(path: str):
    """The orphan modules must stay deleted.  If you re-introduce one,
    wire it into a live import path AND add a reachability test."""
    assert not os.path.exists(path), (
        f"Wave-38 regression: {path} re-created. Either wire it live "
        "or keep it deleted."
    )


def test_wave38_no_dangling_mlops_imports():
    """No backend code may import from the deleted backend.mlops package."""
    import subprocess
    out = subprocess.run(
        ["bash", "-c", "grep -rn 'from backend\\.mlops\\|import backend\\.mlops' backend/ --include='*.py' || true"],
        capture_output=True, text=True, timeout=10,
    )
    hits = [
        line for line in out.stdout.splitlines()
        if line.strip() and "test_" not in line
    ]
    assert len(hits) == 0, (
        f"Wave-38 regression: {len(hits)} dangling backend.mlops "
        f"import(s):\n" + "\n".join(hits)
    )


def test_wave38_canonical_broker_path_intact():
    """The live alpaca path lives in backend/integrations/alpaca_broker.py
    and must survive the wave-38 cleanup."""
    assert os.path.isfile("backend/integrations/alpaca_broker.py"), (
        "Wave-38 over-cleanup: deleted the canonical alpaca broker."
    )


def test_wave38_canonical_ml_modules_intact():
    """The 8 deleted ml modules must NOT have taken down model_manager,
    feature_engineering, or training (the live ml core)."""
    import os
    for must_exist in [
        "backend/ml/model_manager.py",
        "backend/ml/feature_engineering.py",
        "backend/ml/training.py",
    ]:
        assert os.path.isfile(must_exist), (
            f"Wave-38 over-cleanup: deleted live ml module {must_exist}."
        )
