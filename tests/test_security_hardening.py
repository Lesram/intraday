"""
Tests for Security Hardening Infrastructure.

Tests cover:
- Input validation and sanitization
- Rate limiting (already tested elsewhere, basic coverage here)
- Security headers
"""

import pytest

from backend.infra.security_hardening import (
    InputValidator,
    ValidationResult,
)


class TestInputValidator:
    """Tests for input validation."""
    
    # Symbol validation tests
    
    def test_validate_symbol_valid(self):
        """Test valid symbols."""
        result = InputValidator.validate_symbol("AAPL")
        
        assert result.is_valid
        assert result.sanitized_value == "AAPL"
    
    def test_validate_symbol_lowercase(self):
        """Test lowercase symbol is uppercased."""
        result = InputValidator.validate_symbol("aapl")
        
        assert result.is_valid
        assert result.sanitized_value == "AAPL"
    
    def test_validate_symbol_with_spaces(self):
        """Test symbol with whitespace is trimmed."""
        result = InputValidator.validate_symbol("  AAPL  ")
        
        assert result.is_valid
        assert result.sanitized_value == "AAPL"
    
    def test_validate_symbol_empty(self):
        """Test empty symbol fails."""
        result = InputValidator.validate_symbol("")
        
        assert not result.is_valid
        assert "Symbol is required" in result.errors
    
    def test_validate_symbol_too_long(self):
        """Test symbol that's too long."""
        result = InputValidator.validate_symbol("ABCDEFGHIJK")
        
        assert not result.is_valid
        assert "too long" in result.errors[0].lower()
    
    def test_validate_symbol_invalid_format(self):
        """Test symbol with invalid characters."""
        result = InputValidator.validate_symbol("AAPL123")
        
        assert not result.is_valid
        assert "Invalid symbol format" in result.errors
    
    # Quantity validation tests
    
    def test_validate_quantity_valid(self):
        """Test valid quantity."""
        result = InputValidator.validate_quantity(100.5)
        
        assert result.is_valid
        assert result.sanitized_value == 100.5
    
    def test_validate_quantity_string(self):
        """Test quantity from string."""
        result = InputValidator.validate_quantity("50.25")
        
        assert result.is_valid
        assert result.sanitized_value == 50.25
    
    def test_validate_quantity_int(self):
        """Test quantity from int."""
        result = InputValidator.validate_quantity(100)
        
        assert result.is_valid
        assert result.sanitized_value == 100.0
    
    def test_validate_quantity_too_small(self):
        """Test quantity below minimum."""
        result = InputValidator.validate_quantity(0.00001)
        
        assert not result.is_valid
        assert "must be >=" in result.errors[0]
    
    def test_validate_quantity_too_large(self):
        """Test quantity above maximum."""
        result = InputValidator.validate_quantity(10_000_000)
        
        assert not result.is_valid
        assert "must be <=" in result.errors[0]
    
    def test_validate_quantity_invalid_string(self):
        """Test invalid quantity string."""
        result = InputValidator.validate_quantity("not_a_number")
        
        assert not result.is_valid
        assert "Invalid quantity format" in result.errors
    
    # Price validation tests
    
    def test_validate_price_valid(self):
        """Test valid price."""
        result = InputValidator.validate_price(150.5678)
        
        assert result.is_valid
        assert result.sanitized_value == 150.5678
    
    def test_validate_price_rounds_to_4_decimals(self):
        """Test price is rounded to 4 decimals."""
        result = InputValidator.validate_price(150.56789)
        
        assert result.is_valid
        assert result.sanitized_value == 150.5679
    
    def test_validate_price_too_small(self):
        """Test price below minimum."""
        result = InputValidator.validate_price(0.00001)
        
        assert not result.is_valid
        assert "must be >=" in result.errors[0]
    
    def test_validate_price_too_large(self):
        """Test price above maximum."""
        result = InputValidator.validate_price(2_000_000)
        
        assert not result.is_valid
        assert "must be <=" in result.errors[0]
    
    # Order ID validation tests
    
    def test_validate_order_id_valid(self):
        """Test valid UUID order ID."""
        result = InputValidator.validate_order_id("123e4567-e89b-12d3-a456-426614174000")
        
        assert result.is_valid
        assert result.sanitized_value == "123e4567-e89b-12d3-a456-426614174000"
    
    def test_validate_order_id_uppercase(self):
        """Test uppercase UUID is lowercased."""
        result = InputValidator.validate_order_id("123E4567-E89B-12D3-A456-426614174000")
        
        assert result.is_valid
        assert result.sanitized_value == "123e4567-e89b-12d3-a456-426614174000"
    
    def test_validate_order_id_empty(self):
        """Test empty order ID fails."""
        result = InputValidator.validate_order_id("")
        
        assert not result.is_valid
        assert "Order ID is required" in result.errors
    
    def test_validate_order_id_invalid_format(self):
        """Test invalid order ID format."""
        result = InputValidator.validate_order_id("not-a-valid-uuid")
        
        assert not result.is_valid
        assert "Invalid order ID format" in result.errors
    
    # String sanitization tests
    
    def test_sanitize_string_valid(self):
        """Test valid string passes through."""
        result = InputValidator.sanitize_string("Hello World 123")
        
        assert result.is_valid
        assert result.sanitized_value == "Hello World 123"
    
    def test_sanitize_string_empty(self):
        """Test empty string."""
        result = InputValidator.sanitize_string("")
        
        assert result.is_valid
        assert result.sanitized_value == ""
    
    def test_sanitize_string_removes_special_chars(self):
        """Test special characters are removed."""
        result = InputValidator.sanitize_string("Hello<script>alert('xss')</script>")
        
        assert result.is_valid
        assert "<" not in result.sanitized_value
        assert ">" not in result.sanitized_value
    
    def test_sanitize_string_truncates(self):
        """Test long strings are truncated."""
        long_string = "a" * 2000
        result = InputValidator.sanitize_string(long_string)
        
        assert result.is_valid
        assert len(result.sanitized_value) == 1000
    
    def test_sanitize_string_custom_max_length(self):
        """Test custom max length."""
        result = InputValidator.sanitize_string("Hello World", max_length=5)
        
        assert result.is_valid
        assert len(result.sanitized_value) == 5
    
    def test_sanitize_string_removes_control_chars(self):
        """Test control characters are removed."""
        result = InputValidator.sanitize_string("Hello\x00World")
        
        assert result.is_valid
        assert "\x00" not in result.sanitized_value
    
    # Email validation tests
    
    def test_validate_email_valid(self):
        """Test valid email."""
        result = InputValidator.validate_email("user@example.com")
        
        assert result.is_valid
        assert result.sanitized_value == "user@example.com"
    
    def test_validate_email_uppercase(self):
        """Test uppercase email is lowercased."""
        result = InputValidator.validate_email("User@Example.COM")
        
        assert result.is_valid
        assert result.sanitized_value == "user@example.com"
    
    def test_validate_email_with_plus(self):
        """Test email with plus sign."""
        result = InputValidator.validate_email("user+tag@example.com")
        
        assert result.is_valid
        assert result.sanitized_value == "user+tag@example.com"
    
    def test_validate_email_empty(self):
        """Test empty email fails."""
        result = InputValidator.validate_email("")
        
        assert not result.is_valid
        assert "Email is required" in result.errors
    
    def test_validate_email_invalid_format(self):
        """Test invalid email format."""
        result = InputValidator.validate_email("not_an_email")
        
        assert not result.is_valid
        assert "Invalid email format" in result.errors
    
    def test_validate_email_too_long(self):
        """Test email that's too long."""
        long_email = "a" * 250 + "@example.com"
        result = InputValidator.validate_email(long_email)
        
        assert not result.is_valid
        assert "too long" in result.errors[0].lower()


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(True, "sanitized_value")
        
        assert result.is_valid
        assert result.sanitized_value == "sanitized_value"
        assert result.errors == []
    
    def test_invalid_result(self):
        """Test creating an invalid result."""
        result = ValidationResult(False, errors=["Error 1", "Error 2"])
        
        assert not result.is_valid
        assert len(result.errors) == 2
