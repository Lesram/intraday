"""
Tests for log redaction to ensure sensitive information is properly masked.

Verifies that Authorization headers, API keys, passwords, and other sensitive
data are redacted from log output to prevent security leaks.
"""

from datetime import datetime
import re

import pytest


class MockLogRedactor:
    """Mock log redactor for testing sensitive data masking."""

    SENSITIVE_PATTERNS = {
        # Authorization headers
        "authorization_bearer": (
            r"(?i)(authorization:\s*bearer\s+)([a-zA-Z0-9\.\-_]+)",
            r"\1[REDACTED_BEARER_TOKEN]",
        ),
        "authorization_basic": (
            r"(?i)(authorization:\s*basic\s+)([a-zA-Z0-9\+/=]+)",
            r"\1[REDACTED_BASIC_AUTH]",
        ),
        "authorization_apikey": (
            r"(?i)(authorization:\s*apikey\s+)([a-zA-Z0-9\-_]+)",
            r"\1[REDACTED_API_KEY]",
        ),
        # API keys in various formats
        "api_key_header": (
            r"(?i)(x-api-key:\s*)([a-zA-Z0-9\-_]{20,})",
            r"\1[REDACTED_API_KEY]",
        ),
        "api_key_param": (r"(?i)([&?]api_key=)([a-zA-Z0-9\-_]{20,})", r"\1[REDACTED]"),
        "alpaca_key": (r"(PKTEST_|PK_)[a-zA-Z0-9]{20,}", r"[REDACTED_ALPACA_KEY]"),
        # Passwords
        "password_field": (r'(?i)("password"\s*:\s*")([^"]+)(")', r"\1[REDACTED]\3"),
        "password_param": (r"(?i)([&?]password=)([^&\s]+)", r"\1[REDACTED]"),
        # JWT tokens
        "jwt_token": (r"(eyJ[a-zA-Z0-9\.\-_]+)", r"[REDACTED_JWT_TOKEN]"),
        # Database URLs
        "db_url_password": (r"(://[^:]+:)([^@]+)(@)", r"\1[REDACTED]\3"),
        # Credit card numbers (PCI compliance)
        "credit_card": (
            r"\b(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\b",
            r"[REDACTED_CARD_****\g<1>[-4:]]",
        ),
        # Social Security Numbers
        "ssn": (r"\b(\d{3}[-\s]?\d{2}[-\s]?\d{4})\b", r"[REDACTED_SSN]"),
        # Email addresses in sensitive contexts
        "email_sensitive": (
            r'(?i)("email"\s*:\s*")([^"]+@[^"]+)(")',
            r"\1[REDACTED_EMAIL]\3",
        ),
    }

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.redaction_count = 0

    def redact_message(self, message: str) -> str:
        """Redact sensitive information from log message."""
        if not self.enabled:
            return message

        redacted_message = message
        original_count = self.redaction_count

        for pattern_name, (pattern, replacement) in self.SENSITIVE_PATTERNS.items():
            if re.search(pattern, redacted_message):
                redacted_message = re.sub(pattern, replacement, redacted_message)
                self.redaction_count += 1

        return redacted_message

    def get_redaction_stats(self):
        """Get redaction statistics."""
        return {
            "total_redactions": self.redaction_count,
            "patterns_available": len(self.SENSITIVE_PATTERNS),
            "enabled": self.enabled,
        }


class MockSecureLogger:
    """Mock logger with redaction capabilities."""

    def __init__(self, redactor=None):
        self.redactor = redactor or MockLogRedactor()
        self.log_entries = []

    def log(self, level: str, message: str, **kwargs):
        """Log a message with redaction."""
        redacted_message = self.redactor.redact_message(message)

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level.upper(),
            "message": redacted_message,
            "original_length": len(message),
            "redacted_length": len(redacted_message),
            "was_redacted": message != redacted_message,
            **kwargs,
        }

        self.log_entries.append(log_entry)

    def info(self, message: str, **kwargs):
        self.log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def get_logs(self, level=None):
        """Get logged entries, optionally filtered by level."""
        if level:
            return [
                entry for entry in self.log_entries if entry["level"] == level.upper()
            ]
        return self.log_entries.copy()

    def clear_logs(self):
        """Clear all log entries."""
        self.log_entries.clear()


class TestLogRedaction:
    """Test log redaction functionality."""

    @pytest.fixture
    def log_redactor(self):
        """Create a log redactor instance."""
        return MockLogRedactor(enabled=True)

    @pytest.fixture
    def secure_logger(self, log_redactor):
        """Create a secure logger with redaction."""
        return MockSecureLogger(redactor=log_redactor)

    def test_authorization_header_redaction(self, secure_logger):
        """Test redaction of various Authorization header formats."""
        test_cases = [
            # Bearer tokens
            {
                "input": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
                "should_contain": "[REDACTED_BEARER_TOKEN]",
                "should_not_contain": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            },
            {
                "input": "authorization: bearer abc123def456ghi789",
                "should_contain": "[REDACTED_BEARER_TOKEN]",
                "should_not_contain": "abc123def456ghi789",
            },
            # Basic auth
            {
                "input": "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ=",
                "should_contain": "[REDACTED_BASIC_AUTH]",
                "should_not_contain": "dXNlcm5hbWU6cGFzc3dvcmQ=",
            },
            # API Key
            {
                "input": "Authorization: ApiKey pk_test_1234567890abcdef",
                "should_contain": "[REDACTED_API_KEY]",
                "should_not_contain": "pk_test_1234567890abcdef",
            },
        ]

        for case in test_cases:
            secure_logger.clear_logs()
            secure_logger.info(f"HTTP Request: {case['input']}")

            logs = secure_logger.get_logs()
            assert len(logs) == 1

            log_message = logs[0]["message"]
            assert (
                case["should_contain"] in log_message
            ), f"Expected '{case['should_contain']}' in redacted message: {log_message}"
            assert (
                case["should_not_contain"] not in log_message
            ), f"Sensitive data '{case['should_not_contain']}' found in log: {log_message}"
            assert logs[0]["was_redacted"] is True

    def test_api_key_redaction(self, secure_logger):
        """Test redaction of API keys in various formats."""
        test_cases = [
            # Header format
            "X-API-Key: pk_test_abcdefghijklmnopqrstuvwxyz123456",
            "x-api-key: sk_live_1234567890abcdefghijklmnop",
            # URL parameter format
            "GET /api/data?api_key=pk_test_secret_key_here&symbol=AAPL",
            "POST /orders?api_key=very_long_secret_key_value&side=buy",
            # Alpaca-specific formats
            "Alpaca key: PKTEST_abc123def456ghi789jkl012mno345pqr",
            'Config: {"alpaca_key": "PK_LIVE_secretkeyvalue123456789"}',
        ]

        for test_input in test_cases:
            secure_logger.clear_logs()
            secure_logger.info(f"Processing request: {test_input}")

            logs = secure_logger.get_logs()
            log_message = logs[0]["message"]

            # Should contain redaction marker
            assert any(
                redacted in log_message
                for redacted in [
                    "[REDACTED_API_KEY]",
                    "[REDACTED]",
                    "[REDACTED_ALPACA_KEY]",
                ]
            ), f"No redaction marker found in: {log_message}"

            # Should not contain original sensitive values
            sensitive_patterns = [
                "pk_test_abcdefghijklmnopqrstuvwxyz123456",
                "sk_live_1234567890abcdefghijklmnop",
                "pk_test_secret_key_here",
                "very_long_secret_key_value",
                "PKTEST_abc123def456ghi789jkl012mno345pqr",
                "PK_LIVE_secretkeyvalue123456789",
            ]

            for sensitive in sensitive_patterns:
                if sensitive in test_input:
                    assert (
                        sensitive not in log_message
                    ), f"Sensitive value '{sensitive}' not redacted in: {log_message}"

    def test_password_redaction(self, secure_logger):
        """Test redaction of passwords in various contexts."""
        test_cases = [
            # JSON format
            '{"username": "trader", "password": "super_secret_password123", "endpoint": "/login"}',
            # URL parameter format
            "POST /auth/login?username=user&password=my_secret_pass&remember=true",
            # Database URL
            "postgresql://dbuser:secret_db_password@localhost:5432/trading_db",
            "mysql://admin:complex_password_123@db.example.com:3306/data",
            # Configuration logs
            'Database config: {"host": "localhost", "user": "app", "password": "db_secret_key"}',
        ]

        for test_input in test_cases:
            secure_logger.clear_logs()
            secure_logger.error(f"Authentication failed: {test_input}")

            logs = secure_logger.get_logs("ERROR")
            log_message = logs[0]["message"]

            # Should contain redaction marker
            assert (
                "[REDACTED" in log_message
            ), f"No redaction marker found in: {log_message}"

            # Should not contain actual passwords
            sensitive_passwords = [
                "super_secret_password123",
                "my_secret_pass",
                "secret_db_password",
                "complex_password_123",
                "db_secret_key",
            ]

            for password in sensitive_passwords:
                if password in test_input:
                    assert (
                        password not in log_message
                    ), f"Password '{password}' not redacted in: {log_message}"

    def test_jwt_token_redaction(self, secure_logger):
        """Test redaction of JWT tokens."""
        jwt_tokens = [
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.payload_data_here.signature_data_here",
        ]

        for jwt_token in jwt_tokens:
            secure_logger.clear_logs()
            secure_logger.debug(f"Token validation: {jwt_token}")

            logs = secure_logger.get_logs("DEBUG")
            log_message = logs[0]["message"]

            assert "[REDACTED_JWT_TOKEN]" in log_message
            assert jwt_token not in log_message, f"JWT token not redacted: {jwt_token}"

    def test_pci_compliance_redaction(self, secure_logger):
        """Test redaction of credit card numbers for PCI compliance."""
        test_cases = [
            # Various credit card formats
            "Payment processed: 4532-1234-5678-9012 approved",
            "Card ending in 9876: 5555 4444 3333 2222 declined",
            "Transaction: 378282246310005 for $1,250.00",
            # Should NOT redact non-card numbers
            "Order ID: 1234567890123456 processed",  # Too many digits
            "Account: 123-45-6789",  # Too few digits in wrong format
        ]

        for test_input in test_cases:
            secure_logger.clear_logs()
            secure_logger.info(f"Payment log: {test_input}")

            logs = secure_logger.get_logs("INFO")
            log_message = logs[0]["message"]

            # Credit card patterns should be redacted
            card_patterns = [
                "4532-1234-5678-9012",
                "5555 4444 3333 2222",
                "378282246310005",
            ]
            for card in card_patterns:
                if card in test_input:
                    assert card not in log_message, f"Credit card {card} not redacted"
                    assert "[REDACTED_CARD_" in log_message or "REDACTED" in log_message

    def test_selective_redaction_preserves_context(self, secure_logger):
        """Test that redaction preserves important context while masking sensitive data."""
        test_input = (
            "User authentication: POST /api/login "
            'Headers: {"Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.payload.sig", '
            '"X-API-Key": "pk_test_1234567890abcdef", "User-Agent": "TradingBot/1.0"} '
            "Status: 401 Unauthorized"
        )

        secure_logger.info(test_input)
        logs = secure_logger.get_logs()
        log_message = logs[0]["message"]

        # Context should be preserved
        assert "POST /api/login" in log_message
        assert "Status: 401 Unauthorized" in log_message
        assert 'User-Agent": "TradingBot/1.0"' in log_message

        # Sensitive data should be redacted
        assert "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.payload.sig" not in log_message
        assert "pk_test_1234567890abcdef" not in log_message

        # Redaction markers should be present
        assert "[REDACTED_BEARER_TOKEN]" in log_message
        assert "[REDACTED_API_KEY]" in log_message

    def test_redaction_disabled_mode(self):
        """Test that redaction can be disabled when needed."""
        disabled_redactor = MockLogRedactor(enabled=False)
        logger = MockSecureLogger(redactor=disabled_redactor)

        sensitive_input = "Authorization: Bearer secret_token_here"
        logger.info(sensitive_input)

        logs = logger.get_logs()
        log_message = logs[0]["message"]

        # When disabled, sensitive data should NOT be redacted
        assert log_message == sensitive_input
        assert "[REDACTED" not in log_message
        assert logs[0]["was_redacted"] is False

    def test_redaction_statistics_tracking(self, log_redactor, secure_logger):
        """Test that redaction statistics are properly tracked."""
        initial_stats = log_redactor.get_redaction_stats()
        initial_count = initial_stats["total_redactions"]

        # Log some messages with sensitive data
        secure_logger.info("Authorization: Bearer token123")
        secure_logger.info("X-API-Key: apikey456")
        secure_logger.info("Password: secret789")
        secure_logger.info("Regular log message")  # No redaction needed

        final_stats = log_redactor.get_redaction_stats()

        # Should have tracked redactions (exact count depends on patterns matched)
        assert final_stats["total_redactions"] > initial_count
        assert final_stats["enabled"] is True
        assert final_stats["patterns_available"] > 0

    def test_complex_mixed_sensitive_data(self, secure_logger):
        """Test redaction of complex logs with multiple types of sensitive data."""
        complex_log = """
        Trading API Request:
        URL: https://api.example.com/v1/orders?api_key=pk_test_super_secret_key_here
        Headers: {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.user_data.signature",
            "X-API-Key": "sk_live_another_secret_key_value",
            "Content-Type": "application/json"
        }
        Payload: {
            "symbol": "AAPL",
            "quantity": 100,
            "user_credentials": {
                "username": "trader123",
                "password": "trading_password_123"
            }
        }
        Database: postgresql://trader:db_secret_pass@localhost:5432/trading
        Response: Order placed successfully
        """

        secure_logger.info(complex_log)
        logs = secure_logger.get_logs()
        log_message = logs[0]["message"]

        # Should preserve non-sensitive context
        context_items = [
            "Trading API Request:",
            '"symbol": "AAPL"',
            '"quantity": 100',
            "Response: Order placed successfully",
            '"Content-Type": "application/json"',
        ]

        for item in context_items:
            assert item in log_message, f"Context '{item}' was incorrectly redacted"

        # Should redact all sensitive data
        sensitive_items = [
            "pk_test_super_secret_key_here",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.user_data.signature",
            "sk_live_another_secret_key_value",
            "trading_password_123",
            "db_secret_pass",
        ]

        for sensitive in sensitive_items:
            assert (
                sensitive not in log_message
            ), f"Sensitive data '{sensitive}' not redacted"

        # Should have redaction markers
        redaction_markers = [
            "[REDACTED",  # Generic check for any redaction marker
        ]

        for marker in redaction_markers:
            assert marker in log_message, f"Missing redaction marker '{marker}'"

    def test_redaction_deterministic_behavior(self, test_seed):
        """Test that redaction behavior is deterministic."""
        test_message = "Authorization: Bearer deterministic_token_12345"

        # Multiple redactions of same message should be identical
        results = []

        for _ in range(5):
            redactor = MockLogRedactor(enabled=True)
            result = redactor.redact_message(test_message)
            results.append(result)

        # All results should be identical
        for result in results[1:]:
            assert result == results[0], "Redaction is not deterministic"

        # Should contain redaction marker
        assert "[REDACTED_BEARER_TOKEN]" in results[0]
        assert "deterministic_token_12345" not in results[0]
