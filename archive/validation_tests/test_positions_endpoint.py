#!/usr/bin/env python3
"""
Test the positions endpoint with real authentication.
"""

import requests


def test_positions_endpoint():
    """Test the /api/v1/positions endpoint."""
    base_url = "http://localhost:8000"
    
    print("Testing Positions Endpoint...")
    print("=" * 40)
    
    # Test 1: Without authentication (should return 401)
    print("1. Testing without authentication...")
    try:
        response = requests.get(f"{base_url}/api/v1/positions/", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 401:
            print("   ✅ Correctly returns 401 without auth")
        else:
            print(f"   ❌ Expected 401, got {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: With authentication (should return 200)
    print("\n2. Testing with authentication...")
    try:
        # Get token first
        login_resp = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5
        )
        
        if login_resp.status_code == 200:
            token = login_resp.json()["access_token"]
            
            # Test positions endpoint with token
            positions_resp = requests.get(
                f"{base_url}/api/v1/positions/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5
            )
            
            print(f"   Status: {positions_resp.status_code}")
            if positions_resp.status_code == 200:
                positions = positions_resp.json()
                print(f"   ✅ Got {len(positions)} positions")
                
                # Show sample position
                if positions:
                    sample = positions[0]
                    print(f"   Sample: {sample['symbol']} - {sample['qty']} shares @ ${sample['avg_price']}")
            else:
                print(f"   ❌ Expected 200, got {positions_resp.status_code}")
                print(f"   Response: {positions_resp.text}")
        else:
            print(f"   ❌ Login failed: {login_resp.status_code}")
            
    except Exception as e:
        print(f"   Error: {e}")


if __name__ == "__main__":
    test_positions_endpoint()