#!/usr/bin/env python3
"""
🎯 LIVE SERVER WORKING ENDPOINTS TEST
=======================================
Test the working endpoints with proper data formats
"""

import asyncio
import httpx
import json
from datetime import datetime

async def test_working_endpoints():
    """Test the working endpoints with proper data"""
    
    print("🎯 LIVE SERVER WORKING ENDPOINTS TEST")
    print("=======================================")
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # Authenticate
        print("🔐 Authenticating...")
        auth_response = await client.post(
            f"{base_url}/api/v1/auth/login",
            data={"username": "admin", "password": "admin123"}
        )
        
        token = auth_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  ✅ Authenticated")
        
        # Test working signals endpoint
        print("\n📡 Testing Trading Signals Endpoint...")
        signals_data = {
            "symbol": "AAPL",
            "signal_type": "BUY",
            "confidence": 0.85,
            "action": "BUY",
            "quantity": 1,
            "price": 150.0
        }
        
        signals_response = await client.post(
            f"{base_url}/api/v1/signals/",
            json=signals_data,
            headers=headers
        )
        
        print(f"  Status: {signals_response.status_code}")
        if signals_response.status_code == 200:
            print(f"  ✅ Signal created successfully!")
            result = signals_response.json()
            print(f"  Response: {result}")
        else:
            print(f"  Response: {signals_response.text}")
            
        # Test working orders endpoint
        print("\n📦 Testing Orders Endpoint...")
        order_data = {
            "symbol": "AAPL",
            "side": "buy",  # Note: must be lowercase
            "qty": 1,
            "type": "market",
            "time_in_force": "day"
        }
        
        order_response = await client.post(
            f"{base_url}/api/v1/orders/",
            json=order_data,
            headers=headers
        )
        
        print(f"  Status: {order_response.status_code}")
        if order_response.status_code == 200:
            print(f"  ✅ Order created successfully!")
            result = order_response.json()
            print(f"  Response: {result}")
        else:
            print(f"  Response: {order_response.text}")
            
        # Test user profile endpoint
        print("\n👤 Testing User Profile...")
        profile_response = await client.get(
            f"{base_url}/api/v1/auth/me",
            headers=headers
        )
        
        print(f"  Status: {profile_response.status_code}")
        if profile_response.status_code == 200:
            print(f"  ✅ Profile retrieved!")
            result = profile_response.json()
            print(f"  User: {result}")
            
        # Test health endpoint
        print("\n❤️ Testing Health...")
        health_response = await client.get(f"{base_url}/health")
        
        print(f"  Status: {health_response.status_code}")
        if health_response.status_code == 200:
            print(f"  ✅ Server healthy!")
            result = health_response.json()
            print(f"  Health: {result}")

if __name__ == "__main__":
    asyncio.run(test_working_endpoints())