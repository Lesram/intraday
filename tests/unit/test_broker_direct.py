"""
Tests for backend/infra/broker.py - Broker health check utilities
Tests broker health checking functionality using direct import.
"""

import os
import sys
import pytest
import asyncio
import importlib.util
import time
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock, MagicMock


class TestBrokerDirect:
    """Test suite for broker health utilities using direct import."""
    
    def setup_method(self):
        """Set up direct module import."""
        backend_path = Path(__file__).parent.parent.parent / "backend"
        self.backend_path = str(backend_path.resolve())
        
        # Import the broker module using importlib
        broker_path = os.path.join(self.backend_path, 'infra', 'broker.py')
        spec = importlib.util.spec_from_file_location("broker_module", broker_path)
        self.broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.broker)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.broker = None

    def test_redis_import_availability(self):
        """Test Redis import availability flag."""
        # The REDIS_AVAILABLE flag should be set based on import success
        assert hasattr(self.broker, 'REDIS_AVAILABLE')
        assert isinstance(self.broker.REDIS_AVAILABLE, bool)

    def test_logger_initialization(self):
        """Test logger is properly initialized."""
        assert hasattr(self.broker, 'logger')
        assert self.broker.logger is not None

    @pytest.mark.asyncio
    async def test_broker_health_check_redis_unavailable(self):
        """Test broker health check when Redis client is unavailable."""
        # Temporarily set REDIS_AVAILABLE to False
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.REDIS_AVAILABLE = False
        
        try:
            with pytest.raises(RuntimeError, match="Redis client library not installed"):
                await self.broker.broker_health_check()
            
        finally:
            # Restore original value
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    @patch('backend.config.get_settings')
    @patch('backend.utils.logger.get_logger')
    async def test_broker_health_check_success_mocked(self, mock_get_logger, mock_get_settings):
        """Test successful broker health check with mocked dependencies."""
        # Mock logger
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        mock_get_settings.return_value = mock_settings
        
        # Mock Redis client at the module level
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        original_redis = getattr(self.broker, 'redis', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.redis = mock_redis_module
        self.broker.REDIS_AVAILABLE = True
        
        try:
            result = await self.broker.broker_health_check()
            
            assert result is True
            
            # Verify Redis client was created
            mock_redis_module.from_url.assert_called_once()
            
            # Verify ping was called
            mock_redis_client.ping.assert_called_once()
            
            # Verify client was properly closed
            mock_redis_client.aclose.assert_called_once()
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    @patch('backend.config.get_settings')
    @patch('backend.utils.logger.get_logger')
    async def test_broker_health_check_ping_false_mocked(self, mock_get_logger, mock_get_settings):
        """Test broker health check when ping returns False."""
        # Mock logger
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        mock_get_settings.return_value = mock_settings
        
        # Mock Redis client that returns False on ping
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = False
        mock_redis_client.aclose = AsyncMock()
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        original_redis = getattr(self.broker, 'redis', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.redis = mock_redis_module
        self.broker.REDIS_AVAILABLE = True
        
        try:
            with pytest.raises(RuntimeError, match="Broker health check failed: ping returned False"):
                await self.broker.broker_health_check()
            
            # Verify client was still properly closed
            mock_redis_client.aclose.assert_called_once()
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    @patch('backend.config.get_settings')
    @patch('backend.utils.logger.get_logger')
    async def test_broker_health_check_connection_error_mocked(self, mock_get_logger, mock_get_settings):
        """Test broker health check with connection error."""
        # Mock logger
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        mock_get_settings.return_value = mock_settings
        
        # Mock Redis client that raises connection error
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = ConnectionError("Connection refused")
        mock_redis_client.aclose = AsyncMock()
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        original_redis = getattr(self.broker, 'redis', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.redis = mock_redis_module
        self.broker.REDIS_AVAILABLE = True
        
        try:
            with pytest.raises(ConnectionError, match="Connection refused"):
                await self.broker.broker_health_check()
            
            # Verify client was still properly closed
            mock_redis_client.aclose.assert_called_once()
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            self.broker.REDIS_AVAILABLE = original_redis_available

    def test_module_imports(self):
        """Test that all required imports are available."""
        # Check standard library imports
        assert hasattr(self.broker, 'asyncio')
        assert hasattr(self.broker, 'time')
        assert hasattr(self.broker, 'Optional')
        
        # Check the REDIS_AVAILABLE flag was properly set based on import
        assert hasattr(self.broker, 'REDIS_AVAILABLE')

    def test_module_constants(self):
        """Test module-level constants and their types."""
        # REDIS_AVAILABLE should be a boolean
        assert isinstance(self.broker.REDIS_AVAILABLE, bool)
        
        # Logger should be initialized
        assert self.broker.logger is not None

    def test_broker_health_check_function_signature(self):
        """Test that broker_health_check function has the expected signature."""
        import inspect
        
        # Check function exists
        assert hasattr(self.broker, 'broker_health_check')
        
        # Check it's async
        assert asyncio.iscoroutinefunction(self.broker.broker_health_check)
        
        # Check signature
        sig = inspect.signature(self.broker.broker_health_check)
        assert len(sig.parameters) == 0  # No parameters
        
        # Check return annotation
        assert sig.return_annotation == bool

    @pytest.mark.asyncio
    async def test_redis_connection_parameters_mocked(self):
        """Test that Redis connection is created with correct parameters."""
        # Mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        # Mock settings within the module
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://test:6379/0"
        
        # Patch within the module's namespace
        original_redis = getattr(self.broker, 'redis', None)
        original_get_settings = getattr(self.broker, 'get_settings', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        
        self.broker.redis = mock_redis_module
        self.broker.get_settings = Mock(return_value=mock_settings)
        self.broker.REDIS_AVAILABLE = True
        
        try:
            await self.broker.broker_health_check()
            
            # Verify Redis client creation parameters
            call_args = mock_redis_module.from_url.call_args
            assert call_args[0][0] == "redis://test:6379/0"  # URL
            
            kwargs = call_args[1]
            assert kwargs['encoding'] == "utf-8"
            assert kwargs['decode_responses'] is True
            assert kwargs['socket_timeout'] == 5.0
            assert kwargs['socket_connect_timeout'] == 5.0
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            if original_get_settings is not None:
                self.broker.get_settings = original_get_settings
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    async def test_timing_measurement_success(self):
        """Test that broker health check measures timing on success."""
        # Mock Redis client
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis_client.aclose = AsyncMock()
        
        # Mock logger
        mock_logger = Mock()
        
        # Replace the redis module and logger in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        # Mock settings within the module
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        
        # Patch within the module's namespace
        original_redis = getattr(self.broker, 'redis', None)
        original_get_settings = getattr(self.broker, 'get_settings', None)
        original_logger = getattr(self.broker, 'logger', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        
        self.broker.redis = mock_redis_module
        self.broker.get_settings = Mock(return_value=mock_settings)
        self.broker.logger = mock_logger
        self.broker.REDIS_AVAILABLE = True
        
        try:
            result = await self.broker.broker_health_check()
            
            assert result is True
            
            # Check that debug log was called with timing info
            mock_logger.debug.assert_called()
            debug_call = mock_logger.debug.call_args[0][0]
            assert "Broker health check passed in" in debug_call
            assert "s" in debug_call  # Should contain seconds
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            if original_get_settings is not None:
                self.broker.get_settings = original_get_settings
            if original_logger is not None:
                self.broker.logger = original_logger
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    async def test_timing_measurement_error(self):
        """Test that broker health check measures timing on error."""
        # Mock Redis client that raises an error
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = Exception("Test error")
        mock_redis_client.aclose = AsyncMock()
        
        # Mock logger
        mock_logger = Mock()
        
        # Replace the redis module and logger in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        # Mock settings within the module
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        
        # Patch within the module's namespace
        original_redis = getattr(self.broker, 'redis', None)
        original_get_settings = getattr(self.broker, 'get_settings', None)
        original_logger = getattr(self.broker, 'logger', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        
        self.broker.redis = mock_redis_module
        self.broker.get_settings = Mock(return_value=mock_settings)
        self.broker.logger = mock_logger
        self.broker.REDIS_AVAILABLE = True
        
        try:
            with pytest.raises(Exception, match="Test error"):
                await self.broker.broker_health_check()
            
            # Check that error log was called with timing info
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Broker health check failed in" in error_call
            assert "s: Test error" in error_call  # Should contain timing and error
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            if original_get_settings is not None:
                self.broker.get_settings = original_get_settings
            if original_logger is not None:
                self.broker.logger = original_logger
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    @patch('backend.config.get_settings')
    @patch('backend.utils.logger.get_logger')
    async def test_client_cleanup_on_error(self, mock_get_logger, mock_get_settings):
        """Test that Redis client is properly cleaned up even when error occurs during ping."""
        # Mock logger
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "redis://localhost:6379/0"
        mock_get_settings.return_value = mock_settings
        
        # Mock Redis client that raises error during ping
        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = Exception("Network error")
        mock_redis_client.aclose = AsyncMock()
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.return_value = mock_redis_client
        
        original_redis = getattr(self.broker, 'redis', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.redis = mock_redis_module
        self.broker.REDIS_AVAILABLE = True
        
        try:
            with pytest.raises(Exception, match="Network error"):
                await self.broker.broker_health_check()
            
            # Verify client cleanup was called even on error
            mock_redis_client.aclose.assert_called_once()
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            self.broker.REDIS_AVAILABLE = original_redis_available

    @pytest.mark.asyncio
    @patch('backend.config.get_settings')  
    @patch('backend.utils.logger.get_logger')
    async def test_client_creation_error(self, mock_get_logger, mock_get_settings):
        """Test broker health check with Redis client creation error."""
        # Mock logger
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Mock settings
        mock_settings = Mock()
        mock_settings.data.redis_url = "invalid://url"
        mock_get_settings.return_value = mock_settings
        
        # Replace the redis module in the broker module
        mock_redis_module = Mock()
        mock_redis_module.from_url.side_effect = ValueError("Invalid Redis URL")
        
        original_redis = getattr(self.broker, 'redis', None)
        original_redis_available = self.broker.REDIS_AVAILABLE
        self.broker.redis = mock_redis_module
        self.broker.REDIS_AVAILABLE = True
        
        try:
            with pytest.raises(ValueError, match="Invalid Redis URL"):
                await self.broker.broker_health_check()
            
        finally:
            # Restore original values
            if original_redis is not None:
                self.broker.redis = original_redis
            self.broker.REDIS_AVAILABLE = original_redis_available

    def test_docstring_and_typing(self):
        """Test that the function has proper documentation and typing."""
        import inspect
        
        func = self.broker.broker_health_check
        
        # Check docstring exists
        assert func.__doc__ is not None
        assert "Perform broker health check" in func.__doc__
        assert "Returns:" in func.__doc__
        assert "True if broker is healthy" in func.__doc__
        
        # Check return type annotation
        sig = inspect.signature(func)
        assert sig.return_annotation == bool
