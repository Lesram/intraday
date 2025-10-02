import os
import requests
import json

# Test 1: Login to get token
print("🧪 Testing authentication flow...")
print(f"Server health check...")
health_response = requests.get("http://localhost:8000/health")
print(f"Health: {health_response.status_code} - {health_response.json()}")

print(f"\nTesting login...")
login_data = {"username": "admin", "password": "admin123"}
login_response = requests.post(
    "http://localhost:8000/auth/login",
    data=login_data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

if login_response.status_code == 200:
    login_result = login_response.json()
    token = login_result["access_token"]
    print(f"✅ Login successful, token: {token[:20]}...")
    
    # Test 2: Use token to call protected endpoint
    print(f"\nTesting order execution with token...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    order_payload = {
        "symbol": "AAPL",
        "lookback": 200,
        "size_mode": "fixed", 
        "fixed_qty": 10
    }
    
    order_response = requests.post(
        "http://localhost:8000/api/v1/signals/act/",
        json=order_payload,
        headers=headers
    )
    
    print(f"Order response status: {order_response.status_code}")
    if order_response.status_code == 200:
        print("✅ SUCCESS! Order execution worked!")
        print(json.dumps(order_response.json(), indent=2))
    else:
        print(f"❌ Order execution failed")
        print(f"Response: {order_response.text}")
        
        # Check if it's a JWT issue by examining the error
        if "401" in str(order_response.status_code):
            print("\n🔍 JWT Token validation issue detected")
            print("Server likely missing SECURITY_JWT_SECRET environment variable")
else:
    print(f"❌ Login failed: {login_response.status_code} - {login_response.text}")