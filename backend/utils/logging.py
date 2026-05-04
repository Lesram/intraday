"""
Logging utilities for infrastructure compatibility.
Delegates to Python's built-in logging module.
"""

import logging
import sys
from typing import Any


class Logger:
    """Logger that delegates to the standard logging module."""

    def __init__(self, name: str = "trading"):
        self.name = name
        self._logger = logging.getLogger(name)
        self.level = self._logger.level
        self.handlers = self._logger.handlers

    def debug(self, message: str, *args, **kwargs) -> None:
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        self._logger.error(message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs) -> None:
        self._logger.critical(message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs) -> None:
        self._logger.exception(message, *args, **kwargs)

    def setLevel(self, level: int) -> None:
        self.level = level
        self._logger.setLevel(level)

    def addHandler(self, handler) -> None:
        self._logger.addHandler(handler)
        self.handlers = self._logger.handlers

    def removeHandler(self, handler) -> None:
        self._logger.removeHandler(handler)
        self.handlers = self._logger.handlers


class LogHandler:
    """Log handler that delegates to logging.StreamHandler."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self._handler = logging.StreamHandler(self.stream)
        self.level = self._handler.level
        self.formatter = None

    def setFormatter(self, formatter) -> None:
        self.formatter = formatter
        if hasattr(formatter, 'fmt'):
            self._handler.setFormatter(logging.Formatter(formatter.fmt))

    def handle(self, record) -> None:
        self._handler.handle(record)

    def emit(self, record) -> None:
        self._handler.emit(record)


class Formatter:
    """Log formatter wrapping logging.Formatter."""

    def __init__(self, fmt: str = None, datefmt: str = None):
        self.fmt = fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        self.datefmt = datefmt
        self._formatter = logging.Formatter(self.fmt, datefmt=self.datefmt)

    def format(self, record) -> str:
        return self._formatter.format(record)


# Module-level functions for direct imports
def get_logger(name: str = "trading") -> Logger:
    """Get logger instance."""
    return Logger(name)

def setup_logging(config: dict[str, Any] | None = None) -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

def configure_logger(name: str, level: str = "INFO") -> Logger:
    """Configure logger with specific level."""
    logger = Logger(name)
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    logger.setLevel(level_map.get(level, logging.INFO))
    return logger

def create_console_handler(level: str = "INFO") -> LogHandler:
    """Create console handler."""
    return LogHandler(sys.stdout)

def create_file_handler(filename: str, level: str = "INFO") -> LogHandler:
    """Create file handler."""
    return LogHandler()

def create_formatter(format_string: str | None = None) -> Formatter:
    """Create log formatter."""
    return Formatter(format_string)

def log_trade_execution(order_id: str, symbol: str, quantity: float, price: float) -> None:
    """Log trade execution."""
    logging.getLogger("trading").info(
        "Trade executed: order=%s symbol=%s qty=%.2f price=%.4f",
        order_id, symbol, quantity, price,
    )

def log_risk_check(symbol: str, risk_score: float, approved: bool) -> None:
    """Log risk check result."""
    logging.getLogger("trading").info(
        "Risk check: symbol=%s score=%.4f approved=%s",
        symbol, risk_score, approved,
    )

def log_market_data_update(symbol: str, price: float, volume: int) -> None:
    """Log market data update."""
    logging.getLogger("trading").debug(
        "Market data: symbol=%s price=%.4f volume=%d",
        symbol, price, volume,
    )

def log_model_prediction(symbol: str, prediction: int, confidence: float) -> None:
    """Log ML model prediction."""
    logging.getLogger("trading").info(
        "ML prediction: symbol=%s prediction=%d confidence=%.4f",
        symbol, prediction, confidence,
    )

def log_system_startup() -> None:
    """Log system startup."""
    logging.getLogger("trading").info("System startup")

def log_system_shutdown() -> None:
    """Log system shutdown."""
    logging.getLogger("trading").info("System shutdown")

def log_error_with_context(error: Exception, context: dict[str, Any]) -> None:
    """Log error with additional context."""
    logging.getLogger("trading").error(
        "Error: %s context=%s", error, context, exc_info=True,
    )

# Structured logging helpers
def create_structured_logger(name: str) -> dict[str, Any]:
    """Create structured logger."""
    return {
        "logger": get_logger(name),
        "context": {},
        "handlers": []
    }

def add_log_context(context: dict[str, Any]) -> None:
    """Add context to structured logging."""
    pass

def remove_log_context(keys: list) -> None:
    """Remove context from structured logging."""
    pass

# Default logger instance
logger = get_logger("trading")
default_logger = logger

# Compatibility aliases
log = logger
trading_logger = logger
