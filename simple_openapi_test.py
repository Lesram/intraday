#!/usr/bin/env python3
"""
Simplified Phase 3 Test - OpenAPI Endpoints
ASCII-only version to avoid PowerShell Unicode issues
"""

import os
import sys
from threading import Timer
import atexit

# Built-in protection
TIMEOUT = 30
def _emergency_exit():
    print(f"TIMEOUT: Test killed after {TIMEOUT}s")
    os._exit(1)

timer = Timer(TIMEOUT, _emergency_exit)
timer.daemon = True
timer.start()
atexit.register(lambda: timer.cancel() if timer.is_alive() else None)

# Setup
os.environ.setdefault("DISABLE_ML", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from backend.api.factory import create_app
    from fastapi.testclient import TestClient
    
    print("Testing OpenAPI endpoints...")
    app = create_app(light_mode=True)
    
    with TestClient(app) as c:
        # Test OpenAPI
        resp = c.get("/openapi.json")
        assert resp.status_code == 200
        print("PASS: /openapi.json returns 200")
        
        # Test docs
        resp = c.get("/docs")
        assert resp.status_code == 200
        print("PASS: /docs returns 200")
        
        # Test redoc
        resp = c.get("/redoc")  
        assert resp.status_code == 200
        print("PASS: /redoc returns 200")
    
    print("SUCCESS: OpenAPI test completed")
    timer.cancel()
    
except Exception as e:
    print(f"FAILED: {e}")
    timer.cancel()
    sys.exit(1)
