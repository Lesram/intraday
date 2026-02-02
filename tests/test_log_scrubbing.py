"""
Test PII/Secret Log Scrubbing.

Tests the structlog processor that masks sensitive data
to prevent accidental exposure of secrets and PII in logs.
"""

import pytest

from backend.utils.logger import (
    MASK,
    PARTIAL_MASK,
    _mask_value,
    _scrub_dict,
    _scrub_list,
    _scrub_string,
    scrub_sensitive_data,
)


class TestMaskValue:
    """Test value masking utility."""

    def test_short_value_fully_masked(self):
        """Short values are fully masked."""
        assert _mask_value("abc123") == MASK
        assert _mask_value("12345678") == MASK

    def test_long_value_partially_masked(self):
        """Long values show first/last chars."""
        result = _mask_value("my_super_secret_api_key_123")
        assert result.startswith("my")
        assert result.endswith("23")
        assert PARTIAL_MASK in result


class TestScrubString:
    """Test string pattern scrubbing."""

    def test_api_key_pattern(self):
        """API key patterns are masked."""
        text = "Using api_key=abc123xyz789secret for auth"
        result = _scrub_string(text)
        assert "abc123xyz789secret" not in result
        assert MASK in result

    def test_bearer_token(self):
        """Bearer tokens are masked."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
        result = _scrub_string(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_jwt_token_pattern(self):
        """JWT tokens are masked."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.dGVzdHNpZ25hdHVyZQ"
        text = f"Token: {jwt}"
        result = _scrub_string(text)
        assert jwt not in result

    def test_password_pattern(self):
        """Password patterns are masked."""
        text = "Login with password=MySuperSecretPass123!"
        result = _scrub_string(text)
        assert "MySuperSecretPass123!" not in result
        assert MASK in result

    def test_aws_key_pattern(self):
        """AWS access keys are masked."""
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = _scrub_string(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_email_partial_mask(self):
        """Email addresses are partially masked."""
        text = "Contact: user@example.com for support"
        result = _scrub_string(text)
        assert "user@" not in result
        assert "@example.com" in result  # Domain preserved
        assert "[REDACTED]" in result

    def test_credit_card_pattern(self):
        """Credit card numbers are masked."""
        text = "Card: 4111-1111-1111-1111"
        result = _scrub_string(text)
        assert "4111-1111-1111-1111" not in result

    def test_ssn_pattern(self):
        """SSN patterns are masked."""
        text = "SSN: 123-45-6789"
        result = _scrub_string(text)
        assert "123-45-6789" not in result

    def test_alpaca_key_pattern(self):
        """Alpaca API keys are masked."""
        text = "Alpaca key: PKABCDEF12345678901234"
        result = _scrub_string(text)
        assert "PKABCDEF12345678901234" not in result

    def test_generic_secret_pattern(self):
        """Generic secret patterns are masked."""
        text = "secret=verylongsecretvalue12345678"
        result = _scrub_string(text)
        assert "verylongsecretvalue12345678" not in result

    def test_non_sensitive_preserved(self):
        """Non-sensitive text is preserved."""
        text = "Order AAPL 100 shares at market price"
        result = _scrub_string(text)
        assert result == text


class TestScrubDict:
    """Test dictionary scrubbing."""

    def test_sensitive_field_names(self):
        """Sensitive field names have values masked."""
        data = {
            "password": "mysecret123",
            "api_key": "pk_test_abc123xyz",
            "username": "john_doe",
        }
        result = _scrub_dict(data)
        
        assert "mysecret123" not in str(result)
        assert "pk_test_abc123xyz" not in str(result)
        assert result["username"] == "john_doe"  # Non-sensitive preserved

    def test_nested_dict_scrubbing(self):
        """Nested dictionaries are scrubbed."""
        data = {
            "config": {
                "auth": {
                    "token": "secret_token_value",
                    "endpoint": "https://api.example.com",
                }
            }
        }
        result = _scrub_dict(data)
        
        assert "secret_token_value" not in str(result)
        assert result["config"]["auth"]["endpoint"] == "https://api.example.com"

    def test_list_in_dict_scrubbed(self):
        """Lists within dicts are scrubbed."""
        data = {
            "credentials": ["password=secret1", "token=secret2"],
            "symbols": ["AAPL", "GOOGL"],
        }
        result = _scrub_dict(data)
        
        assert "secret1" not in str(result)
        assert "secret2" not in str(result)
        assert "AAPL" in str(result)

    def test_mixed_case_field_names(self):
        """Field names are case-insensitive."""
        data = {
            "Password": "secret1",
            "API_KEY": "secret2",
            "Api-Secret": "secret3",
        }
        result = _scrub_dict(data)
        
        assert "secret1" not in str(result)
        assert "secret2" not in str(result)
        # Note: Api-Secret becomes api_secret in comparison


class TestScrubList:
    """Test list scrubbing."""

    def test_string_items_scrubbed(self):
        """String items in lists are scrubbed."""
        data = ["normal", "password=secret123", "also normal"]
        result = _scrub_list(data)
        
        assert "secret123" not in str(result)
        assert "normal" in result
        assert "also normal" in result

    def test_dict_items_scrubbed(self):
        """Dict items in lists are scrubbed."""
        data = [{"token": "secret_value"}, {"name": "test"}]
        result = _scrub_list(data)
        
        assert "secret_value" not in str(result)
        assert result[1]["name"] == "test"


class TestScrubSensitiveDataProcessor:
    """Test the structlog processor function."""

    def test_processor_returns_scrubbed_dict(self):
        """Processor returns scrubbed event dict."""
        import logging
        
        event_dict = {
            "event": "user_login",
            "password": "user_password_123",
            "username": "testuser",
        }
        
        result = scrub_sensitive_data(
            logging.getLogger("test"),
            "info",
            event_dict
        )
        
        assert "user_password_123" not in str(result)
        assert result["username"] == "testuser"
        assert result["event"] == "user_login"

    def test_processor_handles_complex_events(self):
        """Processor handles complex nested events."""
        import logging
        
        event_dict = {
            "event": "api_call",
            "request": {
                "headers": {
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"
                },
                "body": {"api_key": "secret_api_key_123"}
            },
            "response": {"status": 200}
        }
        
        result = scrub_sensitive_data(
            logging.getLogger("test"),
            "info",
            event_dict
        )
        
        assert "eyJhbGciOiJIUzI1NiJ9" not in str(result)
        assert "secret_api_key_123" not in str(result)
        assert result["response"]["status"] == 200


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_values(self):
        """Empty values are handled."""
        data = {"password": "", "token": None}
        result = _scrub_dict(data)
        assert result["password"] == MASK
        assert result["token"] == MASK

    def test_non_string_values(self):
        """Non-string values are preserved."""
        data = {
            "count": 42,
            "price": 123.45,
            "enabled": True,
            "data": None,
        }
        result = _scrub_dict(data)
        assert result["count"] == 42
        assert result["price"] == 123.45
        assert result["enabled"] is True
        assert result["data"] is None

    def test_deep_nesting_limit(self):
        """Deep nesting doesn't cause stack overflow."""
        # Create deeply nested structure
        data = {"level": 0}
        current = data
        for i in range(15):
            current["nested"] = {"level": i + 1}
            current = current["nested"]
        current["password"] = "deep_secret"
        
        # Should not crash
        result = _scrub_dict(data)
        assert isinstance(result, dict)

    def test_unicode_handling(self):
        """Unicode characters are handled correctly."""
        data = {
            "message": "User: 用户 logged in",
            "password": "秘密password123",
        }
        result = _scrub_dict(data)
        assert "用户" in str(result)
        assert "秘密password123" not in str(result)


class TestRealWorldScenarios:
    """Test real-world logging scenarios."""

    def test_alpaca_broker_log(self):
        """Alpaca broker configuration is scrubbed."""
        data = {
            "event": "broker_init",
            "broker": "alpaca",
            "alpaca_api_key": "PKABCDEF123456789012",
            "alpaca_secret_key": "SKZYXWVU987654321098",
            "base_url": "https://paper-api.alpaca.markets",
        }
        result = _scrub_dict(data)
        
        assert "PKABCDEF123456789012" not in str(result)
        assert "SKZYXWVU987654321098" not in str(result)
        assert result["base_url"] == "https://paper-api.alpaca.markets"

    def test_order_submission_log(self):
        """Order submission log preserves trading data."""
        data = {
            "event": "order_submitted",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "price": 150.50,
            "order_id": "ord_abc123",
        }
        result = _scrub_dict(data)
        
        # All trading data should be preserved
        assert result == data

    def test_error_log_with_stack_trace(self):
        """Error logs with stack traces are preserved."""
        data = {
            "event": "error",
            "error": "Connection failed",
            "stack_trace": "Traceback (most recent call last):\n  File ...",
            "auth_header": "Bearer secret_token_here",
        }
        result = _scrub_dict(data)
        
        assert "Traceback" in result["stack_trace"]
        assert "secret_token_here" not in str(result)


# Marker for unit tests
pytestmark = pytest.mark.unit
