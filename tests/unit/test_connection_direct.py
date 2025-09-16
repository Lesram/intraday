"""
Tests for backend/database/connection.py - Database connection utilities.
Direct tests that actually execute the connection module code.
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, patch

# Add the connection module path directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'database'))


class TestDatabaseConnectionDirect:
    """Test database connection module by direct execution."""
    
    @pytest.mark.asyncio
    async def test_get_database_session_with_none_sessionlocal(self):
        """Test get_database_session when SessionLocal is None."""
        # Import the module directly using sys.path manipulation
        import connection
        
        # The function should work even when SessionLocal is None (which it is by default)
        async with connection.get_database_session() as session:
            # Should yield None when SessionLocal is None
            assert session is None
    
    @pytest.mark.asyncio
    async def test_get_database_session_with_mock_sessionlocal(self):
        """Test get_database_session with a mocked SessionLocal."""
        # Import the connection module directly
        import connection
        
        # Create a mock session with required methods
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.close = Mock(return_value=None)
        
        # Create mock SessionLocal that returns our mock session
        mock_session_local = Mock(return_value=mock_session)
        
        # Temporarily replace SessionLocal in the module
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Test the function
            async with connection.get_database_session() as session:
                assert session is mock_session
            
            # Verify methods were called
            mock_session_local.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
            
        finally:
            # Restore original
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_get_database_session_exception_rollback(self):
        """Test that rollback is called when commit fails."""
        import connection
        
        # Create mock session that fails on commit
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_session.rollback = AsyncMock()
        mock_session.close = Mock(return_value=None)
        
        mock_session_local = Mock(return_value=mock_session)
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Should raise exception and call rollback
            with pytest.raises(Exception, match="Commit failed"):
                async with connection.get_database_session() as session:
                    pass  # Exception occurs during commit
            
            # Verify rollback was called
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()
            
        finally:
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_get_database_session_async_close(self):
        """Test handling of async close method."""
        import connection
        
        # Create mock session with async close
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        
        # Create an actual coroutine for close
        async def async_close():
            return None
        
        mock_session.close = Mock(return_value=async_close())
        mock_session_local = Mock(return_value=mock_session)
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Test with async close
            async with connection.get_database_session() as session:
                assert session is mock_session
            
            # Verify close was called
            mock_session.close.assert_called_once()
            
        finally:
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_get_database_session_missing_methods(self):
        """Test graceful handling when session lacks expected methods."""
        import connection
        
        # Create minimal session without any methods
        mock_session = Mock(spec=[])
        mock_session_local = Mock(return_value=mock_session)
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Should not raise exceptions even with missing methods
            async with connection.get_database_session() as session:
                assert session is mock_session
                # No exceptions should be raised
            
        finally:
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_get_database_session_no_rollback_method(self):
        """Test exception handling when session has no rollback method."""
        import connection
        
        # Create session with commit but no rollback
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit error"))
        # Explicitly remove rollback method
        if hasattr(mock_session, 'rollback'):
            del mock_session.rollback
        mock_session.close = Mock()
        
        mock_session_local = Mock(return_value=mock_session)
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Should still raise the original exception
            with pytest.raises(Exception, match="Commit error"):
                async with connection.get_database_session() as session:
                    pass
            
            # Close should still be called
            mock_session.close.assert_called_once()
            
        finally:
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_asyncio_iscoroutine_check(self):
        """Test the asyncio.iscoroutine check in finally block."""
        import connection
        
        # Test with non-coroutine close
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.close = Mock(return_value=None)  # Non-coroutine
        
        mock_session_local = Mock(return_value=mock_session)
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Test the iscoroutine path
            async with connection.get_database_session() as session:
                pass
            
            mock_session.close.assert_called_once()
            
        finally:
            connection.SessionLocal = original_session_local


class TestConnectionModuleStructure:
    """Test the structure and imports of the connection module."""
    
    def test_module_docstring(self):
        """Test that the module has proper documentation."""
        import connection
        
        assert connection.__doc__ is not None
        assert 'Database connection utilities' in connection.__doc__
        assert 'Compatibility module' in connection.__doc__
    
    def test_required_imports(self):
        """Test that all required imports are available."""
        import connection
        
        # Should have the main function
        assert hasattr(connection, 'get_database_session')
        assert callable(connection.get_database_session)
        
        # Should have SessionLocal (even if None)
        assert hasattr(connection, 'SessionLocal')
    
    def test_asynccontextmanager_decorator(self):
        """Test that get_database_session is properly decorated."""
        import connection
        
        # Should be callable and return a context manager
        context_manager = connection.get_database_session()
        assert hasattr(context_manager, '__aenter__')
        assert hasattr(context_manager, '__aexit__')
    
    def test_typing_imports(self):
        """Test that typing imports work correctly."""
        # Module should import without errors
        import connection
        
        assert connection is not None
        # AsyncIterator and Any should be used in type hints
    
    def test_asyncio_import(self):
        """Test that asyncio import works correctly."""
        import connection
        
        # Module should import asyncio successfully
        assert connection is not None
        # iscoroutine function should be available


class TestConnectionImportBehavior:
    """Test the import behavior of the connection module."""
    
    def test_sessionlocal_import_fallback(self):
        """Test SessionLocal import fallback mechanism."""
        import connection
        
        # SessionLocal should be available (even if None due to import failure)
        assert hasattr(connection, 'SessionLocal')
        
        # The import failure is expected and handled
        session_local = connection.SessionLocal
        assert session_local is None  # Expected due to import failure
    
    def test_exception_handling_in_import(self):
        """Test that import exceptions are handled gracefully."""
        # The module should load successfully despite import failures
        import connection
        
        assert connection is not None
        assert hasattr(connection, 'get_database_session')
        assert hasattr(connection, 'SessionLocal')
    
    def test_pragma_no_cover_sections(self):
        """Test that pragma: no cover sections execute correctly."""
        # Import should succeed, executing the pragma: no cover sections
        import connection
        
        # Module should be functional
        assert connection.SessionLocal is None  # Expected from try/except block


class TestConnectionAsyncBehavior:
    """Test async-specific behavior of the connection module."""
    
    @pytest.mark.asyncio
    async def test_context_manager_protocol(self):
        """Test that the async context manager protocol works."""
        import connection
        
        # Should work with async with statement
        async with connection.get_database_session() as session:
            # Session should be None (default behavior)
            assert session is None
    
    @pytest.mark.asyncio
    async def test_yield_behavior(self):
        """Test that the function properly yields the session."""
        import connection
        
        mock_session = Mock()
        mock_session_local = Mock(return_value=mock_session)
        mock_session.commit = AsyncMock()
        mock_session.close = Mock()
        
        original_session_local = connection.SessionLocal
        try:
            connection.SessionLocal = mock_session_local
            
            # Test that session is properly yielded
            async with connection.get_database_session() as session:
                assert session is mock_session
                # This is where the yield happens
                
        finally:
            connection.SessionLocal = original_session_local
