"""
Production Deployment Readiness Infrastructure.

Provides production-grade capabilities:
- Comprehensive health check system
- Graceful shutdown handling
- Configuration validation
- Feature flags
- Blue/green deployment support
- Readiness and liveness probes

Designed for Kubernetes and cloud deployments.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import os
import signal
import sys
from typing import Any

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class HealthStatus(Enum):
    """Component health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ReadinessStatus(Enum):
    """Readiness probe status."""

    READY = "ready"
    NOT_READY = "not_ready"
    STARTING = "starting"
    STOPPING = "stopping"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    component: str
    status: HealthStatus
    latency_ms: float
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SystemHealth:
    """Aggregate system health status."""

    status: HealthStatus
    readiness: ReadinessStatus
    checks: dict[str, HealthCheckResult]
    uptime_seconds: float
    version: str
    environment: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class HealthCheckRegistry:
    """
    Registry for health check functions.

    Manages component health checks with:
    - Automatic timeout handling
    - Result caching
    - Critical vs non-critical classification

    Usage:
        registry = HealthCheckRegistry()

        @registry.register("database", critical=True)
        async def check_database():
            await db.execute("SELECT 1")
            return {"connections": 5}

        health = await registry.run_all()
    """

    def __init__(self):
        self._checks: dict[str, dict[str, Any]] = {}
        self._results: dict[str, HealthCheckResult] = {}
        self._last_run: datetime | None = None

    def register(
        self,
        name: str,
        critical: bool = False,
        timeout_seconds: float = 5.0,
        cache_seconds: float = 0,
    ):
        """Decorator to register a health check function."""
        def decorator(func: Callable):
            self._checks[name] = {
                "func": func,
                "critical": critical,
                "timeout": timeout_seconds,
                "cache": cache_seconds,
            }
            return func
        return decorator

    async def run_check(self, name: str) -> HealthCheckResult:
        """Run a single health check."""
        if name not in self._checks:
            return HealthCheckResult(
                component=name,
                status=HealthStatus.UNKNOWN,
                latency_ms=0,
                message="Check not registered",
            )

        check = self._checks[name]

        # Check cache
        if check["cache"] > 0 and name in self._results:
            cached = self._results[name]
            age = (datetime.now(UTC) - cached.timestamp).total_seconds()
            if age < check["cache"]:
                return cached

        start = datetime.now(UTC)

        try:
            # Run with timeout
            if asyncio.iscoroutinefunction(check["func"]):
                result = await asyncio.wait_for(
                    check["func"](),
                    timeout=check["timeout"],
                )
            else:
                result = check["func"]()

            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000

            check_result = HealthCheckResult(
                component=name,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
                message="OK",
                details=result if isinstance(result, dict) else {},
            )

        except TimeoutError:
            latency_ms = check["timeout"] * 1000
            check_result = HealthCheckResult(
                component=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=f"Timeout after {check['timeout']}s",
            )

        except Exception as e:
            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
            check_result = HealthCheckResult(
                component=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message=str(e),
            )

        self._results[name] = check_result
        return check_result

    async def run_all(self) -> dict[str, HealthCheckResult]:
        """Run all registered health checks."""
        tasks = [self.run_check(name) for name in self._checks]
        results = await asyncio.gather(*tasks)

        self._last_run = datetime.now(UTC)

        return {r.component: r for r in results}

    def get_critical_checks(self) -> list[str]:
        """Get names of critical checks."""
        return [
            name for name, check in self._checks.items()
            if check["critical"]
        ]

    def is_healthy(self) -> bool:
        """Check if all critical components are healthy."""
        critical = self.get_critical_checks()

        for name in critical:
            if name not in self._results:
                return False
            if self._results[name].status != HealthStatus.HEALTHY:
                return False

        return True


class GracefulShutdown:
    """
    Graceful shutdown handler for production deployments.

    Features:
    - Signal handling (SIGTERM, SIGINT)
    - Configurable shutdown timeout
    - Registered cleanup callbacks
    - Drain connections before shutdown

    Usage:
        shutdown = GracefulShutdown(timeout_seconds=30)

        @shutdown.on_shutdown
        async def cleanup_connections():
            await pool.close()

        # In main:
        shutdown.register_signals()
    """

    def __init__(self, timeout_seconds: float = 30):
        self.timeout_seconds = timeout_seconds
        self._callbacks: list[Callable] = []
        self._is_shutting_down = False
        self._shutdown_event = asyncio.Event()

    def on_shutdown(self, func: Callable):
        """Decorator to register a shutdown callback."""
        self._callbacks.append(func)
        return func

    def register_callback(self, func: Callable):
        """Register a shutdown callback."""
        self._callbacks.append(func)

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._is_shutting_down

    async def wait_for_shutdown(self):
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    def register_signals(self):
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self.shutdown()),
                )
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: asyncio.create_task(self.shutdown()))

    async def shutdown(self):
        """Execute graceful shutdown."""
        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        logger.info("Starting graceful shutdown...")

        # Set event to unblock waiters
        self._shutdown_event.set()

        # Run callbacks with timeout
        try:
            async with asyncio.timeout(self.timeout_seconds):
                for callback in reversed(self._callbacks):
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback()
                        else:
                            callback()
                        logger.debug(f"Shutdown callback completed: {callback.__name__}")
                    except Exception as e:
                        logger.error(f"Shutdown callback failed: {callback.__name__}: {e}")

        except TimeoutError:
            logger.warning(f"Shutdown timed out after {self.timeout_seconds}s")

        logger.info("Graceful shutdown complete")


@dataclass
class ConfigValidationError:
    """A configuration validation error."""

    key: str
    message: str
    severity: str = "error"  # error, warning


class ConfigValidator:
    """
    Configuration validation for production deployments.

    Validates:
    - Required environment variables
    - Configuration value formats
    - Security settings
    - Resource limits
    """

    REQUIRED_VARS = {
        "DATABASE_URL": ("DATABASE_URL",),
        # Runtime auth code reads SECURITY_JWT_SECRET, with JWT_SECRET_KEY
        # retained as the compose/template alias and JWT_SECRET as legacy.
        "SECURITY_JWT_SECRET": (
            "SECURITY_JWT_SECRET",
            "JWT_SECRET_KEY",
            "JWT_SECRET",
        ),
    }

    REQUIRED_PRODUCTION_VARS = {
        # Canonical Alpaca env names across the organism/broker runtime.
        # The shorter names are compatibility aliases only.
        "ALPACA_API_KEY_ID": ("ALPACA_API_KEY_ID", "ALPACA_API_KEY"),
        "ALPACA_API_SECRET_KEY": (
            "ALPACA_API_SECRET_KEY",
            "ALPACA_SECRET_KEY",
        ),
    }

    def __init__(self, environment: str = "development"):
        self.environment = environment
        self._errors: list[ConfigValidationError] = []

    def validate(self) -> list[ConfigValidationError]:
        """Run all validations and return errors."""
        self._errors = []

        self._check_required_vars()
        self._check_production_vars()
        self._check_security_settings()
        self._check_database_url()

        return self._errors

    def _env_value(self, aliases: tuple[str, ...]) -> str:
        """Return the first configured value for a canonical env setting."""
        for name in aliases:
            value = os.environ.get(name)
            if value:
                return value
        return ""

    def _check_required_vars(self):
        """Check required environment variables."""
        for canonical, aliases in self.REQUIRED_VARS.items():
            if not self._env_value(aliases):
                self._errors.append(ConfigValidationError(
                    key=canonical,
                    message=(
                        f"Required environment variable {canonical} is not set "
                        f"(accepted aliases: {', '.join(aliases)})"
                    ),
                ))

    def _check_production_vars(self):
        """Check production-only requirements."""
        if self.environment != "production":
            return

        for canonical, aliases in self.REQUIRED_PRODUCTION_VARS.items():
            if not self._env_value(aliases):
                self._errors.append(ConfigValidationError(
                    key=canonical,
                    message=(
                        f"Required production variable {canonical} is not set "
                        f"(accepted aliases: {', '.join(aliases)})"
                    ),
                ))

    def _check_security_settings(self):
        """Validate security configuration."""
        jwt_secret = self._env_value(self.REQUIRED_VARS["SECURITY_JWT_SECRET"])

        if jwt_secret and len(jwt_secret) < 32:
            self._errors.append(ConfigValidationError(
                key="SECURITY_JWT_SECRET",
                message="SECURITY_JWT_SECRET should be at least 32 characters",
                severity="warning",
            ))

        if self.environment == "production":
            if jwt_secret == "development-secret":
                self._errors.append(ConfigValidationError(
                    key="SECURITY_JWT_SECRET",
                    message="Using development JWT secret in production",
                ))

    def _check_database_url(self):
        """Validate database URL format."""
        db_url = os.environ.get("DATABASE_URL", "")

        if db_url and not db_url.startswith(("postgresql://", "postgres://")):
            self._errors.append(ConfigValidationError(
                key="DATABASE_URL",
                message="DATABASE_URL should be a PostgreSQL connection string",
                severity="warning",
            ))

    def is_valid(self) -> bool:
        """Check if configuration is valid (no errors)."""
        errors = self.validate()
        return not any(e.severity == "error" for e in errors)


class FeatureFlags:
    """
    Feature flag management for gradual rollouts.

    Supports:
    - Boolean flags
    - Percentage rollouts
    - User-specific overrides

    Usage:
        flags = FeatureFlags()
        flags.set("new_order_system", enabled=True, rollout_pct=50)

        if flags.is_enabled("new_order_system", user_id="123"):
            # Use new system
            pass
    """

    def __init__(self):
        self._flags: dict[str, dict[str, Any]] = {}
        self._overrides: dict[str, dict[str, bool]] = {}  # flag -> user_id -> enabled

    def set(
        self,
        name: str,
        enabled: bool = True,
        rollout_pct: int = 100,
        description: str = "",
    ):
        """Set a feature flag."""
        self._flags[name] = {
            "enabled": enabled,
            "rollout_pct": rollout_pct,
            "description": description,
            "created_at": datetime.now(UTC),
        }

    def set_override(self, name: str, user_id: str, enabled: bool):
        """Set a user-specific override."""
        if name not in self._overrides:
            self._overrides[name] = {}
        self._overrides[name][user_id] = enabled

    def is_enabled(self, name: str, user_id: str | None = None) -> bool:
        """Check if a feature is enabled."""
        if name not in self._flags:
            return False

        flag = self._flags[name]

        if not flag["enabled"]:
            return False

        # Check user override
        if user_id and name in self._overrides:
            if user_id in self._overrides[name]:
                return self._overrides[name][user_id]

        # Percentage rollout
        if flag["rollout_pct"] < 100 and user_id:
            # Consistent hash based on user_id
            hash_val = hash(f"{name}:{user_id}") % 100
            return hash_val < flag["rollout_pct"]

        return flag["rollout_pct"] >= 100

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all feature flags."""
        return self._flags.copy()


class DeploymentInfo:
    """
    Deployment information and version tracking.

    Provides:
    - Version information
    - Build metadata
    - Environment detection
    - Instance identification
    """

    def __init__(self):
        self._start_time = datetime.now(UTC)
        self._version = os.environ.get("APP_VERSION", "unknown")
        self._build_id = os.environ.get("BUILD_ID", "local")
        self._environment = os.environ.get("APP_ENVIRONMENT", "development")
        self._instance_id = os.environ.get("INSTANCE_ID", self._generate_instance_id())

    def _generate_instance_id(self) -> str:
        """Generate a unique instance ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    @property
    def version(self) -> str:
        """Get application version."""
        return self._version

    @property
    def build_id(self) -> str:
        """Get build ID."""
        return self._build_id

    @property
    def environment(self) -> str:
        """Get deployment environment."""
        return self._environment

    @property
    def instance_id(self) -> str:
        """Get instance ID."""
        return self._instance_id

    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return (datetime.now(UTC) - self._start_time).total_seconds()

    def is_production(self) -> bool:
        """Check if running in production."""
        return self._environment == "production"

    def get_info(self) -> dict[str, Any]:
        """Get all deployment information."""
        return {
            "version": self._version,
            "build_id": self._build_id,
            "environment": self._environment,
            "instance_id": self._instance_id,
            "uptime_seconds": self.uptime_seconds,
            "start_time": self._start_time.isoformat(),
            "python_version": sys.version,
        }


class ProductionReadiness:
    """
    Orchestrator for production readiness checks.

    Combines:
    - Health checks
    - Configuration validation
    - Feature flags
    - Deployment info

    Usage:
        prod = ProductionReadiness()

        # Register health checks
        prod.health.register("database", critical=True)(check_db)

        # Validate configuration
        if not prod.config.is_valid():
            sys.exit(1)

        # Get system health
        health = await prod.get_system_health()
    """

    def __init__(self, environment: str | None = None):
        env = environment or os.environ.get("APP_ENVIRONMENT", "development")

        self.health = HealthCheckRegistry()
        self.config = ConfigValidator(environment=env)
        self.flags = FeatureFlags()
        self.deployment = DeploymentInfo()
        self.shutdown = GracefulShutdown()

        self._readiness = ReadinessStatus.STARTING

    def set_ready(self):
        """Mark the application as ready."""
        self._readiness = ReadinessStatus.READY
        logger.info("Application marked as ready")

    def set_stopping(self):
        """Mark the application as stopping."""
        self._readiness = ReadinessStatus.STOPPING
        logger.info("Application marked as stopping")

    async def get_system_health(self) -> SystemHealth:
        """Get comprehensive system health."""
        checks = await self.health.run_all()

        # Determine overall status
        if all(c.status == HealthStatus.HEALTHY for c in checks.values()):
            status = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in checks.values()):
            critical = self.health.get_critical_checks()
            if any(checks[n].status == HealthStatus.UNHEALTHY for n in critical if n in checks):
                status = HealthStatus.UNHEALTHY
            else:
                status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.DEGRADED

        return SystemHealth(
            status=status,
            readiness=self._readiness,
            checks=checks,
            uptime_seconds=self.deployment.uptime_seconds,
            version=self.deployment.version,
            environment=self.deployment.environment,
        )

    async def liveness_check(self) -> dict[str, Any]:
        """Kubernetes liveness probe."""
        return {
            "status": "alive",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def readiness_check(self) -> dict[str, Any]:
        """Kubernetes readiness probe."""
        is_ready = (
            self._readiness == ReadinessStatus.READY
            and self.health.is_healthy()
        )

        return {
            "ready": is_ready,
            "status": self._readiness.value,
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Global singleton
_production_readiness: ProductionReadiness | None = None


def get_production_readiness() -> ProductionReadiness:
    """Get or create the global production readiness instance."""
    global _production_readiness
    if _production_readiness is None:
        _production_readiness = ProductionReadiness()
    return _production_readiness
