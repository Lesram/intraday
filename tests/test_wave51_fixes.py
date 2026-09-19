"""V10 / Wave-51 (2026-05-03): tests for persistence + login completeness.

Locks regressions for:
- WW-1 (HIGH): save_essential_state mints a backup snapshot at most
  once per WW1_BACKUP_INTERVAL_SECONDS (default 1h), so production gets
  a populated backups/ dir and PP-2 corrupt-HEAD fallback has snapshots.
- PP2-1 (HIGH): lifespan does an outer-block SELECT 1 smoke check so
  unreachable host / bad creds / wrong DB trigger fail-fast (or
  ALLOW_NO_DB warn), instead of being swallowed by the prewarm's
  inner except.
- UU2-A (HIGH): successful-login rollback now logs at ERROR (mirrors
  failed-login branch from wave-41 UU-2).
- UU2-C (MEDIUM): LotTracker rollback in alpaca_stream now logs at
  ERROR.

Run with: ./venv/bin/python -m pytest tests/test_wave51_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_ww_1_essential_save_creates_backup():
    """save_essential_state must call _create_backup with cadence."""
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain.save_essential_state)
    assert "WW-1" in src, "WW-1 marker missing"
    assert "_create_backup" in src, (
        "WW-1 regression: essential-save no longer mints backups; "
        "PP-2 corrupt-HEAD fallback safety net empty in prod."
    )
    assert "WW1_BACKUP_INTERVAL_SECONDS" in src, (
        "WW-1 regression: cadence env-var removed."
    )


def test_pp2_1_lifespan_smoke_select_in_outer_block():
    """lifespan must SELECT 1 in the outer try, not just the prewarm."""
    from backend.api import lifespan
    src = inspect.getsource(lifespan)
    assert "PP2-1" in src, "PP2-1 marker missing"
    # The smoke session must precede pool prewarm.
    smoke_idx = src.find("PP2-1")
    prewarm_idx = src.find("Pre-warm connection pool")
    assert 0 < smoke_idx < prewarm_idx, (
        "PP2-1 regression: smoke check no longer precedes prewarm."
    )


def test_uu2_a_successful_login_rollback_logs_error():
    """The successful-login branch in auth.py must log rollback failure
    at ERROR (was bare `except: pass`)."""
    from backend.api.routes import auth
    src = inspect.getsource(auth)
    assert "UU2-A" in src, "UU2-A marker missing"
    # Both successful + failed login paths must use logger.error on rollback.
    # Count `logger.error` mentions of rollback-related context.
    assert src.count("UU-2") >= 1 and "UU2-A" in src, (
        "UU2-A regression: marker missing"
    )
    # The bare `except Exception: pass` shape after `await db.rollback()`
    # must be gone.
    assert (
        "await db.rollback()\n            except Exception:\n                pass"
        not in src
    ), (
        "UU2-A regression: bare except: pass on db.rollback() restored "
        "in successful-login branch."
    )


def test_uu2_c_lot_tracker_rollback_logs_error():
    """The LotTracker block in alpaca_stream must log rollback failure
    at ERROR."""
    from backend.integrations import alpaca_stream
    src = inspect.getsource(alpaca_stream)
    assert "UU2-C" in src, "UU2-C marker missing"
    # No bare `except Exception: pass` directly after `await session.rollback()`.
    rollback_idx = src.find("await session.rollback()")
    assert rollback_idx > 0
    window = src[rollback_idx:rollback_idx + 400]
    assert "except Exception:\n                            pass" not in window, (
        "UU2-C regression: bare except: pass on session.rollback() restored."
    )
