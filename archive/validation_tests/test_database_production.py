"""
Test suite for production database configuration and connection pooling
"""

import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

# Import the production database components
from backend.database.database_config import DatabaseConfig, db_config
from backend.database.production import (
    ProductionDatabaseManager,
    production_db_manager,
    initialize_production_database,
    get_production_database_status,
    validate_production_database_config
)


class TestDatabaseConfiguration:
    """Test database configuration and connection pooling."""
    
    def test_database_config_initialization(self):
        """Test DatabaseConfig initializes with proper defaults."""
        config = DatabaseConfig()
        
        assert config.pool_size == int(os.getenv("DB_POOL_SIZE", "10"))
        assert config.max_overflow == int(os.getenv("DB_MAX_OVERFLOW", "20"))
        assert config.pool_timeout == int(os.getenv("DB_POOL_TIMEOUT", "30"))
        assert config.pool_recycle == int(os.getenv("DB_POOL_RECYCLE", "3600"))
        assert config.backup_enabled == (os.getenv("DB_BACKUP_ENABLED", "true").lower() == "true")
    
    def test_database_config_environment_variables(self):
        """Test DatabaseConfig respects environment variables."""
        with patch.dict(os.environ, {
            'DB_POOL_SIZE': '15',
            'DB_MAX_OVERFLOW': '25',
            'DB_POOL_TIMEOUT': '60',
            'DB_BACKUP_ENABLED': 'false'
        }):
            config = DatabaseConfig()
            
            assert config.pool_size == 15
            assert config.max_overflow == 25
            assert config.pool_timeout == 60
            assert config.backup_enabled == False
    
    @patch('backend.database.database_config.create_async_engine')
    def test_async_engine_creation(self, mock_create_engine):
        """Test async engine creation with proper pooling configuration."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        config = DatabaseConfig()
        engine = config.get_async_engine()
        
        assert engine == mock_engine
        mock_create_engine.assert_called_once()
        
        # Verify pool configuration was passed
        call_kwargs = mock_create_engine.call_args[1]
        assert call_kwargs['pool_size'] == config.pool_size
        assert call_kwargs['max_overflow'] == config.max_overflow
        assert call_kwargs['pool_timeout'] == config.pool_timeout
    
    @patch('backend.database.database_config.create_engine')
    def test_sync_engine_creation(self, mock_create_engine):
        """Test sync engine creation with proper pooling configuration."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        config = DatabaseConfig()
        engine = config.get_sync_engine()
        
        assert engine == mock_engine
        mock_create_engine.assert_called_once()


class TestProductionDatabaseManager:
    """Test production database manager functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.manager = ProductionDatabaseManager()
    
    @pytest.mark.asyncio
    @patch('backend.database.production.initialize_database_connections')
    @patch('backend.database.production.check_database_health')
    async def test_initialize_success(self, mock_health_check, mock_init_connections):
        """Test successful database initialization."""
        mock_init_connections.return_value = None
        mock_health_check.return_value = {
            "healthy": True,
            "connectivity": True,
            "pool_status": {"size": 10, "checked_out": 2}
        }
        
        result = await self.manager.initialize()
        
        assert result == True
        assert self.manager._initialized == True
        mock_init_connections.assert_called_once()
        mock_health_check.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('backend.database.production.initialize_database_connections')
    @patch('backend.database.production.check_database_health')
    async def test_initialize_failure(self, mock_health_check, mock_init_connections):
        """Test database initialization failure."""
        mock_init_connections.return_value = None
        mock_health_check.return_value = {
            "healthy": False,
            "connectivity": False,
            "error": "Connection refused"
        }
        
        result = await self.manager.initialize()
        
        assert result == False
        assert self.manager._initialized == False
    
    def test_calculate_pool_utilization(self):
        """Test pool utilization calculation."""
        # Normal utilization
        pool_status = {"checked_out": 5, "size": 10, "overflow": 5}
        utilization = self.manager._calculate_pool_utilization(pool_status)
        assert utilization == 5/15  # 5 out of 15 total capacity
        
        # High utilization
        pool_status = {"checked_out": 14, "size": 10, "overflow": 5}
        utilization = self.manager._calculate_pool_utilization(pool_status)
        assert utilization == 14/15
        
        # Edge case: zero capacity
        pool_status = {"checked_out": 0, "size": 0, "overflow": 0}
        utilization = self.manager._calculate_pool_utilization(pool_status)
        assert utilization == 0.0
    
    @pytest.mark.asyncio
    @patch('backend.database.production.create_database_backup')
    async def test_create_backup_success(self, mock_create_backup):
        """Test successful backup creation."""
        self.manager._initialized = True
        
        mock_create_backup.return_value = {
            "success": True,
            "backup_path": "/path/to/backup.sql",
            "backup_size": 1024000
        }
        
        result = await self.manager.create_backup("test_backup")
        
        assert result["success"] == True
        assert "backup_path" in result
        mock_create_backup.assert_called_once_with("test_backup")
    
    @pytest.mark.asyncio
    async def test_create_backup_not_initialized(self):
        """Test backup creation when not initialized."""
        self.manager._initialized = False
        
        result = await self.manager.create_backup()
        
        assert result["success"] == False
        assert "not initialized" in result["error"].lower()
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test'})
    async def test_validate_configuration_success(self):
        """Test successful configuration validation."""
        result = await self.manager.validate_configuration()
        
        assert result["valid"] == True
        assert "DATABASE_URL" in result["checks"]
        assert result["checks"]["DATABASE_URL"] == "present"
    
    @pytest.mark.asyncio
    @patch.dict(os.environ, {}, clear=True)
    async def test_validate_configuration_missing_env_var(self):
        """Test configuration validation with missing environment variables."""
        result = await self.manager.validate_configuration()
        
        assert result["valid"] == False
        assert len(result["errors"]) > 0
        assert any("DATABASE_URL" in error for error in result["errors"])


class TestDatabaseHealthCheck:
    """Test database health check functionality."""
    
    @pytest.mark.asyncio
    @patch('backend.database.database_config.db_config')
    async def test_health_check_success(self, mock_db_config):
        """Test successful health check."""
        # Mock the async engine and connection
        mock_engine = AsyncMock()
        mock_connection = AsyncMock()
        mock_pool = MagicMock()
        
        # Configure mocks
        mock_db_config.get_async_engine.return_value = mock_engine
        mock_engine.begin.return_value.__aenter__.return_value = mock_connection
        mock_connection.execute.return_value.scalar.return_value = 1
        mock_engine.pool = mock_pool
        mock_pool.size.return_value = 10
        mock_pool.checkedin.return_value = 8
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        mock_pool.invalid.return_value = 0
        
        # Import here to avoid circular import issues
        from backend.database.database_config import DatabaseConfig
        config = DatabaseConfig()
        
        result = await config.check_connection_health()
        
        assert result["healthy"] == True
        assert result["connectivity"] == True
        assert "pool_status" in result
        assert result["pool_status"]["size"] == 10
    
    @pytest.mark.asyncio
    @patch('backend.database.database_config.db_config')
    async def test_health_check_failure(self, mock_db_config):
        """Test health check failure."""
        # Mock engine to raise exception
        mock_engine = AsyncMock()
        mock_db_config.get_async_engine.return_value = mock_engine
        mock_engine.begin.side_effect = Exception("Connection failed")
        
        # Import here to avoid circular import issues
        from backend.database.database_config import DatabaseConfig
        config = DatabaseConfig()
        
        result = await config.check_connection_health()
        
        assert result["healthy"] == False
        assert result["connectivity"] == False
        assert "error" in result


class TestDatabaseBackup:
    """Test database backup functionality."""
    
    @pytest.mark.asyncio
    @patch('subprocess.run')
    @patch('os.path.exists')
    async def test_create_backup_success(self, mock_exists, mock_subprocess):
        """Test successful backup creation."""
        # Mock file system
        mock_exists.return_value = True
        
        # Mock subprocess success
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result
        
        # Mock file stats
        with patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024000
            
            from backend.database.database_config import DatabaseConfig
            config = DatabaseConfig()
            
            result = await config.create_backup("test_backup")
            
            assert result["success"] == True
            assert result["backup_size"] == 1024000
    
    @pytest.mark.asyncio
    @patch('subprocess.run')
    async def test_create_backup_disabled(self, mock_subprocess):
        """Test backup when disabled in configuration."""
        with patch.dict(os.environ, {'DB_BACKUP_ENABLED': 'false'}):
            from backend.database.database_config import DatabaseConfig
            config = DatabaseConfig()
            
            result = await config.create_backup()
            
            assert result["success"] == False
            assert "disabled" in result["message"].lower()
            mock_subprocess.assert_not_called()


@pytest.mark.asyncio
async def test_production_database_integration():
    """Integration test for production database setup."""
    with patch.dict(os.environ, {
        'TESTING': 'true',  # Force testing mode
        'DATABASE_URL': 'postgresql://test:test@localhost:5432/testdb',
        'DB_POOL_SIZE': '5',
        'DB_MAX_OVERFLOW': '10'
    }):
        # Test initialization
        result = await initialize_production_database()
        
        # Should succeed in testing mode
        assert isinstance(result, bool)
        
        # Test status
        status = await get_production_database_status()
        assert "initialized" in status
        
        # Test configuration validation
        config_validation = await validate_production_database_config()
        assert "valid" in config_validation


if __name__ == "__main__":
    pytest.main([__file__])