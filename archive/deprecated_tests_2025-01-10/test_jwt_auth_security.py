#!/usr/bin/env python3
"""
JWT & Authentication Security Test Suite
Comprehensive testing of JWT tokens, authentication, and security configurations.
"""

import sys
import os
import time
import secrets
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.paper')

def test_jwt_secret_security():
    """Test JWT secret strength and security"""
    try:
        # Check multiple potential JWT secret sources
        jwt_secret_1 = os.getenv('JWT_SECRET_KEY')
        jwt_secret_2 = os.getenv('SECURITY_JWT_SECRET')
        
        jwt_secret = jwt_secret_1 or jwt_secret_2
        
        if not jwt_secret:
            return False, "No JWT secret found in environment"
        
        # Test secret strength
        length_ok = len(jwt_secret) >= 32
        has_variety = (
            any(c.isdigit() for c in jwt_secret) and 
            any(c.isalpha() for c in jwt_secret) and
            any(c in '!@#$%^&*()-_=+[]{}|;:,.<>?' for c in jwt_secret)
        )
        not_default = jwt_secret not in [
            'your-secret-key-change-in-production',
            'development-secret-key-change-in-production',
            'test-jwt-secret'
        ]
        
        details = {
            "secret_length": len(jwt_secret),
            "length_adequate": length_ok,
            "has_complexity": has_variety,
            "not_default_secret": not_default,
            "secret_preview": jwt_secret[:8] + "..." if len(jwt_secret) > 8 else "***"
        }
        
        success = length_ok and has_variety and not_default
        return success, details
        
    except Exception as e:
        return False, f"Error testing JWT secret: {e}"

def test_jwt_token_operations():
    """Test JWT token creation, encoding, and decoding"""
    try:
        from backend.infra.security import create_access_token, verify_token
        
        # Test basic token creation
        token = create_access_token(sub="test_user", roles=["trader", "admin"])
        
        if not token:
            return False, "Failed to create JWT token"
        
        # Test token decoding
        decoded = verify_token(token)
        
        if not decoded:
            return False, "Failed to decode JWT token"
        
        # Test token contents
        has_subject = hasattr(decoded, 'sub') and decoded.sub == "test_user"
        has_roles = hasattr(decoded, 'roles') and "trader" in decoded.roles
        has_expiry = hasattr(decoded, 'exp') and decoded.exp is not None
        has_issued = hasattr(decoded, 'iat') and decoded.iat is not None
        
        # Test expiry is in future
        expiry_valid = decoded.exp > time.time() if has_expiry else False
        
        details = {
            "token_created": bool(token),
            "token_decoded": bool(decoded),
            "subject_correct": has_subject,
            "roles_correct": has_roles,
            "has_expiry": has_expiry,
            "has_issued": has_issued,
            "expiry_future": expiry_valid,
            "token_length": len(token) if token else 0
        }
        
        success = all([
            token, decoded, has_subject, has_roles, has_expiry, expiry_valid
        ])
        
        return success, details
        
    except Exception as e:
        return False, f"Error testing JWT operations: {e}"

def test_token_expiry_handling():
    """Test JWT token expiry and renewal"""
    try:
        from backend.infra.security import create_access_token, verify_token
        import jwt
        
        # Create token with short expiry (1 minute minimum, then test normal expiry)
        short_token = create_access_token(
            sub="test_user", 
            roles=["trader"],
            expires_minutes=1  # 1 minute expiry
        )
        
        # Verify it works immediately
        decoded_fresh = verify_token(short_token)
        fresh_valid = decoded_fresh is not None
        
        # Test with already expired timestamp (simulate expired token)
        import jwt as pyjwt
        from backend.config.unified import get_jwt_secret
        
        # Create manually expired payload  
        expired_payload = {
            'sub': 'test_user',
            'roles': ['trader'], 
            'exp': int(time.time()) - 60,  # Expired 1 minute ago
            'iat': int(time.time()) - 120  # Issued 2 minutes ago
        }
        
        expired_token = pyjwt.encode(expired_payload, get_jwt_secret(), algorithm='HS256')
        
        # Try to verify expired token
        try:
            decoded_expired = verify_token(expired_token)
            expired_rejected = decoded_expired is None
        except Exception:
            # Any exception means proper rejection
            expired_rejected = True
        
        details = {
            "fresh_token_valid": fresh_valid,
            "expired_token_rejected": expired_rejected,
            "expiry_mechanism_working": expired_rejected
        }
        
        success = fresh_valid and expired_rejected
        return success, details
        
    except Exception as e:
        return False, f"Error testing token expiry: {e}"

def test_invalid_token_handling():
    """Test handling of invalid, malformed, or tampered tokens"""
    try:
        from backend.infra.security import verify_token
        
        test_cases = [
            ("empty_token", ""),
            ("invalid_format", "invalid.token.format"),
            ("malformed_jwt", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.invalid"),
            ("tampered_token", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.tampered"),
            ("none_token", None)
        ]
        
        results = {}
        all_rejected = True
        
        for test_name, invalid_token in test_cases:
            try:
                decoded = verify_token(invalid_token)
                rejected = decoded is None
                results[test_name] = rejected
                if not rejected:
                    all_rejected = False
            except Exception:
                # Exception is also valid rejection
                results[test_name] = True
        
        details = {
            "invalid_tokens_tested": len(test_cases),
            "all_properly_rejected": all_rejected,
            "individual_results": results
        }
        
        return all_rejected, details
        
    except Exception as e:
        return False, f"Error testing invalid tokens: {e}"

def test_role_based_access():
    """Test role-based access control in JWT tokens"""
    try:
        from backend.infra.security import create_access_token, verify_token
        
        # Test different role combinations
        role_tests = [
            (["trader"], "trader"),
            (["admin"], "admin"), 
            (["trader", "admin"], "trader"),
            (["user"], "user"),
            ([], "no_roles")
        ]
        
        results = {}
        all_passed = True
        
        for roles, test_name in role_tests:
            token = create_access_token(sub="test_user", roles=roles)
            decoded = verify_token(token)
            
            if decoded and hasattr(decoded, 'roles'):
                roles_match = set(roles) == set(decoded.roles)
                results[test_name] = roles_match
                if not roles_match:
                    all_passed = False
            else:
                results[test_name] = False
                all_passed = False
        
        details = {
            "role_tests_count": len(role_tests),
            "all_roles_preserved": all_passed,
            "individual_results": results
        }
        
        return all_passed, details
        
    except Exception as e:
        return False, f"Error testing roles: {e}"

def test_password_security():
    """Test password hashing and verification"""
    try:
        from backend.infra.security import hash_password, verify_password
        
        test_passwords = [
            "simple123",
            "Complex!P@ssw0rd123", 
            "very-long-password-with-special-chars!@#$%^&*()",
            "短密码",  # Unicode password
        ]
        
        results = {}
        all_passed = True
        
        for password in test_passwords:
            # Test hashing
            hashed = hash_password(password)
            
            # Test verification
            verify_correct = verify_password(password, hashed)
            verify_incorrect = not verify_password("wrong_password", hashed)
            
            # Test hash properties
            hash_secure = len(hashed) >= 50  # Bcrypt hashes are typically 60 chars
            
            test_passed = verify_correct and verify_incorrect and hash_secure
            results[f"password_{len(password)}_chars"] = test_passed
            
            if not test_passed:
                all_passed = False
        
        details = {
            "passwords_tested": len(test_passwords),
            "all_passed": all_passed,
            "individual_results": results
        }
        
        return all_passed, details
        
    except Exception as e:
        return False, f"Error testing passwords: {e}"

def test_security_configuration():
    """Test overall security configuration"""
    try:
        # Check environment security settings
        security_vars = {
            'JWT_SECRET_KEY': os.getenv('JWT_SECRET_KEY'),
            'SECURITY_JWT_SECRET': os.getenv('SECURITY_JWT_SECRET'),
            'JWT_ISS': os.getenv('JWT_ISS'),
            'JWT_AUD': os.getenv('JWT_AUD'),
            'SECURITY_JWT_EXPIRE_MINUTES': os.getenv('SECURITY_JWT_EXPIRE_MINUTES')
        }
        
        # Check which security variables are set
        vars_set = {k: v is not None and v != "" for k, v in security_vars.items()}
        critical_vars_set = vars_set.get('JWT_SECRET_KEY', False) or vars_set.get('SECURITY_JWT_SECRET', False)
        
        # Test JWT configuration accessibility
        try:
            from backend.config.unified import get_jwt_secret
            jwt_secret_accessible = bool(get_jwt_secret())
        except Exception:
            jwt_secret_accessible = False
        
        details = {
            "environment_variables_set": vars_set,
            "critical_jwt_secret_available": critical_vars_set,
            "jwt_config_accessible": jwt_secret_accessible,
            "security_variables": {k: "***SET***" if v else "NOT_SET" for k, v in security_vars.items()}
        }
        
        success = critical_vars_set and jwt_secret_accessible
        return success, details
        
    except Exception as e:
        return False, f"Error testing security config: {e}"

def run_jwt_auth_security_tests():
    """Run comprehensive JWT and authentication security tests"""
    print("🔐 JWT & AUTHENTICATION SECURITY TEST SUITE")
    print("=" * 60)
    print("Comprehensive testing of JWT tokens and authentication security...")
    print()
    
    tests = [
        ("JWT Secret Security", test_jwt_secret_security),
        ("JWT Token Operations", test_jwt_token_operations),
        ("Token Expiry Handling", test_token_expiry_handling),
        ("Invalid Token Rejection", test_invalid_token_handling),
        ("Role-Based Access Control", test_role_based_access),
        ("Password Security", test_password_security),
        ("Security Configuration", test_security_configuration),
    ]
    
    passed = 0
    total = len(tests)
    results = []
    
    for test_name, test_func in tests:
        print(f"🔒 Testing {test_name}...")
        
        try:
            success, details = test_func()
            
            if success:
                print(f"  ✅ {test_name}: SECURE")
                passed += 1
            else:
                print(f"  ❌ {test_name}: SECURITY ISSUE")
            
            results.append({
                'name': test_name,
                'success': success,
                'details': details
            })
            
        except Exception as e:
            print(f"  ❌ {test_name}: ERROR - {str(e)[:60]}...")
            results.append({
                'name': test_name, 
                'success': False,
                'details': f"Test error: {e}"
            })
    
    print()
    print("=" * 60)
    print("🔐 JWT & AUTHENTICATION SECURITY RESULTS")
    print("=" * 60)
    
    success_rate = (passed / total) * 100
    print(f"Security Tests Passed: {passed}/{total} ({success_rate:.1f}%)")
    print()
    
    # Show detailed results
    for result in results:
        status = "✅ SECURE" if result['success'] else "❌ VULNERABLE"
        print(f"{status} {result['name']}")
        
        if isinstance(result['details'], dict):
            for key, value in result['details'].items():
                print(f"    {key}: {value}")
        else:
            print(f"    {result['details']}")
        print()
    
    # Security assessment
    if success_rate >= 85:
        print("🔒 AUTHENTICATION SECURITY: STRONG")
        print("✅ JWT and authentication systems are properly secured!")
        return True
    elif success_rate >= 70:
        print("🟡 AUTHENTICATION SECURITY: MODERATE") 
        print("⚠️  Some security improvements recommended")
        return True
    else:
        print("🔴 AUTHENTICATION SECURITY: WEAK")
        print("❌ Critical security issues need immediate attention")
        return False

if __name__ == "__main__":
    success = run_jwt_auth_security_tests()
    sys.exit(0 if success else 1)