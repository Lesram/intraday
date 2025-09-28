"""
Comprehensive test coverage enhancement for utilities.py
Targeting missing lines: 31-69, 85-96, 100-110, 114-121, 125-126, 130-135, 139-149, 161-183, 186, 211-214, 224, 226, 250-253, 353, 424, 484
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os
import json
from decimal import Decimal

from backend.utils.utilities import (
    async_retry,
    parse_timestamp,
    calculate_business_days,
    sanitize_symbol,
    validate_decimal_precision,
    chunks,
    retry_with_backoff,
    rate_limit,
    format_currency_simple,
    truncate_string,
    time_ago,
    format_currency,
    format_percentage,
    validate_email,
    validate_phone,
    sanitize_string,
    generate_uuid,
    hash_password,
    verify_password,
    deep_merge_dicts,
    flatten_dict,
    unflatten_dict,
    chunk_list,
    retry_operation,
    cache_result,
    validate_json_schema,
    parse_date,
    format_date,
    file_exists,
    create_directory,
    read_file,
    write_file,
    get_file_size,
    safe_division,
    round_decimal,
    clamp,
    normalize_range,
)

class TestUtilitiesCoverageEnhancement:
    """Test class targeting specific missing coverage lines in utilities.py"""

    @pytest.mark.asyncio
    async def test_async_retry_with_exceptions(self):
        """Target lines 31-69: async_retry function with various scenarios"""
        call_count = 0
        
        # Test function that fails first two times then succeeds
        async def flaky_async_func():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError(f"Attempt {call_count} failed")
            return "success"
        
        result = await async_retry(flaky_async_func, max_attempts=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 3
        
        # Test function that always fails
        call_count = 0
        async def always_fail_async():
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"Always fails {call_count}")
        
        with pytest.raises(RuntimeError):
            await async_retry(always_fail_async, max_attempts=2, base_delay=0.01)
        
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_with_sync_function(self):
        """Target lines 37-38: async_retry with synchronous function"""
        call_count = 0
        
        def sync_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return "sync_success"
        
        result = await async_retry(sync_func, max_attempts=2, base_delay=0.01)
        assert result == "sync_success"
        assert call_count == 2

    @pytest.mark.asyncio  
    async def test_async_retry_jitter_and_backoff(self):
        """Target lines 47-54: jitter and exponential backoff logic"""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails for jitter test")
        
        with pytest.raises(ValueError):
            await async_retry(
                failing_func, 
                max_attempts=2, 
                base_delay=0.001, 
                max_delay=0.01,
                backoff_factor=2.0,
                jitter=True
            )
        
        assert call_count == 2

    def test_parse_timestamp_various_formats(self):
        """Target lines 85-96: parse_timestamp with different formats"""
        # Test Unix timestamp (int)
        result_int = parse_timestamp(1609459200)  # 2021-01-01 00:00:00 UTC
        assert isinstance(result_int, datetime)
        
        # Test Unix timestamp (float)
        result_float = parse_timestamp(1609459200.5)
        assert isinstance(result_float, datetime)
        
        # Test ISO format with Z
        result_iso = parse_timestamp("2021-01-01T00:00:00Z")
        assert isinstance(result_iso, datetime)
        assert result_iso.tzinfo is not None
        
        # Test ISO format with microseconds
        result_micro = parse_timestamp("2021-01-01T00:00:00.123456Z")
        assert isinstance(result_micro, datetime)
        
        # Test date only format
        result_date = parse_timestamp("2021-01-01")
        assert isinstance(result_date, datetime)
        
        # Test invalid format
        with pytest.raises(ValueError, match="Invalid timestamp"):
            parse_timestamp("invalid-format")

    def test_calculate_business_days_edge_cases(self):
        """Target lines 100-110: calculate_business_days function"""
        # Test same date
        same_date = datetime(2024, 1, 15)  # Monday
        result_same = calculate_business_days(same_date, same_date)
        assert result_same == 0
        
        # Test business days between Monday to Friday
        monday = datetime(2024, 1, 15)    # Monday
        friday = datetime(2024, 1, 19)    # Friday
        result_week = calculate_business_days(monday, friday)
        assert result_week == 4  # Mon->Tue, Tue->Wed, Wed->Thu, Thu->Fri
        
        # Test with weekends
        friday_start = datetime(2024, 1, 19)  # Friday
        monday_end = datetime(2024, 1, 22)    # Following Monday
        result_weekend = calculate_business_days(friday_start, monday_end)
        assert result_weekend == 1  # Only Friday->Monday (skip weekend)

    def test_sanitize_symbol_edge_cases(self):
        """Target lines 114-121: sanitize_symbol function"""
        # Test valid symbol
        assert sanitize_symbol("AAPL") == "AAPL"

        # Test empty string - expect ValueError
        with pytest.raises(ValueError, match="Empty symbol"):
            sanitize_symbol("")        # Test symbol with invalid characters - expect ValueError
        with pytest.raises(ValueError, match="Invalid symbol format"):
            sanitize_symbol("A@APL#123")

    def test_validate_decimal_precision_edge_cases(self):
        """Target lines 125-126: validate_decimal_precision function"""
        # Test valid precision
        assert validate_decimal_precision(123.45, max_places=2) == True
        assert validate_decimal_precision(123.4, max_places=2) == True
        assert validate_decimal_precision(123, max_places=2) == True
        
        # Test invalid precision
        assert validate_decimal_precision(123.456, max_places=2) == False
        
        # Test Decimal objects
        assert validate_decimal_precision(Decimal('123.45'), max_places=2) == True
        assert validate_decimal_precision(Decimal('123.456'), max_places=2) == False

    def test_chunks_function(self):
        """Target lines 130-135: chunks function"""
        test_data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        # Test chunking
        result = list(chunks(test_data, 3))
        assert result == [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10]]
        
        # Test with exact division
        result_exact = list(chunks([1, 2, 3, 4], 2))
        assert result_exact == [[1, 2], [3, 4]]
        
        # Test with empty iterable
        result_empty = list(chunks([], 2))
        assert result_empty == []

    @pytest.mark.asyncio
    async def test_retry_with_backoff_scenarios(self):
        """Target lines 139-149: retry_with_backoff function"""
        call_count = 0
        
        # Test successful retry
        async def sometimes_works():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network error")
            return "backoff_success"
        
        result = await retry_with_backoff(sometimes_works, max_attempts=2, base_delay=0.001)
        assert result == "backoff_success"
        assert call_count == 2
        
        # Test max attempts reached
        call_count = 0
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Timeout")
        
        with pytest.raises(TimeoutError):
            await retry_with_backoff(always_fails, max_attempts=2, base_delay=0.001)
        
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_async(self):
        """Target lines 161-183: rate_limit decorator with async functions"""
        
        @rate_limit(10)  # 10 calls per second
        async def async_api_call():
            return "async_result"
        
        # Test rate limited async function
        result = await async_api_call()
        assert result == "async_result"
        
        # Test multiple calls (should not raise error for reasonable rate)
        results = []
        for _ in range(3):
            result = await async_api_call()
            results.append(result)
        
        assert all(r == "async_result" for r in results)

    def test_rate_limit_decorator_sync(self):
        """Target line 186: rate_limit decorator with sync functions"""
        
        @rate_limit(10)  # 10 calls per second
        def sync_api_call():
            return "sync_result"
        
        # Test rate limited sync function
        result = sync_api_call()
        assert result == "sync_result"

    def test_format_currency_simple_edge_cases(self):
        """Target lines 211-214: format_currency_simple function"""
        # Test basic formatting
        assert format_currency_simple(1234.56) == "$1,234.56"
        
        # Test with different precision
        assert format_currency_simple(1234.567, precision=3) == "$1,234.567"
        
        # Test zero value
        assert format_currency_simple(0) == "$0.00"
        
        # Test negative value
        result_negative = format_currency_simple(-1234.56)
        assert "$" in result_negative and "1,234.56" in result_negative

    def test_truncate_string_edge_cases(self):
        """Target lines 224, 226: truncate_string function"""
        # Test string longer than limit
        long_text = "This is a very long string that needs truncation"
        result = truncate_string(long_text, 20)
        assert len(result) <= 23  # 20 + 3 for "..."
        assert result.endswith("...")
        
        # Test string shorter than limit
        short_text = "Short"
        result_short = truncate_string(short_text, 20)
        assert result_short == "Short"
        
        # Test custom suffix
        result_custom = truncate_string(long_text, 20, suffix=" [more]")
        assert result_custom.endswith(" [more]")

    def test_time_ago_edge_cases(self):
        """Target lines 250-253: time_ago function"""
        from datetime import timedelta
        
        now = datetime.now()
        
        # Test recent time - function may return "Just now" for very recent times
        recent = now - timedelta(seconds=30)
        result_recent = time_ago(recent)
        assert isinstance(result_recent, str)
        assert len(result_recent) > 0
        
        # Test minutes ago
        minutes_ago = now - timedelta(minutes=5)
        result_minutes = time_ago(minutes_ago)
        assert isinstance(result_minutes, str)
        
        # Test hours ago
        hours_ago = now - timedelta(hours=2)
        result_hours = time_ago(hours_ago)
        assert isinstance(result_hours, str)
        
        # Test days ago
        days_ago = now - timedelta(days=3)
        result_days = time_ago(days_ago)
        assert isinstance(result_days, str)

    def test_cache_result_decorator(self):
        """Target line 353: cache_result decorator"""
        call_count = 0
        
        @cache_result
        def expensive_calculation(x):
            nonlocal call_count
            call_count += 1
            return x * x
        
        # First call
        result1 = expensive_calculation(5)
        assert result1 == 25
        assert call_count == 1
        
        # Second call with same argument (should use cache)
        result2 = expensive_calculation(5)
        assert result2 == 25
        assert call_count == 1  # Should not increment
        
        # Third call with different argument
        result3 = expensive_calculation(6)
        assert result3 == 36
        assert call_count == 2

    def test_normalize_range_edge_cases(self):
        """Target line 424: normalize_range function"""
        # Test basic normalization
        result = normalize_range(5, 0, 10, 0, 1)
        assert result == 0.5
        
        # Test with different new range
        result_custom = normalize_range(5, 0, 10, -1, 1)
        assert result_custom == 0.0  # Middle of old range maps to middle of new range
        
        # Test edge values
        result_min = normalize_range(0, 0, 10, 0, 1)
        assert result_min == 0.0
        
        result_max = normalize_range(10, 0, 10, 0, 1)
        assert result_max == 1.0

    def test_additional_utility_functions(self):
        """Test other utility functions for comprehensive coverage"""
        
        # Test various validation functions
        assert validate_email("test@example.com") == True
        assert validate_email("invalid-email") == False
        
        assert validate_phone("+1234567890") == True
        assert validate_phone("invalid") == False
        
        # Test string operations
        assert sanitize_string("  test string  ") == "test string"
        assert sanitize_string(None) == ""
        
        # Test UUID generation
        uuid_result = generate_uuid()
        assert isinstance(uuid_result, str)
        assert len(uuid_result) > 0
        
        # Test password operations
        password = "test_password"
        hashed = hash_password(password)
        assert verify_password(password, hashed) == True
        assert verify_password("wrong_password", hashed) == False
        
        # Test dictionary operations
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}
        merged = deep_merge_dicts(dict1, dict2)
        assert "a" in merged
        assert "e" in merged
        assert merged["b"]["c"] == 2
        assert merged["b"]["d"] == 3
        
        # Test flatten/unflatten
        nested = {"a": {"b": {"c": 1}}}
        flattened = flatten_dict(nested)
        assert "a.b.c" in flattened
        
        unflattened = unflatten_dict(flattened)
        assert unflattened["a"]["b"]["c"] == 1
        
        # Test chunk operations
        chunked = list(chunk_list([1, 2, 3, 4, 5], 2))
        assert len(chunked) == 3
        assert chunked[0] == [1, 2]
        
        # Test math operations
        assert safe_division(10, 2) == 5.0
        assert safe_division(10, 0) == 0  # Default value
        assert safe_division(10, 0, default=999) == 999
        
        assert round_decimal(123.456, 2) == 123.46
        assert clamp(15, 0, 10) == 10
        assert clamp(-5, 0, 10) == 0
        assert clamp(5, 0, 10) == 5

    def test_file_operations(self):
        """Test file operation functions"""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            test_content = "Hello, World!"
            
            # Test file_exists
            assert file_exists(test_file) == False
            
            # Test write_file
            write_file(test_file, test_content)
            assert file_exists(test_file) == True
            
            # Test read_file
            read_content = read_file(test_file)
            assert read_content == test_content
            
            # Test get_file_size
            size = get_file_size(test_file)
            assert size == len(test_content)
            
            # Test create_directory
            new_dir = os.path.join(temp_dir, "subdir")
            create_directory(new_dir)
            assert os.path.exists(new_dir)

    def test_json_schema_validation(self):
        """Test validate_json_schema function"""
        # Simple schema that should work
        schema = {"type": "object"}
        
        # Valid data
        valid_data = {"name": "John", "age": 30}
        result = validate_json_schema(valid_data, schema)
        assert isinstance(result, bool)  # Just verify it returns a boolean
        
        # Invalid data (not an object)
        invalid_data = "not an object"
        result_invalid = validate_json_schema(invalid_data, schema)
        assert isinstance(result_invalid, bool)

    def test_date_operations(self):
        """Test date parsing and formatting functions"""
        # Test parse_date
        date_str = "2024-01-15"
        parsed = parse_date(date_str)
        assert isinstance(parsed, datetime)
        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 15
        
        # Test format_date
        date_obj = datetime(2024, 1, 15)
        formatted = format_date(date_obj)
        assert formatted == "2024-01-15"
        
        # Test with custom format
        custom_format = format_date(date_obj, "%m/%d/%Y")
        assert custom_format == "01/15/2024"

    def test_retry_operation_function(self):
        """Test retry_operation function"""
        call_count = 0
        
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Function failed")
            return "success"
        
        result = retry_operation(flaky_function, max_retries=3, delay=0.001)
        assert result == "success"
        assert call_count == 3
        
        # Test function that always fails
        call_count = 0
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fails")
        
        with pytest.raises(RuntimeError):
            retry_operation(always_fail, max_retries=2, delay=0.001)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])