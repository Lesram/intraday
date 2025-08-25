"""
Backend utilities package.
Provides common utility functions for the trading platform.
"""

# Export utility functions for tests and application components
from .utilities import (
    parse_timestamp,
    calculate_business_days,
    sanitize_symbol,
    validate_decimal_precision,
    chunks,
    retry_with_backoff,
    rate_limit,
    format_currency_simple,
)

# Export logger utilities  
from .logger import get_logger, audit_logger, performance_logger

# Export helper functions that actually exist
from .helpers import (
    align_for_pandas_arithmetic,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_var,
    calculate_cvar,
    kelly_criterion,
    normalize_data,
    correlation_matrix,
    generate_trade_id,
    hash_string,
    is_market_hours,
    round_to_tick_size,
    calculate_position_value,
    safe_divide,
    exponential_moving_average,
    bollinger_bands,
    rsi,
    validate_symbol,
    time_to_market_open,
)

__all__ = [
    # Utilities
    'parse_timestamp',
    'calculate_business_days', 
    'sanitize_symbol',
    'validate_decimal_precision',
    'chunks',
    'retry_with_backoff',
    'rate_limit',
    'format_currency_simple',
    # Logger
    'get_logger',
    'audit_logger',
    'performance_logger',
    # Helpers
    'align_for_pandas_arithmetic',
    'calculate_returns',
    'calculate_sharpe_ratio',
    'calculate_max_drawdown',
    'calculate_var',
    'calculate_cvar',
    'kelly_criterion',
    'normalize_data',
    'correlation_matrix',
    'generate_trade_id',
    'hash_string',
    'is_market_hours',
    'round_to_tick_size',
    'calculate_position_value',
    'safe_divide',
    'exponential_moving_average',
    'bollinger_bands',
    'rsi',
    'validate_symbol',
    'time_to_market_open',
]
