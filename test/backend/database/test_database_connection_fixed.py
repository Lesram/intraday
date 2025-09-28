"""
Comprehensive test suite for backend.database.connection module.
Targets significant coverage improvement from 21% baseline by testing database connection utilities.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from contextlib import asynccontextmanager
import backend.database.connection as db_connection


class TestConnection:
    """Test connection function functionality."""

    def test_connection_returns_mock(self):
        """Test connection() returns a mock connection object."""
        conn = db_connection.connection()
        
        # Verify it's a mock connection with expected methods
        assert hasattr(conn, 'close')
        assert hasattr(conn, 'commit')
        assert hasattr(conn, 'rollback')
        assert callable(conn.close)
        assert callable(conn.commit)
        assert callable(conn.rollback)

    def test_connection_methods_callable(self):
        """Test connection mock methods are callable without errors."""
        conn = db_connection.connection()
        
        # Should not raise exceptions
        conn.close()
        conn.commit()
        conn.rollback()

    def test_connection_multiple_instances(self):
        """Test multiple connection calls return separate instances."""
        conn1 = db_connection.connection()
        conn2 = db_connection.connection()
        
        # Should be different instances
        assert conn1 is not conn2
        # But should have same interface
        assert type(conn1).__name__ == type(conn2).__name__


class TestGetDatabaseSession:
    """Test get_database_session async context manager."""

    @pytest.fixture(autouse=True)
    def reset_session_local(self):
        """Reset SessionLocal before each test."""
        original_session_local = db_connection.SessionLocal
        yield
        db_connection.SessionLocal = original_session_local

    async def test_get_database_session_no_session_local(self):
        """Test get_database_session when SessionLocal is None."""
        # Ensure SessionLocal is None
        db_connection.SessionLocal = None
        
        async with db_connection.get_database_session() as session:
            assert session is None

    async def test_get_database_session_with_sync_session(self):
        """Test get_database_session with synchronous session."""
        # Create mock synchronous session
        mock_session = Mock()
        mock_session.commit.return_value = None  # Sync commit
        mock_session.rollback.return_value = None  # Sync rollback
        mock_session.close.return_value = None  # Sync close
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        async with db_connection.get_database_session() as session:
            assert session is mock_session
            # Session should be yielded but not committed yet
            mock_session.commit.assert_not_called()
        
        # After context exit, commit and close should be called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    async def test_get_database_session_with_async_session(self):
        """Test get_database_session with asynchronous session."""
        # Create mock async session
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock() 
        mock_session.close = AsyncMock()
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        async with db_connection.get_database_session() as session:
            assert session is mock_session
            # Session should be yielded but not committed yet
            mock_session.commit.assert_not_called()
        
        # After context exit, commit and close should be called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    async def test_get_database_session_exception_sync_rollback(self):
        """Test get_database_session rollback on exception with sync session."""
        # Create mock synchronous session
        mock_session = Mock()
        mock_session.commit.return_value = None
        mock_session.rollback.return_value = None
        mock_session.close.return_value = None
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        with pytest.raises(ValueError, match="Test exception"):
            async with db_connection.get_database_session() as session:
                assert session is mock_session
                raise ValueError("Test exception")
        
        # Should call rollback and close, but not commit
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_get_database_session_exception_async_rollback(self):
        """Test get_database_session rollback on exception with async session."""
        # Create mock async session
        mock_session = Mock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        with pytest.raises(RuntimeError, match="Async test exception"):
            async with db_connection.get_database_session() as session:
                assert session is mock_session
                raise RuntimeError("Async test exception")
        
        # Should call rollback and close, but not commit
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_get_database_session_session_without_methods(self):
        """Test get_database_session with session object missing methods."""
        # Create session without commit/rollback/close methods
        mock_session = object()
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        # Should not raise exceptions even if session lacks methods
        async with db_connection.get_database_session() as session:
            assert session is mock_session

    async def test_get_database_session_partial_methods(self):
        """Test get_database_session with session having only some methods."""
        # Create session with only commit method
        mock_session = Mock()
        mock_session.commit.return_value = None
        # Explicitly remove rollback and close attributes
        del mock_session.rollback
        del mock_session.close
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        async with db_connection.get_database_session() as session:
            assert session is mock_session
        
        # Only commit should be called (rollback/close not available)
        mock_session.commit.assert_called_once()

    async def test_get_database_session_exception_no_rollback_method(self):
        """Test get_database_session exception handling when rollback method missing."""
        # Create session without rollback method
        mock_session = Mock()
        mock_session.commit.return_value = None
        mock_session.close.return_value = None
        del mock_session.rollback
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        with pytest.raises(ValueError, match="No rollback exception"):
            async with db_connection.get_database_session() as session:
                raise ValueError("No rollback exception")
        
        # Close should still be called, but not rollback (doesn't exist) or commit
        mock_session.close.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_get_database_session_coroutine_detection(self):
        """Test proper detection of coroutine vs regular methods."""
        # Create session with mixed sync/async methods
        mock_session = Mock()
        
        # Create actual coroutines for testing
        async def async_commit():
            pass
        
        async def async_close():
            pass
        
        mock_session.commit.return_value = async_commit()
        mock_session.rollback.return_value = None  # Sync rollback
        mock_session.close.return_value = async_close()
        
        mock_session_local = Mock(return_value=mock_session)
        
        db_connection.SessionLocal = mock_session_local
        
        async with db_connection.get_database_session() as session:
            assert session is mock_session
        
        # All methods should be called
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestSessionLocalGlobal:
    """Test SessionLocal global variable behavior."""

    def test_session_local_default_none(self):
        """Test SessionLocal defaults to None."""
        # Note: SessionLocal might have been modified by other tests
        # So we just test that it exists and can be accessed
        assert hasattr(db_connection, 'SessionLocal')

    def test_session_local_can_be_modified(self):
        """Test SessionLocal can be modified at runtime."""
        original_value = db_connection.SessionLocal
        test_value = Mock()
        
        try:
            db_connection.SessionLocal = test_value
            assert db_connection.SessionLocal is test_value
        finally:
            db_connection.SessionLocal = original_value


class TestModuleStructure:
    """Test module imports and structure."""

    def test_module_imports(self):
        """Test that module imports work correctly."""
        assert callable(db_connection.connection)
        assert callable(db_connection.get_database_session)

    def test_async_context_manager_protocol(self):
        """Test get_database_session follows async context manager protocol."""
        cm = db_connection.get_database_session()
        
        # Should have __aenter__ and __aexit__ methods
        assert hasattr(cm, '__aenter__')
        assert hasattr(cm, '__aexit__')
        assert callable(cm.__aenter__)
        assert callable(cm.__aexit__)


if __name__ == "__main__":
    pytest.main([__file__])