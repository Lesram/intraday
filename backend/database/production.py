"""
Production Database Initialization and Management
Handles database setup, connection pooling, health checks, and backup procedures
"""

import logging
import os
from typing import Any

from .database_config import create_db_backup, db_config, get_db_health

logger = logging.getLogger(__name__)


class ProductionDatabaseManager:
    """
    Production database manager with connection pooling, health monitoring, and backup capabilities.
    """

    def __init__(self):
        self._initialized = False
        self._health_status = {"healthy": False}

    async def initialize(self) -> bool:
        """
        Initialize production database connections and verify health.

        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize connection pools
            await self._initialize_connections()

            # Verify database health
            health = await self.health_check()

            if health.get("healthy", False):
                self._initialized = True
                logger.info("Production database initialized successfully")

                # Log connection pool status
                pool_info = health.get("pool_status", {})
                logger.info(f"Connection pool status: {pool_info}")

                return True
            else:
                logger.error(f"Database health check failed: {health}")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize production database: {e}")
            return False

    async def health_check(self) -> dict[str, Any]:
        """
        Perform comprehensive database health check.

        Returns:
            Dict containing health status and metrics
        """
        try:
            health = await get_db_health()
            self._health_status = health

            # Add additional production checks
            if health.get("healthy", False):
                # Check connection pool utilization
                pool_status = health.get("pool_status", {})
                pool_utilization = self._calculate_pool_utilization(pool_status)
                health["pool_utilization"] = pool_utilization

                # Warn if pool utilization is high
                if pool_utilization > 0.8:
                    logger.warning(f"High database pool utilization: {pool_utilization:.1%}")

            return health

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            error_health = {
                "healthy": False,
                "connectivity": False,
                "error": str(e),
                "timestamp": "error"
            }
            self._health_status = error_health
            return error_health

    def _calculate_pool_utilization(self, pool_status: dict[str, Any]) -> float:
        """Calculate database connection pool utilization percentage."""
        try:
            checked_out = pool_status.get("checked_out", 0)
            size = pool_status.get("size", 1)
            overflow = pool_status.get("overflow", 0)

            total_capacity = size + overflow
            if total_capacity == 0:
                return 0.0

            return checked_out / total_capacity

        except Exception:
            return 0.0

    async def create_backup(self, backup_name: str | None = None) -> dict[str, Any]:
        """
        Create database backup with validation.

        Args:
            backup_name: Optional backup filename

        Returns:
            Dict containing backup operation results
        """
        if not self._initialized:
            return {
                "success": False,
                "error": "Database not initialized",
                "message": "Initialize database before creating backups"
            }

        try:
            # Check database health before backup
            health = await self.health_check()
            if not health.get("healthy", False):
                logger.warning("Creating backup despite database health issues")

            # Create backup
            result = await create_db_backup(backup_name)

            if result.get("success", False):
                logger.info(f"Database backup created successfully: {result.get('backup_path', 'unknown')}")
            else:
                logger.error(f"Database backup failed: {result.get('error', 'unknown')}")

            return result

        except Exception as e:
            logger.error(f"Backup operation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Backup operation encountered an error"
            }

    async def validate_configuration(self) -> dict[str, Any]:
        """
        Validate database configuration for production readiness.

        Returns:
            Dict containing validation results
        """
        validation_results = {
            "valid": True,
            "checks": {},
            "warnings": [],
            "errors": []
        }

        try:
            # Check environment variables
            required_env_vars = ["DATABASE_URL"]
            for var in required_env_vars:
                if not os.getenv(var):
                    validation_results["errors"].append(f"Missing required environment variable: {var}")
                    validation_results["valid"] = False
                else:
                    validation_results["checks"][var] = "present"

            # Check connection pool configuration
            pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
            max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))

            if pool_size < 5:
                validation_results["warnings"].append(f"Low connection pool size: {pool_size}")

            if max_overflow < pool_size:
                validation_results["warnings"].append(
                    f"Max overflow ({max_overflow}) should be >= pool size ({pool_size})"
                )

            validation_results["checks"]["connection_pool"] = {
                "pool_size": pool_size,
                "max_overflow": max_overflow
            }

            # Check backup configuration
            backup_enabled = os.getenv("DB_BACKUP_ENABLED", "true").lower() == "true"
            backup_dir = os.getenv("DB_BACKUP_DIR", "./backups")

            validation_results["checks"]["backup"] = {
                "enabled": backup_enabled,
                "directory": backup_dir
            }

            if backup_enabled:
                try:
                    from pathlib import Path
                    backup_path = Path(backup_dir)
                    if not backup_path.exists():
                        validation_results["warnings"].append(f"Backup directory does not exist: {backup_dir}")
                except Exception as e:
                    validation_results["warnings"].append(f"Cannot validate backup directory: {e}")

            # Test database connectivity if initialized
            if self._initialized:
                health = await self.health_check()
                validation_results["checks"]["connectivity"] = health.get("healthy", False)

                if not health.get("healthy", False):
                    validation_results["errors"].append("Database connectivity test failed")
                    validation_results["valid"] = False
            else:
                validation_results["warnings"].append("Database not initialized - connectivity not tested")

            return validation_results

        except Exception as e:
            logger.error(f"Database configuration validation failed: {e}")
            return {
                "valid": False,
                "error": str(e),
                "checks": {},
                "warnings": [],
                "errors": [f"Validation process failed: {e}"]
            }

    async def get_status(self) -> dict[str, Any]:
        """
        Get comprehensive database status.

        Returns:
            Dict containing complete database status
        """
        return {
            "initialized": self._initialized,
            "health": self._health_status,
            "configuration": await self.validate_configuration()
        }

    async def close(self):
        """Close database connections and cleanup."""
        try:
            await db_config.close_connections()
            self._initialized = False
            logger.info("Production database manager closed")
        except Exception as e:
            logger.error(f"Error closing database manager: {e}")

    async def _initialize_connections(self):
        """Initialize database connections and test connectivity."""
        # Test basic connection
        health = await get_db_health()
        if not health.get("healthy", False):
            raise Exception(f"Database connection failed: {health.get('error', 'Unknown error')}")

        logger.info("Database connection pools initialized successfully")


# Global production database manager instance
production_db_manager = ProductionDatabaseManager()


# Convenience functions
async def initialize_production_database() -> bool:
    """Initialize production database system."""
    return await production_db_manager.initialize()


async def get_production_database_status() -> dict[str, Any]:
    """Get production database status."""
    return await production_db_manager.get_status()


async def create_production_backup(backup_name: str | None = None) -> dict[str, Any]:
    """Create production database backup."""
    return await production_db_manager.create_backup(backup_name)


async def validate_production_database_config() -> dict[str, Any]:
    """Validate production database configuration."""
    return await production_db_manager.validate_configuration()


async def close_production_database():
    """Close production database connections."""
    await production_db_manager.close()
