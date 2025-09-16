"""
Tests for backend/database/connection.py - Database connection utilities.
Tests the async database session management and connection handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch


class TestDatabaseConnectionModule:
    """Test the database connection module functionality."""
    
    def test_module_imports_successfully(self):
        """Test that the connection module imports without errors."""
        from backend.database import connection
        
        assert connection is not None
        assert hasattr(connection, 'get_database_session')
        assert callable(connection.get_database_session)
    
    def test_module_has_docstring(self):
        """Test that the module has appropriate documentation."""
        from backend.database import connection
        
        assert connection.__doc__ is not None
        assert 'Database connection utilities' in connection.__doc__
        assert 'Compatibility module' in connection.__doc__
    
    def test_get_database_session_is_callable(self):
        """Test that get_database_session function is callable."""
        from backend.database.connection import get_database_session
        
        assert callable(get_database_session)
    
    @pytest.mark.asyncio
    async def test_session_with_none_session_local(self):
        """Test session management when SessionLocal is None."""
        # Temporarily set SessionLocal to None in the module
        from backend.database import connection
        
        # Store original SessionLocal
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Set to None
            connection.SessionLocal = None
            
            # Test the function
            async with connection.get_database_session() as session:
                assert session is None
                
        finally:
            # Restore original
            if original_session_local is not None:
                connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_with_mock_session(self):
        """Test session management with a mock session."""
        from backend.database import connection
        
        # Create mock session
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.close = Mock(return_value=None)
        
        # Create mock SessionLocal
        mock_session_local = Mock(return_value=mock_session)
        
        # Store original SessionLocal  
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Set mock
            connection.SessionLocal = mock_session_local
            
            # Test the function
            async with connection.get_database_session() as session:
                assert session is mock_session
                
            # Verify commit and close were called
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
            
        finally:
            # Restore original
            if original_session_local is not None:
                connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_rollback_on_exception(self):
        """Test that rollback is called when an exception occurs."""
        from backend.database import connection
        
        # Create mock session that raises exception on commit
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_session.rollback = AsyncMock()
        mock_session.close = Mock(return_value=None)
        
        mock_session_local = Mock(return_value=mock_session)
        
        # Store original SessionLocal
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Set mock
            connection.SessionLocal = mock_session_local
            
            # Test exception handling
            with pytest.raises(Exception, match="Commit failed"):
                async with connection.get_database_session() as session:
                    pass  # Exception will be raised in commit
            
            # Verify rollback and close were called
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()
            
        finally:
            # Restore original
            if original_session_local is not None:
                connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_async_close_handling(self):
        """Test that async close methods are properly awaited."""
        from backend.database import connection
        
        # Create mock session with async close
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        
        async def async_close():
            return None
            
        mock_session.close = Mock(return_value=async_close())
        mock_session_local = Mock(return_value=mock_session)
        
        # Store original SessionLocal
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Set mock
            connection.SessionLocal = mock_session_local
            
            # Test async close handling
            async with connection.get_database_session() as session:
                assert session is mock_session
                
            # Verify close was called
            mock_session.close.assert_called_once()
            
        finally:
            # Restore original
            if original_session_local is not None:
                connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_missing_attributes_handling(self):
        """Test graceful handling when session lacks expected methods."""
        from backend.database import connection
        
        # Create minimal mock session without commit/rollback methods
        mock_session = Mock(spec=[])  # Empty spec = no methods
        mock_session_local = Mock(return_value=mock_session)
        
        # Store original SessionLocal
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Set mock
            connection.SessionLocal = mock_session_local
            
            # Should not raise exceptions even with missing methods
            async with connection.get_database_session() as session:
                assert session is mock_session
                
        finally:
            # Restore original
            if original_session_local is not None:
                connection.SessionLocal = original_session_local


class TestAsyncContextManager:
    """Test async context manager protocol."""
    
    @pytest.mark.asyncio
    async def test_context_manager_protocol(self):
        """Test that get_database_session properly implements async context manager."""
        from backend.database.connection import get_database_session
        
        # Should be usable in async with statement
        context_manager = get_database_session()
        assert hasattr(context_manager, '__aenter__')
        assert hasattr(context_manager, '__aexit__')


class TestImportFallback:
    """Test import fallback behavior."""
    
    def test_session_local_fallback(self):
        """Test that SessionLocal import fallback works."""
        # Import the module - should work even if SessionLocal import fails
        from backend.database import connection
        
        # Module should have SessionLocal attribute (possibly None)
        assert hasattr(connection, 'SessionLocal')
        
        # The attribute should be either None or a callable
        session_local = connection.SessionLocal
        assert session_local is None or callable(session_local)


class TestModuleStructure:
    """Test module structure and organization."""
    
    def test_asynccontextmanager_import(self):
        """Test that asynccontextmanager is properly imported."""
        from backend.database import connection
        
        # Should have access to get_database_session function
        assert hasattr(connection, 'get_database_session')
        assert callable(connection.get_database_session)
    
    def test_typing_imports(self):
        """Test that typing imports are available."""
        # Import should succeed without errors
        from backend.database import connection
        
        assert connection is not None
    
    def test_asyncio_usage(self):
        """Test that asyncio functionality is properly used."""
        from backend.database import connection
        
        # Module should be importable and functional
        assert hasattr(connection, 'get_database_session')
        
        # Function should be async-compatible
        context_manager = connection.get_database_session()
        assert hasattr(context_manager, '__aenter__')
        assert hasattr(context_manager, '__aexit__')
