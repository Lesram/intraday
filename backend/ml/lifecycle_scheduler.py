"""In-process ML lifecycle scheduler.

Runs:
- daily monitoring snapshot for active models
- weekly retrain check
- monthly promotion review

This is intentionally simple and opt-in.
Enable with: ENABLE_ML_LIFECYCLE_SCHEDULER=1

WARNING: If you run multiple API workers, each worker will run its own scheduler.
In production, use a single scheduler instance (external cron/worker) or implement
DB-based leader election.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os

from backend.utils.logger import get_structured_logger


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_hhmm(value: str, default: tuple[int, int]) -> tuple[int, int]:
    try:
        parts = value.strip().split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return default


def _next_daily_run(hour: int, minute: int, *, now: datetime) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _next_weekly_run(weekday: int, hour: int, minute: int, *, now: datetime) -> datetime:
    # weekday: Monday=0 ... Sunday=6
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - candidate.weekday()) % 7
    if days_ahead == 0 and candidate <= now:
        days_ahead = 7
    return candidate + timedelta(days=days_ahead)


def _next_monthly_run(day: int, hour: int, minute: int, *, now: datetime) -> datetime:
    # day: 1..28 (keep simple)
    year = now.year
    month = now.month

    def make(y: int, m: int) -> datetime:
        return datetime(y, m, day, hour, minute, tzinfo=UTC)

    candidate = make(year, month)
    if candidate <= now:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        candidate = make(year, month)
    return candidate


@dataclass
class ScheduleConfig:
    daily_time_utc: str = "02:00"
    weekly_time_utc: str = "03:00"
    weekly_weekday: int = 6  # Sunday
    monthly_time_utc: str = "04:00"
    monthly_day: int = 1

    daily_lookback_days: int = 60
    weekly_lookback_days: int = 60
    weekly_min_return_drop: float = 0.02
    weekly_psi_threshold: float = 0.15


class LifecycleScheduler:
    def __init__(self, sessionmaker):
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._logger = get_structured_logger(__name__)

        self.config = ScheduleConfig(
            daily_time_utc=os.getenv("ML_DAILY_MONITOR_TIME_UTC", "02:00"),
            weekly_time_utc=os.getenv("ML_WEEKLY_RETRAIN_TIME_UTC", "03:00"),
            weekly_weekday=int(os.getenv("ML_WEEKLY_RETRAIN_WEEKDAY", "6")),
            monthly_time_utc=os.getenv("ML_MONTHLY_REVIEW_TIME_UTC", "04:00"),
            monthly_day=int(os.getenv("ML_MONTHLY_REVIEW_DAY", "1")),
            daily_lookback_days=int(os.getenv("ML_DAILY_MONITOR_LOOKBACK_DAYS", "60")),
            weekly_lookback_days=int(os.getenv("ML_WEEKLY_RETRAIN_LOOKBACK_DAYS", "60")),
            weekly_min_return_drop=float(os.getenv("ML_WEEKLY_MIN_RETURN_DROP", "0.02")),
            weekly_psi_threshold=float(os.getenv("ML_WEEKLY_PSI_THRESHOLD", "0.15")),
        )

        now = _utcnow()
        d_h, d_m = _parse_hhmm(self.config.daily_time_utc, (2, 0))
        w_h, w_m = _parse_hhmm(self.config.weekly_time_utc, (3, 0))
        m_h, m_m = _parse_hhmm(self.config.monthly_time_utc, (4, 0))

        self._next_daily = _next_daily_run(d_h, d_m, now=now)
        self._next_weekly = _next_weekly_run(self.config.weekly_weekday, w_h, w_m, now=now)
        self._next_monthly = _next_monthly_run(self.config.monthly_day, m_h, m_m, now=now)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def state(self) -> dict[str, str]:
        return {
            "next_daily": self._next_daily.isoformat(),
            "next_weekly": self._next_weekly.isoformat(),
            "next_monthly": self._next_monthly.isoformat(),
            "daily_lookback_days": str(self.config.daily_lookback_days),
            "weekly_lookback_days": str(self.config.weekly_lookback_days),
            "weekly_min_return_drop": str(self.config.weekly_min_return_drop),
            "weekly_psi_threshold": str(self.config.weekly_psi_threshold),
            "promotion_mode": os.getenv("ML_PROMOTION_MODE", "immediate"),
        }

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        self._task = None

    async def _run_loop(self) -> None:
        self._logger.info(
            "ML lifecycle scheduler started",
            daily=str(self._next_daily),
            weekly=str(self._next_weekly),
            monthly=str(self._next_monthly),
        )

        from backend.ml.lifecycle import (
            run_daily_monitoring,
            run_monthly_promotion_review,
            run_weekly_retrain,
        )

        while not self._stop.is_set():
            now = _utcnow()
            try:
                if now >= self._next_daily:
                    async with self._sessionmaker() as session:
                        await run_daily_monitoring(session, lookback_days=self.config.daily_lookback_days)
                    d_h, d_m = _parse_hhmm(self.config.daily_time_utc, (2, 0))
                    self._next_daily = _next_daily_run(d_h, d_m, now=now + timedelta(seconds=1))

                if now >= self._next_weekly:
                    async with self._sessionmaker() as session:
                        await run_weekly_retrain(
                            session,
                            lookback_days=self.config.weekly_lookback_days,
                            min_return_drop=self.config.weekly_min_return_drop,
                            psi_threshold=self.config.weekly_psi_threshold,
                        )
                    w_h, w_m = _parse_hhmm(self.config.weekly_time_utc, (3, 0))
                    self._next_weekly = _next_weekly_run(self.config.weekly_weekday, w_h, w_m, now=now + timedelta(seconds=1))

                if now >= self._next_monthly:
                    async with self._sessionmaker() as session:
                        await run_monthly_promotion_review(session)
                    m_h, m_m = _parse_hhmm(self.config.monthly_time_utc, (4, 0))
                    self._next_monthly = _next_monthly_run(self.config.monthly_day, m_h, m_m, now=now + timedelta(seconds=1))

            except Exception as e:
                self._logger.warning("ML lifecycle scheduler iteration failed", error=str(e))

            poll_seconds = float(os.getenv("ML_SCHEDULER_POLL_SECONDS", "60"))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass

        self._logger.info("ML lifecycle scheduler stopped")
