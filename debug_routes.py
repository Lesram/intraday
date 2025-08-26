#!/usr/bin/env python3

"""Debug script to see what routes are actually available"""

from backend.api.factory import create_app
from fastapi.testclient import TestClient

def debug_available_routes():
    """Debug what routes are actually available in the app"""
    
    # Create test app
    app = create_app()
    
    # Print all routes
    print("=== Available Routes ===")
    for route in app.routes:
        print(f"{route.methods} {route.path}")
        
    # Test specific endpoints
    client = TestClient(app)
    
    print("\n=== Testing Specific Routes ===")
    
    endpoints_to_test = [
        "/portfolio/positions",
        "/api/v1/portfolio/positions", 
        "/positions",
        "/api/v1/positions"
    ]
    
    for endpoint in endpoints_to_test:
        try:
            response = client.get(endpoint)
            print(f"GET {endpoint}: {response.status_code}")
        except Exception as e:
            print(f"GET {endpoint}: ERROR - {e}")

if __name__ == "__main__":
    debug_available_routes()
