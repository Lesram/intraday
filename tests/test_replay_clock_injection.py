"""V5 Wave-17b (2026-05-03): replay clock-injection coverage.

V5 Track U found that `_now_fn` injection patched only OrganismLiveEngine
while RegimeDetector, GovernanceController, etc. each hold their own clock.
Replay produced `regime_state.timestamp.year == 2026` (wall clock) while
the engine clock said 2024.

Wave-17b extended the injection to the auxiliary components AND replaced
direct `datetime.now(UTC)` calls with `self._now_fn()`. These tests pin
the post-fix invariants so a future regression fails CI.
"""
from __future__ import annotations

from datetime import UTC, datetime

from backend.organism.governance import GovernanceController
from backend.organism.regime import RegimeDetector


def _frozen_clock(year: int = 2024, month: int = 1, day: int = 15):
    """Build a deterministic clock pinned to the given date for tests."""
    fixed = datetime(year, month, day, 14, 30, tzinfo=UTC)
    return lambda: fixed


def test_regime_detector_default_uses_wall_clock():
    det = RegimeDetector()
    # Default clock is `datetime.now(UTC)`; it produces tz-aware UTC and
    # the year is the current year (≥ 2026 in this codebase).
    now = det._now_fn()
    assert now.tzinfo is not None
    assert now.year >= 2026


def test_regime_detector_accepts_injected_clock():
    det = RegimeDetector(now_fn=_frozen_clock(2024, 1, 15))
    now = det._now_fn()
    assert now.year == 2024
    assert now.month == 1
    assert now.day == 15


def test_governance_default_uses_wall_clock():
    gov = GovernanceController()
    now = gov._now_fn()
    assert now.tzinfo is not None
    assert now.year >= 2026


def test_governance_accepts_injected_clock():
    gov = GovernanceController(now_fn=_frozen_clock(2024, 1, 15))
    now = gov._now_fn()
    assert now.year == 2024


def test_governance_drawdown_cooldown_uses_injected_clock():
    """V5 U-4: drawdown cooldown anchor must use injected clock so
    replay sees cooldown elapse on replay-clock time, not wall."""
    gov = GovernanceController(now_fn=_frozen_clock(2024, 1, 15))
    gov.trigger_drawdown_kill(0.10)  # well above default 0.05 limit
    # The drawdown trigger anchor should be 2024, not 2026.
    assert gov._drawdown_triggered_at is not None
    assert gov._drawdown_triggered_at.year == 2024


def test_governance_today_et_uses_injected_clock():
    """V5 U-5: daily change-budget reset key must use injected clock."""
    gov = GovernanceController(now_fn=_frozen_clock(2024, 1, 15))
    # can_change() updates _last_reset_date from _today_et(self._now_fn).
    gov.can_change()
    assert gov._last_reset_date.startswith("2024-01-")
