import os
import sys
import requests

# Set JWT secret
os.environ['SECURITY_JWT_SECRET'] = 'your-super-secret-jwt-key-for-development-only-change-in-production'

# Add project to path
sys.path.append('.')

try:
    from backend.infra.security import create_access_token
    
    # Create token
    token = create_access_token('admin', ['admin', 'trader'], 60)
    
    print("=== Phase G Validation ===")
    
    # Test 1: Health
    try:
        r = requests.get('http://localhost:8000/health', timeout=5)
        print(f"Health: {r.status_code} - {r.json().get('status', 'unknown')}")
    except Exception as e:
        print(f"Health: ERROR - {e}")
    
    # Test 2: Positions (authenticated)
    try:
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get('http://localhost:8000/api/v1/positions', headers=headers, timeout=5)
        data = r.json()
        print(f"Positions: {r.status_code} - {len(data)} positions")
    except Exception as e:
        print(f"Positions: ERROR - {e}")
    
    # Test 3: Signals (authenticated)  
    try:
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get('http://localhost:8000/api/v1/signals?symbol=AAPL', headers=headers, timeout=5)
        data = r.json()
        print(f"Signals: {r.status_code} - action: {data.get('action', 'none')}")
    except Exception as e:
        print(f"Signals: ERROR - {e}")
        
    # Test 4: Auth protection
    try:
        r = requests.get('http://localhost:8000/api/v1/positions', timeout=5)
        print(f"Unauth positions: {r.status_code} ({'✅' if r.status_code == 401 else '❌'})")
    except Exception as e:
        print(f"Unauth test: ERROR - {e}")
        
    print("\n✅ Phase G validation completed")
    
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)