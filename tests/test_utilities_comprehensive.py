"""
Comprehensive tests for backend.utils.utilities

Targets 80%+ coverage for the utilities module which provides:
- Retry functions with exponential backoff
- Timestamp parsing and date utilities
- Symbol sanitization and validation
- Rate limiting decorators
- Currency and string formatting
- Dict manipulation (merge, flatten, unflatten)
- File operations
- Caching and memoization decorators
"""

import asyncio
from datetime import datetime, timedelta, UTC
import os
import tempfile
from unittest.mock import Mock, patch
import pytest

from backend.utils.utilities import (
    async_retry,
    calculate_business_days,
    calculate_percentage,
    cache_result,
    chunks,
    chunk_list,
    clamp,
    convert_units,
    create_directory,
    deep_merge_dicts,
    dynamic_import,
    environment_variable,
    file_exists,
    flatten_dict,
    format_currency,
    format_currency_simple,
    format_date,
    format_percentage,
    generate_uuid,
    get_file_size,
    get_nested_value,
    hash_password,
    is_empty,
    is_number,
    memoize,
    merge_lists,
    normalize_range,
    parse_config,
    parse_date,
    parse_timestamp,
    rate_limit,
    read_file,
    remove_duplicates,
    retry_operation,
    retry_with_backoff,
    round_decimal,
    safe_division,
    safe_import,
    sanitize_string,
    sanitize_symbol,
    set_nested_value,
    singleton,
    timer,
    time_ago,
    to_camel_case,
    to_snake_case,
    truncate_string,
    unflatten_dict,
    validate_decimal_precision,
    validate_email,
    validate_json_schema,
    validate_phone,
    verify_password,
    write_file,
)


# ============================================================================
# ASYNC RETRY TESTS
# ============================================================================

class TestAsyncRetry:
    """Tests for async_retry function"""
    
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        """Test successful execution on first attempt"""
        call_count = 0
        
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await async_retry(success_func, max_attempts=3)
        
        assert result == "success"
        assert call_count == 1
        
    @pytest.mark.asyncio
    async def test_success_after_retries(self):
        """Test success after initial failures"""
        call_count = 0
        
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = await async_retry(fail_then_succeed, max_attempts=5, base_delay=0.01)
        
        assert result == "success"
        assert call_count == 3
        
    @pytest.mark.asyncio
    async def test_all_attempts_fail(self):
        """Test exception raised after max attempts"""
        async def always_fail():
            raise ValueError("Persistent failure")
        
        with pytest.raises(ValueError, match="Persistent failure"):
            await async_retry(always_fail, max_attempts=3, base_delay=0.01)
            
    @pytest.mark.asyncio
    async def test_sync_function_wrapped(self):
        """Test wrapping synchronous function"""
        call_count = 0
        
        def sync_func():
            nonlocal call_count
            call_count += 1
            return "sync_result"
        
        result = await async_retry(sync_func, max_attempts=3)
        
        assert result == "sync_result"
        assert call_count == 1


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function"""
    
    @pytest.mark.asyncio
    async def test_success(self):
        """Test successful execution"""
        async def success():
            return "ok"
        
        result = await retry_with_backoff(success, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        
    @pytest.mark.asyncio
    async def test_failure_then_success(self):
        """Test retry on failure"""
        attempts = 0
        
        async def flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise Exception("fail")
            return "recovered"
        
        result = await retry_with_backoff(flaky, max_attempts=3, base_delay=0.01)
        assert result == "recovered"


class TestRetryOperation:
    """Tests for retry_operation function"""
    
    def test_success(self):
        """Test successful operation"""
        result = retry_operation(lambda: 42, max_retries=3)
        assert result == 42
        
    def test_retry_then_success(self):
        """Test retrying then succeeding"""
        attempts = [0]
        
        def flaky():
            attempts[0] += 1
            if attempts[0] < 2:
                raise ValueError("temp")
            return "ok"
        
        result = retry_operation(flaky, max_retries=3, delay=0.01)
        assert result == "ok"
        
    def test_all_retries_fail(self):
        """Test exception after all retries"""
        def always_fail():
            raise ValueError("permanent")
        
        with pytest.raises(ValueError):
            retry_operation(always_fail, max_retries=2, delay=0.01)


# ============================================================================
# TIMESTAMP AND DATE TESTS
# ============================================================================

class TestParseTimestamp:
    """Tests for parse_timestamp function"""
    
    def test_unix_timestamp_int(self):
        """Test parsing Unix timestamp as integer"""
        result = parse_timestamp(1609459200)  # 2021-01-01 00:00:00 UTC
        assert isinstance(result, datetime)
        
    def test_unix_timestamp_float(self):
        """Test parsing Unix timestamp as float"""
        result = parse_timestamp(1609459200.5)
        assert isinstance(result, datetime)
        
    def test_iso_format(self):
        """Test parsing ISO format"""
        result = parse_timestamp("2021-01-01T12:00:00Z")
        assert result.year == 2021
        assert result.month == 1
        
    def test_simple_date(self):
        """Test parsing simple date"""
        result = parse_timestamp("2021-01-01")
        assert result.year == 2021
        
    def test_datetime_format(self):
        """Test parsing datetime format"""
        result = parse_timestamp("2021-01-01 12:30:45")
        assert result.hour == 12
        
    def test_invalid_format_raises(self):
        """Test invalid format raises ValueError"""
        with pytest.raises(ValueError, match="Invalid timestamp"):
            parse_timestamp("not-a-date")


class TestCalculateBusinessDays:
    """Tests for calculate_business_days function"""
    
    def test_same_day(self):
        """Test same day returns 0"""
        date = datetime(2021, 1, 4)  # Monday
        assert calculate_business_days(date, date) == 0
        
    def test_weekdays_only(self):
        """Test counting weekdays"""
        start = datetime(2021, 1, 4)  # Monday
        end = datetime(2021, 1, 8)    # Friday
        assert calculate_business_days(start, end) == 4
        
    def test_skips_weekends(self):
        """Test weekends are skipped"""
        start = datetime(2021, 1, 4)   # Monday
        end = datetime(2021, 1, 11)    # Next Monday
        assert calculate_business_days(start, end) == 5
        
    def test_negative_range(self):
        """Test end before start gives negative"""
        start = datetime(2021, 1, 8)
        end = datetime(2021, 1, 4)
        assert calculate_business_days(start, end) == -4


class TestDateFormatting:
    """Tests for date formatting functions"""
    
    def test_parse_date(self):
        """Test parsing date string"""
        result = parse_date("2021-06-15")
        assert result.year == 2021
        assert result.month == 6
        assert result.day == 15
        
    def test_format_date(self):
        """Test formatting date object"""
        date = datetime(2021, 6, 15)
        result = format_date(date)
        assert result == "2021-06-15"
        
    def test_custom_format(self):
        """Test custom date format"""
        date = datetime(2021, 6, 15)
        result = format_date(date, "%d/%m/%Y")
        assert result == "15/06/2021"


class TestTimeAgo:
    """Tests for time_ago function"""
    
    def test_just_now(self):
        """Test recent time shows 'Just now'"""
        result = time_ago(datetime.now() - timedelta(seconds=30))
        assert result == "Just now"
        
    def test_minutes_ago(self):
        """Test minutes ago"""
        result = time_ago(datetime.now() - timedelta(minutes=5))
        assert "5 minutes ago" in result
        
    def test_hours_ago(self):
        """Test hours ago"""
        result = time_ago(datetime.now() - timedelta(hours=2))
        assert "2 hours ago" in result
        
    def test_days_ago(self):
        """Test days ago"""
        result = time_ago(datetime.now() - timedelta(days=3))
        assert "3 days ago" in result


# ============================================================================
# SYMBOL AND STRING SANITIZATION TESTS
# ============================================================================

class TestSanitizeSymbol:
    """Tests for sanitize_symbol function"""
    
    def test_valid_symbol(self):
        """Test valid symbol passes through"""
        assert sanitize_symbol("AAPL") == "AAPL"
        
    def test_lowercase_converted(self):
        """Test lowercase is uppercased"""
        assert sanitize_symbol("aapl") == "AAPL"
        
    def test_with_whitespace(self):
        """Test whitespace is stripped"""
        assert sanitize_symbol("  GOOG  ") == "GOOG"
        
    def test_empty_raises(self):
        """Test empty symbol raises"""
        with pytest.raises(ValueError, match="Empty symbol"):
            sanitize_symbol("")
            
    def test_too_long_raises(self):
        """Test symbol too long raises"""
        with pytest.raises(ValueError, match="Symbol too long"):
            sanitize_symbol("VERYLONGSYMBOL")
            
    def test_invalid_format_raises(self):
        """Test invalid format raises"""
        with pytest.raises(ValueError, match="Invalid symbol format"):
            sanitize_symbol("123")


class TestSanitizeString:
    """Tests for sanitize_string function"""
    
    def test_removes_dangerous_chars(self):
        """Test dangerous characters removed"""
        result = sanitize_string("<script>alert('xss')</script>")
        assert "<" not in result
        assert ">" not in result
        
    def test_strips_whitespace(self):
        """Test whitespace stripped"""
        result = sanitize_string("  hello  ")
        assert result == "hello"
        
    def test_handles_none(self):
        """Test None returns empty string"""
        assert sanitize_string(None) == ""
        
    def test_handles_non_string(self):
        """Test non-string converted"""
        assert sanitize_string(123) == "123"


class TestTruncateString:
    """Tests for truncate_string function"""
    
    def test_short_string_unchanged(self):
        """Test short string not truncated"""
        assert truncate_string("hello", 10) == "hello"
        
    def test_long_string_truncated(self):
        """Test long string truncated with suffix"""
        result = truncate_string("hello world", 8)
        assert len(result) <= 8
        assert result.endswith("...")
        
    def test_zero_length(self):
        """Test zero length returns empty"""
        assert truncate_string("hello", 0) == ""
        
    def test_custom_suffix(self):
        """Test custom suffix"""
        result = truncate_string("hello world", 10, suffix="++")
        assert result.endswith("++")


# ============================================================================
# VALIDATION TESTS
# ============================================================================

class TestValidateEmail:
    """Tests for validate_email function"""
    
    def test_valid_email(self):
        """Test valid email passes"""
        assert validate_email("user@example.com") is True
        
    def test_invalid_email(self):
        """Test invalid email fails"""
        assert validate_email("not-an-email") is False
        
    def test_missing_at(self):
        """Test missing @ fails"""
        assert validate_email("userexample.com") is False


class TestValidatePhone:
    """Tests for validate_phone function"""
    
    def test_valid_phone(self):
        """Test valid phone passes"""
        assert validate_phone("+1234567890") is True
        
    def test_with_spaces(self):
        """Test phone with spaces"""
        assert validate_phone("123 456 7890") is True
        
    def test_too_short(self):
        """Test too short fails"""
        assert validate_phone("123") is False


class TestValidateDecimalPrecision:
    """Tests for validate_decimal_precision function"""
    
    def test_within_precision(self):
        """Test value within precision"""
        assert validate_decimal_precision(10.12, max_places=2) is True
        
    def test_exceeds_precision(self):
        """Test value exceeds precision"""
        assert validate_decimal_precision(10.12345, max_places=2) is False


class TestValidateJsonSchema:
    """Tests for validate_json_schema function"""
    
    def test_valid_schema(self):
        """Test matching schema passes"""
        data = {"name": "John", "age": 30}
        schema = {"name": str, "age": int}
        assert validate_json_schema(data, schema) is True
        
    def test_missing_key(self):
        """Test missing key fails"""
        data = {"name": "John"}
        schema = {"name": str, "age": int}
        assert validate_json_schema(data, schema) is False
        
    def test_wrong_type(self):
        """Test wrong type fails"""
        data = {"name": "John", "age": "thirty"}
        schema = {"name": str, "age": int}
        assert validate_json_schema(data, schema) is False
        
    def test_non_dict_data(self):
        """Test non-dict data fails"""
        assert validate_json_schema("not a dict", {}) is False


# ============================================================================
# CURRENCY AND NUMBER FORMATTING TESTS
# ============================================================================

class TestFormatCurrency:
    """Tests for currency formatting functions"""
    
    def test_format_currency_usd(self):
        """Test USD formatting"""
        assert format_currency(1234.56, "USD") == "$1234.56"
        
    def test_format_currency_eur(self):
        """Test EUR formatting"""
        assert format_currency(1234.56, "EUR") == "€1234.56"
        
    def test_format_currency_simple(self):
        """Test simple currency format"""
        assert format_currency_simple(1234.56) == "$1,234.56"
        
    def test_format_currency_negative(self):
        """Test negative currency"""
        result = format_currency_simple(-1234.56)
        assert "-" in result


class TestFormatPercentage:
    """Tests for format_percentage function"""
    
    def test_basic_percentage(self):
        """Test basic percentage"""
        assert format_percentage(12.345) == "12.35%"
        
    def test_custom_precision(self):
        """Test custom precision"""
        assert format_percentage(12.345, decimal_places=1) == "12.3%"


class TestRoundDecimal:
    """Tests for round_decimal function"""
    
    def test_basic_rounding(self):
        """Test basic rounding"""
        assert round_decimal(3.14159, 2) == 3.14
        
    def test_string_input(self):
        """Test string input conversion"""
        assert round_decimal("3.14159", 2) == 3.14


class TestSafeDivision:
    """Tests for safe_division function"""
    
    def test_normal_division(self):
        """Test normal division"""
        assert safe_division(10, 2) == 5.0
        
    def test_divide_by_zero(self):
        """Test divide by zero returns default"""
        assert safe_division(10, 0) == 0
        
    def test_custom_default(self):
        """Test custom default on divide by zero"""
        assert safe_division(10, 0, default=-1) == -1


class TestClamp:
    """Tests for clamp function"""
    
    def test_within_range(self):
        """Test value within range unchanged"""
        assert clamp(5, 0, 10) == 5
        
    def test_below_min(self):
        """Test below min clamped"""
        assert clamp(-5, 0, 10) == 0
        
    def test_above_max(self):
        """Test above max clamped"""
        assert clamp(15, 0, 10) == 10


class TestNormalizeRange:
    """Tests for normalize_range function"""
    
    def test_basic_normalization(self):
        """Test basic normalization"""
        result = normalize_range(50, 0, 100, 0, 1)
        assert result == 0.5
        
    def test_same_range(self):
        """Test same old min/max returns new_min"""
        result = normalize_range(50, 50, 50, 0, 1)
        assert result == 0


class TestCalculatePercentage:
    """Tests for calculate_percentage function"""
    
    def test_basic_percentage(self):
        """Test basic percentage calculation"""
        assert calculate_percentage(25, 100) == 25.0
        
    def test_divide_by_zero(self):
        """Test zero whole returns 0"""
        assert calculate_percentage(25, 0) == 0


class TestIsNumber:
    """Tests for is_number function"""
    
    def test_integer(self):
        """Test integer is number"""
        assert is_number(42) is True
        
    def test_float(self):
        """Test float is number"""
        assert is_number(3.14) is True
        
    def test_string_number(self):
        """Test numeric string is number"""
        assert is_number("42") is True
        
    def test_non_number(self):
        """Test non-number returns False"""
        assert is_number("hello") is False


# ============================================================================
# DICT MANIPULATION TESTS
# ============================================================================

class TestDeepMergeDicts:
    """Tests for deep_merge_dicts function"""
    
    def test_simple_merge(self):
        """Test simple dict merge"""
        d1 = {"a": 1}
        d2 = {"b": 2}
        result = deep_merge_dicts(d1, d2)
        assert result == {"a": 1, "b": 2}
        
    def test_nested_merge(self):
        """Test nested dict merge"""
        d1 = {"a": {"x": 1}}
        d2 = {"a": {"y": 2}}
        result = deep_merge_dicts(d1, d2)
        assert result == {"a": {"x": 1, "y": 2}}
        
    def test_override(self):
        """Test value override"""
        d1 = {"a": 1}
        d2 = {"a": 2}
        result = deep_merge_dicts(d1, d2)
        assert result["a"] == 2


class TestFlattenDict:
    """Tests for flatten_dict function"""
    
    def test_simple_flatten(self):
        """Test simple flatten"""
        data = {"a": {"b": 1}}
        result = flatten_dict(data)
        assert result == {"a.b": 1}
        
    def test_multiple_levels(self):
        """Test multiple levels"""
        data = {"a": {"b": {"c": 1}}}
        result = flatten_dict(data)
        assert result == {"a.b.c": 1}


class TestUnflattenDict:
    """Tests for unflatten_dict function"""
    
    def test_simple_unflatten(self):
        """Test simple unflatten"""
        data = {"a.b": 1}
        result = unflatten_dict(data)
        assert result == {"a": {"b": 1}}


class TestGetNestedValue:
    """Tests for get_nested_value function"""
    
    def test_get_value(self):
        """Test getting nested value"""
        data = {"a": {"b": {"c": 42}}}
        assert get_nested_value(data, "a.b.c") == 42
        
    def test_missing_key(self):
        """Test missing key returns default"""
        data = {"a": 1}
        assert get_nested_value(data, "b.c", default="missing") == "missing"


class TestSetNestedValue:
    """Tests for set_nested_value function"""
    
    def test_set_value(self):
        """Test setting nested value"""
        data = {}
        set_nested_value(data, "a.b.c", 42)
        assert data == {"a": {"b": {"c": 42}}}


# ============================================================================
# LIST UTILITIES TESTS
# ============================================================================

class TestChunks:
    """Tests for chunks function"""
    
    def test_basic_chunks(self):
        """Test basic chunking"""
        result = list(chunks([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]
        
    def test_exact_chunks(self):
        """Test exact size chunks"""
        result = list(chunks([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]


class TestChunkList:
    """Tests for chunk_list function"""
    
    def test_basic_chunk(self):
        """Test basic list chunking"""
        result = list(chunk_list([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]


class TestRemoveDuplicates:
    """Tests for remove_duplicates function"""
    
    def test_removes_duplicates(self):
        """Test duplicates removed"""
        result = remove_duplicates([1, 2, 2, 3, 1])
        assert result == [1, 2, 3]
        
    def test_preserves_order(self):
        """Test order preserved"""
        result = remove_duplicates([3, 1, 2, 1, 3])
        assert result == [3, 1, 2]


class TestMergeLists:
    """Tests for merge_lists function"""
    
    def test_merge_two(self):
        """Test merging two lists"""
        result = merge_lists([1, 2], [3, 4])
        assert result == [1, 2, 3, 4]
        
    def test_merge_multiple(self):
        """Test merging multiple lists"""
        result = merge_lists([1], [2], [3])
        assert result == [1, 2, 3]


class TestIsEmpty:
    """Tests for is_empty function"""
    
    def test_none_is_empty(self):
        """Test None is empty"""
        assert is_empty(None) is True
        
    def test_empty_string(self):
        """Test empty string is empty"""
        assert is_empty("") is True
        
    def test_empty_list(self):
        """Test empty list is empty"""
        assert is_empty([]) is True
        
    def test_non_empty(self):
        """Test non-empty is not empty"""
        assert is_empty("hello") is False


# ============================================================================
# FILE OPERATIONS TESTS
# ============================================================================

class TestFileOperations:
    """Tests for file operations"""
    
    def test_file_exists(self):
        """Test file_exists function"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name
            
        try:
            assert file_exists(path) is True
            assert file_exists("/nonexistent/path") is False
        finally:
            os.unlink(path)
            
    def test_create_directory(self):
        """Test create_directory function"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new", "nested", "dir")
            create_directory(new_dir)
            assert os.path.isdir(new_dir)
            
    def test_read_write_file(self):
        """Test read and write file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            write_file(path, "hello world")
            content = read_file(path)
            assert content == "hello world"
            
    def test_get_file_size(self):
        """Test get_file_size function"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello")
            path = f.name
            
        try:
            assert get_file_size(path) == 5
        finally:
            os.unlink(path)


# ============================================================================
# CASE CONVERSION TESTS
# ============================================================================

class TestCaseConversion:
    """Tests for case conversion functions"""
    
    def test_to_snake_case(self):
        """Test converting to snake_case"""
        assert to_snake_case("camelCase") == "camel_case"
        assert to_snake_case("PascalCase") == "pascal_case"
        
    def test_to_camel_case(self):
        """Test converting to camelCase"""
        assert to_camel_case("snake_case") == "snakeCase"


# ============================================================================
# DECORATOR TESTS
# ============================================================================

class TestCacheResult:
    """Tests for cache_result decorator"""
    
    def test_caches_result(self):
        """Test result is cached"""
        call_count = [0]
        
        @cache_result
        def expensive_func(x):
            call_count[0] += 1
            return x * 2
        
        assert expensive_func(5) == 10
        assert expensive_func(5) == 10
        assert call_count[0] == 1  # Only called once


class TestMemoize:
    """Tests for memoize decorator"""
    
    def test_memoizes(self):
        """Test memoization"""
        call_count = [0]
        
        @memoize
        def add(a, b):
            call_count[0] += 1
            return a + b
        
        assert add(1, 2) == 3
        assert add(1, 2) == 3
        assert call_count[0] == 1


class TestSingleton:
    """Tests for singleton decorator"""
    
    def test_singleton(self):
        """Test singleton behavior"""
        @singleton
        class MyClass:
            def __init__(self):
                self.value = 0
        
        obj1 = MyClass()
        obj1.value = 42
        obj2 = MyClass()
        
        assert obj1 is obj2
        assert obj2.value == 42


class TestTimer:
    """Tests for timer decorator"""
    
    def test_timer_logs(self):
        """Test timer decorator works"""
        @timer
        def slow_func():
            return "done"
        
        result = slow_func()
        assert result == "done"


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestGenerateUuid:
    """Tests for generate_uuid function"""
    
    def test_generates_uuid(self):
        """Test UUID generation"""
        uuid1 = generate_uuid()
        uuid2 = generate_uuid()
        
        assert len(uuid1) == 36
        assert uuid1 != uuid2


class TestHashPassword:
    """Tests for password hashing"""
    
    def test_hash_and_verify(self):
        """Test hashing and verification"""
        password = "secret123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
        assert verify_password("wrong", hashed) is False


class TestConvertUnits:
    """Tests for convert_units function"""
    
    def test_inches_to_cm(self):
        """Test inches to cm"""
        result = convert_units(1, "inches", "cm")
        assert result == 2.54
        
    def test_same_unit(self):
        """Test same unit returns value"""
        result = convert_units(10, "cm", "cm")
        assert result == 10


class TestParseConfig:
    """Tests for parse_config function"""
    
    def test_json_config(self):
        """Test parsing JSON config"""
        config = '{"key": "value"}'
        result = parse_config(config)
        assert result == {"key": "value"}
        
    def test_key_value_config(self):
        """Test parsing key=value config"""
        config = "key1=value1\nkey2=value2"
        result = parse_config(config)
        assert result == {"key1": "value1", "key2": "value2"}


class TestEnvironmentVariable:
    """Tests for environment_variable function"""
    
    def test_existing_var(self):
        """Test getting existing variable"""
        os.environ["TEST_VAR"] = "test_value"
        try:
            assert environment_variable("TEST_VAR") == "test_value"
        finally:
            del os.environ["TEST_VAR"]
            
    def test_missing_var(self):
        """Test missing variable returns default"""
        result = environment_variable("NONEXISTENT_VAR", "default")
        assert result == "default"


class TestSafeImport:
    """Tests for safe_import function"""
    
    def test_existing_module(self):
        """Test importing existing module"""
        result = safe_import("os")
        assert result is not None
        
    def test_nonexistent_module(self):
        """Test importing nonexistent module"""
        result = safe_import("nonexistent_module_xyz")
        assert result is None


class TestDynamicImport:
    """Tests for dynamic_import function"""
    
    def test_valid_import(self):
        """Test valid dynamic import"""
        result = dynamic_import("os.path", "join")
        assert result is not None
        
    def test_invalid_import(self):
        """Test invalid import returns None"""
        result = dynamic_import("nonexistent", "class")
        assert result is None


# ============================================================================
# RATE LIMIT TESTS  
# ============================================================================

class TestRateLimit:
    """Tests for rate_limit decorator"""
    
    @pytest.mark.asyncio
    async def test_async_rate_limit(self):
        """Test rate limiting async function"""
        call_times = []
        
        @rate_limit(calls_per_second=100)  # High rate for fast test
        async def limited_func():
            call_times.append(datetime.now())
            return "ok"
        
        # Make a few calls
        for _ in range(3):
            await limited_func()
        
        assert len(call_times) == 3
        
    def test_sync_rate_limit(self):
        """Test rate limiting sync function"""
        @rate_limit(calls_per_second=100)
        def limited_sync():
            return "ok"
        
        result = limited_sync()
        assert result == "ok"
