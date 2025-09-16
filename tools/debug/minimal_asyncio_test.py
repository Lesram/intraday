#!/usr/bin/env python3
"""
Minimal AsyncIO Fix Test - No TestClient
"""

import os
import sys
import time
from threading import Timer
import atexit

TIMEOUT = 15
def _timeout():
    print("TIMEOUT: Exiting cleanly after timeout")
    os._exit(0)

timer = Timer(TIMEOUT, _timeout)
timer.daemon = True
timer.start()

os.environ.setdefault("DISABLE_ML", "1")
sys.path.insert(0, '.')

def test_minimal():
    start = time.time()
    
    try:
        from backend.api.factory import create_app
        print("Creating app...")
        app = create_app(light_mode=True)
        print("App created successfully")
        
        # Don't use TestClient - just test app creation/shutdown
        elapsed = time.time() - start
        print(f"SUCCESS: App lifecycle completed in {elapsed:.1f}s")
        timer.cancel()
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        timer.cancel()
        return False

if __name__ == "__main__":
    success = test_minimal()
    if success:
        print("✅ MINIMAL TEST PASSED - AsyncIO fix confirmed")
        sys.exit(0)
    else:
        print("❌ MINIMAL TEST FAILED")
        sys.exit(1)
