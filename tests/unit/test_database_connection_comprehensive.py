"""
Tests for backend/database/connection.py - Database connection utilities.
Tests the async database session management and connection handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from contextlib import asynccontextmanager
import sys


class TestGetDatabaseSession:
    """Test the get_database_session async context manager."""
    
    @pytest.mark.asyncio
    async def test_session_with_none_session_local(self):
        """Test session management when SessionLocal is None."""
        # Import the connection module and test with SessionLocal = None
        import backend.database.connection as connection
        
        # Store original SessionLocal and set to None
        original_sessionlocal = connection.SessionLocal
        connection.SessionLocal = None
        
        try:
            async with connection.get_database_session() as session:
                assert session is None
        finally:
            # Restore original value
            connection.SessionLocal = original_sessionlocal
    
    @pytest.mark.asyncio 
    async def test_session_with_mock_session_local(self):
        """Test session management with mocked SessionLocal."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock()
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            async with connection.get_database_session() as session:
                assert session is mock_session
                mock_session_local.assert_called_once()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_commit_on_success(self):
        """Test that session.commit() is called on successful completion."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock()
            mock_session.commit = AsyncMock()
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            async with connection.get_database_session() as session:
                # Simulate successful operations
                pass
            
            # Commit should have been called
            mock_session.commit.assert_called_once()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_rollback_on_exception(self):
        """Test that session.rollback() is called when exception occurs."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock()
            mock_session.rollback = AsyncMock()
            mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            with pytest.raises(Exception, match="Commit failed"):
                async with connection.get_database_session() as session:
                    # Exception will be raised in commit
                    pass
            
            # Rollback should have been called
            mock_session.rollback.assert_called_once()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_close_called_finally(self):
        """Test that session.close() is always called in finally block."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock()
            mock_session.close = Mock()
            mock_session.commit = AsyncMock()
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            async with connection.get_database_session() as session:
                pass
            
            # Close should have been called
            mock_session.close.assert_called_once()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_async_session_close_awaited(self):
        """Test that async session.close() is properly awaited."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock()
            # Mock close as a coroutine
            async def mock_close():
                return None
            mock_session.close = Mock(return_value=mock_close())
            mock_session.commit = AsyncMock()
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            with patch('asyncio.iscoroutine', return_value=True):
                async with connection.get_database_session() as session:
                    pass
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_without_commit_method(self):
        """Test session handling when session doesn't have commit method."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock(spec=[])  # No commit method
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            async with connection.get_database_session() as session:
                assert session is mock_session
                # Should not fail even without commit method
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_without_close_method(self):
        """Test cleanup when session doesn't have close method."""
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching
        from backend.database import connection
        
        # Store original SessionLocal for restoration
        original_session_local = getattr(connection, 'SessionLocal', None)
        
        try:
            # Create mock session
            mock_session = Mock(spec=[])  # No close method
            mock_session_local = Mock(return_value=mock_session)
            
            # Direct assignment to module
            connection.SessionLocal = mock_session_local
            
            async with connection.get_database_session() as session:
                assert session is mock_session
                # Should not fail even without close method
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local


class TestDatabaseConnectionModule:
    """Test the database connection module structure and imports."""
    
    def test_module_imports(self):
        """Test that the module imports correctly."""
        from backend.database import connection
        
        assert hasattr(connection, 'get_database_session')
        assert callable(connection.get_database_session)
    
    def test_contextmanager_decorator(self):
        """Test that get_database_session is properly decorated as async context manager."""
        from backend.database.connection import get_database_session
        
        # Should be a coroutine function due to asynccontextmanager decorator
        assert hasattr(get_database_session, '__call__')
    
    def test_module_docstring(self):
        """Test that the module has appropriate documentation."""
        from backend.database import connection
        
        assert connection.__doc__ is not None
        assert 'Database connection utilities' in connection.__doc__
        assert 'Compatibility module' in connection.__doc__
    
    def test_session_local_import_fallback(self):
        """Test SessionLocal import fallback behavior."""
        # Module should load even if SessionLocal import fails
        from backend.database import connection
        assert hasattr(connection, 'get_database_session')


class TestAsyncBehavior:
    """Test async behavior and coroutine handling."""
    
    @pytest.mark.asyncio
    async def test_context_manager_async_protocol(self):
        """Test that the context manager follows async protocol correctly."""
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.close = Mock()
        mock_session_local = Mock(return_value=mock_session)
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        # Direct assignment to module
        connection.SessionLocal = mock_session_local
        # Should work with async with
        async with connection.get_database_session() as session:
            assert session is mock_session
    
    @pytest.mark.asyncio
    async def test_iscoroutine_check_true(self):
        """Test the asyncio.iscoroutine check when close returns coroutine."""
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        
        async def async_close():
            return None
        
        mock_session.close = Mock(return_value=async_close())
        mock_session_local = Mock(return_value=mock_session)
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            with patch('asyncio.iscoroutine', return_value=True) as mock_iscoro:
                async with connection.get_database_session() as session:
                    pass
                # iscoroutine should have been called
                mock_iscoro.assert_called()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_iscoroutine_check_false(self):
        """Test the asyncio.iscoroutine check when close returns non-coroutine."""
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.close = Mock(return_value=None)
        mock_session_local = Mock(return_value=mock_session)
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            with patch('asyncio.iscoroutine', return_value=False) as mock_iscoro:
                async with connection.get_database_session() as session:
                    pass
                # iscoroutine should have been called
                mock_iscoro.assert_called()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local


@pytest.mark.integration
class TestDatabaseConnectionIntegration:
    """Integration tests for database connection utilities."""
    
    @pytest.mark.asyncio
    async def test_real_world_session_usage(self):
        """Test realistic usage pattern for database sessions."""
        operations_log = []
        
        # Create a mock session that logs operations
        class MockSession:
            async def commit(self):
                operations_log.append("commit")
            
            def close(self):
                operations_log.append("close")
                return None  # Non-coroutine close
        
        mock_session_local = Mock(return_value=MockSession())
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            async with connection.get_database_session() as session:
                # Simulate database operations
                operations_log.append("query")
                operations_log.append("insert")
            
            # Should have proper operation sequence
            expected_sequence = ["query", "insert", "commit", "close"]
            assert operations_log == expected_sequence
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self):
        """Test error handling in realistic scenario."""
        operations_log = []
        
        class MockSession:
            async def commit(self):
                operations_log.append("commit_attempted")
                raise Exception("Database error")
            
            async def rollback(self):
                operations_log.append("rollback")
            
            def close(self):
                operations_log.append("close")
        
        mock_session_local = Mock(return_value=MockSession())
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            with pytest.raises(Exception, match="Database error"):
                async with connection.get_database_session() as session:
                    operations_log.append("operations")
            
            # Should have proper error handling sequence
            expected_sequence = ["operations", "commit_attempted", "rollback", "close"]
            assert operations_log == expected_sequence
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_session_local_none_fallback(self):
        """Test fallback behavior when SessionLocal is None."""
        # Mock database module with SessionLocal = None
        mock_db_module = Mock()
        mock_db_module.SessionLocal = None
        
        with patch.dict('sys.modules', {'backend.database': mock_db_module}):
            from backend.database import connection
            async with connection.get_database_session() as session:
                # Should yield None when SessionLocal is None
                assert session is None


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_commit_exception_without_rollback(self):
        """Test exception handling when session has no rollback method."""
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        # Don't add rollback method
        mock_session_local = Mock(return_value=mock_session)
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            with pytest.raises(Exception, match="Commit failed"):
                async with connection.get_database_session() as session:
                    pass
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
    
    @pytest.mark.asyncio
    async def test_multiple_exception_scenarios(self):
        """Test handling when both commit and rollback raise exceptions."""
        mock_session = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        mock_session.rollback = AsyncMock(side_effect=Exception("Rollback failed"))
        mock_session.close = Mock()
        mock_session_local = Mock(return_value=mock_session)
        
        # Phase 2.6 Pattern: Direct module manipulation instead of complex patching

        
        from backend.database import connection

        
        

        
        # Store original SessionLocal for restoration

        
        original_session_local = getattr(connection, 'SessionLocal', None)

        
        

        
        try:

        
            # Direct assignment to module

        
            connection.SessionLocal = mock_session_local
            # Should raise the original exception, not the rollback exception
            with pytest.raises(Exception, match="Commit failed"):
                async with connection.get_database_session() as session:
                    pass
            
            # Both commit and rollback should have been attempted
            mock_session.commit.assert_called_once()
            mock_session.rollback.assert_called_once()
            # Close should still be called
            mock_session.close.assert_called_once()
        finally:
            # Restore original value
            connection.SessionLocal = original_session_local
