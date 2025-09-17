#!/usr/bin/env python3
"""
Test API Authentication Without Server
Direct testing of authentication components
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

from backend.config.settings import settings
from backend.infra.security import verify_token, create_access_token
from backend.infra.users import UserRepository
from backend.api.auth import router as auth_router

# Create a simple test app
app = FastAPI(title="Authentication Test API")
app.include_router(auth_router)

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    try:
        claims = verify_token(token)
        return {"username": claims.sub, "roles": claims.roles}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Authentication Test API", "status": "running"}

@app.get("/protected")
async def protected_endpoint(current_user=Depends(get_current_user)):
    """Protected endpoint that requires authentication."""
    return {
        "message": "This is a protected endpoint",
        "user": current_user,
        "timestamp": "2025-09-16"
    }

@app.get("/api/v1/trading/signals")
async def get_trading_signals(current_user=Depends(get_current_user)):
    """Mock trading signals endpoint."""
    return {
        "signals": [
            {"symbol": "AAPL", "action": "BUY", "confidence": 0.85},
            {"symbol": "MSFT", "action": "HOLD", "confidence": 0.72}
        ],
        "user": current_user["username"],
        "timestamp": "2025-09-16"
    }

@app.get("/api/v1/portfolio/status") 
async def get_portfolio_status(current_user=Depends(get_current_user)):
    """Mock portfolio status endpoint."""
    return {
        "portfolio_value": 102309.30,
        "buying_power": 129894.43,
        "positions": ["AAPL", "MSFT", "QQQ", "SPY"],
        "user": current_user["username"],
        "timestamp": "2025-09-16"
    }

def test_auth_manually():
    """Test authentication manually without HTTP requests."""
    print("🧪 Manual Authentication Test")
    print("=" * 40)
    
    # Test user repository
    user_repo = UserRepository()
    user = user_repo.authenticate_user("admin", "admin123")
    
    if user:
        print(f"✅ User authenticated: {user.username}")
        
        # Create token
        token = create_access_token(user.username, user.roles)
        print(f"✅ Token created: {token[:50]}...")
        
        # Verify token  
        try:
            claims = verify_token(token)
            print(f"✅ Token verified: {claims.sub} with roles {claims.roles}")
            return token
        except Exception as e:
            print(f"❌ Token verification failed: {e}")
    else:
        print("❌ User authentication failed")
    
    return None

if __name__ == "__main__":
    # Test authentication manually first
    token = test_auth_manually()
    
    if token:
        print(f"\n🚀 Starting test server on port 8001...")
        print(f"📋 Test endpoints:")
        print(f"   • Login: POST http://localhost:8001/auth/login")
        print(f"   • Protected: GET http://localhost:8001/protected")
        print(f"   • Signals: GET http://localhost:8001/api/v1/trading/signals")
        print(f"   • Portfolio: GET http://localhost:8001/api/v1/portfolio/status")
        print(f"\n🔑 Test token: {token}")
        print(f"\n📖 Test with curl:")
        print(f'curl -H "Authorization: Bearer {token}" http://localhost:8001/protected')
        
        # Start the server on a different port
        uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
    else:
        print("❌ Authentication test failed. Please check the setup.")
        sys.exit(1)