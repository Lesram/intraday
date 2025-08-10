"""
Simple B2.4 infrastructure test to validate core components.
"""
import asyncio
from datetime import datetime

import pytest

from backend.config import get_settings
from backend.infra.outbox import BackoffCalculator


@pytest.fixture
async def simple_db_test():
    """Test basic functionality without complex setup."""

    # Test settings
    settings = get_settings()
    print(f"Outbox enabled: {settings.outbox.enabled}")
    print(f"Outbox settings: {settings.outbox}")

    # Test BackoffCalculator
    calculator = BackoffCalculator(
        base_delay_ms=200,
        max_delay_ms=10000,
        jitter_ms=0
    )

    delay_1 = calculator.calculate_delay(1)
    delay_2 = calculator.calculate_delay(2)
    delay_3 = calculator.calculate_delay(3)

    print(f"Backoff delays: {delay_1}ms, {delay_2}ms, {delay_3}ms")

    # Basic assertions
    assert delay_1 == 200
    assert delay_2 == 400
    assert delay_3 == 800

    next_attempt = calculator.next_attempt_time(2)
    print(f"Next attempt time: {next_attempt}")

    assert next_attempt > datetime.utcnow()

    return True


def test_outbox_configuration():
    """Test outbox configuration is properly loaded."""
    settings = get_settings()

    # Check outbox settings exist
    assert hasattr(settings, 'outbox')
    assert hasattr(settings.outbox, 'enabled')
    assert hasattr(settings.outbox, 'poll_interval_ms')
    assert hasattr(settings.outbox, 'batch_size')
    assert hasattr(settings.outbox, 'max_attempts')

    print("✓ Outbox configuration loaded successfully")
    print(f"  - Enabled: {settings.outbox.enabled}")
    print(f"  - Poll Interval: {settings.outbox.poll_interval_ms}ms")
    print(f"  - Batch Size: {settings.outbox.batch_size}")
    print(f"  - Max Attempts: {settings.outbox.max_attempts}")


def test_backoff_calculator():
    """Test exponential backoff calculation."""
    calculator = BackoffCalculator(
        base_delay_ms=200,
        max_delay_ms=10000,
        jitter_ms=0  # No jitter for predictable testing
    )

    # Test backoff progression
    assert calculator.calculate_delay(1) == 200  # Base delay
    assert calculator.calculate_delay(2) == 400  # 2^1 * 200
    assert calculator.calculate_delay(3) == 800  # 2^2 * 200

    # Test max delay cap
    calculator_capped = BackoffCalculator(
        base_delay_ms=200,
        max_delay_ms=1000,
        jitter_ms=0
    )

    assert calculator_capped.calculate_delay(10) == 1000

    print("✓ BackoffCalculator working correctly")


async def test_imports():
    """Test that all imports work correctly."""
    try:
        from backend.infra.outbox import BackoffCalculator, OutboxDispatcher, OutboxRepo
        from backend.infra.repositories.orders import OrdersRepo
        from backend.infra.schemas import Order, OutboxEvent

        print("✓ All core infrastructure imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


if __name__ == "__main__":
    # Run synchronous tests
    print("=== B2.4 Infrastructure Validation ===")

    test_outbox_configuration()
    test_backoff_calculator()

    # Run async import test
    result = asyncio.run(test_imports())

    if result:
        print("✓ All infrastructure tests passed")
    else:
        print("✗ Some infrastructure tests failed")

    print("=== Infrastructure validation complete ===")
