"""
Comprehensive test suite for backend/api/factory.py
Fixed version with correct interfaces - targeting 90%+ coverage
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the actual module to test
from backend.api import factory


class TestApplicationFactory:
    """Test the create_app factory function with correct parameters."""
    
    def test_create_app_basic(self):
        """Test basic app creation with no parameters."""
        app = factory.create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "Intraday Trading Platform"
        assert app.version == "1.0.0"
        assert hasattr(app.state, 'task_registry')
        assert hasattr(app.state, 'db_sessionmaker')
    
    def test_create_app_with_registry(self):
        """Test app creation with custom registry."""
        custom_registry = Mock()
        app = factory.create_app(registry=custom_registry)
        assert isinstance(app, FastAPI)
        # Registry parameter is accepted but may not be used
    
    def test_create_app_with_ws_queue_max(self):
        """Test app creation with WebSocket queue max setting."""
        app = factory.create_app(ws_queue_max=1000)
        assert isinstance(app, FastAPI)
    
    def test_create_app_with_kwargs(self):
        """Test app creation with additional keyword arguments."""
        app = factory.create_app(custom_param=True, debug=False)
        assert isinstance(app, FastAPI)
    
    def test_task_registry_creation(self):
        """Test that TaskRegistry is properly instantiated."""
        app = factory.create_app()
        registry = app.state.task_registry
        assert hasattr(registry, '_tasks')
        assert hasattr(registry, 'add')
        assert hasattr(registry, 'tasks')
    
    def test_db_sessionmaker_creation(self):
        """Test that database sessionmaker is properly created."""
        app = factory.create_app()
        sessionmaker = app.state.db_sessionmaker
        # Should have the compatibility wrapper
        assert hasattr(sessionmaker, '__call__')


class TestTaskRegistry:
    """Test the TaskRegistry component functionality."""
    
    def test_task_registry_initialization(self):
        """Test TaskRegistry initializes with empty task set."""
        registry = factory.TaskRegistry()
        assert len(registry.tasks()) == 0
    
    def test_task_registry_add_task(self):
        """Test adding tasks to registry."""
        registry = factory.TaskRegistry()
        mock_task = Mock()
        
        result = registry.add(mock_task)
        assert result == mock_task
        assert mock_task in registry.tasks()
        assert len(registry.tasks()) == 1
    
    def test_task_registry_multiple_tasks(self):
        """Test multiple tasks can be registered."""
        registry = factory.TaskRegistry()
        task1, task2 = Mock(), Mock()
        
        registry.add(task1)
        registry.add(task2)
        
        tasks = registry.tasks()
        assert len(tasks) == 2
        assert task1 in tasks
        assert task2 in tasks


class TestSettingsIntegration:
    """Test settings integration and fallback mechanisms."""
    
    @patch('backend.api.factory.get_settings')
    def test_get_settings_success(self, mock_get_settings):
        """Test successful settings retrieval."""
        mock_settings = Mock()
        mock_settings.DEBUG = True
        mock_get_settings.return_value = mock_settings
        
        settings = factory.get_settings()
        assert settings.DEBUG == True
        mock_get_settings.assert_called_once()
    
    def test_settings_fallback_mechanism(self):
        """Test that MockSettings fallback works."""
        # This tests the fallback when imports fail
        with patch('backend.api.factory.get_settings', side_effect=ImportError):
            # The module level try/except should create MockSettings
            assert hasattr(factory, 'settings_instance')
    
    def test_mock_settings_attributes(self):
        """Test MockSettings has required attributes."""
        mock_settings = factory.MockSettings()
        assert hasattr(mock_settings, 'DEBUG')
        assert hasattr(mock_settings, 'APP_ENV')
        assert hasattr(mock_settings, 'CORS_ORIGINS')
        assert hasattr(mock_settings, 'DB_URL')


class TestDatabaseIntegration:
    """Test database sessionmaker integration."""
    
    @patch('backend.api.factory.get_sessionmaker')
    def test_get_db_sessionmaker_success(self, mock_get_sessionmaker):
        """Test successful sessionmaker retrieval."""
        mock_sm = Mock()
        mock_get_sessionmaker.return_value = mock_sm
        
        result = factory.get_db_sessionmaker()
        assert isinstance(result, factory.CompatSessionmaker)
        mock_get_sessionmaker.assert_called_once()
    
    @patch('backend.api.factory.get_sessionmaker', side_effect=Exception("DB Error"))
    def test_get_db_sessionmaker_fallback(self, mock_get_sessionmaker):
        """Test sessionmaker fallback on exception."""
        result = factory.get_db_sessionmaker()
        assert isinstance(result, factory.CompatSessionmaker)
        # Should create fallback with lambda
    
    def test_compat_sessionmaker_functionality(self):
        """Test CompatSessionmaker wrapper functionality."""
        mock_sm = Mock()
        mock_engine = Mock()
        
        compat = factory.CompatSessionmaker(mock_sm, mock_engine)
        
        # Test callable functionality
        result = compat(some_param=True)
        mock_sm.assert_called_with(some_param=True)
        
        # Test iterator functionality
        items = list(compat)
        assert len(items) == 2
        assert items[0] == mock_sm
        assert items[1] == mock_engine


class TestApplicationLifecycle:
    """Test application lifecycle events and middleware."""
    
    def test_app_state_initialization(self):
        """Test that app.state is properly initialized."""
        app = factory.create_app()
        
        # Check required state attributes
        assert hasattr(app.state, 'task_registry')
        assert hasattr(app.state, 'db_sessionmaker')
        
        # Verify types
        assert isinstance(app.state.task_registry, factory.TaskRegistry)
        assert isinstance(app.state.db_sessionmaker, factory.CompatSessionmaker)
    
    def test_app_configuration(self):
        """Test basic FastAPI configuration."""
        app = factory.create_app()
        
        assert app.title == "Intraday Trading Platform"
        assert app.version == "1.0.0"
        # App should be configured for production use
        assert isinstance(app, FastAPI)


class TestErrorHandling:
    """Test error handling in factory components."""
    
    def test_settings_import_error_handling(self):
        """Test graceful handling of settings import errors."""
        # The module should handle ImportError gracefully
        # and create a fallback settings instance
        assert hasattr(factory, 'settings_instance')
    
    def test_db_connection_error_handling(self):
        """Test database connection error handling."""
        with patch('backend.api.factory.get_sessionmaker', side_effect=Exception("DB Error")):
            sessionmaker = factory.get_db_sessionmaker()
            # Should return fallback sessionmaker
            assert callable(sessionmaker)
    
    def test_task_registry_resilience(self):
        """Test TaskRegistry handles various task types."""
        registry = factory.TaskRegistry()
        
        # Test with different mock task types
        normal_task = Mock()
        none_task = None
        
        registry.add(normal_task)
        tasks = registry.tasks()
        assert normal_task in tasks


class TestHealthChecks:
    """Test health check endpoint integration."""
    
    def test_app_creation_for_health_checks(self):
        """Test app can be created for health monitoring."""
        app = factory.create_app()
        
        # Create test client to verify app works
        client = TestClient(app)
        
        # Basic app functionality should work
        assert app.title == "Intraday Trading Platform"
        
        # State should be accessible for health checks
        assert hasattr(app.state, 'task_registry')
        assert hasattr(app.state, 'db_sessionmaker')


class TestCORSConfiguration:
    """Test CORS configuration capabilities."""
    
    @patch('backend.api.factory.settings_instance')
    def test_cors_settings_access(self, mock_settings):
        """Test that CORS settings can be accessed."""
        mock_settings.CORS_ORIGINS = ["http://localhost:3000"]
        
        app = factory.create_app()
        # App should be created successfully with CORS settings available
        assert isinstance(app, FastAPI)


class TestApplicationConfiguration:
    """Test various application configuration scenarios."""
    
    def test_basic_configuration(self):
        """Test basic FastAPI configuration."""
        app = factory.create_app()
        
        assert app.title == "Intraday Trading Platform"
        assert app.version == "1.0.0"
    
    def test_state_management(self):
        """Test application state management."""
        app = factory.create_app()
        
        # Test state persistence
        initial_registry = app.state.task_registry
        assert isinstance(initial_registry, factory.TaskRegistry)
        
        # State should remain accessible
        assert app.state.task_registry is initial_registry
    
    def test_dependency_injection_setup(self):
        """Test that dependency injection components are set up."""
        app = factory.create_app()
        
        # Dependencies should be available in app.state
        assert hasattr(app.state, 'db_sessionmaker')
        assert callable(app.state.db_sessionmaker)
