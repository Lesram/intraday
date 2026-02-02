"""
Tests for backend/infra/broker.py

Tests broker health check functionality with proper mocking.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBrokerModule:
    """Tests for broker module."""

    def test_redis_available_constant(self):
        """REDIS_AVAILABLE constant exists."""
        from backend.infra import broker
        
        assert hasattr(broker, "REDIS_AVAILABLE")
        assert isinstance(broker.REDIS_AVAILABLE, bool)

    def test_broker_health_check_exists(self):
        """broker_health_check function exists."""
        from backend.infra import broker
        
        assert hasattr(broker, "broker_health_check")
        assert callable(broker.broker_health_check)


class TestBrokerHealthCheckRedisUnavailable:
    """Tests for broker_health_check when Redis is not available."""

    @pytest.mark.asyncio
    async def test_health_check_fails_when_redis_not_available(self):
        """Health check fails when Redis is not available."""
        from backend.infra import broker
        
        # Save original value
        original_value = broker.REDIS_AVAILABLE
        
        try:
            broker.REDIS_AVAILABLE = False
            
            with pytest.raises(RuntimeError, match="Redis client library not installed"):
                await broker.broker_health_check()
        finally:
            broker.REDIS_AVAILABLE = original_value
