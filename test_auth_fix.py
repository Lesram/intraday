"""
Quick test to verify JWT authentication is working properly.
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from fastapi.testclient import TestClient
from backend.api.factory import create_app
from backend.infra.security import create_access_token

def test_jwt_auth():
    """Test JWT authentication with real tokens."""
    app = create_app()
    client = TestClient(app)
    
    # Create a real JWT token
    token = create_access_token(
        subject="testuser", roles=["user", "trader"]
    )
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test without auth first
    response = client.post('/api/v1/orders/submit', json={'symbol': 'AAPL', 'qty': 100})
    print(f'No auth: {response.status_code} - {response.text}')
    
    # Test with real JWT token
    response = client.post('/api/v1/orders/submit', json={'symbol': 'AAPL', 'qty': 100}, headers=headers)
    print(f'With real JWT: {response.status_code} - {response.text[:200]}')
    
    # Test large payload
    large_data = {"data": "x" * 10000, "symbol": "AAPL", "qty": 100}
    response = client.post('/api/v1/orders/submit', json=large_data, headers=headers)
    print(f'Large payload: {response.status_code} - {response.text[:200]}')

if __name__ == "__main__":
    test_jwt_auth()