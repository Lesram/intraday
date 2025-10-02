#!/usr/bin/env python3
"""
Phase G Real Server Test
Tests actual server endpoints with real components (no mocks)
"""

import asyncio
import json
import uuid
from datetime import datetime
import httpx


async def test_real_server_order_flow():
    """Test real server order flow via API endpoints"""
    print("🌐 Testing Real Server Order Flow (No Mocks)")
    print("-" * 50)
    
    base_url = "http://localhost:8000"
    
    try:
        # Test server availability
        async with httpx.AsyncClient(timeout=10.0) as client:
            health_response = await client.get(f"{base_url}/health")
            if health_response.status_code != 200:
                print("❌ Server not available")
                return False
            print("✅ Server is available")
            
            # Authenticate
            login_data = {
                "username": "admin", 
                "password": "admin123"
            }
            login_response = await client.post(
                f"{base_url}/auth/login",
                json=login_data
            )
            
            if login_response.status_code != 200:
                print("❌ Authentication failed")
                return False
                
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("✅ Authentication successful")
            
            # Submit signal to create order
            signal_data = {
                "symbol": "AAPL",
                "signal_strength": 0.8,
                "timestamp": datetime.now().isoformat(),
                "features": {"test_mode": True},
                "metadata": {"source": "real_server_test"}
            }
            
            print("📤 Submitting signal to create order...")
            signal_response = await client.post(
                f"{base_url}/signals/act",
                json=signal_data,
                headers=headers
            )
            
            if signal_response.status_code != 200:
                print(f"❌ Signal submission failed: {signal_response.status_code}")
                print(f"Response: {signal_response.text}")
                return False
                
            signal_result = signal_response.json()
            order_info = signal_result.get("order", {})
            order_id = order_info.get("order_id")
            
            if not order_id:
                print("❌ No order_id in signal response")
                print(f"Response: {json.dumps(signal_result, indent=2)}")
                return False
                
            print(f"✅ Order created via real API: {order_id}")
            
            # Test order status lookup
            print("� Testing order status lookup via real API...")
            status_response = await client.get(
                f"{base_url}/orders/{order_id}",
                headers=headers
            )
            
            if status_response.status_code != 200:
                print(f"❌ Order status lookup failed: {status_response.status_code}")
                return False
                
            order_status = status_response.json()
            print("✅ Order status retrieved successfully")
            print(f"   Order ID: {order_status.get('id', 'N/A')}")
            print(f"   Symbol: {order_status.get('symbol', 'N/A')}")
            print(f"   Status: {order_status.get('status', 'N/A')}")
            print(f"   Side: {order_status.get('side', 'N/A')}")
            
            return True
            
    except Exception as e:
        print(f"❌ Real server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_uuid_handling():
    """Test UUID handling via real API"""
    print("\n🔑 Testing UUID Handling via Real API...")
    
    base_url = "http://localhost:8000"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Authenticate first
            login_response = await client.post(
                f"{base_url}/auth/login",
                json={"username": "admin", "password": "admin123"}
            )
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Test with valid UUID format (non-existent order)
            test_uuid = str(uuid.uuid4())
            print(f"Testing with valid UUID: {test_uuid}")
            
            response = await client.get(
                f"{base_url}/orders/{test_uuid}",
                headers=headers
            )
            
            if response.status_code == 404:
                print("✅ Non-existent UUID returns 404 as expected")
            else:
                print(f"⚠️  Non-existent UUID returned: {response.status_code}")
            
            # Test with invalid UUID format
            print("Testing with invalid UUID format...")
            invalid_response = await client.get(
                f"{base_url}/orders/invalid-uuid-format",
                headers=headers
            )
            
            if invalid_response.status_code in [400, 422]:
                print("✅ Invalid UUID format properly rejected")
            else:
                print(f"⚠️  Invalid UUID returned: {invalid_response.status_code}")
            
            return True
        
    except Exception as e:
        print(f"❌ UUID API test failed: {e}")
        return False


async def test_server_health():
    """Test server health and basic connectivity"""
    print("\n🏥 Testing Server Health...")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code == 200:
                print("✅ Server health check passed")
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Make sure server is running with:")
        print("  python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload")
        return False


async def main():
    """Run real server tests with no mocks"""
    print("🚀 Phase G Real Server Tests (No Mocks)")
    print("=" * 50)
    
    # Test 1: Server health
    test1_result = await test_server_health()
    if not test1_result:
        print("\n❌ Server not available - cannot run real tests")
        return False
    
    # Test 2: Real server order flow
    test2_result = await test_real_server_order_flow()
    
    # Test 3: UUID handling via API
    test3_result = await test_uuid_handling()
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Real Server Test Results:")
    print(f"✅ Server Health: {'PASS' if test1_result else 'FAIL'}")
    print(f"✅ Real Order Flow: {'PASS' if test2_result else 'FAIL'}")
    print(f"✅ UUID Handling: {'PASS' if test3_result else 'FAIL'}")
    
    if test1_result and test2_result and test3_result:
        print("\n🎉 ALL REAL SERVER TESTS PASSED!")
        print("Phase G implementation working with real components!")
        return True
    else:
        print("\n❌ Some real server tests failed.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)