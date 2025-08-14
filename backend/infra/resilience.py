"""
Resilience Infrastructure for Production Operations

This module provides comprehensive resilience patterns including:
- Circuit breakers with configurable thresholds
- Exponential backoff with jitter
- Timeout management
- Dead Letter Queue (DLQ) handling
- Retry mechanisms with idempotency
- Health checks and monitoring integration
"""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
import logging
import random
import time
from typing import Any

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Metrics for resilience monitoring
circuit_breaker_state_changes = Counter(
    "resilience_circuit_breaker_state_changes_total",
    "Circuit breaker state changes",
    ["service", "from_state", "to_state"],
)

circuit_breaker_requests = Counter(
    "resilience_circuit_breaker_requests_total",
    "Circuit breaker request outcomes",
    ["service", "outcome"],  # success, failure, rejected
)

retry_attempts = Counter(
    "resilience_retry_attempts_total",
    "Retry attempts by service and outcome",
    ["service", "attempt_number", "outcome"],
)

timeout_occurrences = Counter(
    "resilience_timeout_occurrences_total",
    "Timeout occurrences by service",
    ["service", "operation"],
)

dlq_messages = Counter(
    "resilience_dlq_messages_total",
    "Messages sent to Dead Letter Queue",
    ["service", "reason"],
)

backoff_delays = Histogram(
    "resilience_backoff_delay_seconds",
    "Exponential backoff delay distribution",
    ["service"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)


class CircuitBreakerState(Enum):
    """Circuit breaker states following the standard pattern."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 60.0  # Seconds before half-open
    success_threshold: int = 3  # Successes before closing from half-open
    timeout: float = 30.0  # Request timeout in seconds


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    backoff_multiplier: float = 2.0
    jitter: bool = True  # Add randomization to prevent thundering herd


class ResilienceException(Exception):
    """Base exception for resilience-related errors."""

    pass


class CircuitBreakerOpenException(ResilienceException):
    """Raised when circuit breaker is open and rejecting requests."""

    pass


class TimeoutException(ResilienceException):
    """Raised when operation exceeds configured timeout."""

    pass


class MaxRetriesExceededException(ResilienceException):
    """Raised when maximum retry attempts are exceeded."""

    pass


class CircuitBreaker:
    """
    Circuit breaker implementation with monitoring integration.

    Follows the standard circuit breaker pattern:
    - CLOSED: Normal operation, counting failures
    - OPEN: Failing fast, rejecting all requests
    - HALF_OPEN: Testing recovery with limited requests
    """

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.next_attempt_time = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if await self._should_reject():
                circuit_breaker_requests.labels(
                    service=self.name, outcome="rejected"
                ).inc()
                raise CircuitBreakerOpenException(
                    f"Circuit breaker {self.name} is OPEN"
                )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                func(*args, **kwargs), timeout=self.config.timeout
            )

            await self._on_success()
            circuit_breaker_requests.labels(service=self.name, outcome="success").inc()

            return result

        except TimeoutError:
            timeout_occurrences.labels(service=self.name, operation=func.__name__).inc()
            await self._on_failure()
            circuit_breaker_requests.labels(service=self.name, outcome="timeout").inc()
            raise TimeoutException(f"Operation {func.__name__} timed out")

        except Exception:
            await self._on_failure()
            circuit_breaker_requests.labels(service=self.name, outcome="failure").inc()
            raise

    async def _should_reject(self) -> bool:
        """Determine if request should be rejected."""
        if self.state == CircuitBreakerState.CLOSED:
            return False

        elif self.state == CircuitBreakerState.OPEN:
            if time.time() >= self.next_attempt_time:
                await self._transition_to_half_open()
                return False
            return True

        elif self.state == CircuitBreakerState.HALF_OPEN:
            # Allow limited requests through
            return False

    async def _on_success(self):
        """Handle successful operation."""
        async with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    await self._transition_to_closed()
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self):
        """Handle failed operation."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if (
                self.state == CircuitBreakerState.CLOSED
                and self.failure_count >= self.config.failure_threshold
            ) or self.state == CircuitBreakerState.HALF_OPEN:
                await self._transition_to_open()

    async def _transition_to_open(self):
        """Transition circuit breaker to OPEN state."""
        old_state = self.state
        self.state = CircuitBreakerState.OPEN
        self.next_attempt_time = time.time() + self.config.recovery_timeout

        circuit_breaker_state_changes.labels(
            service=self.name, from_state=old_state.value, to_state=self.state.value
        ).inc()

        logger.warning(f"Circuit breaker {self.name} opened due to failures")

    async def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state."""
        old_state = self.state
        self.state = CircuitBreakerState.HALF_OPEN
        self.success_count = 0

        circuit_breaker_state_changes.labels(
            service=self.name, from_state=old_state.value, to_state=self.state.value
        ).inc()

        logger.info(f"Circuit breaker {self.name} half-opened for testing")

    async def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state."""
        old_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0

        circuit_breaker_state_changes.labels(
            service=self.name, from_state=old_state.value, to_state=self.state.value
        ).inc()

        logger.info(f"Circuit breaker {self.name} closed - recovery successful")


class ExponentialBackoff:
    """Exponential backoff with jitter for retry delays."""

    def __init__(self, config: RetryConfig):
        self.config = config

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        delay = min(
            self.config.base_delay * (self.config.backoff_multiplier**attempt),
            self.config.max_delay,
        )

        if self.config.jitter:
            # Add jitter to prevent thundering herd
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


class RetryManager:
    """
    Retry manager with exponential backoff and dead letter queue support.
    """

    def __init__(self, name: str, config: RetryConfig):
        self.name = name
        self.config = config
        self.backoff = ExponentialBackoff(config)

    async def execute_with_retry(
        self, func: Callable, *args, idempotency_key: str | None = None, **kwargs
    ) -> Any:
        """Execute function with retry logic."""
        last_exception = None

        for attempt in range(self.config.max_attempts):
            try:
                logger.debug(
                    f"Retry attempt {attempt + 1}/{self.config.max_attempts} for {self.name}"
                )

                result = await func(*args, **kwargs)

                retry_attempts.labels(
                    service=self.name,
                    attempt_number=str(attempt + 1),
                    outcome="success",
                ).inc()

                if attempt > 0:
                    logger.info(
                        f"Retry succeeded for {self.name} on attempt {attempt + 1}"
                    )

                return result

            except Exception as e:
                last_exception = e

                retry_attempts.labels(
                    service=self.name,
                    attempt_number=str(attempt + 1),
                    outcome="failure",
                ).inc()

                logger.warning(
                    f"Retry attempt {attempt + 1} failed for {self.name}: {e}"
                )

                # If this is the last attempt, don't wait
                if attempt == self.config.max_attempts - 1:
                    break

                # Calculate and apply backoff delay
                delay = self.backoff.calculate_delay(attempt)
                backoff_delays.labels(service=self.name).observe(delay)

                logger.debug(f"Backing off for {delay:.2f} seconds before retry")
                await asyncio.sleep(delay)

        # All retries exhausted - send to DLQ if configured
        await self._send_to_dlq(func, args, kwargs, last_exception, idempotency_key)

        raise MaxRetriesExceededException(
            f"Max retries ({self.config.max_attempts}) exceeded for {self.name}. "
            f"Last error: {last_exception}"
        )

    async def _send_to_dlq(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        exception: Exception,
        idempotency_key: str | None,
    ):
        """Send failed operation to Dead Letter Queue."""
        dlq_message = {
            "service": self.name,
            "function": func.__name__,
            "args": str(args),  # Simplified serialization
            "kwargs": str(kwargs),
            "exception": str(exception),
            "idempotency_key": idempotency_key,
            "timestamp": time.time(),
            "attempts": self.config.max_attempts,
        }

        # In production, this would write to a proper DLQ (Redis, SQS, etc.)
        logger.error(f"Sending to DLQ: {dlq_message}")

        dlq_messages.labels(service=self.name, reason="max_retries_exceeded").inc()


class ResilienceManager:
    """
    Central manager for resilience patterns.

    Provides a unified interface for circuit breakers, retries, and timeouts.
    """

    def __init__(self):
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._retry_managers: dict[str, RetryManager] = {}
        self._default_cb_config = CircuitBreakerConfig()
        self._default_retry_config = RetryConfig()

    def get_circuit_breaker(
        self, service_name: str, config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Get or create circuit breaker for service."""
        if service_name not in self._circuit_breakers:
            cb_config = config or self._default_cb_config
            self._circuit_breakers[service_name] = CircuitBreaker(
                service_name, cb_config
            )
        return self._circuit_breakers[service_name]

    def get_retry_manager(
        self, service_name: str, config: RetryConfig | None = None
    ) -> RetryManager:
        """Get or create retry manager for service."""
        if service_name not in self._retry_managers:
            retry_config = config or self._default_retry_config
            self._retry_managers[service_name] = RetryManager(
                service_name, retry_config
            )
        return self._retry_managers[service_name]

    @asynccontextmanager
    async def resilient_call(
        self,
        service_name: str,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
    ):
        """Context manager for resilient service calls."""
        cb = self.get_circuit_breaker(service_name, circuit_breaker_config)
        retry_manager = self.get_retry_manager(service_name, retry_config)

        class ResilientCaller:
            async def execute(self, func: Callable, *args, **kwargs):
                return await retry_manager.execute_with_retry(
                    lambda: cb.call(func, *args, **kwargs)
                )

        yield ResilientCaller()

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of all resilience components."""
        status = {
            "circuit_breakers": {},
            "retry_managers": {},
            "timestamp": time.time(),
        }

        for name, cb in self._circuit_breakers.items():
            status["circuit_breakers"][name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count,
                "last_failure_time": cb.last_failure_time,
            }

        for name, rm in self._retry_managers.items():
            status["retry_managers"][name] = {
                "max_attempts": rm.config.max_attempts,
                "base_delay": rm.config.base_delay,
                "max_delay": rm.config.max_delay,
            }

        return status


# Global resilience manager instance
resilience_manager = ResilienceManager()


# Convenience decorators for common patterns
def circuit_breaker(service_name: str, config: CircuitBreakerConfig | None = None):
    """Decorator to add circuit breaker protection to async functions."""

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            cb = resilience_manager.get_circuit_breaker(service_name, config)
            return await cb.call(func, *args, **kwargs)

        return wrapper

    return decorator


def retry_with_backoff(service_name: str, config: RetryConfig | None = None):
    """Decorator to add retry logic with exponential backoff."""

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            retry_manager = resilience_manager.get_retry_manager(service_name, config)
            return await retry_manager.execute_with_retry(func, *args, **kwargs)

        return wrapper

    return decorator


# Health check endpoint helper
async def get_resilience_health() -> dict[str, Any]:
    """Get comprehensive resilience health status."""
    return resilience_manager.get_health_status()
