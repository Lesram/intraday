"""
Tests for backend.config.base_settings module
Target: High coverage on config classes (1730 lines - test key components)
"""
import pytest
import os
from pydantic import ValidationError


class TestAppConfig:
    """Test AppConfig settings"""
    
    def test_app_config_defaults(self):
        """Test default configuration values"""
        # Temporarily clear environment to test defaults
        orig_env = os.environ.pop("APP_ENVIRONMENT", None)
        try:
            from backend.config.base_settings import AppConfig
            
            config = AppConfig()
            # In test environment, might be "testing" or "development"
            assert config.environment in ("development", "testing")
            assert isinstance(config.debug, bool)
            assert config.port == 8000
            assert config.host == "0.0.0.0"
        finally:
            if orig_env:
                os.environ["APP_ENVIRONMENT"] = orig_env
    
    def test_app_config_custom_values(self):
        """Test custom configuration values"""
        from backend.config.base_settings import AppConfig
        
        config = AppConfig(
            environment="production",
            debug=False,
            port=9000,
            host="127.0.0.1"
        )
        assert config.environment == "production"
        assert config.debug is False
        assert config.port == 9000
    
    def test_app_config_invalid_environment(self):
        """Test invalid environment raises error"""
        from backend.config.base_settings import AppConfig
        
        with pytest.raises(ValidationError):
            AppConfig(environment="invalid_env")
    
    def test_app_config_invalid_port(self):
        """Test invalid port raises error"""
        from backend.config.base_settings import AppConfig
        
        with pytest.raises(ValidationError):
            AppConfig(port=70000)  # Above max
        
        with pytest.raises(ValidationError):
            AppConfig(port=0)  # Below min
    
    def test_app_config_cors_origins_string(self):
        """Test CORS origins parsing from string"""
        from backend.config.base_settings import AppConfig
        
        config = AppConfig(cors_origins="http://localhost:3000,http://localhost:5173")
        assert len(config.cors_origins) == 2
        assert "http://localhost:3000" in config.cors_origins
    
    def test_app_config_cors_origins_list(self):
        """Test CORS origins as list"""
        from backend.config.base_settings import AppConfig
        
        origins = ["http://example.com", "http://test.com"]
        config = AppConfig(cors_origins=origins)
        assert config.cors_origins == origins
    
    def test_app_config_log_level_validation(self):
        """Test log level validation"""
        from backend.config.base_settings import AppConfig
        
        config = AppConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"
        
        config = AppConfig(log_level="debug")  # Should uppercase
        assert config.log_level == "DEBUG"
        
        with pytest.raises(ValidationError):
            AppConfig(log_level="INVALID")


class TestSecurityConfig:
    """Test SecurityConfig settings"""
    
    def test_security_config_defaults(self):
        """Test default security configuration"""
        from backend.config.base_settings import SecurityConfig
        
        config = SecurityConfig()
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 30
    
    def test_security_config_jwt_secret_too_short(self):
        """Test JWT secret validation"""
        from backend.config.base_settings import SecurityConfig
        
        with pytest.raises(ValidationError, match="at least 32 characters"):
            SecurityConfig(jwt_secret_key="short")
    
    def test_security_config_jwt_algorithm_validation(self):
        """Test JWT algorithm validation"""
        from backend.config.base_settings import SecurityConfig
        
        valid_secret = "a" * 32
        config = SecurityConfig(jwt_secret_key=valid_secret, jwt_algorithm="HS512")
        assert config.jwt_algorithm == "HS512"
        
        with pytest.raises(ValidationError):
            SecurityConfig(jwt_secret_key=valid_secret, jwt_algorithm="INVALID")
    
    def test_security_config_custom_values(self):
        """Test custom security configuration"""
        from backend.config.base_settings import SecurityConfig
        
        secret = "my-super-secret-key-that-is-very-long-and-secure"
        config = SecurityConfig(
            jwt_secret_key=secret,
            jwt_algorithm="HS384",
            jwt_expire_minutes=60,
            jwt_issuer="test-platform"
        )
        assert config.jwt_secret_key == secret
        assert config.jwt_expire_minutes == 60
        assert config.jwt_issuer == "test-platform"


class TestAlpacaConfig:
    """Test AlpacaConfig settings"""
    
    def test_alpaca_config_defaults(self):
        """Test default Alpaca configuration"""
        from backend.config.base_settings import AlpacaConfig
        
        config = AlpacaConfig()
        assert config.api_key == ""
        assert config.secret_key == ""
    
    def test_alpaca_config_custom_values(self):
        """Test custom Alpaca configuration"""
        from backend.config.base_settings import AlpacaConfig
        
        config = AlpacaConfig(
            api_key="test_api_key",
            secret_key="test_secret_key"
        )
        assert config.api_key == "test_api_key"
        assert config.secret_key == "test_secret_key"
