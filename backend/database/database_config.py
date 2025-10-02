"""
Production Database Configuration with Connection Pooling and Backup Support
"""

import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import logging
from pathlib import Path

from sqlalchemy import create_engine, pool, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.orm import sessionmaker
import asyncpg

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Production database configuration with connection pooling."""
    
    def __init__(self):
        # Use SQLite for local testing if no DATABASE_URL is provided
        default_db_url = "sqlite:///./trading_platform.db"
        self.database_url = os.getenv("DATABASE_URL", default_db_url)
        
        # Set up async database URL
        if self.database_url.startswith("postgresql://"):
            self.async_database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")
        elif self.database_url.startswith("sqlite://"):
            self.async_database_url = self.database_url.replace("sqlite://", "sqlite+aiosqlite://")
        else:
            self.async_database_url = self.database_url
        
        # Connection pool settings
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour
        self.pool_pre_ping = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
        
        # Backup settings
        self.backup_enabled = os.getenv("DB_BACKUP_ENABLED", "true").lower() == "true"
        self.backup_directory = Path(os.getenv("DB_BACKUP_DIR", "./backups"))
        self.backup_retention_days = int(os.getenv("DB_BACKUP_RETENTION_DAYS", "30"))
        
        # Initialize engines
        self._async_engine = None
        self._sync_engine = None
        self._async_session_factory = None
        self._sync_session_factory = None
        
    def get_async_engine(self):
        """Get or create async database engine with connection pooling."""
        if self._async_engine is None:
            # For SQLite (testing), use different pool settings
            if "sqlite" in self.async_database_url.lower():
                self._async_engine = create_async_engine(
                    self.async_database_url,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                    echo=False,
                    future=True
                )
            else:
                # For PostgreSQL, use async-compatible pooling
                self._async_engine = create_async_engine(
                    self.async_database_url,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    pool_timeout=self.pool_timeout,
                    pool_recycle=self.pool_recycle,
                    pool_pre_ping=self.pool_pre_ping,
                    echo=False,
                    future=True
                )
            logger.info(
                f"Created async engine with pool_size={self.pool_size}, "
                f"max_overflow={self.max_overflow}, timeout={self.pool_timeout}s"
            )
        return self._async_engine
    
    def get_sync_engine(self):
        """Get or create sync database engine with connection pooling."""
        if self._sync_engine is None:
            self._sync_engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_recycle=self.pool_recycle,
                pool_pre_ping=self.pool_pre_ping,
                echo=False,
                future=True
            )
            logger.info(
                f"Created sync engine with pool_size={self.pool_size}, "
                f"max_overflow={self.max_overflow}, timeout={self.pool_timeout}s"
            )
        return self._sync_engine
    
    def get_async_session_factory(self):
        """Get async session factory."""
        if self._async_session_factory is None:
            self._async_session_factory = async_sessionmaker(
                bind=self.get_async_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )
        return self._async_session_factory
    
    def get_sync_session_factory(self):
        """Get sync session factory."""
        if self._sync_session_factory is None:
            self._sync_session_factory = sessionmaker(
                bind=self.get_sync_engine(),
                expire_on_commit=False,
                autocommit=False,
                autoflush=False
            )
        return self._sync_session_factory
    
    async def check_connection_health(self) -> Dict[str, Any]:
        """Check database connection health and pool status."""
        try:
            async_engine = self.get_async_engine()
            
            # Test basic connectivity
            async with async_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                connectivity = result.scalar() == 1
            
            # Get pool status - handle different pool types
            pool = async_engine.pool
            
            # SQLite uses StaticPool which has different methods
            if isinstance(pool, StaticPool):
                pool_status = {
                    "pool_type": "StaticPool",
                    "size": "N/A (StaticPool)",
                    "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                    "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                    "overflow": getattr(pool, 'overflow', lambda: 0)(),
                    "invalid": getattr(pool, 'invalid', lambda: 0)()
                }
            else:
                # For other pool types (QueuePool, etc.)
                pool_status = {
                    "pool_type": type(pool).__name__,
                    "size": getattr(pool, 'size', lambda: self.pool_size)(),
                    "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                    "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                    "overflow": getattr(pool, 'overflow', lambda: 0)(),
                    "invalid": getattr(pool, 'invalid', lambda: 0)()
                }
            
            return {
                "healthy": connectivity,
                "connectivity": connectivity,
                "pool_status": pool_status,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "healthy": False,
                "connectivity": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def get_health(self) -> Dict[str, Any]:
        """Alias for check_connection_health for backward compatibility."""
        return await self.check_connection_health()
    
    async def create_backup(self, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """Create database backup using pg_dump."""
        if not self.backup_enabled:
            return {"success": False, "message": "Backup disabled in configuration"}
        
        try:
            # Ensure backup directory exists
            self.backup_directory.mkdir(parents=True, exist_ok=True)
            
            # Generate backup filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            if backup_name is None:
                backup_name = f"trading_db_backup_{timestamp}.sql"
            
            backup_path = self.backup_directory / backup_name
            
            # Parse database URL for pg_dump
            db_parts = self.database_url.replace("postgresql://", "").split("/")
            db_name = db_parts[-1]
            host_part = db_parts[0].split("@")[-1].split(":")[0]
            
            # Run pg_dump (this is a simplified example - production should use proper credentials)
            import subprocess
            
            cmd = [
                "pg_dump",
                "-h", host_part,
                "-d", db_name,
                "-f", str(backup_path),
                "--no-password",
                "--verbose"
            ]
            
            # Note: In production, use proper authentication methods
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                backup_size = backup_path.stat().st_size
                logger.info(f"Database backup created: {backup_path} ({backup_size} bytes)")
                
                # Clean up old backups
                await self._cleanup_old_backups()
                
                return {
                    "success": True,
                    "backup_path": str(backup_path),
                    "backup_size": backup_size,
                    "timestamp": timestamp
                }
            else:
                logger.error(f"pg_dump failed: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "message": "pg_dump command failed"
                }
                
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Backup process failed"
            }
    
    async def _cleanup_old_backups(self):
        """Remove backups older than retention period."""
        try:
            cutoff_time = datetime.utcnow().timestamp() - (self.backup_retention_days * 24 * 3600)
            
            for backup_file in self.backup_directory.glob("*.sql"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    logger.info(f"Removed old backup: {backup_file}")
                    
        except Exception as e:
            logger.warning(f"Failed to cleanup old backups: {e}")
    
    async def close_connections(self):
        """Close all database connections and engines."""
        if self._async_engine:
            await self._async_engine.dispose()
            self._async_engine = None
            logger.info("Closed async database engine")
            
        if self._sync_engine:
            self._sync_engine.dispose()
            self._sync_engine = None
            logger.info("Closed sync database engine")


# Global database configuration instance
db_config = DatabaseConfig()


async def get_db_session():
    """Dependency to get database session with connection pooling."""
    session_factory = db_config.get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_health() -> Dict[str, Any]:
    """Get database health status."""
    return await db_config.check_connection_health()


async def create_db_backup(backup_name: Optional[str] = None) -> Dict[str, Any]:
    """Create database backup."""
    return await db_config.create_backup(backup_name)