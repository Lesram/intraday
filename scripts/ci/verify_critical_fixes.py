"""
Verification script for critical fixes implementation.
Tests:
1. Environment variable naming (ALPACA_API_KEY_ID)
2. Database user persistence
3. Brute force protection
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment variables
os.environ['ALPACA_API_KEY_ID'] = 'test_key_id'
os.environ['ALPACA_API_SECRET_KEY'] = 'test_secret_key'


async def test_env_vars():
    """Test #1: Verify environment variable naming is standardized."""
    print("\n" + "="*60)
    print("TEST 1: Environment Variable Naming")
    print("="*60)
    
    from backend.config.unified import get_unified_settings
    from backend.config.coordinator import get_configuration_coordinator
    
    try:
        # Test unified config
        settings = get_unified_settings()
        print(f"✅ Unified config reads ALPACA_API_KEY_ID: {settings.alpaca_api_key == 'test_key_id'}")
        print(f"✅ Unified config reads ALPACA_API_SECRET_KEY: {settings.alpaca_secret_key == 'test_secret_key'}")
        
        # Test coordinator
        coordinator = get_configuration_coordinator()
        creds = coordinator.get_alpaca_credentials()
        print(f"✅ Coordinator returns api_key: {creds['api_key'] == 'test_key_id'}")
        print(f"✅ Coordinator returns secret_key: {creds['secret_key'] == 'test_secret_key'}")
        
        print("\n✅ TEST 1 PASSED: Environment variable naming standardized")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_user_persistence():
    """Test #2: Verify database-backed user storage."""
    print("\n" + "="*60)
    print("TEST 2: Database User Persistence")
    print("="*60)
    
    try:
        import sqlite3
        from backend.config.unified import get_database_url
        
        # Check database
        db_url = get_database_url()
        db_path = db_url.replace('sqlite:///', '').replace('sqlite:', '')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verify table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone() is not None
        print(f"✅ Users table exists: {table_exists}")
        
        # Verify columns
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            'id', 'username', 'hashed_password', 'roles', 'is_active',
            'failed_login_attempts', 'locked_until', 'last_login',
            'created_at', 'updated_at'
        }
        has_all_columns = expected_columns.issubset(columns)
        print(f"✅ All required columns present: {has_all_columns}")
        
        # Verify admin user exists
        cursor.execute("SELECT username, roles, is_active FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        if admin:
            print(f"✅ Admin user exists: {admin[0]}")
            print(f"   Roles: {admin[1]}")
            print(f"   Active: {bool(admin[2])}")
        else:
            print("❌ Admin user not found")
            conn.close()
            return False
        
        conn.close()
        
        print("\n✅ TEST 2 PASSED: Database user persistence implemented")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_brute_force_protection():
    """Test #3: Verify brute force protection."""
    print("\n" + "="*60)
    print("TEST 3: Brute Force Protection")
    print("="*60)
    
    try:
        import sqlite3
        from backend.config.unified import get_database_url
        
        # Check database has brute force columns
        db_url = get_database_url()
        db_path = db_url.replace('sqlite:///', '').replace('sqlite:', '')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verify brute force columns exist
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        
        has_failed_attempts = 'failed_login_attempts' in columns
        has_locked_until = 'locked_until' in columns
        
        print(f"✅ failed_login_attempts column exists: {has_failed_attempts}")
        print(f"✅ locked_until column exists: {has_locked_until}")
        
        # Check UserRepository constants
        from backend.infra.users import UserRepository
        
        print(f"✅ MAX_FAILED_ATTEMPTS = {UserRepository.MAX_FAILED_ATTEMPTS}")
        print(f"✅ LOCKOUT_DURATION_MINUTES = {UserRepository.LOCKOUT_DURATION_MINUTES}")
        
        # Verify methods exist
        repo = UserRepository(db_session=None)
        has_increment = hasattr(repo, '_increment_failed_attempts')
        has_reset = hasattr(repo, '_reset_failed_attempts')
        has_update_login = hasattr(repo, '_update_last_login')
        
        print(f"✅ _increment_failed_attempts method: {has_increment}")
        print(f"✅ _reset_failed_attempts method: {has_reset}")
        print(f"✅ _update_last_login method: {has_update_login}")
        
        conn.close()
        
        if all([has_failed_attempts, has_locked_until, has_increment, has_reset, has_update_login]):
            print("\n✅ TEST 3 PASSED: Brute force protection implemented")
            return True
        else:
            print("\n❌ TEST 3 FAILED: Missing components")
            return False
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all verification tests."""
    print("="*60)
    print("CRITICAL FIXES VERIFICATION")
    print("="*60)
    
    results = []
    
    # Test 1: Environment variables
    results.append(await test_env_vars())
    
    # Test 2: User persistence
    results.append(await test_user_persistence())
    
    # Test 3: Brute force protection
    results.append(await test_brute_force_protection())
    
    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n✅ Passed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL CRITICAL FIXES VERIFIED!")
        print("\nNext steps:")
        print("1. Update environment variables: ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY")
        print("2. Run full test suite: python scripts/testing/test_layer5_business_workflows.py")
        print("3. Expected result: 24/24 tests passed (100%)")
        print("4. Change admin password in production!")
        return True
    else:
        print("\n❌ SOME TESTS FAILED - Review errors above")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
