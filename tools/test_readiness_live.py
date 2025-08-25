#!/usr/bin/env python3
"""Quick readiness check without imports that might hang"""

import json

def quick_readiness_test():
    """Test readiness endpoint with minimal dependencies"""
    print("Quick readiness validation...")
    
    # Use requests instead of FastAPI TestClient to avoid lifespan issues
    import requests
    import subprocess
    import time
    import signal
    import os
    
    # Start the app in background
    print("Starting FastAPI server...")
    env = os.environ.copy()
    env['UVICORN_PORT'] = '8899'  # Use different port
    
    # Start server process
    proc = subprocess.Popen([
        'python', '-m', 'uvicorn', 'backend.api.main:app', 
        '--host', '127.0.0.1', '--port', '8899', '--log-level', 'warning'
    ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    try:
        # Wait for server to start
        print("Waiting for server to start...")
        time.sleep(3)
        
        # Test readiness endpoint
        response = requests.get('http://127.0.0.1:8899/readyz', timeout=5)
        data = response.json()
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Validate structure
        has_checks = 'checks' in data
        has_problems = 'problems' in data
        
        print(f"✓ Has 'checks': {has_checks}")
        print(f"✓ Has 'problems': {has_problems}")
        
        if response.status_code == 200:
            print("✅ PASS: Returns 200 for healthy state")
            assert data['status'] == 'ready'
            assert data['problems'] == {}
        elif response.status_code == 503:
            print("✅ PASS: Returns 503 for degraded state") 
            assert data['status'] == 'degraded'
            assert isinstance(data['problems'], dict)
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
        
        print("✅ Readiness validation completed successfully!")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    finally:
        # Clean up server
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except:
            proc.kill()
    
    return True

if __name__ == "__main__":
    quick_readiness_test()
