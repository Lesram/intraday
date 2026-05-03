"""V7 HH R-5 / Wave-27 (2026-05-03): shared clock-injection helpers.

The `_now_fn` constructor pattern shipped in V5/V6/V7 (waves 17b, 19,
20b, 22) appears in 6+ classes:
- OrganismLiveEngine (wave-17b)
- RegimeDetector (wave-17b)
- GovernanceController (wave-17b)
- PromotionController (wave-19)
- ContinuousLearner (wave-19)
- StreamingDataProvider (wave-19)
- OrganismBrain (wave-20b)
- BackgroundTrainer (wave-20b)
- DriftDetector (wave-22)

Each class repeats roughly the same 7-line stanza:

    if now_fn is None:
        def _default_now() -> datetime:
            return datetime.now(UTC)
        self._now_fn = _default_now
    else:
        self._now_fn = now_fn

This module provides `default_now_fn()` and `default_time_fn()` so
new classes can write a one-liner:

    self._now_fn = now_fn or default_now_fn

Existing classes can adopt incrementally; not breaking.

Track HH (V7) flagged this as repeated boilerplate at 6+ sites
(refactor proposal R-5). Track U (V5) and Z3 (V6) confirm the pattern
is replay-determinism-critical, so the helper exists in `backend/utils/`
(no replay-time clock dependency to cycle-import).
"""
from __future__ import annotations

import time as _time
from datetime import UTC, datetime
from typing import Callable


def default_now_fn() -> datetime:
    """Canonical wall-clock provider for `_now_fn` slots.

    Returns a tz-aware UTC datetime. Replay engines override per
    instance; live code uses this default.
    """
    return datetime.now(UTC)


def default_time_fn() -> float:
    """Canonical monotonic-ish clock for `_time_fn` slots (uses
    `time.time()` not `time.monotonic()` because most callers compare
    against persisted bar timestamps, which are wall-clock-anchored).
    """
    return _time.time()


# Convenient type aliases.
NowFn = Callable[[], datetime]
TimeFn = Callable[[], float]
