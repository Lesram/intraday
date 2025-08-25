#!/usr/bin/env python3
"""Test the RobustTestClient step by step."""

import os
os.environ["DISABLE_ML"] = "1" 
os.environ["LIGHTWEIGHT_TESTING"] = "1"
os.environ["DEBUG_TESTCLIENT"] = "1"

def test_step_by_step():
    try:
        print("Step 1: Testing FastAPI availability...")
        from fastapi.testclient import TestClient as _FastAPITestClient
        from fastapi import FastAPI
        print("✅ FastAPI available")
        
        print("Step 2: Testing RobustTestClient import...")
        from robust_testclient import RobustTestClient, robust_testclient
        print("✅ RobustTestClient imported")
        
        print("Step 3: Testing app creation...")
        from backend.api.factory import create_app
        app = create_app()
        print("✅ App created")
        
        print("Step 4: Testing RobustTestClient context...")
        with robust_testclient(app) as client:
            print("✅ RobustTestClient context entered")
            
            print("Step 5: Testing /health endpoint...")
            response = client.get("/health")
            print(f"✅ Health endpoint: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Expected 200, got {response.status_code}")
                return False
            
            print("Step 6: Testing error endpoints...")
            for status in [401, 403, 422, 500]:
                response = client.get(f"/test/http-{status}")
                print(f"📋 /test/http-{status}: {response.status_code}")
                if response.status_code != status:
                    print(f"❌ Expected {status}, got {response.status_code}")
                    return False
        
        print("✅ RobustTestClient context exited successfully")
        print("🎉 ALL TESTS PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed at some step: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔧 RobustTestClient Step-by-Step Test")
    print("=" * 50)
    result = test_step_by_step()
    print(f"\nFinal result: {'✅ PASS' if result else '❌ FAIL'}")
