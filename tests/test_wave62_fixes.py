"""V11 prep / Wave-62 (2026-05-03): YY-3 + YY-4 observability completeness.

Locks regressions for:
- YY-3 (MEDIUM, deferred V10): ORGANISM_ENTRIES_BLOCKED has a `reason`
  label dimension so dashboards can break down halt cause without
  scraping logs.
- YY-4 (MEDIUM, deferred V10): BackgroundTrainer training-internal
  failure path now wires Prometheus counter (ml_retrain_failures_total)
  + dispatch_alert_from_thread for operator paging.

Run with: ./venv/bin/python -m pytest tests/test_wave62_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_yy_3_organism_entries_blocked_has_reason_label():
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    assert "YY-3 closure" in src, "YY-3 closure marker missing"
    assert 'labelnames=("reason",)' in src, (
        "YY-3 regression: ORGANISM_ENTRIES_BLOCKED no longer has reason label."
    )
    assert "ORGANISM_ENTRIES_BLOCKED.labels(reason=" in src, (
        "YY-3 regression: counter increment no longer passes reason label."
    )


def test_yy_4_ml_retrain_failures_counter_exists():
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    assert "YY-4 closure" in src, "YY-4 closure marker missing"
    assert "ml_retrain_failures_total" in src, (
        "YY-4 regression: ml_retrain_failures_total counter removed."
    )


def test_yy_4_background_trainer_alerts_on_training_error():
    from backend.organism import background_trainer
    src = inspect.getsource(background_trainer)
    assert "YY-4 closure" in src, "YY-4 closure marker missing in background_trainer"
    assert "ML Retrain Internal Failure" in src, (
        "YY-4 regression: training-internal error no longer dispatches alert."
    )
    # The executor-exception path should also bump the counter.
    assert 'labels(phase="executor")' in src
    assert 'labels(phase="training")' in src
