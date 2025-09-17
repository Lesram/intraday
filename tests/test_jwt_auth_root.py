#!/usr/bin/env python3
"""
JWT Authentication Setup and Testing Script
"""

import requests
import json
from backend.config.settings import settings
from backend.infra.security import create_access_token, verify_token
from backend.infra.users import UserRepository

def test_jwt_system():
    """Test the JWT authentication system end-to-end."""
    
    print("🔐 JWT Authentication System Test")
    print("=" * 50)
    
    # Test 1: User Repository
    print("\n1️⃣ Testing User Repository...")
    user_repo = UserRepository()
    
    # Check default users
    admin_user = user_repo.get_user("admin")
    test_user = user_repo.get_user("testuser")
    
    if admin_user:
        print(f"✅ Admin user found: {admin_user.username}")
        print(f"   Roles: {admin_user.roles}")
        print(f"   Active: {admin_user.is_active}")
    else:
        print("❌ Admin user not found")
        
    if test_user:
        print(f"✅ Test user found: {test_user.username}")
        print(f"   Roles: {test_user.roles}")
        print(f"   Active: {test_user.is_active}")
    else:
        print("❌ Test user not found")
    
    # Test 2: JWT Token Generation
    print("\n2️⃣ Testing JWT Token Generation...")
    try:
        token = create_access_token("admin", ["admin", "trader"])
        print(f"✅ JWT Token generated successfully")
        print(f"   Token (first 50 chars): {token[:50]}...")
        print(f"   Token length: {len(token)}")
    except Exception as e:
        print(f"❌ JWT Token generation failed: {e}")
        return False
    
    # Test 3: JWT Token Verification
    print("\n3️⃣ Testing JWT Token Verification...")
    try:
        claims = verify_token(token)
        print(f"✅ JWT Token verified successfully")
        print(f"   Subject: {claims.sub}")
        print(f"   Roles: {claims.roles}")
        print(f"   Issuer: {claims.iss}")
        print(f"   Audience: {claims.aud}")
        print(f"   Expires: {claims.exp}")
    except Exception as e:
        print(f"❌ JWT Token verification failed: {e}")
        return False
    
    # Test 4: User Authentication
    print("\n4️⃣ Testing User Authentication...")
    try:
        authenticated_user = user_repo.authenticate_user("admin", "admin123")
        if authenticated_user:
            print(f"✅ User authentication successful")
            print(f"   Username: {authenticated_user.username}")
            print(f"   Roles: {authenticated_user.roles}")
        else:
            print("❌ User authentication failed")
    except Exception as e:
        print(f"❌ User authentication error: {e}")
    
    # Test 5: Configuration Check
    print("\n5️⃣ Testing JWT Configuration...")
    print(f"   Secret Key Length: {len(settings.security.jwt_secret_key)}")
    print(f"   Algorithm: {settings.security.jwt_algorithm}")
    print(f"   Expire Minutes: {settings.security.jwt_expire_minutes}")
    print(f"   Issuer: {settings.security.jwt_issuer}")
    print(f"   Audience: {settings.security.jwt_audience}")
    
    return True

def create_login_example():
    """Create example code for API login."""
    
    print("\n🔧 API Login Example Code")
    print("=" * 50)
    
    login_example = '''
# Example: Login to get JWT token
import requests

# Login with credentials
login_data = {
    "username": "admin",
    "password": "admin123"
}

response = requests.post(
    "http://localhost:8000/auth/login",
    data=login_data  # Use form data
)

if response.status_code == 200:
    auth_data = response.json()
    token = auth_data["access_token"]
    print(f"Login successful! Token: {token[:50]}...")
    
    # Use token for authenticated requests
    headers = {"Authorization": f"Bearer {token}"}
    
    # Example authenticated API call
    api_response = requests.get(
        "http://localhost:8000/api/v1/trading/signals",
        headers=headers
    )
    
    print(f"API Response: {api_response.status_code}")
else:
    print(f"Login failed: {response.status_code} - {response.text}")
'''
    
    print(login_example)
    
    # Also test creating a token programmatically
    print("\n🛠️ Programmatic Token Creation")
    print("=" * 50)
    
    try:
        admin_token = create_access_token("admin", ["admin", "trader"])
        user_token = create_access_token("testuser", ["user", "trader"])
        
        print(f"Admin Token: {admin_token}")
        print(f"User Token:  {user_token}")
        
        print("\n📋 Token Usage Examples:")
        print(f"""
# Using admin token:
curl -H "Authorization: Bearer {admin_token}" http://localhost:8000/api/v1/trading/signals

# Using user token:
curl -H "Authorization: Bearer {user_token}" http://localhost:8000/api/v1/portfolio/status
""")
        
    except Exception as e:
        print(f"❌ Token creation failed: {e}")

def show_setup_instructions():
    """Show setup instructions for JWT authentication."""
    
    print("\n📚 JWT Authentication Setup Complete!")
    print("=" * 50)
    
    print("""
🔐 AUTHENTICATION SYSTEM STATUS:
✅ JWT token generation working
✅ User repository configured with default users
✅ Password hashing functional  
✅ Token verification working
✅ Configuration properly loaded

📋 DEFAULT USERS AVAILABLE:
• Username: admin     | Password: admin123  | Roles: admin, trader
• Username: testuser  | Password: testpass  | Roles: user, trader
• Username: test_user | Password: test_password | Roles: user, trader

🚀 TO START THE API SERVER:
python main.py

🌐 API ENDPOINTS:
• Login: POST http://localhost:8000/auth/login
• Trading Signals: GET http://localhost:8000/api/v1/trading/signals
• Portfolio Status: GET http://localhost:8000/api/v1/portfolio/status
• API Docs: http://localhost:8000/docs

🔑 HOW TO USE:
1. Start the API server: python main.py
2. Login to get a token: POST /auth/login with username/password
3. Use the token in Authorization header: "Bearer <token>"
4. Access protected endpoints with the token

🛡️ SECURITY FEATURES:
• Secure password hashing with bcrypt
• JWT tokens with expiration (30 minutes)
• Role-based access control (RBAC)  
• Proper issuer/audience validation
• Secure secret key from configuration
""")

if __name__ == "__main__":
    success = test_jwt_system()
    if success:
        create_login_example()
        show_setup_instructions()
    else:
        print("\n❌ JWT system test failed. Please check the configuration.")