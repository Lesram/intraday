#!/usr/bin/env python3
"""
Test Comprehensive Configuration Loading
"""

from backend.config.settings import settings
import os

def test_configuration_loading():
    """Test all configuration sections load properly."""
    print("🧪 Testing Configuration Loading...")
    
    # Test App Configuration
    print("\n📱 App Configuration:")
    print(f"  Environment: {settings.app.environment}")
    print(f"  Debug: {settings.app.debug}")
    print(f"  Host: {settings.app.host}")
    print(f"  Port: {settings.app.port}")
    print(f"  Workers: {settings.app.workers}")
    print(f"  Log Level: {settings.app.log_level}")
    
    # Test Security Configuration
    print("\n🔒 Security Configuration:")
    print(f"  JWT Algorithm: {settings.security.jwt_algorithm}")
    print(f"  JWT Expire Minutes: {settings.security.jwt_expire_minutes}")
    print(f"  JWT Secret Key: {'*' * 10}... (masked)")
    
    # Test Alpaca Configuration
    print("\n📈 Alpaca Configuration:")
    print(f"  API Key: {settings.alpaca.api_key[:8]}... (masked)")
    print(f"  Secret Key: {'*' * 10}... (masked)")
    print(f"  Paper Trading: {settings.alpaca.paper_trading}")
    print(f"  Base URL: {settings.alpaca.base_url}")
    print(f"  WebSocket URL: {settings.alpaca.websocket_url}")
    
    # Test Data Configuration
    print("\n🗄️ Data Configuration:")
    print(f"  Database URL: {settings.data.database_url}")
    print(f"  Redis Host: {settings.data.redis_host}")
    print(f"  Redis Port: {settings.data.redis_port}")
    print(f"  Redis DB: {settings.data.redis_db}")
    print(f"  Default Symbols: {settings.data.default_symbols}")
    print(f"  Subreddit List: {settings.data.subreddit_list}")
    
    # Test Trading Configuration  
    print("\n💰 Trading Configuration:")
    print(f"  Max Daily Loss %: {settings.trading.max_daily_loss_pct}")
    print(f"  Max Drawdown %: {settings.trading.max_drawdown_pct}")
    print(f"  Max Position %: {settings.trading.max_position_pct}")
    print(f"  Max Leverage: {settings.trading.max_leverage}")
    
    # Test Environment Variables Loading
    print("\n🌍 Environment Variables Test:")
    env_vars_to_check = [
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY", 
        "ALPACA_PAPER_TRADING",
        "DATABASE_URL",
        "REDIS_HOST",
        "LOG_LEVEL"
    ]
    
    for var in env_vars_to_check:
        value = os.getenv(var)
        if value:
            if "KEY" in var or "SECRET" in var:
                print(f"  ✅ {var}: {'*' * 10}... (masked)")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: Not found")
    
    print("\n🎉 Configuration loading test completed!")
    return True

if __name__ == "__main__":
    test_configuration_loading()