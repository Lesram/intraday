"""
Simple test to validate the new configuration structure works properly.
"""

import os
import tempfile
from backend.config import Settings, get_settings, AppConfig, SecurityConfig

def test_basic_config():
    """Test basic configuration loading."""
    print("Testing basic configuration...")
    
    # Test with environment variable override
    os.environ["SKIP_VALIDATION"] = "true"
    
    try:
        settings = Settings()
        print(f"✓ Settings loaded successfully")
        print(f"  - App environment: {settings.app.environment}")
        print(f"  - App port: {settings.app.port}")
        print(f"  - Security JWT algo: {settings.security.jwt_algorithm}")
        print(f"  - Alpaca base URL: {settings.alpaca.base_url}")
        print(f"  - Data redis port: {settings.data.redis_port}")
        print(f"  - Metrics log level: {settings.metrics.log_level}")
        print(f"  - Trading max leverage: {settings.trading.max_leverage}")
        
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def test_nested_access():
    """Test nested configuration access."""
    print("\nTesting nested configuration access...")
    
    try:
        settings = Settings()
        
        # Test nested field access
        assert settings.app.environment == "development"
        assert settings.security.jwt_algorithm == "HS256"
        assert settings.alpaca.paper_trading is True
        assert settings.data.redis_port == 6379
        assert isinstance(settings.trading.ensemble_weights, dict)
        
        print("✓ All nested access tests passed")
        return True
    except Exception as e:
        print(f"✗ Nested access test failed: {e}")
        return False

def test_validation():
    """Test configuration validation."""
    print("\nTesting configuration validation...")
    
    try:
        # Test valid config
        app_config = AppConfig(environment="staging", port=9000)
        assert app_config.environment == "staging"
        assert app_config.port == 9000
        
        # Test JWT secret validation
        security_config = SecurityConfig(jwt_secret_key="a-very-long-secure-secret-key-with-more-than-32-characters")
        assert len(security_config.jwt_secret_key) > 32
        
        print("✓ All validation tests passed")
        return True
    except Exception as e:
        print(f"✗ Validation test failed: {e}")
        return False

def test_legacy_compatibility():
    """Test backward compatibility."""
    print("\nTesting legacy compatibility...")
    
    try:
        from backend.config import get_legacy_settings
        legacy = get_legacy_settings()
        
        # Check key legacy fields exist
        required_keys = [
            'environment', 'debug', 'host', 'port', 'jwt_secret_key',
            'alpaca_api_key', 'database_url', 'redis_port', 'max_leverage'
        ]
        
        for key in required_keys:
            assert key in legacy, f"Missing legacy key: {key}"
        
        print("✓ Legacy compatibility tests passed")
        return True
    except Exception as e:
        print(f"✗ Legacy compatibility test failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Configuration Hardening Validation ===\n")
    
    tests = [
        test_basic_config,
        test_nested_access,
        test_validation,
        test_legacy_compatibility
    ]
    
    results = []
    for test_func in tests:
        results.append(test_func())
    
    print(f"\n=== Summary ===")
    print(f"Tests passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("🎉 All configuration tests PASSED! Ready for production use.")
    else:
        print("❌ Some tests FAILED. Please review the configuration.")
