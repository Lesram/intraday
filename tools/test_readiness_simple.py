#!/usr/bin/env python3
"""Simple readiness validation"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

def test_readiness():
    print("Testing readiness endpoint shapes...")
    
    # Import and create app
    from backend.api.factory import create_app
    from fastapi.testclient import TestClient
    
    app = create_app()
    client = TestClient(app)
    
    # Test readiness endpoint
    response = client.get("/readyz")
    data = response.json()
    
    print(f"Status Code: {response.status_code}")
    print(f"Status: {data.get('status')}")
    print(f"Checks: {data.get('checks')}")
    print(f"Problems: {data.get('problems')}")
    
    # Validate structure
    has_checks = 'checks' in data
    has_problems = 'problems' in data
    
    print(f"Has 'checks' field: {has_checks}")
    print(f"Has 'problems' field: {has_problems}")
    
    if response.status_code == 200:
        print("✅ Readiness returned 200 (healthy)")
        assert data['status'] == 'ready', f"Expected ready, got {data['status']}"
        assert data['problems'] == {}, f"Expected empty problems, got {data['problems']}"
    else:
        print(f"ℹ️ Readiness returned {response.status_code} (degraded)")
        assert data['status'] == 'degraded', f"Expected degraded, got {data['status']}"
        assert isinstance(data['problems'], dict), f"Problems should be dict, got {type(data['problems'])}"
    
    print("✅ All validations passed!")

if __name__ == "__main__":
    test_readiness()
