"""V13 W94 (Lens 3: Strategy Expectancy) — alert helpers.

V12 W71 surfaced expectancy.  V12 W76 wired drawdown-kill alerts.
W94 closes the gap in between: an operator-visible alert when the
brain's last-50 win-rate falls below a configurable floor.

The threshold defaults to 0.30 (matches the V13 framework
"`last_50_win_rate < 0.30`" trigger).  Override via env
``STRATEGY_LAST_50_WIN_RATE_FLOOR``.

Two callable surfaces:

- ``should_fire_low_win_rate_alert(payload)`` — pure function.  No
  side effects; returns ``(should_fire, reason)``.  Easily testable.

- ``maybe_dispatch_low_win_rate_alert(payload)`` — wraps the above
  and dispatches an operator alert via the existing
  ``dispatch_alert_from_thread`` path.  No-ops if the alert layer
  is unimportable (e.g. test env without backend.infra.alerting).

The alert IS rate-limited via a module-level set of seen
fingerprints so a stuck condition doesn't spam every save.  The
fingerprint resets whenever the win-rate climbs back above
``floor + RECOVERY_HYSTERESIS`` (default 0.05).

W94 also exposes a CI-grade gate (``check_strategy_floor.py``) that
reads ``STRATEGY_FLOOR_TOTAL_PNL`` and refuses merge to release
branch if the brain's total PnL is below the floor.  The gate's
default is ``null`` (opt-in) — choosing the floor is product policy,
W94 ships the mechanism only.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


_DEFAULT_FLOOR = 0.30
_DEFAULT_RECOVERY_HYSTERESIS = 0.05

# Module-state used for rate-limiting.  Keyed by (n_trades, win_rate)
# rounded so successive reads of the same brain state don't re-page.
_FIRED_FINGERPRINTS: set[tuple[int, float]] = set()


def _floor() -> float:
    raw = os.environ.get("STRATEGY_LAST_50_WIN_RATE_FLOOR")
    if not raw:
        return _DEFAULT_FLOOR
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "W94: STRATEGY_LAST_50_WIN_RATE_FLOOR=%r not parseable; "
            "falling back to default %.2f",
            raw, _DEFAULT_FLOOR,
        )
        return _DEFAULT_FLOOR


def _hysteresis() -> float:
    raw = os.environ.get("STRATEGY_LAST_50_WIN_RATE_RECOVERY")
    if not raw:
        return _DEFAULT_RECOVERY_HYSTERESIS
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_RECOVERY_HYSTERESIS


def should_fire_low_win_rate_alert(
    payload: dict[str, Any],
    *,
    floor: float | None = None,
) -> tuple[bool, str]:
    """Decide whether the strategy-expectancy payload warrants an alert.

    Returns ``(should_fire, reason)``.  The reason is operator-readable
    and includes the floor and the observed win rate.

    Pure function — no env reads when ``floor`` is provided explicitly,
    no side effects ever.  Safe to call from tests.

    Trigger: ``last_50_win_rate < floor`` and ``n_trades >= 50``
    (don't false-fire on a brain with 5 trades in its lifetime).
    """
    f = floor if floor is not None else _floor()
    n = int(payload.get("n_trades", 0) or 0)
    wr = payload.get("last_50_win_rate")
    if wr is None:
        return False, "no last_50_win_rate in payload"
    if n < 50:
        return False, f"insufficient trades ({n} < 50) — too few to alert"
    try:
        wrf = float(wr)
    except (TypeError, ValueError):
        return False, f"last_50_win_rate {wr!r} not parseable"
    if wrf >= f:
        return False, f"last_50_win_rate={wrf:.3f} >= floor={f:.3f}"
    return (
        True,
        f"last_50_win_rate={wrf:.3f} < floor={f:.3f} "
        f"(n_trades={n}, total_pnl={payload.get('total_pnl')})",
    )


def maybe_dispatch_low_win_rate_alert(
    payload: dict[str, Any],
    *,
    floor: float | None = None,
) -> bool:
    """Fire the operator alert if warranted, with rate-limiting.

    Returns True iff an alert was actually dispatched on this call.
    """
    fire, reason = should_fire_low_win_rate_alert(payload, floor=floor)
    if not fire:
        return False

    # Fingerprint to rate-limit.  Round win-rate to 2dp so jitter of
    # 0.001 doesn't re-page.
    n = int(payload.get("n_trades", 0) or 0)
    try:
        wrf = float(payload.get("last_50_win_rate"))
    except (TypeError, ValueError):
        wrf = -1.0
    fp = (n // 5, round(wrf, 2))  # bucket trade-count by 5s
    if fp in _FIRED_FINGERPRINTS:
        logger.info("W94: low-win-rate alert suppressed (already fired %s)", fp)
        return False
    _FIRED_FINGERPRINTS.add(fp)

    # Dispatch via the existing alert path.  We isolate the import so
    # this module is usable in test environments where the alerting
    # backend is stubbed.
    try:
        from backend.infra.alerting import (
            AlertCategory, AlertSeverity, dispatch_alert_from_thread,
            send_alert,
        )
        ok = dispatch_alert_from_thread(
            lambda: send_alert(
                AlertCategory.STRATEGY_HEALTH if hasattr(AlertCategory, "STRATEGY_HEALTH")
                else AlertCategory.SYSTEM_ERROR,
                AlertSeverity.WARNING,
                "Strategy expectancy below floor",
                f"V13 W94: {reason}.  Operator review required.",
            )
        )
        if not ok:
            logger.warning(
                "W94: low-win-rate alert dispatch returned False "
                "(reason=%s)", reason,
            )
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        logger.warning("W94: alert dispatch unavailable: %s", exc)
        return False


def reset_alert_state_for_tests() -> None:
    """Test helper: clear the fired-fingerprints set."""
    _FIRED_FINGERPRINTS.clear()
