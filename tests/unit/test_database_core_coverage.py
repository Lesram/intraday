"""
Comprehensive tests for backend.database module (backend/database.py)
Targets 0% coverage -> 90%+ coverage
This file was identified as having 78 statements with 0% test coverage
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from contextlib import asynccontextmanager
import sys
import os

# Add the root to sys.path to ensure proper imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Import the specific backend.database.py file directly, not the package
import importlib.util
database_module_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'database.py')
spec = importlib.util.spec_from_file_location("backend_database", database_module_path)
db_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db_module)


class TestDatabaseManager:
    """Test the main DatabaseManager class from backend/database.py."""
    
    @pytest.fixture
    def database_url(self):
        return "sqlite+aiosqlite:///test.db"
    
    @pytest.fixture
    def db_manager_instance(self, database_url):
        return db_module.DatabaseManager(database_url)
    
    def test_initialization(self, database_url):
        """Test DatabaseManager initialization."""
        manager = db_module.DatabaseManager(database_url)
        assert manager.database_url == database_url
        assert manager.engine is None
        assert manager.session_maker is None
        assert manager._is_healthy is False
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, db_manager_instance):
        """Test successful database initialization."""
        with patch.object(db_module, 'create_async_engine') as mock_engine, \
             patch.object(db_module, 'async_sessionmaker') as mock_session_maker, \
             patch.object(db_manager_instance, 'health_check', return_value=True) as mock_health:
            
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker_instance = AsyncMock()
            mock_session_maker.return_value = mock_session_maker_instance
            
            await db_manager_instance.initialize()
            
            # Verify engine creation
            mock_engine.assert_called_once_with(
                db_manager_instance.database_url,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            
            # Verify session maker creation
            mock_session_maker.assert_called_once()
            # Verify health check was called
            mock_health.assert_called_once()
            
            assert db_manager_instance.engine == mock_engine_instance
            assert db_manager_instance.session_maker == mock_session_maker_instance
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self, db_manager_instance):
        """Test database initialization failure."""
        with patch.object(db_module, 'create_async_engine', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await db_manager_instance.initialize()
    
    @pytest.mark.asyncio
    async def test_health_check_no_engine(self, db_manager_instance):
        """Test health check when no engine is available."""
        result = await db_manager_instance.health_check()
        assert result is False
        assert db_manager_instance.is_healthy is False
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, db_manager_instance):
        """Test successful health check."""
        # Mock engine and connection
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()

        # Setup async context manager properly
        async_context_manager = AsyncMock()
        async_context_manager.__aenter__ = AsyncMock(return_value=mock_conn)
        async_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_engine.begin.return_value = async_context_manager

        db_manager_instance.engine = mock_engine

        result = await db_manager_instance.health_check()

        assert result is True
        assert db_manager_instance.is_healthy is True
        mock_conn.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, db_manager_instance):
        """Test health check failure."""
        mock_engine = AsyncMock()
        mock_engine.begin.side_effect = Exception("Connection lost")
        
        db_manager_instance.engine = mock_engine
        
        result = await db_manager_instance.health_check()
        
        assert result is False
        assert db_manager_instance.is_healthy is False
    
    def test_is_healthy_property(self, db_manager_instance):
        """Test the is_healthy property."""
        assert db_manager_instance.is_healthy is False
        
        db_manager_instance._is_healthy = True
        assert db_manager_instance.is_healthy is True
    
    @pytest.mark.asyncio
    async def test_get_session_no_session_maker(self, db_manager_instance):
        """Test get_session when session_maker is not initialized."""
        with pytest.raises(RuntimeError, match="Database not initialized"):
            async with db_manager_instance.get_session():
                pass
    
    @pytest.mark.asyncio
    async def test_get_session_success(self, db_manager_instance):
        """Test successful session retrieval."""
        mock_session = AsyncMock()
        mock_session_maker = AsyncMock()
        
        # Create proper async context manager mock
        mock_session_maker.return_value = mock_session
        db_manager_instance.session_maker = mock_session_maker
        
        async with db_manager_instance.get_session() as session:
            assert session == mock_session
        
        mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_with_exception(self, db_manager_instance):
        """Test session handling when exception occurs."""
        mock_session = AsyncMock()
        mock_session_maker = AsyncMock()
        
        # Create proper async context manager mock
        mock_session_maker.return_value = mock_session
        db_manager_instance.session_maker = mock_session_maker
        
        with pytest.raises(ValueError, match="Test error"):
            async with db_manager_instance.get_session() as session:
                raise ValueError("Test error")
        
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_with_engine(self, db_manager_instance):
        """Test closing database connections."""
        mock_engine = AsyncMock()
        db_manager_instance.engine = mock_engine
        
        await db_manager_instance.close()
        
        mock_engine.dispose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_without_engine(self, db_manager_instance):
        """Test closing when no engine exists."""
        await db_manager_instance.close()  # Should not raise


class TestGlobalDatabaseFunctions:
    """Test global database management functions."""
    
    def setup_method(self):
        """Reset global state before each test."""
        db_module.db_manager = None
    
    @pytest.mark.asyncio
    async def test_get_database_not_initialized(self):
        """Test get_database when not initialized."""
        with pytest.raises(RuntimeError, match="Database not initialized"):
            await db_module.get_database()
    
    @pytest.mark.asyncio
    async def test_init_database_success(self):
        """Test successful database initialization."""
        database_url = "sqlite+aiosqlite:///test.db"
        
        with patch.object(db_module.DatabaseManager, 'initialize') as mock_initialize:
            result = await db_module.init_database(database_url)
            
            mock_initialize.assert_called_once()
            assert result is not None
            assert isinstance(result, db_module.DatabaseManager)
            assert result.database_url == database_url
            
            # Test that global instance is set
            assert db_module.db_manager == result
    
    @pytest.mark.asyncio
    async def test_get_database_after_init(self):
        """Test get_database after initialization."""
        database_url = "sqlite+aiosqlite:///test.db"
        
        with patch.object(db_module.DatabaseManager, 'initialize'):
            manager = await db_module.init_database(database_url)
            result = await db_module.get_database()
            
            assert result == manager
    
    @pytest.mark.asyncio
    async def test_close_database_with_manager(self):
        """Test closing database when manager exists."""
        database_url = "sqlite+aiosqlite:///test.db"
        
        with patch.object(db_module.DatabaseManager, 'initialize'), \
             patch.object(db_module.DatabaseManager, 'close') as mock_close:
            
            manager = await db_module.init_database(database_url)
            await db_module.close_database()
            
            mock_close.assert_called_once()
            
            # Test that global instance is cleared
            assert db_module.db_manager is None
    
    @pytest.mark.asyncio
    async def test_close_database_without_manager(self):
        """Test closing database when no manager exists."""
        await db_module.close_database()  # Should not raise


class TestLegacyDatabase:
    """Test the legacy Database class for compatibility."""
    
    def test_initialization(self):
        """Test Database initialization."""
        db = db_module.Database()
        assert db.is_connected is False
    
    @pytest.mark.asyncio
    async def test_connect(self):
        """Test database connection."""
        db = db_module.Database()
        await db.connect()
        assert db.is_connected is True
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test database disconnection."""
        db = db_module.Database()
        await db.connect()
        await db.disconnect()
        assert db.is_connected is False
    
    @pytest.mark.asyncio
    async def test_health_check_connected(self):
        """Test health check when connected."""
        db = db_module.Database()
        await db.connect()
        result = await db.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_disconnected(self):
        """Test health check when disconnected."""
        db = db_module.Database()
        result = await db.health_check()
        assert result is False


class TestDefaultDatabaseInstance:
    """Test the default database instance."""
    
    def test_default_instance_exists(self):
        """Test that default database instance exists."""
        assert db_module.database is not None
        assert isinstance(db_module.database, db_module.Database)
        assert db_module.database.is_connected is False
    
    @pytest.mark.asyncio
    async def test_default_instance_operations(self):
        """Test operations on default instance."""
        # Store original state
        original_state = db_module.database.is_connected
        
        await db_module.database.connect()
        assert db_module.database.is_connected is True
        
        result = await db_module.database.health_check()
        assert result is True
        
        await db_module.database.disconnect()
        assert db_module.database.is_connected is False
        
        # Restore original state for clean test isolation
        db_module.database.is_connected = original_state


class TestIntegrationScenarios:
    """Test integration scenarios."""
    
    def setup_method(self):
        """Reset global state before each test."""
        db_module.db_manager = None
    
    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test full database lifecycle."""
        database_url = "sqlite+aiosqlite:///test.db"
        
        with patch.object(db_module.DatabaseManager, 'initialize'), \
             patch.object(db_module.DatabaseManager, 'close'):
            
            # Initialize
            manager = await db_module.init_database(database_url)
            assert manager is not None
            
            # Get database
            retrieved_manager = await db_module.get_database()
            assert retrieved_manager == manager
            
            # Close
            await db_module.close_database()
    
    @pytest.mark.asyncio
    async def test_error_handling_during_init(self):
        """Test error handling during initialization."""
        database_url = "invalid://url"
        
        with patch.object(db_module.DatabaseManager, 'initialize', side_effect=Exception("Invalid URL")):
            with pytest.raises(Exception, match="Invalid URL"):
                await db_module.init_database(database_url)
            
            # Ensure global state is not corrupted
            assert db_module.db_manager is None


class TestCoverageCompleteness:
    """Test to ensure complete coverage of all functions."""
    
    def test_all_imports_covered(self):
        """Test that all imports are covered."""
        # Test logging
        assert hasattr(db_module, 'logger')
        assert db_module.logger is not None
        
        # Test asyncio imports
        assert hasattr(db_module, 'asyncio')
        
        # Test contextlib imports
        assert hasattr(db_module, 'asynccontextmanager')
    
    @pytest.mark.asyncio
    async def test_exception_coverage(self):
        """Test exception handling coverage."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        
        # Test various exception scenarios with mock SQLAlchemy
        with patch.object(db_module, 'create_async_engine', side_effect=Exception("SQL Error")):
            with pytest.raises(Exception, match="SQL Error"):
                await manager.initialize()
        
        with patch.object(db_module, 'create_async_engine', side_effect=RuntimeError("Runtime Error")):
            with pytest.raises(RuntimeError, match="Runtime Error"):
                await manager.initialize()
    
    def test_logging_coverage(self):
        """Test that logging is properly configured."""
        assert db_module.logger is not None
        assert db_module.logger.name == 'backend_database'
    
    def test_text_import_coverage(self):
        """Test that text import is covered."""
        # This covers the "from sqlalchemy import text" line
        assert hasattr(db_module, 'text')


class TestSpecialCoverage:
    """Test edge cases and special coverage scenarios."""
    
    @pytest.mark.asyncio
    async def test_health_check_with_sqlalchemy_error(self):
        """Test health check with SQLAlchemy specific error."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        
        mock_engine = AsyncMock()
        # Test with SQLAlchemyError specifically
        with patch('sqlalchemy.exc.SQLAlchemyError', Exception):
            mock_engine.begin.side_effect = Exception("SQL Error")
            
            manager.engine = mock_engine
            
            result = await manager.health_check()
            assert result is False
            assert manager.is_healthy is False
    
    def test_module_level_coverage(self):
        """Test module-level variables and imports."""
        # Test that db_manager global exists
        assert hasattr(db_module, 'db_manager')
        
        # Test Optional import
        assert hasattr(db_module, 'Optional')
        
        # Test AsyncGenerator import  
        assert hasattr(db_module, 'AsyncGenerator')
    
    @pytest.mark.asyncio
    async def test_initialize_logging_coverage(self):
        """Test logging statements in initialize method."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        
        with patch('sqlalchemy.ext.asyncio.create_async_engine') as mock_engine, \
             patch('sqlalchemy.ext.asyncio.async_sessionmaker') as mock_session_maker, \
             patch.object(manager, 'health_check', return_value=True), \
             patch.object(db_module.logger, 'info') as mock_info:
            
            mock_engine.return_value = AsyncMock()
            mock_session_maker.return_value = AsyncMock()
            
            await manager.initialize()
            
            mock_info.assert_called_with("Database initialized successfully")
    
    @pytest.mark.asyncio
    async def test_close_logging_coverage(self):
        """Test logging statements in close method."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        mock_engine = AsyncMock()
        manager.engine = mock_engine
        
        with patch.object(db_module.logger, 'info') as mock_info:
            await manager.close()
            
            mock_info.assert_called_with("Database connections closed")
    
    @pytest.mark.asyncio
    async def test_health_check_logging_coverage(self):
        """Test logging statements in health_check method."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        mock_engine = AsyncMock()
        mock_engine.begin.side_effect = Exception("Connection error")
        manager.engine = mock_engine
        
        with patch.object(db_module.logger, 'error') as mock_error:
            result = await manager.health_check()
            
            assert result is False
            mock_error.assert_called_with("Database health check failed: Connection error")
    
    @pytest.mark.asyncio
    async def test_initialize_error_logging_coverage(self):
        """Test error logging in initialize method."""
        manager = db_module.DatabaseManager("sqlite+aiosqlite:///test.db")
        
        with patch.object(db_module, 'create_async_engine', side_effect=Exception("Init error")), \
             patch.object(db_module.logger, 'error') as mock_error:
            
            with pytest.raises(Exception, match="Init error"):
                await manager.initialize()
            
            mock_error.assert_called_with("Failed to initialize database: Init error")