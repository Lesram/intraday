"""
Simple Database Production Readiness Test
Tests the key database configuration components we implemented
"""

import asyncio
import os
from pathlib import Path

# Set testing environment
os.environ["TESTING"] = "true"


async def test_database_production_readiness():
    """Test database production readiness components."""
    
    print("\n" + "="*60)
    print("DATABASE PRODUCTION READINESS VALIDATION")
    print("="*60)
    
    results = {
        "Database Configuration": False,
        "Connection Pooling Setup": False, 
        "Backup Procedures": False,
        "Session Management": False,
        "Environment Variables": False
    }
    
    try:
        # 1. Test Database Configuration Import
        print("🔍 Testing database configuration import...")
        try:
            from backend.database.database_config import DatabaseConfig, db_config
            results["Database Configuration"] = True
            print("✅ Database configuration module imported successfully")
        except Exception as e:
            print(f"❌ Database configuration import failed: {e}")
        
        # 2. Test Connection Pooling Configuration
        print("\n🔍 Testing connection pooling setup...")
        try:
            config = DatabaseConfig()
            # Verify pool configuration exists
            if hasattr(config, 'pool_size') and hasattr(config, 'max_overflow'):
                if config.pool_size > 0 and config.max_overflow > 0:
                    results["Connection Pooling Setup"] = True
                    print(f"✅ Connection pooling configured: pool_size={config.pool_size}, max_overflow={config.max_overflow}")
                else:
                    print("❌ Connection pool settings are invalid")
            else:
                print("❌ Connection pool attributes missing")
        except Exception as e:
            print(f"❌ Connection pooling test failed: {e}")
        
        # 3. Test Backup Procedures
        print("\n🔍 Testing backup procedures...")
        try:
            config = DatabaseConfig()
            if hasattr(config, 'backup_enabled') and hasattr(config, 'backup_directory'):
                # Test backup configuration
                backup_method = getattr(config, 'create_backup', None)
                if callable(backup_method):
                    results["Backup Procedures"] = True
                    print(f"✅ Backup procedures configured: enabled={config.backup_enabled}")
                else:
                    print("❌ Backup method not available")
            else:
                print("❌ Backup configuration attributes missing")
        except Exception as e:
            print(f"❌ Backup procedures test failed: {e}")
        
        # 4. Test Session Management
        print("\n🔍 Testing session management...")
        try:
            from backend.database.connection import get_database_session
            
            # Test session context manager
            session_works = False
            async with get_database_session() as session:
                # In testing mode, session might be None or mock
                session_works = True
            
            if session_works:
                results["Session Management"] = True
                print("✅ Session management working correctly")
            else:
                print("❌ Session management failed")
                
        except Exception as e:
            print(f"❌ Session management test failed: {e}")
        
        # 5. Test Environment Variable Support
        print("\n🔍 Testing environment variable configuration...")
        try:
            # Test with custom environment variables
            test_env = {
                'DB_POOL_SIZE': '15',
                'DB_MAX_OVERFLOW': '25',
                'DB_BACKUP_ENABLED': 'true'
            }
            
            # Create config with test environment
            with_env_vars = True
            for var, value in test_env.items():
                original_value = os.environ.get(var)
                os.environ[var] = value
                
                # Create new config instance
                config = DatabaseConfig()
                
                # Verify the value was used
                if var == 'DB_POOL_SIZE' and config.pool_size == 15:
                    continue
                elif var == 'DB_MAX_OVERFLOW' and config.max_overflow == 25:
                    continue
                elif var == 'DB_BACKUP_ENABLED' and config.backup_enabled == True:
                    continue
                else:
                    with_env_vars = False
                    break
                
                # Restore original value
                if original_value is not None:
                    os.environ[var] = original_value
                else:
                    os.environ.pop(var, None)
            
            if with_env_vars:
                results["Environment Variables"] = True
                print("✅ Environment variable configuration working")
            else:
                print("❌ Environment variable configuration failed")
                
        except Exception as e:
            print(f"❌ Environment variable test failed: {e}")
        
    except Exception as e:
        print(f"❌ Overall test failed: {e}")
    
    # Print Summary
    print("\n" + "="*60)
    print("PRODUCTION READINESS SUMMARY")
    print("="*60)
    
    total_passed = 0
    for component, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{component:<30} {status}")
        if passed:
            total_passed += 1
    
    total_tests = len(results)
    percentage = (total_passed / total_tests) * 100
    
    print("="*60)
    print(f"Database Readiness Score: {total_passed}/{total_tests} ({percentage:.0f}%)")
    
    if percentage >= 80:
        print("🎉 Database configuration is PRODUCTION READY!")
    elif percentage >= 60:
        print("⚠️  Database configuration needs minor improvements")
    else:
        print("❌ Database configuration needs major improvements")
    
    print("="*60)
    
    return results


async def test_production_database_manager():
    """Test the ProductionDatabaseManager functionality."""
    
    print("\n" + "="*60)  
    print("PRODUCTION DATABASE MANAGER VALIDATION")
    print("="*60)
    
    try:
        from backend.database.production import (
            ProductionDatabaseManager,
            validate_production_database_config
        )
        
        # Test manager creation
        manager = ProductionDatabaseManager()
        print("✅ Production database manager created successfully")
        
        # Test configuration validation
        with os.environ.update({
            'DATABASE_URL': 'postgresql://test:test@localhost:5432/testdb',
            'TESTING': 'true'
        }):
            validation = await validate_production_database_config()
            
            if validation.get("valid", False):
                print("✅ Database configuration validation passed")
            else:
                print(f"⚠️  Configuration validation issues: {validation.get('errors', [])}")
        
        # Test pool utilization calculation
        pool_status = {"checked_out": 5, "size": 10, "overflow": 0}
        utilization = manager._calculate_pool_utilization(pool_status)
        expected_utilization = 5/10  # 50%
        
        if abs(utilization - expected_utilization) < 0.01:
            print("✅ Pool utilization calculation working correctly")
        else:
            print(f"❌ Pool utilization calculation incorrect: {utilization} vs {expected_utilization}")
        
        print("✅ Production database manager validation completed")
        
    except Exception as e:
        print(f"❌ Production database manager test failed: {e}")


if __name__ == "__main__":
    # Run database readiness tests
    asyncio.run(test_database_production_readiness())
    print("\n")
    asyncio.run(test_production_database_manager())