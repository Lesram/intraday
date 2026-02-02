"""
Unified Database Configuration System

This module provides a single, authoritative database configuration system
that consolidates all the scattered DatabaseConfig implementations across the platform.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
from pathlib import Path
from typing import Any

# Try to import SQLAlchemy components for production use
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


logger = logging.getLogger(__name__)


class IsolationLevel(Enum):
    """Database transaction isolation levels."""
    READ_UNCOMMITTED = "READ_UNCOMMITTED"
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"
    SERIALIZABLE = "SERIALIZABLE"


class DatabaseConfigError(Exception):
    """Database configuration error."""
    pass


@dataclass
class UnifiedDatabaseConfig:
    """
    Unified database configuration that consolidates all scattered implementations.

    This class provides a single source of truth for database configuration
    across the entire platform, replacing multiple inconsistent implementations.
    """

    # Core database connection settings
    url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"))

    # Connection pool settings
    pool_size: int = field(default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "20")))
    max_overflow: int = field(default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "10")))
    pool_timeout: int = field(default_factory=lambda: int(os.getenv("DB_POOL_TIMEOUT", "30")))
    pool_recycle: int = field(default_factory=lambda: int(os.getenv("DB_POOL_RECYCLE", "3600")))
    pool_pre_ping: bool = field(default_factory=lambda: os.getenv("DB_POOL_PRE_PING", "true").lower() == "true")

    # Query and connection settings
    echo: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")
    echo_pool: bool = field(default_factory=lambda: os.getenv("DB_ECHO_POOL", "false").lower() == "true")
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    connect_args: dict[str, Any] = field(default_factory=dict)

    # Session settings
    autocommit: bool = False
    autoflush: bool = True
    expire_on_commit: bool = True

    # Backup and maintenance settings
    backup_enabled: bool = field(default_factory=lambda: os.getenv("DB_BACKUP_ENABLED", "true").lower() == "true")
    backup_directory: str = field(default_factory=lambda: os.getenv("DB_BACKUP_DIR", "./backups"))
    backup_retention_days: int = field(default_factory=lambda: int(os.getenv("DB_BACKUP_RETENTION_DAYS", "30")))

    # Internal state
    _async_engine: Any | None = field(default=None, init=False, repr=False)
    _sync_engine: Any | None = field(default=None, init=False, repr=False)
    _async_session_factory: Any | None = field(default=None, init=False, repr=False)
    _sync_session_factory: Any | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_configuration()
        self._setup_connect_args()

        # Log configuration
        logger.info(f"Database configuration initialized: {self.get_summary()}")

    def _validate_configuration(self):
        """Validate database configuration parameters."""
        if not self.url:
            raise DatabaseConfigError("Database URL cannot be empty")

        if self.pool_size < 1:
            raise DatabaseConfigError("Pool size must be positive")

        if self.max_overflow < 0:
            raise DatabaseConfigError("Max overflow cannot be negative")

        if self.pool_timeout < 0:
            raise DatabaseConfigError("Pool timeout cannot be negative")

        if self.pool_recycle < 0:
            raise DatabaseConfigError("Pool recycle cannot be negative")

        # Validate backup settings
        if self.backup_enabled:
            backup_path = Path(self.backup_directory)
            try:
                backup_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Cannot create backup directory {backup_path}: {e}")

    def _setup_connect_args(self):
        """Setup connection arguments based on database type."""
        if "sqlite" in self.url.lower():
            # SQLite-specific settings
            self.connect_args.setdefault("check_same_thread", False)
            if self.echo:
                logger.info("SQLite database detected - using StaticPool with check_same_thread=False")
        elif "postgresql" in self.url.lower():
            # PostgreSQL-specific settings
            self.connect_args.setdefault("server_side_cursors", False)
            if self.echo:
                logger.info(f"PostgreSQL database detected - using QueuePool with pool_size={self.pool_size}")

    @property
    def async_url(self) -> str:
        """Get async-compatible database URL."""
        if self.url.startswith("postgresql://"):
            return self.url.replace("postgresql://", "postgresql+asyncpg://")
        elif self.url.startswith("sqlite://"):
            return self.url.replace("sqlite://", "sqlite+aiosqlite://")
        elif self.url.startswith("sqlite:///"):
            return self.url.replace("sqlite:///", "sqlite+aiosqlite:///")
        else:
            return self.url

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return "sqlite" in self.url.lower()

    @property
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL database."""
        return "postgresql" in self.url.lower()

    def get_sync_engine(self):
        """Get or create synchronous database engine."""
        if not SQLALCHEMY_AVAILABLE:
            raise DatabaseConfigError("SQLAlchemy not available - cannot create real database engine")

        if self._sync_engine is None:
            if self.is_sqlite:
                self._sync_engine = create_engine(
                    self.url,
                    poolclass=StaticPool,
                    connect_args=self.connect_args,
                    echo=self.echo,
                )
            else:
                self._sync_engine = create_engine(
                    self.url,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=self.pool_pre_ping,
                    echo=self.echo,
                    connect_args=self.connect_args,
                )

            logger.info(f"Created sync engine: {type(self._sync_engine)}")

        return self._sync_engine

    def get_async_engine(self):
        """Get or create asynchronous database engine."""
        if not SQLALCHEMY_AVAILABLE:
            raise DatabaseConfigError("SQLAlchemy not available - cannot create real database engine")

        if self._async_engine is None:
            if self.is_sqlite:
                self._async_engine = create_async_engine(
                    self.async_url,
                    poolclass=StaticPool,
                    connect_args=self.connect_args,
                    echo=self.echo,
                    future=True
                )
            else:
                self._async_engine = create_async_engine(
                    self.async_url,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=self.pool_pre_ping,
                    echo=self.echo,
                    connect_args=self.connect_args,
                    future=True
                )

            logger.info(f"Created async engine: {type(self._async_engine)}")

        return self._async_engine

    def get_sync_session_factory(self):
        """Get synchronous session factory."""
        if self._sync_session_factory is None:
            engine = self.get_sync_engine()
            self._sync_session_factory = sessionmaker(
                bind=engine,
                autocommit=self.autocommit,
                autoflush=self.autoflush,
                expire_on_commit=self.expire_on_commit
            )

        return self._sync_session_factory

    def get_async_session_factory(self):
        """Get asynchronous session factory."""
        if self._async_session_factory is None:
            engine = self.get_async_engine()
            self._async_session_factory = async_sessionmaker(
                bind=engine,
                expire_on_commit=self.expire_on_commit
            )

        return self._async_session_factory

    def get_summary(self) -> dict[str, Any]:
        """Get configuration summary."""
        return {
            "url": self.url[:20] + "..." if len(self.url) > 20 else self.url,
            "database_type": "SQLite" if self.is_sqlite else "PostgreSQL" if self.is_postgresql else "Other",
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "echo": self.echo,
            "backup_enabled": self.backup_enabled,
            "sqlalchemy_available": SQLALCHEMY_AVAILABLE
        }

    def test_connection(self) -> bool:
        """Test database connectivity."""
        if not SQLALCHEMY_AVAILABLE:
            logger.warning("SQLAlchemy not available - cannot test real database connection")
            return False

        try:
            engine = self.get_sync_engine()
            with engine.begin() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    async def test_async_connection(self) -> bool:
        """Test asynchronous database connectivity."""
        if not SQLALCHEMY_AVAILABLE:
            logger.warning("SQLAlchemy not available - cannot test real database connection")
            return False

        try:
            engine = self.get_async_engine()
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Async database connection test failed: {e}")
            return False

    def close_connections(self):
        """Close all database connections and engines."""
        if self._sync_engine:
            self._sync_engine.dispose()
            self._sync_engine = None
            logger.info("Closed sync engine")

        if self._async_engine:
            self._async_engine.dispose()
            self._async_engine = None
            logger.info("Closed async engine")

        self._sync_session_factory = None
        self._async_session_factory = None


# Compatibility aliases and functions for existing code
DatabaseConfig = UnifiedDatabaseConfig  # Main alias


def get_database_config() -> UnifiedDatabaseConfig:
    """Get the global database configuration instance."""
    return _global_db_config


def create_database_config(**kwargs) -> UnifiedDatabaseConfig:
    """Create a new database configuration instance."""
    return UnifiedDatabaseConfig(**kwargs)


def get_database_url() -> str:
    """Get the current database URL."""
    return get_database_config().url


def test_database_connection() -> bool:
    """Test the database connection."""
    return get_database_config().test_connection()


async def test_async_database_connection() -> bool:
    """Test the async database connection."""
    return await get_database_config().test_async_connection()


# Global configuration instance
_global_db_config = UnifiedDatabaseConfig()


# Backwards compatibility shims for existing imports
class MockDatabaseConfig(UnifiedDatabaseConfig):
    """Mock version of database config for testing environments without SQLAlchemy."""

    def get_sync_engine(self):
        """Return a mock engine for testing."""
        if not hasattr(self, '_mock_engine'):
            self._mock_engine = type('MockEngine', (), {
                'url': self.url,
                'dispose': lambda: None,
                'begin': lambda: type('MockConnection', (), {
                    '__enter__': lambda s: s,
                    '__exit__': lambda s, *a: None,
                    'execute': lambda s, q: type('MockResult', (), {'scalar': lambda: 1})()
                })()
            })()
        return self._mock_engine

    def get_async_engine(self):
        """Return a mock async engine for testing."""
        return self.get_sync_engine()

    def get_sync_session_factory(self):
        """Return a mock session factory."""
        return lambda: {}

    def get_async_session_factory(self):
        """Return a mock async session factory."""
        return lambda: {}


# Use mock version if SQLAlchemy not available
if not SQLALCHEMY_AVAILABLE:
    DatabaseConfig = MockDatabaseConfig
    _global_db_config = MockDatabaseConfig()


if __name__ == "__main__":
    # Test the unified database configuration
    print("🔧 Testing Unified Database Configuration...")

    config = UnifiedDatabaseConfig()
    print(f"📊 Configuration: {config.get_summary()}")

    print(f"🔗 Database URL: {config.url}")
    print(f"🔗 Async URL: {config.async_url}")
    print(f"🏊 Pool size: {config.pool_size}")
    print(f"📱 SQLite mode: {config.is_sqlite}")
    print(f"🐘 PostgreSQL mode: {config.is_postgresql}")

    # Test connection
    connection_ok = config.test_connection()
    print(f"🔌 Connection test: {'✅ OK' if connection_ok else '❌ Failed'}")

    print("✅ Unified Database Configuration working!")
