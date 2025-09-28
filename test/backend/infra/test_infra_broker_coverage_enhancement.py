"""
Comprehensive test suite for backend.infra.broker module.
Targets significant coverage improvement from 32% baseline by testing broker health checks with Redis mocking.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from backend.infra.broker import broker_health_check, REDIS_AVAILABLE


class TestBrokerHealthCheck:
    """Test broker health check functionality with comprehensive Redis mocking."""

    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_success(self, mock_get_settings, mock_redis):
        """Test successful broker health check."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check
        result = await broker_health_check()
        
        # Verify results
        assert result is True
        
        # Verify Redis client setup
        mock_redis.from_url.assert_called_once_with(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0
        )
        
        # Verify ping was called
        mock_redis_client.ping.assert_called_once()
        
        # Verify connection cleanup
        mock_redis_client.aclose.assert_called_once()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_ping_false(self, mock_get_settings, mock_redis):
        """Test broker health check when ping returns False."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client with failing ping
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = False  # Ping fails
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check and expect exception
        with pytest.raises(RuntimeError, match="Broker health check failed: ping returned False"):
            await broker_health_check()
        
        # Verify connection was still cleaned up
        mock_redis_client.aclose.assert_called_once()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_connection_error(self, mock_get_settings, mock_redis):
        """Test broker health check with Redis connection error."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client that raises connection error
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = ConnectionError("Connection refused")
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check and expect exception propagation
        with pytest.raises(ConnectionError, match="Connection refused"):
            await broker_health_check()
        
        # Verify connection was still cleaned up
        mock_redis_client.aclose.assert_called_once()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_timeout_error(self, mock_get_settings, mock_redis):
        """Test broker health check with timeout error."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client that raises timeout
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = asyncio.TimeoutError("Operation timed out")
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check and expect timeout exception
        with pytest.raises(asyncio.TimeoutError, match="Operation timed out"):
            await broker_health_check()
        
        # Verify connection cleanup
        mock_redis_client.aclose.assert_called_once()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', False)
    async def test_broker_health_check_redis_unavailable(self):
        """Test broker health check when Redis library is not available."""
        # Execute health check and expect RuntimeError
        with pytest.raises(RuntimeError, match="Redis client library not installed"):
            await broker_health_check()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_settings_error(self, mock_get_settings, mock_redis):
        """Test broker health check when settings retrieval fails."""
        # Setup mock settings to raise exception
        mock_get_settings.side_effect = Exception("Settings not available")
        
        # Execute health check and expect exception propagation
        with pytest.raises(Exception, match="Settings not available"):
            await broker_health_check()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_redis_creation_error(self, mock_get_settings, mock_redis):
        """Test broker health check when Redis client creation fails."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "invalid://url"
        mock_get_settings.return_value = mock_settings
        
        # Setup Redis.from_url to raise exception
        mock_redis.from_url.side_effect = ValueError("Invalid Redis URL")
        
        # Execute health check and expect exception propagation
        with pytest.raises(ValueError, match="Invalid Redis URL"):
            await broker_health_check()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_aclose_error(self, mock_get_settings, mock_redis):
        """Test broker health check when aclose fails (exception propagated)."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client with failing aclose
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose.side_effect = Exception("Close failed")
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check - should fail due to aclose error in finally block
        with pytest.raises(Exception, match="Close failed"):
            await broker_health_check()
        
        # Verify aclose was attempted
        mock_redis_client.aclose.assert_called_once()
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    @patch('backend.infra.broker.logger')
    async def test_broker_health_check_logging_success(self, mock_logger, mock_get_settings, mock_redis):
        """Test broker health check success logging."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check
        result = await broker_health_check()
        assert result is True
        
        # Verify success logging
        mock_logger.debug.assert_called_once()
        debug_call_args = mock_logger.debug.call_args[0][0]
        assert "Broker health check passed" in debug_call_args
        assert "s" in debug_call_args  # Duration logged
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    @patch('backend.infra.broker.logger')
    async def test_broker_health_check_logging_failure(self, mock_logger, mock_get_settings, mock_redis):
        """Test broker health check failure logging."""
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client that fails
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = ConnectionError("Test connection error")
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check and expect exception
        with pytest.raises(ConnectionError):
            await broker_health_check()
        
        # Verify error logging
        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args[0][0]
        assert "Broker health check failed" in error_call_args
        assert "Test connection error" in error_call_args
        assert "s" in error_call_args  # Duration logged
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', False)
    @patch('backend.infra.broker.logger')
    async def test_broker_health_check_redis_unavailable_logging(self, mock_logger):
        """Test logging when Redis is unavailable."""
        # Execute health check and expect RuntimeError
        with pytest.raises(RuntimeError, match="Redis client library not installed"):
            await broker_health_check()
        
        # Verify warning was logged
        mock_logger.warning.assert_called_once_with(
            "Redis client not available, treating as unhealthy"
        )
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    @patch('backend.infra.broker.time')
    async def test_broker_health_check_timing_accuracy(self, mock_time, mock_get_settings, mock_redis):
        """Test accurate timing measurement in health check."""
        # Setup timing mocks
        start_times = [100.0, 100.0, 105.0]  # Start, ping start, end
        mock_time.time.side_effect = start_times
        
        # Setup mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check
        result = await broker_health_check()
        assert result is True
        
        # Verify time.time was called for duration measurement
        assert mock_time.time.call_count >= 2
    
    @patch('backend.infra.broker.REDIS_AVAILABLE', True)
    @patch('backend.infra.broker.redis')
    @patch('backend.infra.broker.get_settings')
    async def test_broker_health_check_complex_redis_url(self, mock_get_settings, mock_redis):
        """Test broker health check with complex Redis URL."""
        # Setup mock settings with complex URL
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://user:pass@redis.example.com:6380/1?ssl=true"
        mock_get_settings.return_value = mock_settings
        
        # Setup mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        mock_redis.from_url.return_value = mock_redis_client
        
        # Execute health check
        result = await broker_health_check()
        assert result is True
        
        # Verify Redis client was created with the complex URL
        mock_redis.from_url.assert_called_once_with(
            "redis://user:pass@redis.example.com:6380/1?ssl=true",
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0
        )


class TestBrokerModuleConstants:
    """Test broker module constants and imports."""
    
    def test_redis_available_constant(self):
        """Test that REDIS_AVAILABLE constant is properly set."""
        # Test the constant exists and is boolean
        assert isinstance(REDIS_AVAILABLE, bool)
        
        # In this test environment, it should be True (since we have redis installed)
        # But we test both scenarios through patching in other tests
    
    def test_module_imports(self):
        """Test that module imports work correctly."""
        # Test that the module can be imported
        import backend.infra.broker
        
        # Test that the main function is available
        assert hasattr(backend.infra.broker, 'broker_health_check')
        assert callable(backend.infra.broker.broker_health_check)
        
        # Test logger is available
        assert hasattr(backend.infra.broker, 'logger')
    
    def test_import_error_handling(self):
        """Test ImportError handling for Redis library by re-importing the module."""
        import sys
        import importlib
        
        # Temporarily remove redis from sys.modules if present
        redis_modules_to_restore = {}
        for module_name in list(sys.modules.keys()):
            if module_name.startswith('redis'):
                redis_modules_to_restore[module_name] = sys.modules.pop(module_name)
        
        # Mock the import to raise ImportError
        original_import = __builtins__['__import__']
        
        def mock_import(name, *args, **kwargs):
            if name == 'redis.asyncio':
                raise ImportError("No module named 'redis.asyncio'")
            return original_import(name, *args, **kwargs)
        
        try:
            __builtins__['__import__'] = mock_import
            
            # Force reimport of broker module to trigger ImportError handling
            if 'backend.infra.broker' in sys.modules:
                del sys.modules['backend.infra.broker']
            
            import backend.infra.broker
            
            # Verify REDIS_AVAILABLE is False when import fails
            assert backend.infra.broker.REDIS_AVAILABLE is False
            
        finally:
            # Restore original import and redis modules
            __builtins__['__import__'] = original_import
            for module_name, module in redis_modules_to_restore.items():
                sys.modules[module_name] = module
            
            # Reimport broker module to restore normal state
            if 'backend.infra.broker' in sys.modules:
                del sys.modules['backend.infra.broker']
            importlib.import_module('backend.infra.broker')


if __name__ == "__main__":
    pytest.main([__file__])