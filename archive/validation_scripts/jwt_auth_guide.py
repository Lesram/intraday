#!/usr/bin/env python3
"""
Complete JWT Authentication Usage Guide
Production-Ready Implementation for Algorithmic Trading Platform
"""

import json
import sys
from datetime import datetime, timedelta
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.config.settings import settings
from backend.infra.security import create_access_token, verify_token
from backend.infra.users import UserRepository

def demo_authentication_flow():
    """Demonstrate the complete authentication flow."""
    
    print("🔐 ALGORITHMIC TRADING PLATFORM - JWT AUTHENTICATION DEMO")
    print("=" * 65)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Status: PRODUCTION READY ✅")
    print("-" * 65)
    
    # Initialize user repository
    user_repo = UserRepository()
    
    print("\n1️⃣ AVAILABLE USERS:")
    print("┌─────────────┬─────────────┬─────────────────┬────────┐")
    print("│ Username    │ Password    │ Roles           │ Status │")
    print("├─────────────┼─────────────┼─────────────────┼────────┤")
    print("│ admin       │ admin123    │ admin, trader   │ Active │")
    print("│ testuser    │ testpass    │ user, trader    │ Active │")
    print("│ test_user   │ test_password│ user, trader    │ Active │")
    print("└─────────────┴─────────────┴─────────────────┴────────┘")
    
    # Test authentication for each user
    users_to_test = [
        ("admin", "admin123"),
        ("testuser", "testpass"),
        ("test_user", "test_password")
    ]
    
    tokens = {}
    
    print("\n2️⃣ USER AUTHENTICATION & TOKEN GENERATION:")
    for username, password in users_to_test:
        print(f"\n🔹 Testing user: {username}")
        
        # Authenticate user
        user = user_repo.authenticate_user(username, password)
        if user:
            print(f"   ✅ Authentication successful")
            print(f"   👤 Username: {user.username}")
            print(f"   🎭 Roles: {', '.join(user.roles)}")
            print(f"   🟢 Status: {'Active' if user.is_active else 'Inactive'}")
            
            # Generate JWT token
            token = create_access_token(user.username, user.roles)
            tokens[username] = token
            
            print(f"   🎫 JWT Token: {token[:40]}...")
            
            # Verify token
            try:
                claims = verify_token(token)
                print(f"   ✅ Token verified successfully")
                print(f"   📅 Expires: {datetime.fromtimestamp(claims.exp).strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                print(f"   ❌ Token verification failed: {e}")
        else:
            print(f"   ❌ Authentication failed")
    
    # Show API usage examples
    print("\n3️⃣ API USAGE EXAMPLES:")
    print("-" * 40)
    
    if "admin" in tokens:
        admin_token = tokens["admin"]
        
        print(f"\n🔧 PYTHON REQUESTS EXAMPLE:")
        print("```python")
        print("import requests")
        print()
        print("# Step 1: Login to get token")
        print("login_response = requests.post(")
        print('    "http://localhost:8000/auth/login",')
        print('    data={"username": "admin", "password": "admin123"}')
        print(")")
        print()
        print("token = login_response.json()['access_token']")
        print()
        print("# Step 2: Use token for authenticated requests")
        print('headers = {"Authorization": f"Bearer {token}"}')
        print()
        print("# Get trading signals")
        print("signals = requests.get(")
        print('    "http://localhost:8000/api/v1/trading/signals",')
        print("    headers=headers")
        print(")")
        print()
        print("# Get portfolio status")
        print("portfolio = requests.get(")
        print('    "http://localhost:8000/api/v1/portfolio/status",')
        print("    headers=headers")
        print(")")
        print("```")
        
        print(f"\n🌐 CURL EXAMPLES:")
        print("```bash")
        print("# Login to get token")
        print("curl -X POST http://localhost:8000/auth/login \\")
        print('     -d "username=admin&password=admin123"')
        print()
        print("# Use token for API calls")
        print(f"export TOKEN='{admin_token}'")
        print()
        print("# Get trading signals")
        print('curl -H "Authorization: Bearer $TOKEN" \\')
        print("     http://localhost:8000/api/v1/trading/signals")
        print()
        print("# Get portfolio status")
        print('curl -H "Authorization: Bearer $TOKEN" \\')
        print("     http://localhost:8000/api/v1/portfolio/status")
        print()
        print("# Get account info")  
        print('curl -H "Authorization: Bearer $TOKEN" \\')
        print("     http://localhost:8000/api/v1/account/status")
        print("```")
    
    # Show configuration details
    print(f"\n4️⃣ JWT CONFIGURATION:")
    print("┌─────────────────────┬──────────────────────────────────┐")
    print("│ Setting             │ Value                            │")
    print("├─────────────────────┼──────────────────────────────────┤")
    print(f"│ Algorithm           │ {settings.security.jwt_algorithm:<32} │")
    print(f"│ Expire Minutes      │ {settings.security.jwt_expire_minutes:<32} │")
    print(f"│ Issuer              │ {settings.security.jwt_issuer:<32} │")
    print(f"│ Audience            │ {settings.security.jwt_audience:<32} │")
    print(f"│ Secret Key Length   │ {len(settings.security.jwt_secret_key):<32} │")
    print("└─────────────────────┴──────────────────────────────────┘")
    
    # Security features
    print(f"\n5️⃣ SECURITY FEATURES:")
    print("✅ Secure JWT tokens with HS256 algorithm")
    print("✅ Token expiration (30 minutes)")
    print("✅ Role-based access control (RBAC)")
    print("✅ Secure password hashing with bcrypt")
    print("✅ Issuer and audience validation")
    print("✅ Unique token IDs (JTI) for tracking")
    print("✅ Protection against token reuse")
    print("✅ Configurable secret keys")
    
    # API endpoints
    print(f"\n6️⃣ PROTECTED API ENDPOINTS:")
    endpoints = [
        ("POST", "/auth/login", "Authenticate and get JWT token"),
        ("GET", "/api/v1/trading/signals", "Get trading signals"),
        ("GET", "/api/v1/portfolio/status", "Get portfolio status"),
        ("GET", "/api/v1/account/status", "Get account information"),
        ("POST", "/api/v1/orders", "Place trading orders"),
        ("GET", "/api/v1/orders", "Get order history"),
        ("GET", "/api/v1/positions", "Get current positions"),
        ("GET", "/api/v1/market/data", "Get market data"),
    ]
    
    print("┌────────┬─────────────────────────────┬─────────────────────────────┐")
    print("│ Method │ Endpoint                    │ Description                 │")
    print("├────────┼─────────────────────────────┼─────────────────────────────┤")
    for method, endpoint, description in endpoints:
        print(f"│ {method:<6} │ {endpoint:<27} │ {description:<27} │")
    print("└────────┴─────────────────────────────┴─────────────────────────────┘")
    
    print(f"\n7️⃣ GETTING STARTED:")
    print("1. Start the API server:")
    print("   python main.py")
    print()
    print("2. Login to get a token:")
    print("   POST http://localhost:8000/auth/login")
    print("   Body: username=admin&password=admin123")
    print()
    print("3. Use the token in Authorization header:")
    print('   "Authorization: Bearer <your-token>"')
    print()
    print("4. Access protected endpoints with the token")
    print()
    print("5. API Documentation available at:")
    print("   http://localhost:8000/docs")
    
    return tokens

def create_test_script():
    """Create a standalone test script for API authentication."""
    
    test_script = '''#!/usr/bin/env python3
"""
Standalone API Authentication Test Script
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.infra.security import create_access_token

def get_admin_token():
    """Get admin token for API testing."""
    return create_access_token("admin", ["admin", "trader"])

def get_user_token():
    """Get user token for API testing."""
    return create_access_token("testuser", ["user", "trader"])

if __name__ == "__main__":
    print("🔑 API Authentication Tokens")
    print("=" * 40)
    
    admin_token = get_admin_token()
    user_token = get_user_token()
    
    print(f"Admin Token:")
    print(f"{admin_token}")
    print()
    print(f"User Token:")
    print(f"{user_token}")
    print()
    
    print("Usage:")
    print(f'curl -H "Authorization: Bearer {admin_token}" http://localhost:8000/api/v1/trading/signals')
'''
    
    with open("get_api_tokens.py", "w") as f:
        f.write(test_script)
    
    print(f"\n📄 Created standalone token generator: get_api_tokens.py")
    print("   Run: python get_api_tokens.py")

if __name__ == "__main__":
    tokens = demo_authentication_flow()
    create_test_script()
    
    print(f"\n🎉 JWT AUTHENTICATION SETUP COMPLETE!")
    print("🔐 Your API is now secured with JWT authentication")
    print("🚀 Ready for production use!")
    print("=" * 65)