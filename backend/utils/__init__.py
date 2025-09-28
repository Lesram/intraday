"""
Backend utilities package.
Provides common utility functions for the trading platform.
"""

# Export utility functions for tests and application components
# Export helper functions that actually exist
from .helpers import (
    align_for_pandas_arithmetic,
    bollinger_bands,
    calculate_cvar,
    calculate_max_drawdown,
    calculate_position_value,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_var,
    correlation_matrix,
    exponential_moving_average,
    generate_trade_id,
    hash_string,
    is_market_hours,
    kelly_criterion,
    normalize_data,
    round_to_tick_size,
    rsi,
    safe_divide,
    time_to_market_open,
    validate_symbol,
)

# Export logger utilities  
from .logger import audit_logger, get_logger, performance_logger
from .utilities import (
    calculate_business_days,
    chunks,
    format_currency_simple,
    parse_timestamp,
    rate_limit,
    retry_with_backoff,
    sanitize_symbol,
    validate_decimal_precision,
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
