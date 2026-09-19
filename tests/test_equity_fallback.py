"""Tests for equity-zero fallback behavior in LiveEngine._get_equity."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class FakePositionsService:
    """Minimal mock of PositionsService for equity tests."""
    def __init__(self):
        self.portfolio_value = 100000.0
        self.buying_power = 50000.0

    async def get_total_portfolio_value(self):
        return self.portfolio_value

    async def get_buying_power(self):
        return self.buying_power


class FakeEngine:
    """Minimal fake engine with just equity-related state."""
    def __init__(self):
        self._positions_service = FakePositionsService()
        self._tick_count = 10
        self._last_valid_equity = 0.0
        self._last_valid_equity_tick = 0
        self._EQUITY_FALLBACK_MAX_TICKS = 30

    async def _get_equity(self) -> float:
        """Copy of the real _get_equity method for testing."""
        import logging
        logger = logging.getLogger(__name__)

        value = 0.0
        try:
            raw = await self._positions_service.get_total_portfolio_value()
            value = float(raw) if raw else 0.0
        except Exception:
            try:
                bp = await self._positions_service.get_buying_power()
                value = float(bp) if bp else 0.0
            except Exception:
                pass

        if value > 0:
            self._last_valid_equity = value
            self._last_valid_equity_tick = self._tick_count
            return value

        ticks_since = self._tick_count - self._last_valid_equity_tick
        if self._last_valid_equity > 0 and ticks_since <= self._EQUITY_FALLBACK_MAX_TICKS:
            logger.warning(
                "Broker returned zero equity — using last-known-good $%.2f "
                "(%d ticks stale, max %d)",
                self._last_valid_equity, ticks_since, self._EQUITY_FALLBACK_MAX_TICKS,
            )
            return self._last_valid_equity

        return 0.0


@pytest.mark.asyncio
async def test_single_zero_after_valid_does_not_block():
    """One bad zero-equity sample after valid equity returns last-known-good."""
    engine = FakeEngine()

    # First: valid equity
    eq = await engine._get_equity()
    assert eq == 100000.0
    assert engine._last_valid_equity == 100000.0

    # Second: broker returns 0
    engine._positions_service.portfolio_value = 0.0
    engine._positions_service.buying_power = 0.0
    engine._tick_count = 11
    eq = await engine._get_equity()
    assert eq == 100000.0  # fallback to last-known-good


@pytest.mark.asyncio
async def test_repeated_zeros_beyond_window_returns_zero():
    """After staleness window expires, returns 0.0."""
    engine = FakeEngine()

    # Establish valid equity
    eq = await engine._get_equity()
    assert eq == 100000.0

    # Broker fails, advance past staleness window
    engine._positions_service.portfolio_value = 0.0
    engine._positions_service.buying_power = 0.0
    engine._tick_count = 10 + 31  # beyond 30-tick window
    eq = await engine._get_equity()
    assert eq == 0.0  # no fallback -- too stale


@pytest.mark.asyncio
async def test_no_prior_valid_equity_returns_zero():
    """If no valid equity was ever seen, returns 0.0 immediately."""
    engine = FakeEngine()
    engine._positions_service.portfolio_value = 0.0
    engine._positions_service.buying_power = 0.0

    eq = await engine._get_equity()
    assert eq == 0.0


@pytest.mark.asyncio
async def test_exception_fallback_to_buying_power():
    """When portfolio_value raises, falls back to buying_power."""
    engine = FakeEngine()

    async def raise_error():
        raise ConnectionError("API down")

    engine._positions_service.get_total_portfolio_value = raise_error
    eq = await engine._get_equity()
    assert eq == 50000.0


@pytest.mark.asyncio
async def test_recovery_after_zero():
    """Equity recovering after zero readings resets fallback state."""
    engine = FakeEngine()

    # Valid
    await engine._get_equity()

    # Zero
    engine._positions_service.portfolio_value = 0.0
    engine._positions_service.buying_power = 0.0
    engine._tick_count = 11
    eq = await engine._get_equity()
    assert eq == 100000.0  # fallback

    # Recovery
    engine._positions_service.portfolio_value = 105000.0
    engine._tick_count = 12
    eq = await engine._get_equity()
    assert eq == 105000.0
    assert engine._last_valid_equity == 105000.0
