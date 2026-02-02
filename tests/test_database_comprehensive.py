"""
Comprehensive tests for backend.database package.

Tests all components:
- DatabaseManager class
- Error classes
- Configuration classes
- Stub classes
- QueryBuilder
- Utility functions
"""

import pytest
from unittest.mock import patch

from backend.database import (
    # Core classes
    DatabaseManager,
    # Error classes
    DatabaseError,
    ConnectionError,
    TransactionError,
    MigrationError,
    # Configuration
    DatabaseConfig,
    # Stub classes
    ConnectionPool,
    SessionManager,
    TransactionManager,
    QueryBuilder,
    DatabaseMigrator,
    DatabaseMonitor,
    # Utility functions
    get_connection_info,
    get_database_stats,
    setup_database,
    teardown_database,
    initialize_database,
    execute_query,
    execute_async_query,
    begin_transaction,
    commit_transaction,
    rollback_transaction,
    close_session,
    create_engine,
    create_session,
    get_session,
    migrate_database,
    backup_database,
    restore_database,
    create_tables,
    drop_tables,
    test_connection,
    health_check,
    # Global functions
    init_database,
)


# ============================================================================
# ERROR CLASSES TESTS
# ============================================================================

class TestErrorClasses:
    """Tests for database error classes."""
    
    def test_database_error(self):
        """Test DatabaseError."""
        error = DatabaseError("Test error")
        assert str(error) == "Test error"
        
    def test_connection_error(self):
        """Test ConnectionError extends DatabaseError."""
        error = ConnectionError("Connection failed")
        assert isinstance(error, DatabaseError)
        assert str(error) == "Connection failed"
        
    def test_transaction_error(self):
        """Test TransactionError extends DatabaseError."""
        error = TransactionError("Transaction failed")
        assert isinstance(error, DatabaseError)
        
    def test_migration_error(self):
        """Test MigrationError extends DatabaseError."""
        error = MigrationError("Migration failed")
        assert isinstance(error, DatabaseError)


# ============================================================================
# DATABASE CONFIG TESTS
# ============================================================================

class TestDatabaseConfig:
    """Tests for DatabaseConfig class."""
    
    def test_config_with_valid_url(self):
        """Test config with valid PostgreSQL URL."""
        config = DatabaseConfig(url='postgresql+asyncpg://user:pass@localhost:5432/db')
        assert config.url == 'postgresql+asyncpg://user:pass@localhost:5432/db'
        assert config.pool_size == 20
        assert config.max_overflow == 10
            
    def test_config_missing_url(self):
        """Test error when DATABASE_URL not set."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(DatabaseError, match="DATABASE_URL environment variable required"):
                DatabaseConfig(url=None)
                
    def test_config_non_postgresql_url(self):
        """Test error for non-PostgreSQL URL."""
        with pytest.raises(DatabaseError, match="Only PostgreSQL supported"):
            DatabaseConfig(url='sqlite:///test.db')


# ============================================================================
# STUB CLASSES TESTS  
# ============================================================================

class TestConnectionPoolStub:
    """Tests for ConnectionPool stub."""
    
    def test_init(self):
        """Test ConnectionPool can be instantiated."""
        pool = ConnectionPool()
        assert pool is not None


class TestSessionManagerStub:
    """Tests for SessionManager stub."""
    
    def test_init(self):
        """Test SessionManager can be instantiated."""
        manager = SessionManager()
        assert manager is not None


class TestTransactionManagerStub:
    """Tests for TransactionManager stub."""
    
    def test_init(self):
        """Test TransactionManager can be instantiated."""
        manager = TransactionManager()
        assert manager is not None


class TestDatabaseMigratorStub:
    """Tests for DatabaseMigrator stub."""
    
    def test_init(self):
        """Test DatabaseMigrator can be instantiated."""
        migrator = DatabaseMigrator()
        assert migrator is not None


class TestDatabaseMonitorStub:
    """Tests for DatabaseMonitor stub."""
    
    def test_init(self):
        """Test DatabaseMonitor can be instantiated."""
        monitor = DatabaseMonitor()
        assert monitor is not None


# ============================================================================
# QUERY BUILDER TESTS
# ============================================================================

class TestQueryBuilder:
    """Tests for QueryBuilder class."""
    
    def test_simple_select(self):
        """Test simple SELECT query."""
        qb = QueryBuilder()
        query = qb.select("id", "name").from_table("users").build()
        assert query == "SELECT id, name FROM users"
        
    def test_select_with_where(self):
        """Test SELECT with WHERE clause."""
        qb = QueryBuilder()
        query = qb.select("*").from_table("users").where("id = 1").build()
        assert "WHERE id = 1" in query
        
    def test_select_with_join(self):
        """Test SELECT with JOIN."""
        qb = QueryBuilder()
        query = qb.select("u.id", "o.total").from_table("users u").join("JOIN orders o ON u.id = o.user_id").build()
        assert "JOIN orders o ON u.id = o.user_id" in query
        
    def test_select_with_order_by(self):
        """Test SELECT with ORDER BY."""
        qb = QueryBuilder()
        query = qb.select("*").from_table("users").order_by("created_at DESC").build()
        assert "ORDER BY created_at DESC" in query
        
    def test_select_with_limit(self):
        """Test SELECT with LIMIT."""
        qb = QueryBuilder()
        query = qb.select("*").from_table("users").limit(10).build()
        assert "LIMIT 10" in query
        
    def test_select_with_offset(self):
        """Test SELECT with OFFSET."""
        qb = QueryBuilder()
        query = qb.select("*").from_table("users").offset(20).build()
        assert "OFFSET 20" in query
        
    def test_build_without_select(self):
        """Test build fails without SELECT."""
        qb = QueryBuilder()
        qb.from_table("users")
        
        with pytest.raises(DatabaseError, match="No SELECT fields"):
            qb.build()
            
    def test_build_without_from(self):
        """Test build fails without FROM."""
        qb = QueryBuilder()
        qb.select("*")
        
        with pytest.raises(DatabaseError, match="No FROM table"):
            qb.build()
            
    def test_reset(self):
        """Test reset clears builder state."""
        qb = QueryBuilder()
        qb.select("*").from_table("users").where("id = 1")
        qb.reset()
        
        with pytest.raises(DatabaseError, match="No SELECT fields"):
            qb.build()


# ============================================================================
# UTILITY FUNCTIONS TESTS
# ============================================================================

class TestUtilityFunctions:
    """Tests for database utility functions."""
    
    def test_get_connection_info(self):
        """Test get_connection_info."""
        info = get_connection_info()
        assert isinstance(info, dict)
        
    def test_get_database_stats(self):
        """Test get_database_stats."""
        stats = get_database_stats()
        assert isinstance(stats, dict)
        
    def test_setup_database(self):
        """Test setup_database."""
        setup_database()  # Should not raise
        
    def test_teardown_database(self):
        """Test teardown_database."""
        teardown_database()  # Should not raise
        
    def test_initialize_database(self):
        """Test initialize_database."""
        initialize_database()  # Should not raise
        
    def test_execute_query(self):
        """Test execute_query."""
        result = execute_query("SELECT 1")
        assert result == []
        
    def test_execute_async_query(self):
        """Test execute_async_query."""
        result = execute_async_query("SELECT 1")
        assert result == []
        
    def test_begin_transaction(self):
        """Test begin_transaction."""
        begin_transaction()  # Should not raise
        
    def test_commit_transaction(self):
        """Test commit_transaction."""
        commit_transaction()  # Should not raise
        
    def test_rollback_transaction(self):
        """Test rollback_transaction."""
        rollback_transaction()  # Should not raise
        
    def test_close_session(self):
        """Test close_session."""
        close_session()  # Should not raise
        
    def test_create_engine_func(self):
        """Test create_engine."""
        engine = create_engine("postgresql://test")
        assert engine == "mock_engine"
        
    def test_create_session(self):
        """Test create_session."""
        session = create_session()
        assert session is None
        
    def test_get_session_func(self):
        """Test get_session."""
        session = get_session()
        assert session is None
        
    def test_migrate_database(self):
        """Test migrate_database."""
        migrate_database()  # Should not raise
        
    def test_backup_database(self):
        """Test backup_database."""
        backup_database()  # Should not raise
        
    def test_restore_database(self):
        """Test restore_database."""
        restore_database()  # Should not raise
        
    def test_create_tables(self):
        """Test create_tables."""
        create_tables()  # Should not raise
        
    def test_drop_tables(self):
        """Test drop_tables."""
        drop_tables()  # Should not raise
        
    def test_test_connection(self):
        """Test test_connection."""
        assert test_connection() is True
        
    def test_health_check_func(self):
        """Test health_check function."""
        result = health_check()
        assert result['status'] == 'healthy'


# ============================================================================
# DATABASE MANAGER TESTS
# ============================================================================

class TestDatabaseManager:
    """Tests for DatabaseManager class."""
    
    def test_init(self):
        """Test DatabaseManager initialization."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        assert dm.database_url == "postgresql+asyncpg://test"
        assert dm.engine is None
        assert dm._is_healthy is False
        
    def test_is_healthy_property(self):
        """Test is_healthy property."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        assert dm.is_healthy is False
        
    def test_initialize(self):
        """Test initialize method."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        result = dm.initialize()
        assert result is True
        assert dm._is_initialized is True
        assert dm.engine == "mock_engine"
        
    def test_create_session(self):
        """Test create_session method."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        session = dm.create_session()
        assert session is not None
        
    def test_get_connection(self):
        """Test get_connection method."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        conn = dm.get_connection()
        assert conn is not None
        
    def test_close(self):
        """Test close method."""
        dm = DatabaseManager("postgresql+asyncpg://test")
        dm.initialize()
        dm.close()
        
        assert dm.engine is None
        assert dm._is_initialized is False
        
    def test_init_with_session_maker(self):
        """Test init with custom session maker."""
        def custom_session_maker():
            return "custom_session"
        
        dm = DatabaseManager("postgresql://test", session_maker=custom_session_maker)
        assert dm.session_maker == custom_session_maker
        
    def test_init_with_invalid_session_maker(self):
        """Test init with invalid session maker creates default."""
        dm = DatabaseManager("postgresql://test", session_maker="not_callable")
        assert dm.session_maker is not None  # Should create a default


# ============================================================================
# GLOBAL FUNCTIONS TESTS
# ============================================================================

class TestGlobalFunctions:
    """Tests for global database functions."""
    
    @pytest.mark.asyncio
    async def test_init_database(self):
        """Test init_database returns a DatabaseManager."""
        result = await init_database("postgresql://test")
        assert isinstance(result, DatabaseManager)
