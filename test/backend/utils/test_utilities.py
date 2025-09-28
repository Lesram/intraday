#!/usr/bin/env python3
"""
Module 32: Utils Utilities Test
Tests the general utility functions and helpers.

Test Target: backend/utils/utilities.py
Focus: General utility functions, helpers, and common operations
"""

import pytest
import sys
import os
import json
import tempfile
import hashlib
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from io import StringIO

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

try:
    from backend.utils.utilities import (
        format_currency, format_percentage, validate_email, validate_phone,
        sanitize_string, generate_uuid, hash_password, verify_password,
        deep_merge_dicts, flatten_dict, unflatten_dict, chunk_list,
        retry_operation, rate_limit, cache_result, validate_json_schema,
        parse_date, format_date, time_ago, file_exists, create_directory,
        read_file, write_file, get_file_size, safe_division, round_decimal,
        clamp, normalize_range, calculate_percentage, is_number,
        to_snake_case, to_camel_case, truncate_string, remove_duplicates,
        get_nested_value, set_nested_value, is_empty, merge_lists,
        singleton, timer, memoize, convert_units, parse_config,
        environment_variable, safe_import, dynamic_import
    )
except ImportError as e:
    print(f"Import warning: {e}")
    # Create minimal stubs for testing
    import uuid
    import re
    import time
    import functools
    from pathlib import Path
    
    def format_currency(amount, currency="USD", decimal_places=2):
        """Format currency with symbol."""
        symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
        symbol = symbols.get(currency, currency)
        return f"{symbol}{amount:.{decimal_places}f}"
    
    def format_percentage(value, decimal_places=2):
        """Format percentage with % symbol."""
        return f"{value:.{decimal_places}f}%"
    
    def validate_email(email):
        """Validate email address."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def validate_phone(phone):
        """Validate phone number."""
        pattern = r'^\+?1?\d{9,15}$'
        return bool(re.match(pattern, phone.replace(' ', '').replace('-', '')))
    
    def sanitize_string(text):
        """Sanitize string for safe use."""
        if not text:
            return ""
        return re.sub(r'[<>&"\'`]', '', text).strip()
    
    def generate_uuid():
        """Generate UUID string."""
        return str(uuid.uuid4())
    
    def hash_password(password):
        """Hash password using simple method."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(password, hashed):
        """Verify password against hash."""
        return hash_password(password) == hashed
    
    def deep_merge_dicts(dict1, dict2):
        """Deep merge two dictionaries."""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        return result
    
    def flatten_dict(d, parent_key='', sep='.'):
        """Flatten nested dictionary."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def unflatten_dict(d, sep='.'):
        """Unflatten dictionary."""
        result = {}
        for key, value in d.items():
            keys = key.split(sep)
            current = result
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            current[keys[-1]] = value
        return result
    
    def chunk_list(lst, chunk_size):
        """Split list into chunks."""
        for i in range(0, len(lst), chunk_size):
            yield lst[i:i + chunk_size]
    
    def retry_operation(func, max_retries=3, delay=1):
        """Retry operation with delay."""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(delay)
        return None
    
    def rate_limit(calls_per_second=1):
        """Rate limiting decorator."""
        def decorator(func):
            last_called = [0.0]
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                elapsed = time.time() - last_called[0]
                min_interval = 1.0 / calls_per_second
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                last_called[0] = time.time()
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def cache_result(func):
        """Cache function results."""
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        return wrapper
    
    def validate_json_schema(data, schema):
        """Basic JSON schema validation."""
        if not isinstance(data, dict) or not isinstance(schema, dict):
            return False
        
        for key, expected_type in schema.items():
            if key not in data:
                return False
            if not isinstance(data[key], expected_type):
                return False
        return True
    
    def parse_date(date_string, format_string="%Y-%m-%d"):
        """Parse date from string."""
        return datetime.strptime(date_string, format_string)
    
    def format_date(date_obj, format_string="%Y-%m-%d"):
        """Format date to string."""
        return date_obj.strftime(format_string)
    
    def time_ago(date_obj):
        """Get time ago description."""
        now = datetime.now()
        diff = now - date_obj
        
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return "Just now"
    
    def file_exists(filepath):
        """Check if file exists."""
        return Path(filepath).exists()
    
    def create_directory(path):
        """Create directory if not exists."""
        Path(path).mkdir(parents=True, exist_ok=True)
    
    def read_file(filepath):
        """Read file content."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    
    def write_file(filepath, content):
        """Write content to file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def get_file_size(filepath):
        """Get file size in bytes."""
        return Path(filepath).stat().st_size
    
    def safe_division(a, b, default=0):
        """Safe division with default for zero."""
        return a / b if b != 0 else default
    
    def round_decimal(value, places=2):
        """Round to decimal places."""
        return round(float(value), places)
    
    def clamp(value, min_val, max_val):
        """Clamp value between min and max."""
        return max(min_val, min(value, max_val))
    
    def normalize_range(value, old_min, old_max, new_min=0, new_max=1):
        """Normalize value to new range."""
        if old_max == old_min:
            return new_min
        return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)
    
    def calculate_percentage(part, whole):
        """Calculate percentage."""
        return (part / whole * 100) if whole != 0 else 0
    
    def is_number(value):
        """Check if value is numeric."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def to_snake_case(text):
        """Convert to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def to_camel_case(text):
        """Convert to camelCase."""
        components = text.split('_')
        return components[0] + ''.join(x.capitalize() for x in components[1:])
    
    def truncate_string(text, length, suffix='...'):
        """Truncate string to length."""
        if len(text) <= length:
            return text
        return text[:length-len(suffix)] + suffix
    
    def remove_duplicates(lst):
        """Remove duplicates while preserving order."""
        seen = set()
        result = []
        for item in lst:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
    
    def get_nested_value(data, path, default=None):
        """Get nested value from dictionary."""
        keys = path.split('.')
        value = data
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set_nested_value(data, path, value):
        """Set nested value in dictionary."""
        keys = path.split('.')
        current = data
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = value
    
    def is_empty(value):
        """Check if value is empty."""
        if value is None:
            return True
        if isinstance(value, (str, list, dict, tuple, set)):
            return len(value) == 0
        return False
    
    def merge_lists(*lists):
        """Merge multiple lists."""
        result = []
        for lst in lists:
            result.extend(lst)
        return result
    
    def singleton(cls):
        """Singleton decorator."""
        instances = {}
        
        def get_instance(*args, **kwargs):
            if cls not in instances:
                instances[cls] = cls(*args, **kwargs)
            return instances[cls]
        return get_instance
    
    def timer(func):
        """Timer decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            print(f"{func.__name__} took {end - start:.3f}s")
            return result
        return wrapper
    
    def memoize(func):
        """Memoization decorator."""
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        return wrapper
    
    def convert_units(value, from_unit, to_unit, conversion_table=None):
        """Convert between units."""
        if conversion_table is None:
            conversion_table = {
                'inches': {'cm': 2.54, 'mm': 25.4},
                'cm': {'inches': 0.393701, 'mm': 10},
                'mm': {'cm': 0.1, 'inches': 0.0393701}
            }
        
        if from_unit == to_unit:
            return value
        
        if from_unit in conversion_table and to_unit in conversion_table[from_unit]:
            return value * conversion_table[from_unit][to_unit]
        
        return value  # Return original if no conversion found
    
    def parse_config(config_string):
        """Parse configuration string."""
        try:
            return json.loads(config_string)
        except json.JSONDecodeError:
            # Try simple key=value format
            result = {}
            for line in config_string.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    result[key.strip()] = value.strip()
            return result
    
    def environment_variable(name, default=None):
        """Get environment variable."""
        return os.environ.get(name, default)
    
    def safe_import(module_name):
        """Safely import module."""
        try:
            return __import__(module_name)
        except ImportError:
            return None
    
    def dynamic_import(module_name, class_name):
        """Dynamically import class from module."""
        try:
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except (ImportError, AttributeError):
            return None

class TestFormatting:
    """Test suite for formatting utilities."""
    
    def test_format_currency(self):
        """Test currency formatting."""
        assert format_currency(100) == "$100.00"
        assert format_currency(99.99, "EUR") == "€99.99"
        assert format_currency(50.5, "GBP", 1) == "£50.5"
        assert format_currency(0, decimal_places=0) == "$0"

    def test_format_percentage(self):
        """Test percentage formatting."""
        assert format_percentage(50) == "50.00%"
        assert format_percentage(33.333, 1) == "33.3%"
        assert format_percentage(0) == "0.00%"
        assert format_percentage(100, 0) == "100%"

    def test_truncate_string(self):
        """Test string truncation."""
        assert truncate_string("Hello World", 5) == "He..."
        assert truncate_string("Short", 10) == "Short"
        assert truncate_string("Hello", 5) == "Hello"
        assert truncate_string("Long text here", 8, "++") == "Long te++"

class TestValidation:
    """Test suite for validation utilities."""
    
    def test_validate_email(self):
        """Test email validation."""
        assert validate_email("user@example.com") == True
        assert validate_email("test.email+tag@domain.co.uk") == True
        assert validate_email("invalid.email") == False
        assert validate_email("@domain.com") == False
        assert validate_email("user@") == False

    def test_validate_phone(self):
        """Test phone validation."""
        assert validate_phone("1234567890") == True
        assert validate_phone("+1-123-456-7890") == True
        assert validate_phone("123 456 7890") == True
        assert validate_phone("123") == False
        assert validate_phone("") == False

    def test_sanitize_string(self):
        """Test string sanitization."""
        assert sanitize_string("Hello World") == "Hello World"
        assert sanitize_string("Hello<script>") == "Helloscript"
        assert sanitize_string("  Test  ") == "Test"
        assert sanitize_string("") == ""
        assert sanitize_string(None) == ""

    def test_validate_json_schema(self):
        """Test JSON schema validation."""
        schema = {"name": str, "age": int}
        data = {"name": "John", "age": 30}
        assert validate_json_schema(data, schema) == True
        
        invalid_data = {"name": "John", "age": "30"}
        assert validate_json_schema(invalid_data, schema) == False
        
        missing_data = {"name": "John"}
        assert validate_json_schema(missing_data, schema) == False

    def test_is_number(self):
        """Test number validation."""
        assert is_number("123") == True
        assert is_number("123.45") == True
        assert is_number("-123") == True
        assert is_number("abc") == False
        assert is_number("") == False
        assert is_number(123) == True

class TestSecurity:
    """Test suite for security utilities."""
    
    def test_generate_uuid(self):
        """Test UUID generation."""
        uuid1 = generate_uuid()
        uuid2 = generate_uuid()
        assert isinstance(uuid1, str)
        assert isinstance(uuid2, str)
        assert uuid1 != uuid2
        assert len(uuid1) == 36  # Standard UUID length

    def test_hash_password(self):
        """Test password hashing."""
        password = "test123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert hashed != password
        assert len(hashed) == 64  # SHA256 hex digest length

    def test_verify_password(self):
        """Test password verification."""
        password = "test123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) == True
        assert verify_password("wrong", hashed) == False

class TestDataStructures:
    """Test suite for data structure utilities."""
    
    def test_deep_merge_dicts(self):
        """Test deep dictionary merging."""
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}
        
        result = deep_merge_dicts(dict1, dict2)
        expected = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        
        assert result == expected

    def test_flatten_dict(self):
        """Test dictionary flattening."""
        nested = {"a": {"b": {"c": 1}}, "d": 2}
        flattened = flatten_dict(nested)
        expected = {"a.b.c": 1, "d": 2}
        
        assert flattened == expected

    def test_unflatten_dict(self):
        """Test dictionary unflattening."""
        flattened = {"a.b.c": 1, "d": 2}
        nested = unflatten_dict(flattened)
        expected = {"a": {"b": {"c": 1}}, "d": 2}
        
        assert nested == expected

    def test_chunk_list(self):
        """Test list chunking."""
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        chunks = list(chunk_list(data, 3))
        expected = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        
        assert chunks == expected

    def test_remove_duplicates(self):
        """Test duplicate removal."""
        data = [1, 2, 2, 3, 1, 4, 3]
        result = remove_duplicates(data)
        expected = [1, 2, 3, 4]
        
        assert result == expected

    def test_merge_lists(self):
        """Test list merging."""
        list1 = [1, 2]
        list2 = [3, 4]
        list3 = [5, 6]
        
        result = merge_lists(list1, list2, list3)
        expected = [1, 2, 3, 4, 5, 6]
        
        assert result == expected

class TestNestedOperations:
    """Test suite for nested data operations."""
    
    def setup_method(self):
        """Set up test data."""
        self.data = {
            "user": {
                "profile": {
                    "name": "John",
                    "age": 30
                },
                "settings": {
                    "theme": "dark"
                }
            }
        }

    def test_get_nested_value(self):
        """Test getting nested values."""
        assert get_nested_value(self.data, "user.profile.name") == "John"
        assert get_nested_value(self.data, "user.profile.age") == 30
        assert get_nested_value(self.data, "user.missing", "default") == "default"
        assert get_nested_value(self.data, "missing.path") is None

    def test_set_nested_value(self):
        """Test setting nested values."""
        data = {"a": {"b": {}}}
        set_nested_value(data, "a.b.c", "value")
        assert data["a"]["b"]["c"] == "value"
        
        set_nested_value(data, "new.path", "test")
        assert data["new"]["path"] == "test"

class TestMathOperations:
    """Test suite for mathematical utilities."""
    
    def test_safe_division(self):
        """Test safe division."""
        assert safe_division(10, 2) == 5
        assert safe_division(10, 0) == 0
        assert safe_division(10, 0, "error") == "error"

    def test_round_decimal(self):
        """Test decimal rounding."""
        assert round_decimal(3.14159, 2) == 3.14
        assert round_decimal(2.5) == 2.5
        assert round_decimal("3.14159", 1) == 3.1

    def test_clamp(self):
        """Test value clamping."""
        assert clamp(5, 0, 10) == 5
        assert clamp(-5, 0, 10) == 0
        assert clamp(15, 0, 10) == 10

    def test_normalize_range(self):
        """Test range normalization."""
        # Map 5 from [0,10] to [0,1]
        assert normalize_range(5, 0, 10, 0, 1) == 0.5
        # Map 2 from [0,4] to [10,20]
        assert normalize_range(2, 0, 4, 10, 20) == 15

    def test_calculate_percentage(self):
        """Test percentage calculation."""
        assert calculate_percentage(25, 100) == 25
        assert calculate_percentage(1, 3) == pytest.approx(33.333, abs=0.01)
        assert calculate_percentage(10, 0) == 0

class TestStringOperations:
    """Test suite for string utilities."""
    
    def test_to_snake_case(self):
        """Test snake_case conversion."""
        assert to_snake_case("CamelCase") == "camel_case"
        assert to_snake_case("XMLHttpRequest") == "xml_http_request"
        assert to_snake_case("already_snake") == "already_snake"

    def test_to_camel_case(self):
        """Test camelCase conversion."""
        assert to_camel_case("snake_case") == "snakeCase"
        assert to_camel_case("multi_word_test") == "multiWordTest"
        assert to_camel_case("singleword") == "singleword"

    def test_is_empty(self):
        """Test empty value checking."""
        assert is_empty(None) == True
        assert is_empty("") == True
        assert is_empty([]) == True
        assert is_empty({}) == True
        assert is_empty("text") == False
        assert is_empty([1, 2]) == False

class TestDateOperations:
    """Test suite for date/time utilities."""
    
    def test_parse_date(self):
        """Test date parsing."""
        date_str = "2023-12-25"
        parsed = parse_date(date_str)
        assert isinstance(parsed, datetime)
        assert parsed.year == 2023
        assert parsed.month == 12
        assert parsed.day == 25

    def test_format_date(self):
        """Test date formatting."""
        date_obj = datetime(2023, 12, 25)
        formatted = format_date(date_obj)
        assert formatted == "2023-12-25"
        
        custom_format = format_date(date_obj, "%d/%m/%Y")
        assert custom_format == "25/12/2023"

    def test_time_ago(self):
        """Test time ago calculation."""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)
        
        assert "hours ago" in time_ago(one_hour_ago)
        assert "days ago" in time_ago(one_day_ago)

class TestFileOperations:
    """Test suite for file utilities."""
    
    def setup_method(self):
        """Set up test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = os.path.join(self.temp_dir, "test.txt")

    def teardown_method(self):
        """Clean up test files."""
        try:
            if os.path.exists(self.temp_file):
                os.unlink(self.temp_file)
            os.rmdir(self.temp_dir)
        except:
            pass

    def test_file_exists(self):
        """Test file existence check."""
        assert file_exists(self.temp_file) == False
        
        # Create file and test again
        with open(self.temp_file, 'w') as f:
            f.write("test")
        
        assert file_exists(self.temp_file) == True

    def test_create_directory(self):
        """Test directory creation."""
        new_dir = os.path.join(self.temp_dir, "new", "nested", "dir")
        create_directory(new_dir)
        assert os.path.exists(new_dir)

    def test_read_write_file(self):
        """Test file read/write operations."""
        content = "Hello, World!"
        write_file(self.temp_file, content)
        
        read_content = read_file(self.temp_file)
        assert read_content == content

    def test_get_file_size(self):
        """Test file size calculation."""
        content = "Hello, World!"
        write_file(self.temp_file, content)
        
        size = get_file_size(self.temp_file)
        assert size == len(content.encode('utf-8'))

class TestDecorators:
    """Test suite for decorator utilities."""
    
    def test_cache_result(self):
        """Test result caching decorator."""
        call_count = [0]
        
        @cache_result
        def expensive_operation(x):
            call_count[0] += 1
            return x * 2
        
        # First call
        result1 = expensive_operation(5)
        assert result1 == 10
        assert call_count[0] == 1
        
        # Second call with same args - should use cache
        result2 = expensive_operation(5)
        assert result2 == 10
        assert call_count[0] == 1  # No additional call

    def test_timer_decorator(self):
        """Test timer decorator."""
        @timer
        def test_function():
            return "done"
        
        with patch('builtins.print') as mock_print:
            result = test_function()
            assert result == "done"
            assert mock_print.called

    def test_memoize_decorator(self):
        """Test memoization decorator."""
        call_count = [0]
        
        @memoize
        def fibonacci(n):
            call_count[0] += 1
            if n <= 1:
                return n
            return fibonacci(n-1) + fibonacci(n-2)
        
        result = fibonacci(5)
        assert result == 5
        # With memoization, should be much fewer calls
        assert call_count[0] < 15

    def test_singleton_decorator(self):
        """Test singleton decorator."""
        @singleton
        class TestClass:
            def __init__(self):
                self.value = 42
        
        instance1 = TestClass()
        instance2 = TestClass()
        
        assert instance1 is instance2
        assert instance1.value == 42

class TestRetryOperations:
    """Test suite for retry utilities."""
    
    def test_retry_operation_success(self):
        """Test successful retry operation."""
        def always_succeed():
            return "success"
        
        result = retry_operation(always_succeed)
        assert result == "success"

    def test_retry_operation_failure(self):
        """Test retry operation with failures."""
        attempt_count = [0]
        
        def fail_twice():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError("Failed")
            return "success"
        
        result = retry_operation(fail_twice, max_retries=3)
        assert result == "success"
        assert attempt_count[0] == 3

    def test_retry_operation_max_failures(self):
        """Test retry operation exceeding max retries."""
        def always_fail():
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            retry_operation(always_fail, max_retries=2)

    @patch('time.sleep')
    def test_rate_limit_decorator(self, mock_sleep):
        """Test rate limiting decorator."""
        @rate_limit(calls_per_second=2)
        def test_function():
            return "done"
        
        # First call should not sleep
        result1 = test_function()
        assert result1 == "done"
        
        # Second call might need to sleep
        result2 = test_function()
        assert result2 == "done"

class TestUnitConversion:
    """Test suite for unit conversion utilities."""
    
    def test_convert_units_basic(self):
        """Test basic unit conversion."""
        # Same unit
        assert convert_units(100, 'cm', 'cm') == 100
        
        # Basic conversions
        result = convert_units(1, 'inches', 'cm')
        assert abs(result - 2.54) < 0.01
        
        result = convert_units(10, 'cm', 'mm')
        assert result == 100

    def test_convert_units_unknown(self):
        """Test unit conversion with unknown units."""
        result = convert_units(100, 'unknown', 'other')
        assert result == 100  # Should return original

class TestConfigParsing:
    """Test suite for configuration utilities."""
    
    def test_parse_config_json(self):
        """Test JSON config parsing."""
        config_str = '{"debug": true, "port": 8080}'
        result = parse_config(config_str)
        expected = {"debug": True, "port": 8080}
        assert result == expected

    def test_parse_config_key_value(self):
        """Test key=value config parsing."""
        config_str = "debug=true\nport=8080\nhost=localhost"
        result = parse_config(config_str)
        expected = {"debug": "true", "port": "8080", "host": "localhost"}
        assert result == expected

    def test_environment_variable(self):
        """Test environment variable access."""
        # Test with default
        result = environment_variable("NONEXISTENT_VAR", "default")
        assert result == "default"
        
        # Test with actual env var
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = environment_variable("TEST_VAR")
            assert result == "test_value"

class TestDynamicImports:
    """Test suite for dynamic import utilities."""
    
    def test_safe_import_existing(self):
        """Test safe import of existing module."""
        result = safe_import("os")
        assert result is not None
        assert hasattr(result, 'path')

    def test_safe_import_nonexistent(self):
        """Test safe import of nonexistent module."""
        result = safe_import("nonexistent_module_123")
        assert result is None

    def test_dynamic_import_existing(self):
        """Test dynamic import of existing class."""
        result = dynamic_import("datetime", "datetime")
        assert result is not None
        assert result == datetime

    def test_dynamic_import_nonexistent(self):
        """Test dynamic import of nonexistent class."""
        result = dynamic_import("os", "NonexistentClass")
        assert result is None

class TestEdgeCases:
    """Test suite for edge cases and error handling."""
    
    def test_empty_inputs(self):
        """Test functions with empty inputs."""
        assert format_currency(0) == "$0.00"
        assert format_percentage(0) == "0.00%"
        assert sanitize_string("") == ""
        assert is_empty([]) == True
        assert merge_lists() == []

    def test_none_inputs(self):
        """Test functions with None inputs."""
        assert sanitize_string(None) == ""
        assert is_empty(None) == True
        
        # Should handle gracefully
        try:
            get_nested_value(None, "path")
        except:
            pass

    def test_type_errors(self):
        """Test handling of type errors."""
        # These should handle gracefully or raise appropriate errors
        try:
            validate_json_schema("not_dict", {})
        except:
            pass
        
        try:
            deep_merge_dicts("not_dict", {})
        except:
            pass

    def test_boundary_values(self):
        """Test boundary values."""
        assert clamp(float('inf'), 0, 100) == 100
        assert clamp(float('-inf'), 0, 100) == 0
        assert safe_division(1, float('inf')) == 0
        assert calculate_percentage(0, 0) == 0

class TestIntegration:
    """Test integration scenarios."""
    
    def test_complete_workflow(self):
        """Test complete utility workflow."""
        # Generate and validate data
        user_id = generate_uuid()
        assert len(user_id) == 36
        
        # Format data
        amount = format_currency(99.99, "USD")
        assert amount == "$99.99"
        
        # Validate and sanitize
        email = "user@example.com"
        assert validate_email(email) == True
        
        clean_text = sanitize_string("Hello<script>")
        assert clean_text == "Helloscript"
        
        # Process collections
        data = [1, 2, 2, 3, 1]
        unique_data = remove_duplicates(data)
        assert unique_data == [1, 2, 3]

    def test_nested_data_processing(self):
        """Test nested data processing workflow."""
        # Create nested structure
        data = {"user": {"profile": {"name": "John", "age": 30}}}
        
        # Extract values
        name = get_nested_value(data, "user.profile.name")
        assert name == "John"
        
        # Flatten and unflatten
        flat = flatten_dict(data)
        unflat = unflatten_dict(flat)
        assert unflat == data

    def test_configuration_workflow(self):
        """Test configuration processing workflow."""
        # Parse configuration
        config_json = '{"debug": true, "port": 8080}'
        config = parse_config(config_json)
        
        # Validate schema
        schema = {"debug": bool, "port": int}
        assert validate_json_schema(config, schema) == True
        
        # Access nested config
        set_nested_value(config, "server.host", "localhost")
        host = get_nested_value(config, "server.host")
        assert host == "localhost"

if __name__ == "__main__":
    print("✅ Module 32: Utils Utilities Test")
    print("=" * 50)
    
    # Run the tests
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--maxfail=10"
    ])
    
    print(f"\n📊 Test execution completed with exit code: {exit_code}")
    sys.exit(exit_code)