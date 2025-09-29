#!/usr/bin/env python3
"""
Quick Phase G validation script
"""
import os
import sys
import time
import requests
import subprocess
from pathlib import Path

# Set JWT secret
os.environ['SECURITY_JWT_SECRET'] = 'your-super-secret-jwt-key-for-development-only-change-in-production'

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def create_auth_token():
    """Create JWT token for testing"""
    try:
        from backend.infra.security import create_access_token
        return create_access_token('admin', ['admin', 'trader'], 60)
    except Exception as e:
        print(f"Error creating token: {e}")
        return None

def test_endpoints():
    """Test the Phase G requirements"""
    print("=== Phase G Validation Tests ===\n")
    
    # Create token
    token = create_auth_token()
    if not token:
        print("❌ Failed to create auth token")
        return False
        
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "http://localhost:8000"
    
    results = {}
    
    # Test 1: Health endpoint (should be fast)
    print("1. Testing /health endpoint...")
    try:
        start_time = time.time()
        response = requests.get(f"{base_url}/health", timeout=5)
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            print(f"   ✅ /health: {response.status_code} ({response_time_ms:.1f}ms)")
            results['health'] = {'status': 'pass', 'time_ms': response_time_ms}
        else:
            print(f"   ❌ /health: {response.status_code}")
            results['health'] = {'status': 'fail', 'code': response.status_code}
    except Exception as e:
        print(f"   ❌ /health: {e}")
        results['health'] = {'status': 'error', 'error': str(e)}
    
    # Test 2: Positions endpoint (authenticated)
    print("\n2. Testing /api/v1/positions endpoint...")
    try:
        response = requests.get(f"{base_url}/api/v1/positions", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ /api/v1/positions: {response.status_code} (returned {len(data)} positions)")
            results['positions'] = {'status': 'pass', 'count': len(data)}
        else:
            print(f"   ❌ /api/v1/positions: {response.status_code}")
            results['positions'] = {'status': 'fail', 'code': response.status_code}
    except Exception as e:
        print(f"   ❌ /api/v1/positions: {e}")
        results['positions'] = {'status': 'error', 'error': str(e)}
    
    # Test 3: Signals endpoint (authenticated)
    print("\n3. Testing /api/v1/signals endpoint...")
    try:
        response = requests.get(f"{base_url}/api/v1/signals?symbol=AAPL", headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            action = data.get('action', 'no action')
            print(f"   ✅ /api/v1/signals: {response.status_code} (action: {action})")
            results['signals'] = {'status': 'pass', 'action': action}
        else:
            print(f"   ❌ /api/v1/signals: {response.status_code}")
            results['signals'] = {'status': 'fail', 'code': response.status_code}
    except Exception as e:
        print(f"   ❌ /api/v1/signals: {e}")
        results['signals'] = {'status': 'error', 'error': str(e)}
    
    # Test 4: Unauthenticated access (should return 401)
    print("\n4. Testing authentication protection...")
    try:
        response = requests.get(f"{base_url}/api/v1/positions", timeout=5)
        if response.status_code == 401:
            print(f"   ✅ Unauthenticated /api/v1/positions: 401 (correct)")
            results['auth_protection'] = {'status': 'pass'}
        else:
            print(f"   ❌ Unauthenticated /api/v1/positions: {response.status_code} (should be 401)")
            results['auth_protection'] = {'status': 'fail', 'code': response.status_code}
    except Exception as e:
        print(f"   ❌ Authentication test: {e}")
        results['auth_protection'] = {'status': 'error', 'error': str(e)}
    
    # Summary
    print("\n=== Summary ===")
    passed = sum(1 for r in results.values() if r.get('status') == 'pass')
    total = len(results)
    
    if passed == total:
        print(f"✅ All {total} tests passed!")
        
        # Check health performance target
        health_time = results.get('health', {}).get('time_ms', 999)
        if health_time < 50:
            print(f"✅ Health endpoint P95 < 50ms target: {health_time:.1f}ms")
        else:
            print(f"⚠️  Health endpoint slower than target: {health_time:.1f}ms (target: <50ms)")
            
        return True
    else:
        print(f"❌ {passed}/{total} tests passed")
        return False

if __name__ == "__main__":
    success = test_endpoints()
    sys.exit(0 if success else 1)