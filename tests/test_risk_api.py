"""Risk Management DB smoke test.

This is disabled by default because it requires a live database.
Enable with RUN_DB_INTEGRATION_TESTS=1.
"""

import os

import pytest

from backend.infra.db import get_db_session, init_db
from backend.services.risk_manager import RiskManager


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION_TESTS") != "1",
    reason="DB integration tests are disabled by default. Set RUN_DB_INTEGRATION_TESTS=1 and configure DATABASE_URL to enable.",
)


@pytest.mark.asyncio
async def test_risk_dashboard_smoke():
    """Smoke-test dashboard data load without crashing."""
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading_platform",
    )
    init_db(dsn)
    
    # Get a database session
    async for session in get_db_session():
        try:
            # Use a test user ID (should exist in your users table)
            # For now, let's just test with user ID 1
            risk_manager = RiskManager(session)
            
            dashboard_data = await risk_manager.get_dashboard_data(user_id=1)
            
            assert dashboard_data is not None
            
        except Exception as e:
            raise AssertionError(f"Risk dashboard smoke test failed: {e}") from e
        finally:
            break  # Only need one iteration


if __name__ == "__main__":
    raise SystemExit(
        "Run via pytest: `RUN_DB_INTEGRATION_TESTS=1 python -m pytest -q tests/test_risk_api.py -s`"
    )
