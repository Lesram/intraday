#!/usr/bin/env python3
"""
🔧 LIVE SERVER ENDPOINT DEBUGGING
==============================================
Debug the 307 redirects for trading endpoints
"""

import asyncio
import httpx
import json
from datetime import datetime

async def debug_server_endpoints():
    """Debug server endpoints to understand 307 redirects"""
    
    print("🔧 LIVE SERVER ENDPOINT DEBUGGING")
    print("==============================================")
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # First authenticate to get token
        print("🔐 Authenticating to get JWT token...")
        auth_response = await client.post(
            f"{base_url}/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"}
        )
        
        if auth_response.status_code == 200:
            token_data = auth_response.json()
            token = token_data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print(f"  ✅ Token obtained: {token[:50]}...")
        else:
            print(f"  ❌ Auth failed: {auth_response.status_code}")
            return
            
        # Test different endpoint variations
        endpoints_to_test = [
            # Different variations of trading signal endpoint
            "/api/v1/signals",
            "/api/v1/signals/",  # with trailing slash
            "/api/v1/trading/signals",
            "/api/v1/trading/signals/",
            "/signals",
            "/trading/signals",
            
            # Different variations of order endpoint
            "/api/v1/orders", 
            "/api/v1/orders/",  # with trailing slash
            "/api/v1/trading/orders",
            "/api/v1/trading/orders/",
            "/orders",
            "/trading/orders",
            
            # Test some known endpoints
            "/api/v1/health",
            "/health",
            "/api/v1/auth/me",
            "/me",
        ]
        
        print("\n📍 Testing endpoint variations...")
        print("=" * 80)
        
        for endpoint in endpoints_to_test:
            try:
                print(f"\n🌐 Testing: {endpoint}")
                
                # Test GET request
                response = await client.get(f"{base_url}{endpoint}", headers=headers)
                print(f"  GET  {response.status_code}: {endpoint}")
                
                if response.status_code == 307:
                    location = response.headers.get('location', 'No location header')
                    print(f"    🔄 Redirect to: {location}")
                elif response.status_code == 200:
                    print(f"    ✅ Success")
                elif response.status_code == 404:
                    print(f"    ❓ Not found")
                elif response.status_code == 401:
                    print(f"    🔒 Unauthorized")
                elif response.status_code == 422:
                    print(f"    📝 Validation error")
                else:
                    print(f"    ⚠️  Status: {response.status_code}")
                
                # For trading endpoints, also test POST
                if any(word in endpoint for word in ['signals', 'orders']):
                    test_data = {
                        "symbol": "AAPL",
                        "action": "BUY",
                        "quantity": 1,
                        "price": 150.0
                    }
                    
                    post_response = await client.post(
                        f"{base_url}{endpoint}", 
                        json=test_data,
                        headers=headers
                    )
                    print(f"  POST {post_response.status_code}: {endpoint}")
                    
                    if post_response.status_code == 307:
                        location = post_response.headers.get('location', 'No location header')
                        print(f"    🔄 Redirect to: {location}")
                    elif post_response.status_code == 422:
                        try:
                            error_detail = post_response.json()
                            print(f"    📝 Validation: {error_detail}")
                        except:
                            print(f"    📝 Validation error (no JSON)")
                            
            except Exception as e:
                print(f"    ❌ Error: {e}")
                
        print("\n" + "=" * 80)
        print("🔧 Debug complete!")

if __name__ == "__main__":
    asyncio.run(debug_server_endpoints())