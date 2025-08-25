#!/usr/bin/env python3
"""
Phase 3: Quick Coverage - OpenAPI and Documentation Endpoints
Fast, deterministic test for API documentation endpoints
"""

import os
import sys
from threading import Timer
import atexit

# Built-in anti-stall protection
TIMEOUT = 30
def _emergency_exit():
    print(f"\n🚨 TEST TIMEOUT: Killed after {TIMEOUT}s")
    os._exit(1)

timer = Timer(TIMEOUT, _emergency_exit)
timer.daemon = True
timer.start()
atexit.register(lambda: timer.cancel() if timer.is_alive() else None)

# Light mode environment
os.environ.setdefault("DISABLE_ML", "1")

# Add current directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.api.factory import create_app
from fastapi.testclient import TestClient

def test_openapi_and_docs():
    """Test that OpenAPI schema and documentation endpoints work."""
    app = create_app(light_mode=True)  # Force light mode
    with TestClient(app) as c:
        # Test OpenAPI schema endpoint
        response = c.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Test Swagger UI docs
        response = c.get("/docs")
        assert response.status_code == 200
        
        # Test ReDoc documentation
        response = c.get("/redoc")
        assert response.status_code == 200

if __name__ == "__main__":
    print("🔍 Testing OpenAPI and documentation endpoints...")
    test_openapi_and_docs()
    print("✅ OpenAPI and docs endpoints working")
    timer.cancel()
    print("⏰ Test completed successfully")
