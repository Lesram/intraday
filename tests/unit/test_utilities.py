"""
Unit tests for utility functions and helpers.

Tests time/date handling, configuration loading, schema validation,
and other utility functions.
"""

from datetime import UTC, datetime
from decimal import Decimal
import os
from unittest.mock import patch

import pytest

from backend.infra.validation import validate_order, validate_symbol, validate_price
from backend.utils.helpers import (
    format_currency,
    is_market_hours,
    generate_trade_id,
    hash_string,
    calculate_returns,
    calculate_sharpe_ratio
)
from backend.utils.logger import get_logger


class TestTimeUtilities:
    """Test time and date utility functions."""

    @pytest.mark.unit
    def test_parse_timestamp_iso_format(self):
        """Test parsing ISO format timestamps."""
        iso_string = "2024-01-02T09:30:15.123456Z"
        parsed = parse_timestamp(iso_string)

        assert isinstance(parsed, datetime)
        assert parsed.tzinfo == UTC
        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 2
        assert parsed.hour == 9
        assert parsed.minute == 30
        assert parsed.second == 15

    @pytest.mark.unit
    def test_parse_timestamp_unix_format(self):
        """Test parsing Unix timestamp format."""
        unix_timestamp = 1704183015.123456  # 2024-01-02T09:30:15.123456Z
        parsed = parse_timestamp(unix_timestamp)

        assert isinstance(parsed, datetime)
        assert parsed.tzinfo == UTC

    @pytest.mark.unit
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamp formats."""
        invalid_timestamps = [
            "not-a-date",
            "2024-13-01",  # Invalid month
            "",
            None,
        ]

        for invalid_ts in invalid_timestamps:
            with pytest.raises((ValueError, TypeError)):
                parse_timestamp(invalid_ts)

    @pytest.mark.unit
    def test_is_market_hours_weekday(self):
        """Test market hours detection for weekdays."""
        # Tuesday, 2024-01-02 at different times
        market_open = datetime(2024, 1, 2, 9, 30, tzinfo=UTC)  # 9:30 AM EST
        market_mid = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)  # 2:00 PM EST
        market_close = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)  # 4:00 PM EST
        before_market = datetime(2024, 1, 2, 8, 0, tzinfo=UTC)  # 8:00 AM EST
        after_market = datetime(2024, 1, 2, 22, 0, tzinfo=UTC)  # 10:00 PM EST

        assert is_market_hours(market_open) is True
        assert is_market_hours(market_mid) is True
        assert is_market_hours(market_close) is False  # Market closes at 4 PM
        assert is_market_hours(before_market) is False
        assert is_market_hours(after_market) is False

    @pytest.mark.unit
    def test_is_market_hours_weekend(self):
        """Test market hours detection for weekends."""
        # Saturday, 2024-01-06 at market time
        saturday = datetime(2024, 1, 6, 14, 0, tzinfo=UTC)  # 2:00 PM EST
        sunday = datetime(2024, 1, 7, 14, 0, tzinfo=UTC)  # 2:00 PM EST

        assert is_market_hours(saturday) is False
        assert is_market_hours(sunday) is False

    @pytest.mark.unit
    def test_calculate_business_days(self):
        """Test business day calculation."""
        # Monday to Friday (same week)
        start = datetime(2024, 1, 1)  # Monday
        end = datetime(2024, 1, 5)  # Friday

        business_days = calculate_business_days(start, end)
        assert business_days == 4  # Mon, Tue, Wed, Thu (end date exclusive)

        # Include weekends
        start = datetime(2024, 1, 1)  # Monday
        end = datetime(2024, 1, 8)  # Next Monday

        business_days = calculate_business_days(start, end)
        assert business_days == 5  # Mon-Fri of first week

    @pytest.mark.unit
    def test_calculate_business_days_same_day(self):
        """Test business day calculation for same day."""
        same_day = datetime(2024, 1, 2)

        business_days = calculate_business_days(same_day, same_day)
        assert business_days == 0

    @pytest.mark.unit
    def test_calculate_business_days_reverse(self):
        """Test business day calculation with reversed dates."""
        start = datetime(2024, 1, 5)  # Friday
        end = datetime(2024, 1, 1)  # Monday (earlier)

        business_days = calculate_business_days(start, end)
        assert business_days == -4  # Negative for reverse


class TestStringUtilities:
    """Test string manipulation utilities."""

    @pytest.mark.unit
    def test_sanitize_symbol_valid(self):
        """Test symbol sanitization with valid symbols."""
        valid_symbols = ["AAPL", "GOOGL", "BRK.A", "BRK.B"]

        for symbol in valid_symbols:
            sanitized = sanitize_symbol(symbol)
            assert sanitized == symbol.upper()

    @pytest.mark.unit
    def test_sanitize_symbol_invalid(self):
        """Test symbol sanitization with invalid symbols."""
        invalid_symbols = [
            "aapl",  # Lowercase
            " AAPL ",  # Whitespace
            "AA@PL",  # Special chars
            "123ABC",  # Numbers first
            "",  # Empty
            "TOOLONGNAME",  # Too long
        ]

        for symbol in invalid_symbols:
            if symbol.strip().upper() in ["AAPL"]:
                # Should be cleaned
                sanitized = sanitize_symbol(symbol)
                assert sanitized == "AAPL"
            else:
                # Should raise exception for truly invalid
                with pytest.raises(ValueError):
                    sanitize_symbol(symbol)

    @pytest.mark.unit
    def test_format_currency(self):
        """Test currency formatting."""
        test_cases = [
            (Decimal("1234.56"), "$1,234.56"),
            (Decimal("0.99"), "$0.99"),
            (Decimal("1000000"), "$1,000,000.00"),
            (Decimal("-500.25"), "-$500.25"),
            (Decimal("0"), "$0.00"),
        ]

        for amount, expected in test_cases:
            formatted = format_currency(amount)
            assert formatted == expected

    @pytest.mark.unit
    def test_format_currency_precision(self):
        """Test currency formatting with different precisions."""
        amount = Decimal("1234.56789")

        # Default precision (2)
        assert format_currency(amount) == "$1,234.57"  # Rounded

        # Custom precision
        assert format_currency(amount, precision=4) == "$1,234.5679"
        assert format_currency(amount, precision=0) == "$1,235"


class TestDecimalUtilities:
    """Test decimal precision and validation utilities."""

    @pytest.mark.unit
    def test_validate_decimal_precision_valid(self):
        """Test decimal precision validation with valid inputs."""
        valid_decimals = [
            (Decimal("123.45"), 2),
            (Decimal("100.0"), 1),
            (Decimal("999"), 0),
            (Decimal("0.12345"), 5),
        ]

        for decimal_val, max_precision in valid_decimals:
            result = validate_decimal_precision(decimal_val, max_precision)
            assert result is True

    @pytest.mark.unit
    def test_validate_decimal_precision_invalid(self):
        """Test decimal precision validation with invalid inputs."""
        invalid_cases = [
            (Decimal("123.456"), 2),  # Too many decimals
            (Decimal("100.01"), 1),  # Too many decimals
            (Decimal("0.123456"), 5),  # Too many decimals
        ]

        for decimal_val, max_precision in invalid_cases:
            result = validate_decimal_precision(decimal_val, max_precision)
            assert result is False

    @pytest.mark.unit
    def test_validate_decimal_precision_edge_cases(self):
        """Test decimal precision validation edge cases."""
        # Zero precision
        assert validate_decimal_precision(Decimal("100"), 0) is True
        assert validate_decimal_precision(Decimal("100.1"), 0) is False

        # Large numbers
        assert validate_decimal_precision(Decimal("999999999.99"), 2) is True

        # Negative numbers
        assert validate_decimal_precision(Decimal("-123.45"), 2) is True


class TestCollectionUtilities:
    """Test collection manipulation utilities."""

    @pytest.mark.unit
    def test_chunks_even_division(self):
        """Test chunking with even division."""
        data = list(range(10))  # [0, 1, 2, ..., 9]
        chunk_size = 2

        chunked = list(chunks(data, chunk_size))

        assert len(chunked) == 5
        assert chunked[0] == [0, 1]
        assert chunked[1] == [2, 3]
        assert chunked[-1] == [8, 9]

    @pytest.mark.unit
    def test_chunks_uneven_division(self):
        """Test chunking with uneven division."""
        data = list(range(11))  # [0, 1, 2, ..., 10]
        chunk_size = 3

        chunked = list(chunks(data, chunk_size))

        assert len(chunked) == 4
        assert chunked[0] == [0, 1, 2]
        assert chunked[1] == [3, 4, 5]
        assert chunked[2] == [6, 7, 8]
        assert chunked[3] == [9, 10]  # Last chunk smaller

    @pytest.mark.unit
    def test_chunks_empty_list(self):
        """Test chunking with empty list."""
        data = []
        chunk_size = 5

        chunked = list(chunks(data, chunk_size))
        assert len(chunked) == 0

    @pytest.mark.unit
    def test_chunks_larger_chunk_size(self):
        """Test chunking where chunk size exceeds data length."""
        data = [1, 2, 3]
        chunk_size = 10

        chunked = list(chunks(data, chunk_size))
        assert len(chunked) == 1
        assert chunked[0] == [1, 2, 3]


class TestRetryUtilities:
    """Test retry and resilience utilities."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retry_with_backoff_success(self):
        """Test retry utility with successful operation."""
        call_count = 0

        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = await retry_with_backoff(
            flaky_operation,
            max_attempts=5,
            base_delay=0.01,  # Fast for testing
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retry_with_backoff_max_attempts(self):
        """Test retry utility reaching max attempts."""
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent failure")

        with pytest.raises(Exception, match="Persistent failure"):
            await retry_with_backoff(always_fails, max_attempts=3, base_delay=0.01)

        assert call_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rate_limit_decorator(self):
        """Test rate limiting decorator."""
        call_times = []

        @rate_limit(calls_per_second=10)  # 100ms between calls
        async def rate_limited_func():
            call_times.append(datetime.now())
            return "called"

        # Make multiple rapid calls
        for _ in range(3):
            await rate_limited_func()

        # Check that calls were spaced appropriately
        assert len(call_times) == 3
        if len(call_times) >= 2:
            time_diff = call_times[1] - call_times[0]
            assert time_diff.total_seconds() >= 0.09  # ~100ms spacing


class TestConfigurationLoading:
    """Test configuration loading and validation."""

    @pytest.fixture
    def sample_config_dict(self):
        """Sample configuration dictionary."""
        return {
            "environment": "test",
            "database_url": "sqlite:///test.db",
            "alpaca_api_key": "test_key",
            "alpaca_secret": "test_secret",
            "jwt_secret_key": "test_jwt_secret",
            "log_level": "DEBUG",
            "trading_mode": "DRY_RUN",
        }

    @pytest.mark.unit
    def test_config_from_dict(self, sample_config_dict):
        """Test configuration loading from dictionary."""
        config = Config(**sample_config_dict)

        assert config.environment == "test"
        assert config.database_url == "sqlite:///test.db"
        assert config.alpaca_api_key == "test_key"
        assert config.log_level == "DEBUG"

    @pytest.mark.unit
    def test_config_from_env_vars(self, sample_config_dict):
        """Test configuration loading from environment variables."""
        env_vars = {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://prod:pass@db:5432/trading",
            "ALPACA_API_KEY": "prod_key",
            "LOG_LEVEL": "INFO",
        }

        with patch.dict(os.environ, env_vars):
            config = load_config_from_env()

            assert config.environment == "production"
            assert config.database_url == "postgresql://prod:pass@db:5432/trading"
            assert config.alpaca_api_key == "prod_key"
            assert config.log_level == "INFO"

    @pytest.mark.unit
    def test_config_validation_missing_required(self):
        """Test configuration validation with missing required fields."""
        incomplete_config = {
            "environment": "test",
            # Missing database_url, alpaca_api_key, etc.
        }

        with pytest.raises(ValueError):
            Config(**incomplete_config)

    @pytest.mark.unit
    def test_config_validation_invalid_values(self):
        """Test configuration validation with invalid values."""
        invalid_configs = [
            # Invalid environment
            {"environment": "invalid", "database_url": "sqlite:///test.db"},
            # Invalid log level
            {
                "environment": "test",
                "log_level": "INVALID",
                "database_url": "sqlite:///test.db",
            },
            # Invalid trading mode
            {
                "environment": "test",
                "trading_mode": "INVALID",
                "database_url": "sqlite:///test.db",
            },
        ]

        for invalid_config in invalid_configs:
            with pytest.raises(ValueError):
                Config(**invalid_config)

    @pytest.mark.unit
    def test_config_defaults(self):
        """Test configuration default values."""
        minimal_config = {
            "database_url": "sqlite:///test.db",
            "alpaca_api_key": "test_key",
            "alpaca_secret": "test_secret",
            "jwt_secret_key": "test_jwt",
        }

        config = Config(**minimal_config)

        assert config.environment == "development"  # Default
        assert config.log_level == "INFO"  # Default
        assert config.trading_mode == "DRY_RUN"  # Default


class TestSchemaValidation:
    """Test schema validation utilities."""

    @pytest.mark.unit
    def test_validate_symbol_valid(self):
        """Test symbol validation with valid data."""
        result = validate_symbol("AAPL")
        assert result == "AAPL"
        
        result = validate_symbol("BTC-USD")
        assert result == "BTC-USD"

    @pytest.mark.unit  
    def test_validate_price_valid(self):
        """Test price validation with valid data."""
        result = validate_price(185.0)
        assert result == 185.0
        
        result = validate_price(0.001)
        assert result == 0.001
        
        # Test price validation catches negative prices
        with pytest.raises(ValueError):
            validate_price(-10.0)

    @pytest.mark.unit
    def test_validate_order_schema_valid(self):
        """Test order schema validation with valid data."""
        valid_order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": "100",
            "order_type": "market",
            "time_in_force": "day",
        }

        result = validate_order(valid_order)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.unit
    def test_validate_order_schema_invalid(self):
        """Test order schema validation with invalid data."""
        invalid_order = {
            "symbol": "",  # Empty symbol
            "side": "invalid",  # Invalid side
            "qty": "0",  # Zero quantity
            "order_type": "unknown",  # Invalid order type
            "price": "-100",  # Negative price
        }

        result = validate_order(invalid_order)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0


class TestLoggerUtilities:
    """Test logging utilities and configuration."""

    @pytest.mark.unit
    def test_get_logger_creation(self):
        """Test logger creation with proper configuration."""
        logger = get_logger("test_module")

        assert logger.name == "test_module"
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")

    @pytest.mark.unit
    def test_audit_logger_structure(self):
        """Test audit logger structured logging."""
        with patch("backend.utils.logger.audit_logger") as mock_audit:
            audit_logger.info(
                "Trade executed",
                extra={
                    "user_id": "user_123",
                    "order_id": "order_456",
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 100,
                    "price": 185.50,
                },
            )

            mock_audit.info.assert_called_once()
            args, kwargs = mock_audit.info.call_args

            assert args[0] == "Trade executed"
            assert "extra" in kwargs
            assert kwargs["extra"]["user_id"] == "user_123"
            assert kwargs["extra"]["symbol"] == "AAPL"

    @pytest.mark.unit
    def test_logger_level_filtering(self):
        """Test that logger respects level filtering."""
        logger = get_logger("test_logger")

        # Set to INFO level
        logger.setLevel("INFO")

        with patch.object(logger, "debug") as mock_debug:
            with patch.object(logger, "info") as mock_info:
                logger.debug("Debug message")  # Should be filtered
                logger.info("Info message")  # Should pass

                mock_debug.assert_not_called()
                mock_info.assert_called_once()
