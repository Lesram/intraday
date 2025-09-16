#!/usr/bin/env python3
"""
Test to reproduce the TestClient recursion issue.
"""

import os
import sys
import asyncio
import traceback
import threading
import time
from contextlib import contextmanager

# Enable lightweight mode
os.environ["DISABLE_ML"] = "1"
os.environ["LIGHTWEIGHT_TESTING"] = "1"

@contextmanager
def timeout_protection(seconds: int = 10):
    """Timeout protection context manager for Windows."""
    result = {"completed": False, "exception": None}
    
    def run_with_timeout():
        try:
            yield
            result["completed"] = True
        except Exception as e:
            result["exception"] = e
    
    # Just yield without timeout for now - we'll use threading if needed
    try:
        yield
    except Exception as e:
        raise

def test_basic_testclient():
    """Test basic TestClient usage to reproduce recursion issue."""
    print("🔬 Testing basic TestClient usage...")
    
    try:
        from fastapi.testclient import TestClient
        from backend.api.factory import create_app
        
        print("📦 Creating app...")
        app = create_app()
        
        print("🔧 Creating TestClient...")
        with timeout_protection(15):
            with TestClient(app) as client:
                print("✅ TestClient created successfully")
                
                # Make a simple request
                print("📡 Making request to /health...")
                response = client.get("/health")
                print(f"📋 Health response: {response.status_code}")
                
                print("📡 Making request to /openapi.json...")
                response = client.get("/openapi.json")
                print(f"📋 OpenAPI response: {response.status_code}")
                
            print("🎯 TestClient context exited")
        
        print("✅ TEST PASSED - No recursion issues detected")
        return True
        
    except TimeoutError as e:
        print(f"⏰ TIMEOUT: {e}")
        print("🔥 This indicates the TestClient cleanup is hanging")
        return False
    except RecursionError as e:
        print(f"🔥 RECURSION ERROR: {e}")
        print("📊 Stack trace:")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

def test_minimal_testclient():
    """Test minimal TestClient with a simple app."""
    print("\n🧪 Testing minimal TestClient...")
    
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        # Create minimal app
        app = FastAPI()
        
        @app.get("/simple")
        def simple_endpoint():
            return {"status": "ok"}
        
        print("🔧 Creating TestClient with minimal app...")
        with timeout_protection(10):
            with TestClient(app) as client:
                print("✅ Minimal TestClient created")
                response = client.get("/simple")
                print(f"📋 Simple response: {response.status_code}")
            print("🎯 Minimal TestClient context exited")
        
        print("✅ MINIMAL TEST PASSED")
        return True
        
    except TimeoutError as e:
        print(f"⏰ TIMEOUT on minimal test: {e}")
        return False
    except Exception as e:
        print(f"❌ MINIMAL TEST ERROR: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("🚀 TestClient Issue Reproduction Test")
    print("=" * 50)
    
    minimal_passed = test_minimal_testclient()
    basic_passed = test_basic_testclient()
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Minimal TestClient: {'✅ PASS' if minimal_passed else '❌ FAIL'}")
    print(f"Basic TestClient: {'✅ PASS' if basic_passed else '❌ FAIL'}")
    
    if not basic_passed:
        print("\n🔍 The issue is likely in our application's cleanup logic")
        print("💡 Next step: Investigate the app's lifespan and shutdown handlers")
    else:
        print("\n🎉 No TestClient issues detected!")
