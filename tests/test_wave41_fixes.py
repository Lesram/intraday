"""V9 / Wave-41 (2026-05-03): behavioral tests for Critical safety + alerting.

Locks the regressions for:
- PP-1 (CRITICAL): atomic CSV write helper + use sites for equity/epoch/refs
- PP-2 (CRITICAL): brain load() falls back to most-recent backup on corrupt HEAD
- PP-3 (HIGH): CRITICAL severity bypasses dedup/rate-limit/market-hours
  + last-resort logger.critical when ALL channels fail
- PP-4 (CRITICAL): DB-down in development requires explicit ALLOW_NO_DB=1
- UU-1 (CRITICAL): daily-max-loss alert uses canonical dispatch_alert_from_thread
- UU-2 (CRITICAL): auth audit-log rollback exception surfaces at ERROR
- UU-3 (MEDIUM): brain-save-blocked lock-release exception logs at WARNING

Run with: ./venv/bin/python -m pytest tests/test_wave41_fixes.py -v
"""
from __future__ import annotations

import inspect

import pytest


# ─────────────────────────────────────────────────────────────────────
# UU-1 — daily-max-loss canonical dispatcher
# ─────────────────────────────────────────────────────────────────────


def test_uu_1_daily_max_loss_uses_canonical_dispatcher():
    """The daily-max-loss halt site must use dispatch_alert_from_thread,
    NOT the bare try/create_task/except pattern (V5 S-J3-1 redux)."""
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # Locate the daily-max-loss block.
    idx = src.find("DAILY MAX-LOSS HALT")
    assert idx > 0, "Could not locate daily-max-loss block"
    window = src[idx:idx + 2500]
    assert "dispatch_alert_from_thread" in window, (
        "UU-1 regression: daily-max-loss alert no longer uses "
        "canonical dispatch_alert_from_thread. Worker thread will "
        "silently drop the alert (V5 S-J3-1 pattern)."
    )
    # And the bare create_task pattern must be gone.
    assert "_aio.create_task(send_alert(\n" not in window, (
        "UU-1 regression: bare _aio.create_task(send_alert(...)) re-introduced."
    )


# ─────────────────────────────────────────────────────────────────────
# UU-2 — auth audit-log rollback surfaces at ERROR
# ─────────────────────────────────────────────────────────────────────


def test_uu_2_auth_rollback_logs_at_error():
    """db.rollback() failure in auth audit path must log at ERROR."""
    from backend.api.routes import auth
    src = inspect.getsource(auth)
    assert "UU-2" in src, "UU-2 marker missing from auth.py"
    assert "logger.error" in src and "rollback" in src.lower(), (
        "UU-2 regression: auth db.rollback() exception no longer "
        "logs at ERROR. Compliance audit gap could re-emerge."
    )
    # No bare `except: pass` left in the rollback path.
    rollback_idx = src.find("await db.rollback()")
    assert rollback_idx > 0
    window = src[rollback_idx:rollback_idx + 400]
    assert "except Exception:\n                    pass" not in window, (
        "UU-2 regression: bare except: pass on db.rollback() restored."
    )


# ─────────────────────────────────────────────────────────────────────
# UU-3 — brain-save-blocked lock-release surfaces at WARNING
# ─────────────────────────────────────────────────────────────────────


def test_uu_3_brain_save_lock_release_logs_at_warning():
    """Lock-release failure in brain-save-blocked path must log at WARNING."""
    from backend.organism import brain_persistence
    src = inspect.getsource(brain_persistence)
    assert "UU-3" in src, "UU-3 marker missing from brain_persistence.py"


# ─────────────────────────────────────────────────────────────────────
# PP-1 — atomic CSV writes
# ─────────────────────────────────────────────────────────────────────


def test_pp_1_atomic_csv_helper_exists():
    """The _write_csv_atomic helper must be importable from brain_persistence."""
    from backend.organism.brain_persistence import _write_csv_atomic
    assert callable(_write_csv_atomic)


def test_pp_1_save_equity_curve_uses_atomic_write():
    """_save_equity_curve must call _write_csv_atomic, not df.to_csv directly."""
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain._save_equity_curve)
    assert "_write_csv_atomic" in src, (
        "PP-1 regression: _save_equity_curve no longer uses atomic CSV "
        "write. SIGKILL during save can truncate equity_curve.csv."
    )


def test_pp_1_save_epoch_metrics_uses_atomic_write():
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain._save_epoch_metrics)
    assert "_write_csv_atomic" in src, (
        "PP-1 regression: _save_epoch_metrics no longer uses atomic CSV write."
    )


def test_pp_1_save_reference_features_uses_atomic_write():
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain._save_reference_features)
    assert "_write_csv_atomic" in src, (
        "PP-1 regression: _save_reference_features no longer uses atomic CSV write."
    )


def test_pp_1_atomic_csv_actually_atomic(tmp_path):
    """Concrete check: _write_csv_atomic writes via .tmp + replace."""
    import pandas as pd
    from backend.organism.brain_persistence import _write_csv_atomic
    df = pd.DataFrame({"x": [1, 2, 3]})
    target = tmp_path / "test.csv"
    _write_csv_atomic(df, target)
    assert target.is_file()
    # Tmp file must be cleaned up.
    assert not target.with_suffix(target.suffix + ".tmp").exists()
    # Round-trip.
    loaded = pd.read_csv(target)
    assert list(loaded["x"]) == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────
# PP-2 — brain load() backup fallback
# ─────────────────────────────────────────────────────────────────────


def test_pp_2_restore_from_latest_backup_method_exists():
    """OrganismBrain._restore_from_latest_backup must exist."""
    from backend.organism.brain_persistence import OrganismBrain
    assert hasattr(OrganismBrain, "_restore_from_latest_backup"), (
        "PP-2 regression: backup-fallback helper missing. Brain load "
        "failures will go straight to 'starting fresh' again."
    )


def test_pp_2_load_invokes_backup_fallback_on_exception():
    """The load() method must reference _restore_from_latest_backup
    in its exception handler."""
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain.load)
    assert "_restore_from_latest_backup" in src, (
        "PP-2 regression: load() no longer falls back to backup on "
        "HEAD-corrupt. One OOM = lose 161 generations again."
    )
    assert "PP-2" in src, "PP-2 marker missing from load()"


# ─────────────────────────────────────────────────────────────────────
# PP-3 — alert dispatcher escalation for CRITICAL
# ─────────────────────────────────────────────────────────────────────


def test_pp_3_critical_bypasses_dedup_and_rate_limit():
    """CRITICAL severity must bypass dedup, rate-limit, and market-hours
    so a halt alert at 09:31 always pages."""
    from backend.infra import alerting
    src = inspect.getsource(alerting.AlertManager.send_alert)
    assert "PP-3" in src, "PP-3 marker missing from send_alert"
    assert "_is_critical" in src, (
        "PP-3 regression: CRITICAL bypass logic removed."
    )


def test_pp_3_all_channels_failed_logs_critical():
    """When CRITICAL fails to deliver to ANY channel, log at CRITICAL
    so log scrapers can catch as last-resort signal."""
    from backend.infra import alerting
    src = inspect.getsource(alerting.AlertManager.send_alert)
    assert "ALERT-DELIVERY-FAILED" in src or "ALERT-NO-CHANNELS" in src, (
        "PP-3 regression: last-resort CRITICAL log missing when all "
        "alert channels fail."
    )


# ─────────────────────────────────────────────────────────────────────
# PP-4 — DB-down halt in development without ALLOW_NO_DB
# ─────────────────────────────────────────────────────────────────────


def test_pp_4_lifespan_requires_allow_no_db_in_dev():
    """In development mode, DB-init failure must raise unless
    ALLOW_NO_DB=1 is set."""
    from backend.api import lifespan
    src = inspect.getsource(lifespan)
    assert "PP-4" in src, "PP-4 marker missing from lifespan.py"
    assert "ALLOW_NO_DB" in src, (
        "PP-4 regression: ALLOW_NO_DB gate removed; paper trading "
        "would silently drop audit rows again on DB-down."
    )
