"""
Logger utilities for audit and application logging.
Provides standardized logging setup for the trading platform.
"""

import logging
import sys
from typing import Optional


def get_audit_logger(name: str = "audit") -> logging.Logger:
    """
    Create or get audit logger with standardized configuration.
    
    Args:
        name: Logger name (default: "audit")
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only add handler if none exists (avoid duplicate handlers)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(logging.INFO)
    return logger


def get_application_logger(
    name: str, 
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Get application logger with custom configuration.
    
    Args:
        name: Logger name
        level: Logging level (default: INFO)
        format_string: Custom format string
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        if format_string is None:
            format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(level)
    return logger
