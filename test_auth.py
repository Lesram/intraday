#!/usr/bin/env python3
"""
Quick authentication test script.
"""

import requests
import json

def test_authentication():
    """Test the authentication endpoints."""
    base_url = "http://localhost:8000"
    
    print("Testing Authentication Flow...")
    print("=" * 40)
    
    # Test 1: Login with valid credentials
    print("1. Testing login with admin/admin123...")
    try:
        login_resp = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5
        )
        print(f"   Status: {login_resp.status_code}")
        if login_resp.status_code == 200:
            login_data = login_resp.json()
            token = login_data.get("access_token")
            print(f"   Token: {token[:50]}..." if token else "   No token received")
            
            # Test 2: Verify token
            if token:
                print("\n2. Testing token verification...")
                verify_resp = requests.get(
                    f"{base_url}/api/v1/auth/verify",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5
                )
                print(f"   Status: {verify_resp.status_code}")
                print(f"   Response: {verify_resp.text}")
        else:
            print(f"   Error: {login_resp.text}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Try staging API key if available
    print("\n3. Testing staging API key...")
    import os
    staging_key = os.environ.get("STAGING_API_KEY", "test-staging-key")
    try:
        verify_resp = requests.get(
            f"{base_url}/api/v1/auth/verify",
            headers={"X-API-Key": staging_key},
            timeout=5
        )
        print(f"   Status: {verify_resp.status_code}")
        print(f"   Response: {verify_resp.text}")
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_authentication()