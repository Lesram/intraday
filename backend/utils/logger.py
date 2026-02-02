"""
Logging configuration and utilities for the Algorithmic Trading Platform.
Provides structured logging with audit trail capabilities.
"""

from datetime import UTC, datetime
import logging
from pathlib import Path
import re
import sys
from typing import Any

import structlog
from structlog import get_logger

# ============================================================================
# PII/Secret Scrubbing Processor
# ============================================================================

# Patterns for sensitive data that should be masked in logs
SENSITIVE_PATTERNS = {
    # API Keys (various formats)
    "api_key": re.compile(
        r"(api[_-]?key|apikey|api_secret|apisecret)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?",
        re.IGNORECASE
    ),
    # Bearer tokens
    "bearer_token": re.compile(
        r"(Bearer\s+)([a-zA-Z0-9_\-\.]+)",
        re.IGNORECASE
    ),
    # JWT tokens (three base64 parts separated by dots)
    "jwt_token": re.compile(
        r"(eyJ[a-zA-Z0-9_\-]*\.eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*)"
    ),
    # Password fields
    "password": re.compile(
        r"(password|passwd|pwd|secret|credential)\s*[:=]\s*['\"]?([^\s'\",}]+)['\"]?",
        re.IGNORECASE
    ),
    # AWS keys
    "aws_key": re.compile(
        r"(AKIA[0-9A-Z]{16})"
    ),
    # Credit card numbers (basic pattern)
    "credit_card": re.compile(
        r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b"
    ),
    # SSN pattern
    "ssn": re.compile(
        r"\b(\d{3}[\s\-]?\d{2}[\s\-]?\d{4})\b"
    ),
    # Email addresses (for PII protection)
    "email": re.compile(
        r"\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    ),
    # Alpaca API keys
    "alpaca_key": re.compile(
        r"(PK[A-Z0-9]{18,}|SK[A-Z0-9]{18,})"
    ),
    # Generic secret patterns
    "generic_secret": re.compile(
        r"(secret|token|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?",
        re.IGNORECASE
    ),
}

# Field names that should have their values masked entirely
SENSITIVE_FIELD_NAMES = frozenset({
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "api_secret",
    "apikey",
    "apisecret",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "private_key",
    "ssn",
    "credit_card",
    "card_number",
    "cvv",
    "alpaca_api_key",
    "alpaca_secret_key",
})

# Mask string used to replace sensitive data
MASK = "***REDACTED***"
PARTIAL_MASK = "***...***"


def _mask_value(value: str) -> str:
    """Mask a sensitive value, showing only first/last chars if long enough."""
    if len(value) <= 8:
        return MASK
    return f"{value[:2]}{PARTIAL_MASK}{value[-2:]}"


def _scrub_string(text: str) -> str:
    """Scrub sensitive patterns from a string value."""
    result = text

    for pattern_name, pattern in SENSITIVE_PATTERNS.items():
        if pattern_name == "email":
            # Partially mask emails: keep first char and domain
            result = pattern.sub(r"\1[REDACTED]@\2", result)
        elif pattern_name in ("bearer_token", "password", "api_key", "generic_secret"):
            # Replace the captured secret group
            def mask_group(m):
                groups = m.groups()
                if len(groups) >= 2:
                    return f"{groups[0]}{MASK}"
                return MASK
            result = pattern.sub(mask_group, result)
        else:
            # Full mask for other patterns
            result = pattern.sub(MASK, result)

    return result


def _scrub_dict(data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """Recursively scrub sensitive data from a dictionary."""
    if depth > 10:  # Prevent infinite recursion
        return data

    result = {}
    for key, value in data.items():
        key_lower = key.lower().replace("-", "_")

        # Check if field name is sensitive
        if key_lower in SENSITIVE_FIELD_NAMES:
            if isinstance(value, str) and len(value) > 0:
                result[key] = _mask_value(value)
            else:
                result[key] = MASK
        elif isinstance(value, str):
            result[key] = _scrub_string(value)
        elif isinstance(value, dict):
            result[key] = _scrub_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = _scrub_list(value, depth + 1)
        else:
            result[key] = value

    return result


def _scrub_list(data: list[Any], depth: int = 0) -> list[Any]:
    """Recursively scrub sensitive data from a list."""
    if depth > 10:
        return data

    result = []
    for item in data:
        if isinstance(item, str):
            result.append(_scrub_string(item))
        elif isinstance(item, dict):
            result.append(_scrub_dict(item, depth + 1))
        elif isinstance(item, list):
            result.append(_scrub_list(item, depth + 1))
        else:
            result.append(item)

    return result


def scrub_sensitive_data(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor that scrubs PII and secrets from log events.
    
    This processor should be added early in the processor chain to ensure
    sensitive data is masked before it reaches any output handlers.
    """
    return _scrub_dict(event_dict)


# ============================================================================
# Structlog Configuration
# ============================================================================

# Configure structlog with PII scrubbing
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        scrub_sensitive_data,  # PII/Secret scrubbing before output
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


class AuditLogger:
    """Specialized logger for audit trail and compliance events."""

    def __init__(self, log_file: str = "audit_trail.log"):
        self.logger = get_logger("audit")
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # File handler for audit logs
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Add handler to the logger
        logging.getLogger("audit").addHandler(file_handler)
        logging.getLogger("audit").setLevel(logging.INFO)

    def info(self, event_type: str, **kwargs):
        """Log info level event with structured data."""
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        self.logger.info(f"Event: {event_type}", **event)

    def warning(self, event_type: str, **kwargs):
        """Log warning level event with structured data."""
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        self.logger.warning(f"Event: {event_type}", **event)

    def error(self, event_type: str, **kwargs):
        """Log error level event with structured data."""
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        self.logger.error(f"Event: {event_type}", **event)

    def log_trade_execution(
        self,
        strategy: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Log trade execution for audit trail."""
        if timestamp is None:
            timestamp = datetime.now(UTC)

        event = {
            "event_type": "trade_execution",
            "timestamp": timestamp.isoformat(),
            "strategy": strategy,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "order_id": order_id,
            "event_id": f"trade_{order_id}_{int(timestamp.timestamp())}",
        }

        self.logger.info("Trade executed", **event)

    def log_risk_event(
        self,
        event_type: str,
        description: str,
        severity: str = "INFO",
        data: dict | None = None,
    ) -> None:
        """Log risk management events."""
        event = {
            "event_type": f"risk_{event_type}",
            "timestamp": datetime.now(UTC).isoformat(),
            "description": description,
            "severity": severity,
            "data": data or {},
            "event_id": f"risk_{int(datetime.now(UTC).timestamp())}",
        }

        if severity.upper() == "ERROR":
            self.logger.error("Risk event", **event)
        elif severity.upper() == "WARNING":
            self.logger.warning("Risk event", **event)
        else:
            self.logger.info("Risk event", **event)

    def log_strategy_signal(
        self,
        strategy: str,
        symbol: str,
        signal: str,
        confidence: float | None = None,
        data: dict | None = None,
    ) -> None:
        """Log trading strategy signals."""
        event = {
            "event_type": "strategy_signal",
            "timestamp": datetime.now(UTC).isoformat(),
            "strategy": strategy,
            "symbol": symbol,
            "signal": signal,
            "confidence": confidence,
            "data": data or {},
            "event_id": f"signal_{strategy}_{int(datetime.now(UTC).timestamp())}",
        }

        self.logger.info("Strategy signal", **event)

    def log_model_prediction(
        self,
        model_name: str,
        symbol: str,
        prediction: float,
        confidence: float | None = None,
        features: dict | None = None,
    ) -> None:
        """Log ML model predictions."""
        event = {
            "event_type": "model_prediction",
            "timestamp": datetime.now(UTC).isoformat(),
            "model_name": model_name,
            "symbol": symbol,
            "prediction": prediction,
            "confidence": confidence,
            "features": features or {},
            "event_id": f"pred_{model_name}_{int(datetime.now(UTC).timestamp())}",
        }

        self.logger.info("Model prediction", **event)

    def log_system_event(
        self,
        event_type: str,
        description: str,
        severity: str = "INFO",
        data: dict | None = None,
    ) -> None:
        """Log general system events."""
        event = {
            "event_type": f"system_{event_type}",
            "timestamp": datetime.now(UTC).isoformat(),
            "description": description,
            "severity": severity,
            "data": data or {},
            "event_id": f"sys_{int(datetime.now(UTC).timestamp())}",
        }

        if severity.upper() == "ERROR":
            self.logger.error("System event", **event)
        elif severity.upper() == "WARNING":
            self.logger.warning("System event", **event)
        else:
            self.logger.info("System event", **event)


def setup_logging(
    log_level: str = "INFO", log_file: str | None = None
) -> logging.Logger:
    """Setup application logging configuration."""

    # Set up the root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)

    return logging.getLogger(__name__)


def get_structured_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return get_logger(name)


# Global audit logger instance
audit_logger = AuditLogger()


class PerformanceContext:
    """Context manager for timing operations.

    Phase 1.3 Fix: Add context manager support for PerformanceLogger.
    """

    def __init__(self, logger: 'PerformanceLogger', operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        import time
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            import time
            latency_ms = (time.time() - self.start_time) * 1000
            self.logger.log_latency(self.operation, latency_ms)


class PerformanceLogger:
    """Logger for performance metrics and monitoring."""

    def __init__(self):
        self.logger = get_structured_logger("performance")

    def __call__(self, operation: str):
        """Make PerformanceLogger callable to create context manager for timing.

        Phase 1.3 Fix: Add missing __call__ method for TypeError resolution.
        Following roadmap: Fix function signature mismatches.
        """
        return PerformanceContext(self, operation)

    def log_latency(
        self, operation: str, latency_ms: float, context: dict | None = None
    ) -> None:
        """Log operation latency metrics."""
        self.logger.info(
            "Operation latency",
            operation=operation,
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC).isoformat(),
            context=context or {},
        )

    def log_throughput(
        self,
        operation: str,
        count: int,
        time_window_sec: float,
        context: dict | None = None,
    ) -> None:
        """Log throughput metrics."""
        throughput = count / time_window_sec if time_window_sec > 0 else 0

        self.logger.info(
            "Operation throughput",
            operation=operation,
            count=count,
            time_window_sec=time_window_sec,
            throughput_per_sec=throughput,
            timestamp=datetime.now(UTC).isoformat(),
            context=context or {},
        )

    def log_resource_usage(
        self, cpu_percent: float, memory_mb: float, context: dict | None = None
    ) -> None:
        """Log resource usage metrics."""
        self.logger.info(
            "Resource usage",
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            timestamp=datetime.now(UTC).isoformat(),
            context=context or {},
        )


# Global performance logger
performance_logger = PerformanceLogger()


def log_event(event: str, logger_instance=None, **fields):
    """
    Standardized event logging function for consistent structured logging across all routes.

    Args:
        event: Event type (e.g., SIGNAL_DECIDED, ORDER_SUBMIT, RISK_BLOCKED)
        logger_instance: Optional logger instance (uses structured logger if None)
        **fields: Additional structured fields to include in log

    Standard fields automatically added:
    - timestamp: ISO format timestamp
    - trace_id: If available from context
    - event_type: The event name
    """
    import uuid

    if logger_instance is None:
        logger_instance = get_structured_logger("events")

    # Build structured event data
    event_data = {
        "event_type": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **fields
    }

    # Add trace_id if available (for distributed tracing)
    trace_id = fields.get("trace_id")
    if not trace_id:
        # Generate a simple trace ID if none provided
        event_data["trace_id"] = str(uuid.uuid4())[:8]

    # Map event types to appropriate log levels
    critical_events = {"SYSTEM_FAILURE", "SECURITY_BREACH", "DATA_CORRUPTION"}
    warning_events = {"RISK_BLOCKED", "ORDER_REJECTED", "LIMIT_EXCEEDED", "CIRCUIT_BREAKER"}
    info_events = {
        "SIGNAL_DECIDED", "ORDER_SUBMIT", "ORDER_STATUS", "ORDER_CANCEL",
        "ORDER_SUBMITTED", "ORDER_ACK", "ORDER_CANCELLED", "SIGNAL_CREATED", "POSITION_UPDATE", "STRATEGY_EXECUTION"
    }

    if event in critical_events:
        logger_instance.error(f"Critical event: {event}", **event_data)
    elif event in warning_events:
        logger_instance.warning(f"Warning event: {event}", **event_data)
    elif event in info_events:
        logger_instance.info(f"Event: {event}", **event_data)
    else:
        # Default to info level for unknown events
        logger_instance.info(f"Event: {event}", **event_data)


class StandardEventLogger:
    """
    Standardized event logger for consistent logging patterns across the application.
    Provides typed methods for common event categories.
    """

    def __init__(self, logger_name: str):
        self.logger = get_structured_logger(logger_name)
        self.service_name = logger_name

    def signal_decided(self, symbol: str, action: str, confidence: float, **kwargs):
        """Log a trading signal decision event."""
        log_event(
            "SIGNAL_DECIDED",
            self.logger,
            symbol=symbol,
            action=action,
            confidence=confidence,
            service=self.service_name,
            **kwargs
        )

    def order_submit(self, order_id: str, symbol: str, side: str, qty: float, **kwargs):
        """Log an order submission event."""
        log_event(
            "ORDER_SUBMIT",
            self.logger,
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            service=self.service_name,
            **kwargs
        )

    def order_status(self, order_id: str, status: str, **kwargs):
        """Log an order status change event."""
        log_event(
            "ORDER_STATUS",
            self.logger,
            order_id=order_id,
            status=status,
            service=self.service_name,
            **kwargs
        )

    def order_cancel(self, order_id: str, reason: str = None, **kwargs):
        """Log an order cancellation event."""
        log_event(
            "ORDER_CANCEL",
            self.logger,
            order_id=order_id,
            reason=reason,
            service=self.service_name,
            **kwargs
        )

    def risk_blocked(self, symbol: str, side: str, qty: float, issues: list, **kwargs):
        """Log a risk management block event."""
        log_event(
            "RISK_BLOCKED",
            self.logger,
            symbol=symbol,
            side=side,
            qty=qty,
            issues=issues,
            service=self.service_name,
            **kwargs
        )

    def position_update(self, symbol: str, position_type: str, **kwargs):
        """Log a position update event."""
        log_event(
            "POSITION_UPDATE",
            self.logger,
            symbol=symbol,
            position_type=position_type,
            service=self.service_name,
            **kwargs
        )


# Order event logging helpers
def log_order_submitted(**fields):
    """Log an order submission event."""
    log_event("ORDER_SUBMITTED", **fields)


def log_order_ack(**fields):
    """Log an order acknowledgment event."""
    log_event("ORDER_ACK", **fields)


def log_order_rejected(**fields):
    """Log an order rejection event."""
    log_event("ORDER_REJECTED", **fields)


def log_order_cancelled(**fields):
    """Log an order cancellation event."""
    log_event("ORDER_CANCELLED", **fields)


# Convenience function to get a standard event logger
def get_event_logger(name: str) -> StandardEventLogger:
    """Get a standardized event logger for a service/module."""
    return StandardEventLogger(name)
