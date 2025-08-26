#!/usr/bin/env python3

"""Debug script to see the actual registration validation response"""

from fastapi.testclient import TestClient
from backend.api.factory import create_app
import json

def debug_register_validation():
    """Debug what the register endpoint actually returns for validation errors"""
    
    # Create test client
    app = create_app()
    test_client = TestClient(app)
    
    # Test with invalid email
    payload = {
        "email": "not-an-email",
        "password": "password123"
    }
    
    print("=== Testing invalid email ===")
    response = test_client.post("/auth/register", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {json.dumps(response.json(), indent=2)}")
    
    # Test with short password
    payload = {
        "email": "test@example.com",
        "password": "short"
    }
    
    print("\n=== Testing short password ===")
    response = test_client.post("/auth/register", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {json.dumps(response.json(), indent=2)}")
    
    # Test with missing fields
    payload = {
        "password": "password123"
    }
    
    print("\n=== Testing missing email ===")
    response = test_client.post("/auth/register", json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {json.dumps(response.json(), indent=2)}")

if __name__ == "__main__":
    debug_register_validation()
