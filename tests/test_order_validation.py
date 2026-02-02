"""
Test Pre-Trade Validation Endpoint
Quick test to verify the new /orders/validate endpoint works correctly

NOTE: This is an INTEGRATION test that requires a running backend server.
Run the server first, then execute this test.
"""

import pytest
import requests
import json


def _server_is_running() -> bool:
    """Check if the backend server is running."""
    try:
        resp = requests.get("http://localhost:8000/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _auth_works() -> bool:
    """Check if test auth credentials work with the live server."""
    try:
        resp = requests.post(
            "http://localhost:8000/auth/login",
            json={"username": "admin@example.com", "password": "Admin123!@#"},
            timeout=5
        )
        return resp.status_code == 200
    except Exception:
        return False


# Mark all tests in this module as requiring live server with working auth
pytestmark = pytest.mark.skipif(
    not _server_is_running() or not _auth_works(),
    reason="Order validation integration test requires running server at localhost:8000 with working auth. "
           "Start server with 'python start_backend.py' and ensure admin user exists."
)

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TEST_USER = {
    "username": "admin@example.com",
    "password": "Admin123!@#"
}

def login():
    """Login and get auth token"""
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        json=TEST_USER
    )
    response.raise_for_status()
    return response.json()["access_token"]

def validate_order(token, order_data):
    """Validate an order via the API"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        f"{API_BASE_URL}/orders/validate",
        json=order_data,
        headers=headers
    )
    return response


@pytest.fixture
def live_token():
    """Get a real token from the running server."""
    return login()


def test_validate_order(live_token: str):
    """Test order validation endpoint with various scenarios"""
    # Test Case 1: Valid Order
    order_data = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "orderType": "market"
    }
    response = validate_order(live_token, order_data)
    assert response.status_code == 200
    result = response.json()
    assert "valid" in result
    assert "checks" in result

def main():
    print("🔐 Logging in...")
    try:
        token = login()
        print("✅ Login successful!\n")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return
    
    # Test Case 1: Valid Order
    print("=" * 60)
    print("TEST 1: Valid Order (AAPL, 10 shares)")
    print("=" * 60)
    order_data = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "orderType": "market"
    }
    
    response = validate_order(token, order_data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Valid: {result['valid']}")
        est_cost = result.get('estimated_cost')
        est_bp = result.get('estimated_buying_power_after')
        print(f"Estimated Cost: ${est_cost:,.2f}" if est_cost else "Estimated Cost: N/A")
        print(f"Buying Power After: ${est_bp:,.2f}" if est_bp else "Buying Power After: N/A")
        print("\nChecks:")
        for check in result['checks']:
            icon = "✅" if check['passed'] else "❌"
            print(f"  {icon} {check['name']}: {check['message']}")
        
        if result['warnings']:
            print("\n⚠️  Warnings:")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        if result['errors']:
            print("\n❌ Errors:")
            for error in result['errors']:
                print(f"  - {error}")
    else:
        print(f"❌ Error: {response.text}")
    
    # Test Case 2: Large Order (Should trigger warnings)
    print("\n" + "=" * 60)
    print("TEST 2: Large Order (AAPL, 1000 shares - should warn about concentration)")
    print("=" * 60)
    order_data = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 1000,
        "orderType": "limit",
        "limitPrice": 175.0
    }
    
    response = validate_order(token, order_data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Valid: {result['valid']}")
        print(f"Estimated Cost: ${result.get('estimated_cost', 0):,.2f}")
        print("\nChecks:")
        for check in result['checks']:
            icon = "✅" if check['passed'] else "❌" if check['severity'] == 'error' else "⚠️ "
            print(f"  {icon} {check['name']}: {check['message']}")
        
        if result['warnings']:
            print("\n⚠️  Warnings:")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        if result['errors']:
            print("\n❌ Errors:")
            for error in result['errors']:
                print(f"  - {error}")
    else:
        print(f"❌ Error: {response.text}")
    
    # Test Case 3: Invalid Order (No symbol)
    print("\n" + "=" * 60)
    print("TEST 3: Invalid Order (No symbol - should fail)")
    print("=" * 60)
    order_data = {
        "symbol": "",
        "side": "buy",
        "quantity": 10,
        "orderType": "market"
    }
    
    response = validate_order(token, order_data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Valid: {result['valid']}")
        print("\nChecks:")
        for check in result['checks']:
            icon = "✅" if check['passed'] else "❌"
            print(f"  {icon} {check['name']}: {check['message']}")
        
        if result['errors']:
            print("\n❌ Errors:")
            for error in result['errors']:
                print(f"  - {error}")
    else:
        print(f"❌ Error: {response.text}")
    
    # Test Case 4: Huge Order (Should fail - exceeds limits)
    print("\n" + "=" * 60)
    print("TEST 4: Huge Order (10000 shares - should exceed position limit)")
    print("=" * 60)
    order_data = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10000,
        "orderType": "market"
    }
    
    response = validate_order(token, order_data)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Valid: {result['valid']}")
        print(f"Estimated Cost: ${result.get('estimated_cost', 0):,.2f}")
        print("\nChecks:")
        for check in result['checks']:
            icon = "✅" if check['passed'] else "❌"
            print(f"  {icon} {check['name']}: {check['message']}")
        
        if result['errors']:
            print("\n❌ Errors:")
            for error in result['errors']:
                print(f"  - {error}")
    else:
        print(f"❌ Error: {response.text}")
    
    print("\n" + "=" * 60)
    print("✅ All validation tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()
