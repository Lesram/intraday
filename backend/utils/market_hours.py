"""
Canonical US equity market hours — single source of truth.

All modules should import from here instead of defining their own
9:30/16:00 constants.  Handles NYSE holidays, early closes, weekends,
and extended-hours windows.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

# ── Timezone ─────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")
UTC = timezone.utc

# ── Core market hours ────────────────────────────────────────────────
MARKET_OPEN = dt_time(9, 30)   # 9:30 AM ET
MARKET_CLOSE = dt_time(16, 0)  # 4:00 PM ET
EARLY_CLOSE = dt_time(13, 0)   # 1:00 PM ET (early close days)

# ── Extended / pre-post hours ────────────────────────────────────────
EXTENDED_OPEN = dt_time(4, 0)    # 4:00 AM ET pre-market
EXTENDED_CLOSE = dt_time(20, 0)  # 8:00 PM ET after-hours

# ── Engine tick-window buffers ───────────────────────────────────────
TICK_START = dt_time(9, 28)   # 2 min before open (warm-up)
TICK_STOP = dt_time(16, 1)    # 1 min after close (late fills)

# ── Diagnostic windows ──────────────────────────────────────────────
PRE_OPEN_TIME = dt_time(9, 25)   # pre-open diagnostics
POST_CLOSE_TIME = dt_time(16, 5)  # post-close diagnostics

# ── Slippage time-of-day buckets ────────────────────────────────────
SLIPPAGE_TIME_ADJUSTMENTS: dict[str, tuple[dt_time, dt_time, float]] = {
    "pre_market":    (dt_time(4, 0),   dt_time(9, 30),  2.0),
    "open_auction":  (dt_time(9, 30),  dt_time(10, 0),  1.5),
    "morning":       (dt_time(10, 0),  dt_time(11, 30), 0.9),
    "midday":        (dt_time(11, 30), dt_time(14, 0),  1.0),
    "afternoon":     (dt_time(14, 0),  dt_time(15, 30), 0.95),
    "close_auction": (dt_time(15, 30), dt_time(16, 0),  1.3),
    "after_hours":   (dt_time(16, 0),  dt_time(20, 0),  2.5),
}


# ═══════════════════════════════════════════════════════════════════════
# NYSE Holiday / Early-Close Calculation
# ═══════════════════════════════════════════════════════════════════════

def _calculate_nyse_holidays(year: int) -> set[date]:
    """Dynamically calculate NYSE holidays for a given year."""
    holidays: set[date] = set()

    # New Year's Day — Jan 1 (observed if weekend)
    ny = date(year, 1, 1)
    if ny.weekday() == 5:
        holidays.add(date(year - 1, 12, 31))
    elif ny.weekday() == 6:
        holidays.add(date(year, 1, 2))
    else:
        holidays.add(ny)

    # MLK Day — Third Monday of January
    jan1 = date(year, 1, 1)
    holidays.add(jan1 + timedelta(days=(7 - jan1.weekday()) % 7 + 14))

    # Presidents Day — Third Monday of February
    feb1 = date(year, 2, 1)
    holidays.add(feb1 + timedelta(days=(7 - feb1.weekday()) % 7 + 14))

    # Good Friday — Friday before Easter (anonymous Gregorian algorithm)
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    holidays.add(easter - timedelta(days=2))

    # Memorial Day — Last Monday of May
    may31 = date(year, 5, 31)
    memorial = may31 - timedelta(days=(may31.weekday() + 7) % 7)
    if memorial.month != 5:
        memorial = may31 - timedelta(days=may31.weekday())
    holidays.add(memorial)

    # Juneteenth — June 19 (observed if weekend)
    jt = date(year, 6, 19)
    if jt.weekday() == 5:
        jt = date(year, 6, 18)
    elif jt.weekday() == 6:
        jt = date(year, 6, 20)
    holidays.add(jt)

    # Independence Day — July 4 (observed if weekend)
    j4 = date(year, 7, 4)
    if j4.weekday() == 5:
        holidays.add(date(year, 7, 3))
    elif j4.weekday() == 6:
        holidays.add(date(year, 7, 5))
    else:
        holidays.add(j4)

    # Labor Day — First Monday of September
    sep1 = date(year, 9, 1)
    holidays.add(sep1 + timedelta(days=(7 - sep1.weekday()) % 7))

    # Thanksgiving — Fourth Thursday of November
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday() + 7) % 7)
    holidays.add(first_thu + timedelta(days=21))

    # Christmas — Dec 25 (observed if weekend)
    xmas = date(year, 12, 25)
    if xmas.weekday() == 5:
        holidays.add(date(year, 12, 24))
    elif xmas.weekday() == 6:
        holidays.add(date(year, 12, 26))
    else:
        holidays.add(xmas)

    return holidays


def _calculate_nyse_early_close(year: int) -> set[date]:
    """NYSE early close days (1:00 PM ET)."""
    early: set[date] = set()

    # Day before July 4
    july3 = date(year, 7, 3)
    if july3.weekday() < 5:
        early.add(july3)

    # Black Friday (day after Thanksgiving)
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday() + 7) % 7)
    early.add(first_thu + timedelta(days=22))

    # Christmas Eve
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5:
        early.add(dec24)

    return early


def _build_sets() -> tuple[set[date], set[date]]:
    """Build holiday + early-close sets for current ± 5 years."""
    cur = datetime.now().year
    holidays: set[date] = set()
    early: set[date] = set()
    for y in range(cur - 1, cur + 6):
        holidays.update(_calculate_nyse_holidays(y))
        early.update(_calculate_nyse_early_close(y))
    return holidays, early


# Module-level cache (built once at import time)
NYSE_HOLIDAYS, NYSE_EARLY_CLOSE = _build_sets()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def is_market_open(
    check_time: datetime | None = None,
    *,
    include_extended: bool = False,
) -> bool:
    """Check if NYSE is currently open.

    Handles weekends, NYSE holidays, and early-close days (1 PM ET).

    Parameters
    ----------
    check_time : datetime, optional
        Defaults to now (UTC).
    include_extended : bool
        If True, returns True during pre/post market (4 AM – 8 PM ET).
    """
    if check_time is None:
        check_time = datetime.now(UTC)

    et = check_time.astimezone(ET)

    # Weekend
    if et.weekday() >= 5:
        return False

    # Holiday
    if et.date() in NYSE_HOLIDAYS:
        return False

    t = et.time()

    if include_extended:
        return EXTENDED_OPEN <= t < EXTENDED_CLOSE

    # Early close
    close = EARLY_CLOSE if et.date() in NYSE_EARLY_CLOSE else MARKET_CLOSE
    return MARKET_OPEN <= t < close


def market_close_time(d: date | None = None) -> dt_time:
    """Return the close time for a given date (handles early closes)."""
    if d is None:
        d = datetime.now(ET).date()
    return EARLY_CLOSE if d in NYSE_EARLY_CLOSE else MARKET_CLOSE


def is_trading_day(d: date | None = None) -> bool:
    """Check if a date is a valid NYSE trading day (not weekend/holiday)."""
    if d is None:
        d = datetime.now(ET).date()
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def get_next_market_open(from_time: datetime | None = None) -> datetime:
    """Get the next market open time (UTC)."""
    if from_time is None:
        from_time = datetime.now(UTC)

    et = from_time.astimezone(ET)
    candidate = et.replace(
        hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute, second=0, microsecond=0
    )
    if et.time() >= MARKET_OPEN:
        candidate += timedelta(days=1)

    while candidate.weekday() >= 5 or candidate.date() in NYSE_HOLIDAYS:
        candidate += timedelta(days=1)

    return candidate.astimezone(UTC)


def get_slippage_multiplier(check_time: datetime | None = None) -> float:
    """Return time-of-day slippage multiplier (1.0 = baseline)."""
    if check_time is None:
        check_time = datetime.now(UTC)
    t = check_time.astimezone(ET).time()
    for _name, (start, end, mult) in SLIPPAGE_TIME_ADJUSTMENTS.items():
        if start <= t < end:
            return mult
    return 1.0  # outside all buckets
