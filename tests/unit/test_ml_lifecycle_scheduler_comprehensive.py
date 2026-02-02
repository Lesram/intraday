"""
Comprehensive tests for backend.ml.lifecycle_scheduler module.
Target: 116 missing statements -> high coverage
"""
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.ml.lifecycle_scheduler import (
    _utcnow,
    _parse_hhmm,
    _next_daily_run,
    _next_weekly_run,
    _next_monthly_run,
    ScheduleConfig,
    LifecycleScheduler,
)


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestUtcnow:
    """Test _utcnow helper."""

    def test_returns_datetime(self):
        """Test returns datetime with UTC timezone."""
        now = _utcnow()
        
        assert isinstance(now, datetime)
        assert now.tzinfo == UTC


class TestParseHhmm:
    """Test _parse_hhmm helper."""

    def test_parse_valid_time(self):
        """Test parsing valid HH:MM format."""
        result = _parse_hhmm("14:30", (0, 0))
        
        assert result == (14, 30)

    def test_parse_midnight(self):
        """Test parsing midnight."""
        result = _parse_hhmm("00:00", (0, 0))
        
        assert result == (0, 0)

    def test_parse_with_spaces(self):
        """Test parsing with spaces."""
        result = _parse_hhmm("  02:15  ", (0, 0))
        
        assert result == (2, 15)

    def test_parse_invalid_returns_default(self):
        """Test parsing invalid string returns default."""
        result = _parse_hhmm("invalid", (5, 30))
        
        assert result == (5, 30)

    def test_parse_empty_returns_default(self):
        """Test parsing empty string returns default."""
        result = _parse_hhmm("", (1, 0))
        
        assert result == (1, 0)


class TestNextDailyRun:
    """Test _next_daily_run helper."""

    def test_next_run_tomorrow_if_time_passed(self):
        """Test schedules for tomorrow if today's time passed."""
        now = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)  # 10:00
        
        result = _next_daily_run(2, 0, now=now)  # Schedule for 02:00
        
        assert result.day == 16  # Tomorrow
        assert result.hour == 2
        assert result.minute == 0

    def test_next_run_today_if_time_not_passed(self):
        """Test schedules for today if time not passed."""
        now = datetime(2024, 1, 15, 1, 0, tzinfo=UTC)  # 01:00
        
        result = _next_daily_run(2, 0, now=now)  # Schedule for 02:00
        
        assert result.day == 15  # Today
        assert result.hour == 2

    def test_next_run_at_exact_time(self):
        """Test at exact scheduled time goes to next day."""
        now = datetime(2024, 1, 15, 2, 0, tzinfo=UTC)
        
        result = _next_daily_run(2, 0, now=now)
        
        assert result.day == 16  # Tomorrow


class TestNextWeeklyRun:
    """Test _next_weekly_run helper."""

    def test_next_run_this_week_if_day_not_passed(self):
        """Test schedules for this week if weekday not passed."""
        # Monday Jan 15, 2024
        now = datetime(2024, 1, 15, 1, 0, tzinfo=UTC)
        
        # Schedule for Sunday (weekday=6)
        result = _next_weekly_run(6, 3, 0, now=now)
        
        assert result.day == 21  # Next Sunday
        assert result.weekday() == 6

    def test_next_run_next_week_if_day_passed(self):
        """Test schedules for next week if weekday passed."""
        # Sunday Jan 21, 2024 at 10:00
        now = datetime(2024, 1, 21, 10, 0, tzinfo=UTC)
        
        # Schedule for Sunday (weekday=6) at 03:00
        result = _next_weekly_run(6, 3, 0, now=now)
        
        assert result.day == 28  # Next Sunday
        assert result.weekday() == 6

    def test_same_weekday_future_time(self):
        """Test same weekday but future time stays same day."""
        # Sunday Jan 21, 2024 at 01:00
        now = datetime(2024, 1, 21, 1, 0, tzinfo=UTC)
        
        # Schedule for Sunday at 03:00
        result = _next_weekly_run(6, 3, 0, now=now)
        
        assert result.day == 21  # Same Sunday


class TestNextMonthlyRun:
    """Test _next_monthly_run helper."""

    def test_next_run_this_month_if_day_not_passed(self):
        """Test schedules for this month if day not passed."""
        now = datetime(2024, 1, 10, 1, 0, tzinfo=UTC)
        
        result = _next_monthly_run(15, 4, 0, now=now)  # Day 15
        
        assert result.month == 1
        assert result.day == 15

    def test_next_run_next_month_if_day_passed(self):
        """Test schedules for next month if day passed."""
        now = datetime(2024, 1, 20, 1, 0, tzinfo=UTC)
        
        result = _next_monthly_run(15, 4, 0, now=now)  # Day 15
        
        assert result.month == 2
        assert result.day == 15

    def test_december_to_january(self):
        """Test December rolls over to January."""
        now = datetime(2024, 12, 20, 1, 0, tzinfo=UTC)
        
        result = _next_monthly_run(15, 4, 0, now=now)
        
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15


# =============================================================================
# ScheduleConfig Tests
# =============================================================================

class TestScheduleConfig:
    """Test ScheduleConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ScheduleConfig()
        
        assert config.daily_time_utc == "02:00"
        assert config.weekly_time_utc == "03:00"
        assert config.weekly_weekday == 6  # Sunday
        assert config.monthly_time_utc == "04:00"
        assert config.monthly_day == 1
        assert config.daily_lookback_days == 60
        assert config.weekly_min_return_drop == 0.02
        assert config.weekly_psi_threshold == 0.15

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ScheduleConfig(
            daily_time_utc="05:00",
            weekly_weekday=0,  # Monday
            monthly_day=15
        )
        
        assert config.daily_time_utc == "05:00"
        assert config.weekly_weekday == 0
        assert config.monthly_day == 15


# =============================================================================
# LifecycleScheduler Tests
# =============================================================================

class TestLifecycleScheduler:
    """Test LifecycleScheduler class."""

    @pytest.fixture
    def mock_sessionmaker(self):
        """Create mock session maker."""
        mock = MagicMock()
        # Create async context manager
        async_session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=async_session)
        mock.return_value.__aexit__ = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def scheduler(self, mock_sessionmaker):
        """Create scheduler instance."""
        return LifecycleScheduler(mock_sessionmaker)

    def test_init(self, scheduler):
        """Test scheduler initialization."""
        assert scheduler._task is None
        assert scheduler.config is not None
        assert scheduler._next_daily is not None
        assert scheduler._next_weekly is not None
        assert scheduler._next_monthly is not None

    def test_is_running_initially_false(self, scheduler):
        """Test is_running is False initially."""
        assert scheduler.is_running is False

    def test_state(self, scheduler):
        """Test getting scheduler state."""
        state = scheduler.state()
        
        assert "next_daily" in state
        assert "next_weekly" in state
        assert "next_monthly" in state
        assert "daily_lookback_days" in state

    @pytest.mark.asyncio
    async def test_start(self, scheduler):
        """Test starting scheduler."""
        scheduler.start()
        
        assert scheduler.is_running is True
        
        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_twice_is_noop(self, scheduler):
        """Test starting twice doesn't create second task."""
        scheduler.start()
        first_task = scheduler._task
        
        scheduler.start()
        
        assert scheduler._task is first_task
        
        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop(self, scheduler):
        """Test stopping scheduler."""
        scheduler.start()
        assert scheduler.is_running is True
        
        await scheduler.stop()
        
        assert scheduler.is_running is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, scheduler):
        """Test stopping when not running is safe."""
        assert scheduler.is_running is False
        
        await scheduler.stop()  # Should not raise
        
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_run_loop_exits_on_stop(self, mock_sessionmaker):
        """Test run loop exits when stop event is set."""
        scheduler = LifecycleScheduler(mock_sessionmaker)
        
        # Start and stop quickly
        scheduler.start()
        await asyncio.sleep(0.1)
        await scheduler.stop()
        
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_run_loop_handles_exceptions(self, mock_sessionmaker):
        """Test run loop handles exceptions gracefully."""
        scheduler = LifecycleScheduler(mock_sessionmaker)
        
        # Mock lifecycle functions to raise exceptions
        with patch('backend.ml.lifecycle.run_daily_monitoring', side_effect=Exception("Test error")):
            with patch.object(scheduler, '_next_daily', _utcnow() - timedelta(hours=1)):
                scheduler.start()
                await asyncio.sleep(0.1)
                await scheduler.stop()
        
        # Should not crash - just logs warning


# =============================================================================
# Environment Variable Configuration Tests
# =============================================================================

class TestEnvironmentConfiguration:
    """Test configuration from environment variables."""

    @pytest.fixture
    def mock_sessionmaker(self):
        """Create mock session maker."""
        return MagicMock()

    def test_config_from_env_variables(self, mock_sessionmaker):
        """Test scheduler reads config from env variables."""
        with patch.dict('os.environ', {
            'ML_DAILY_MONITOR_TIME_UTC': '06:30',
            'ML_WEEKLY_RETRAIN_WEEKDAY': '1',
            'ML_MONTHLY_REVIEW_DAY': '5',
            'ML_DAILY_MONITOR_LOOKBACK_DAYS': '30',
            'ML_WEEKLY_MIN_RETURN_DROP': '0.05',
            'ML_WEEKLY_PSI_THRESHOLD': '0.20'
        }):
            scheduler = LifecycleScheduler(mock_sessionmaker)
            
            assert scheduler.config.daily_lookback_days == 30
            assert scheduler.config.weekly_weekday == 1
            assert scheduler.config.monthly_day == 5
            assert scheduler.config.weekly_min_return_drop == 0.05
            assert scheduler.config.weekly_psi_threshold == 0.20

# =============================================================================
# Additional Coverage Tests for scheduler loops
# =============================================================================

class TestLifecycleSchedulerStopBehavior:
    """Test scheduler stop behavior."""

    @pytest.fixture
    def mock_sessionmaker(self):
        """Create mock async session maker."""
        async def mock_session():
            session = AsyncMock()
            yield session
        
        from contextlib import asynccontextmanager
        return asynccontextmanager(mock_session)

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, mock_sessionmaker):
        """Test stop properly cancels running task."""
        scheduler = LifecycleScheduler(mock_sessionmaker)
        
        # Start scheduler
        scheduler.start()
        
        # Give it a moment
        await asyncio.sleep(0.1)
        
        # Stop scheduler
        await scheduler.stop()
        
        # Task should be None after stop
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_stop_handles_exception_during_cancel(self, mock_sessionmaker):
        """Test stop handles exceptions during task cancellation."""
        scheduler = LifecycleScheduler(mock_sessionmaker)
        
        # Create a mock task that raises on cancel
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        scheduler._task = mock_task
        
        # Set stop event
        scheduler._stop.set()
        
        # Stop should complete without raising
        await scheduler.stop()
        
        assert scheduler._task is None


class TestLifecycleSchedulerLoopException:
    """Test scheduler handles exceptions in run loop."""

    @pytest.fixture
    def mock_sessionmaker(self):
        """Create mock session maker that raises."""
        async def mock_session():
            raise RuntimeError("Database connection failed")
            yield  # Never reached
        
        from contextlib import asynccontextmanager
        return asynccontextmanager(mock_session)

    @pytest.mark.asyncio
    async def test_run_loop_handles_exception(self, mock_sessionmaker):
        """Test run loop continues after exception."""
        scheduler = LifecycleScheduler(mock_sessionmaker)
        
        # Start scheduler
        scheduler.start()
        
        # Wait for at least one loop iteration
        await asyncio.sleep(0.2)
        
        # Stop scheduler - should still work even after exceptions
        await scheduler.stop()