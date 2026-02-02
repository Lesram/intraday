"""
Tests for backend.infra.broker module  
Target: 100% coverage on broker health checks
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBrokerHealthCheck:
    """Test broker_health_check function"""
    
    @pytest.mark.asyncio
    async def test_broker_health_check_redis_unavailable(self):
        """Test broker health check when Redis not available"""
        with patch('backend.infra.broker.REDIS_AVAILABLE', False):
            from backend.infra.broker import broker_health_check
            
            with pytest.raises(RuntimeError, match="not installed"):
                await broker_health_check()
    
    @pytest.mark.asyncio
    async def test_broker_health_check_success_with_actual_redis(self):
        """Test broker health check with mocked redis client"""
        # We can test the actual function if redis.asyncio is available
        import backend.infra.broker as broker_module
        
        if not broker_module.REDIS_AVAILABLE:
            pytest.skip("Redis not installed")
        
        # Mock the redis.from_url to return a mock client
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        
        # Patch redis.asyncio.from_url at the point where it's used
        with patch('redis.asyncio.from_url', return_value=mock_client):
            result = await broker_module.broker_health_check()
            assert result is True
            mock_client.ping.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broker_health_check_ping_fails(self):
        """Test broker health check when ping fails"""
        import backend.infra.broker as broker_module
        
        if not broker_module.REDIS_AVAILABLE:
            pytest.skip("Redis not installed")
        
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=False)
        mock_client.aclose = AsyncMock()
        
        with patch('redis.asyncio.from_url', return_value=mock_client):
            with pytest.raises(RuntimeError, match="ping returned False"):
                await broker_module.broker_health_check()
    
    @pytest.mark.asyncio
    async def test_broker_health_check_connection_error(self):
        """Test broker health check with connection error"""
        import backend.infra.broker as broker_module
        
        if not broker_module.REDIS_AVAILABLE:
            pytest.skip("Redis not installed")
        
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("Connection failed"))
        mock_client.aclose = AsyncMock()
        
        with patch('redis.asyncio.from_url', return_value=mock_client):
            with pytest.raises(ConnectionError):
                await broker_module.broker_health_check()
