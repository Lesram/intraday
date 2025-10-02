"""
Structured JSON logging with OpenTelemetry trace correlation.
Provides consistent log formatting across HTTP, DB, broker, and outbox operations.
"""

import json
import logging
import logging.config
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

# Try to import OpenTelemetry, fall back gracefully if not available
try:
    from opentelemetry.sdk.trace import ReadableSpan

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    ReadableSpan = None


class TraceIdFilter(logging.Filter):
    """
    Logging filter to inject OpenTelemetry trace and span IDs into log records.
    Enables correlation between logs and distributed traces.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add trace_id and span_id to log record if available.

        Args:
            record: Log record to enhance

        Returns:
            True to allow record processing
        """
        if OTEL_AVAILABLE:
            # Get current span context
            current_span = trace.get_current_span()

            if current_span and current_span.get_span_context().is_valid:
                span_context = current_span.get_span_context()

                # Format trace and span IDs as hex strings
                record.trace_id = f"{span_context.trace_id:032x}"
                record.span_id = f"{span_context.span_id:016x}"

                # Add trace flags
                record.trace_flags = span_context.trace_flags
            else:
                record.trace_id = None
                record.span_id = None
                record.trace_flags = None
        else:
            # OpenTelemetry not available
            record.trace_id = None
            record.span_id = None
            record.trace_flags = None

        return True


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter with structured fields and trace correlation.
    Produces consistent log format across all components.
    """

    def __init__(
        self,
        service_name: str = "intraday-trading",
        service_version: str = "2.0.0",
        include_trace: bool = True,
        extra_fields: dict[str, Any] | None = None,
    ):
        super().__init__()
        self.service_name = service_name
        self.service_version = service_version
        self.include_trace = include_trace
        self.extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON with structured fields.

        Args:
            record: Log record to format

        Returns:
            JSON formatted log string
        """
        # Base log structure
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": {"name": self.service_name, "version": self.service_version},
        }

        # Add trace correlation if available and enabled
        if self.include_trace:
            if hasattr(record, "trace_id") and record.trace_id:
                log_entry["trace_id"] = record.trace_id
                log_entry["span_id"] = record.span_id
                if hasattr(record, "trace_flags") and record.trace_flags:
                    log_entry["trace_flags"] = record.trace_flags

        # Add standard fields
        log_entry.update(
            {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "thread": record.thread,
                "process": record.process,
            }
        )

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields from record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "exc_info",
                "exc_text",
                "stack_info",
                "trace_id",
                "span_id",
                "trace_flags",
            }:
                # Only include JSON-serializable values
                try:
                    json.dumps(value)
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)

        if extra:
            log_entry["extra"] = extra

        # Add configured extra fields
        if self.extra_fields:
            log_entry.update(self.extra_fields)

        return json.dumps(log_entry, ensure_ascii=False)


class StructuredLogger:
    """
    Wrapper for structured logging with business context.
    Provides convenient methods for logging with domain-specific context.
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log_with_context(
        self, level: int, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log message with structured context."""
        if context:
            # Add context as extra fields
            self.logger.log(level, message, extra=context, **kwargs)
        else:
            self.logger.log(level, message, **kwargs)

    def debug(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log debug message with context."""
        self._log_with_context(logging.DEBUG, message, context, **kwargs)

    def info(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log info message with context."""
        self._log_with_context(logging.INFO, message, context, **kwargs)

    def warning(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log warning message with context."""
        self._log_with_context(logging.WARNING, message, context, **kwargs)

    def error(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log error message with context."""
        self._log_with_context(logging.ERROR, message, context, **kwargs)

    def critical(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log critical message with context."""
        self._log_with_context(logging.CRITICAL, message, context, **kwargs)

    def exception(
        self, message: str, context: dict[str, Any] | None = None, **kwargs
    ) -> None:
        """Log exception with context and traceback."""
        kwargs.setdefault("exc_info", True)
        self._log_with_context(logging.ERROR, message, context, **kwargs)

    # Domain-specific logging methods

    def log_http_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Log HTTP request with structured context."""
        context = {
            "http": {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
        }

        if user_id:
            context["user_id"] = user_id
        if request_id:
            context["request_id"] = request_id

        level = logging.INFO
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING

        message = f"{method} {path} - {status_code} ({duration_ms:.1f}ms)"
        self._log_with_context(level, message, context)

    def log_database_operation(
        self,
        operation: str,
        table: str | None = None,
        duration_ms: float | None = None,
        rows_affected: int | None = None,
        error: str | None = None,
    ) -> None:
        """Log database operation with structured context."""
        context = {"database": {"operation": operation}}

        if table:
            context["database"]["table"] = table
        if duration_ms is not None:
            context["database"]["duration_ms"] = duration_ms
        if rows_affected is not None:
            context["database"]["rows_affected"] = rows_affected
        if error:
            context["database"]["error"] = error

        level = logging.ERROR if error else logging.DEBUG
        message = f"Database {operation}"
        if table:
            message += f" on {table}"
        if error:
            message += f" failed: {error}"

        self._log_with_context(level, message, context)

    def log_alpaca_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        request_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """Log Alpaca API request with structured context."""
        context = {
            "alpaca": {
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
        }

        if request_id:
            context["alpaca"]["request_id"] = request_id
        if error:
            context["alpaca"]["error"] = error

        level = logging.INFO
        if status_code >= 500 or error:
            level = logging.ERROR
        elif status_code >= 400:
            level = logging.WARNING

        message = f"Alpaca {method} {endpoint} - {status_code} ({duration_ms:.1f}ms)"
        if error:
            message += f" - {error}"

        self._log_with_context(level, message, context)

    def log_order_event(
        self,
        event: str,
        order_id: str,
        symbol: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        price: float | None = None,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        """Log order lifecycle event with structured context."""
        context = {"order": {"event": event, "order_id": order_id}}

        if symbol:
            context["order"]["symbol"] = symbol
        if side:
            context["order"]["side"] = side
        if quantity is not None:
            context["order"]["quantity"] = quantity
        if price is not None:
            context["order"]["price"] = price
        if status:
            context["order"]["status"] = status
        if error:
            context["order"]["error"] = error

        level = logging.ERROR if error else logging.INFO
        message = f"Order {event}: {order_id}"
        if symbol:
            message += f" ({symbol})"
        if error:
            message += f" - {error}"

        self._log_with_context(level, message, context)

    def log_outbox_event(
        self,
        event: str,
        message_id: str,
        topic: str | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        next_retry: datetime | None = None,
        error: str | None = None,
    ) -> None:
        """Log outbox pattern event with structured context."""
        context = {"outbox": {"event": event, "message_id": message_id}}

        if topic:
            context["outbox"]["topic"] = topic
        if attempt is not None:
            context["outbox"]["attempt"] = attempt
        if max_attempts is not None:
            context["outbox"]["max_attempts"] = max_attempts
        if next_retry:
            context["outbox"]["next_retry"] = next_retry.isoformat()
        if error:
            context["outbox"]["error"] = error

        level = logging.ERROR if error else logging.INFO
        message = f"Outbox {event}: {message_id}"
        if topic:
            message += f" ({topic})"
        if error:
            message += f" - {error}"

        self._log_with_context(level, message, context)

    def log_auth_event(
        self,
        event: str,
        user_id: str | None = None,
        method: str | None = None,
        success: bool | None = None,
        reason: str | None = None,
    ) -> None:
        """Log authentication event with structured context."""
        context = {"auth": {"event": event}}

        if user_id:
            context["auth"]["user_id"] = user_id
        if method:
            context["auth"]["method"] = method
        if success is not None:
            context["auth"]["success"] = success
        if reason:
            context["auth"]["reason"] = reason

        level = logging.INFO
        if success is False:
            level = logging.WARNING

        message = f"Auth {event}"
        if user_id:
            message += f" for user {user_id}"
        if reason:
            message += f" - {reason}"

        self._log_with_context(level, message, context)


def configure_structured_logging(
    level: str | int = "INFO",
    service_name: str = "intraday-trading",
    service_version: str = "2.0.0",
    enable_trace_correlation: bool = True,
    json_format: bool = True,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """
    Configure structured JSON logging with trace correlation.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service_name: Service name for log entries
        service_version: Service version for log entries
        enable_trace_correlation: Whether to include trace/span IDs
        json_format: Whether to use JSON formatting (vs plain text for development)
        extra_fields: Additional fields to include in all log entries
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper())

    # Create formatter
    if json_format:
        formatter = JSONFormatter(
            service_name=service_name,
            service_version=service_version,
            include_trace=enable_trace_correlation,
            extra_fields=extra_fields,
        )
    else:
        # Simple format for development
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Add trace ID filter if trace correlation is enabled
    if enable_trace_correlation and json_format:
        trace_filter = TraceIdFilter()
        handler.addFilter(trace_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)

    logging.info(
        f"Structured logging configured: level={logging.getLevelName(level)}, "
        f"json={json_format}, trace_correlation={enable_trace_correlation}"
    )


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance with domain-specific methods
    """
    return StructuredLogger(name)
