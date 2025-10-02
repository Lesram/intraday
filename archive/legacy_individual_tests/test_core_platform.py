#!/usr/bin/env python3
"""
Core Platform Components Testing Script
Tests database, configuration, and core services with correct import paths.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.paper')

def test_database_functionality():
    """Test database operations with proper async handling"""
    try:
        from backend.database.database_config import DatabaseConfig
        
        async def run_db_test():
            db_config = DatabaseConfig()
            health = await db_config.check_connection_health()
            return health['healthy'] and health['connectivity']
        
        return asyncio.run(run_db_test())
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_unified_settings():
    """Test UnifiedSettings configuration system"""
    try:
        from backend.config.unified import UnifiedSettings
        
        settings = UnifiedSettings()
        
        # Test basic settings loading
        has_get_alpaca = hasattr(settings, 'get_alpaca_config')
        has_get_database = hasattr(settings, 'get_database_config')
        
        return has_get_alpaca and has_get_database
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_alpaca_configuration():
    """Test Alpaca API configuration"""
    try:
        from backend.config.unified import UnifiedSettings
        
        settings = UnifiedSettings()
        alpaca_config = settings.get_alpaca_config()
        
        # Verify required config keys exist
        required_keys = ['api_key', 'secret_key', 'base_url']
        has_keys = all(key in alpaca_config for key in required_keys)
        
        # Test config values are not empty/default
        api_key = alpaca_config.get('api_key', '')
        secret_key = alpaca_config.get('secret_key', '')
        
        has_values = len(api_key) > 0 and len(secret_key) > 0
        
        return has_keys and has_values
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_jwt_configuration():
    """Test JWT authentication configuration"""
    try:
        # Check JWT secret in environment
        jwt_secret = os.getenv('JWT_SECRET_KEY')
        
        if not jwt_secret:
            return False
            
        # Test JWT secret is valid length and format
        is_valid_length = len(jwt_secret) >= 32
        
        return is_valid_length
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_database_configuration():
    """Test database configuration system"""
    try:
        from backend.config.unified import UnifiedSettings
        
        settings = UnifiedSettings()
        db_config = settings.get_database_config()
        
        # Test database config has required keys
        required_keys = ['url', 'echo']
        has_keys = all(key in db_config for key in required_keys)
        
        return has_keys
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_order_service():
    """Test OrderService with correct method names"""
    try:
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        # Test correct method existence
        has_submit = hasattr(service, 'submit_order')
        has_validate = hasattr(service, 'validate_order') 
        has_cancel = hasattr(service, 'cancel_order')
        
        return has_submit and has_validate and has_cancel
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_risk_manager():
    """Test RiskManager functionality with correct return types"""
    try:
        from backend.risk.risk_manager import RiskManager
        
        risk_manager = RiskManager()
        
        # Test risk check with correct expected return type
        risk_result = risk_manager.check_risk('AAPL', 100)
        
        # Should return dict with 'allowed' key
        is_dict = isinstance(risk_result, dict)
        has_allowed = 'allowed' in risk_result if is_dict else False
        
        # Test validate_order method existence
        has_validate = hasattr(risk_manager, 'validate_order')
        
        return is_dict and has_allowed and has_validate
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_positions_service():
    """Test PositionsService functionality"""
    try:
        from backend.services.positions_service import PositionsService
        
        service = PositionsService()
        
        # Test service creation and correct method existence
        has_get_all_positions = hasattr(service, 'get_all_positions')
        has_get_position = hasattr(service, 'get_position')
        has_get_portfolio_value = hasattr(service, 'get_total_portfolio_value')
        
        return has_get_all_positions and has_get_position and has_get_portfolio_value
    except Exception as e:
        print(f"  Error: {e}")
        return False

def run_core_platform_tests():
    """Run all core platform component tests"""
    print("🔬 CORE PLATFORM COMPONENTS TESTING")
    print("=" * 40)
    
    tests = [
        ("Database Operations", test_database_functionality),
        ("Unified Settings", test_unified_settings),
        ("Alpaca Configuration", test_alpaca_configuration),
        ("JWT Configuration", test_jwt_configuration),
        ("Database Configuration", test_database_configuration),
        ("OrderService Methods", test_order_service),
        ("RiskManager Operations", test_risk_manager),
        ("PositionsService", test_positions_service),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Testing {test_name}...")
        try:
            result = test_func()
            if result:
                print(f"  ✅ {test_name}: FUNCTIONAL")
                passed += 1
            else:
                print(f"  ❌ {test_name}: FAILED")
        except Exception as e:
            print(f"  ❌ {test_name}: ERROR - {str(e)[:60]}...")
    
    success_rate = (passed / total) * 100
    print(f"\n📊 Core Platform Tests: {passed}/{total} ({success_rate:.1f}%)")
    
    return success_rate >= 90

if __name__ == "__main__":
    success = run_core_platform_tests()
    sys.exit(0 if success else 1)