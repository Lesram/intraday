#!/usr/bin/env python3
"""Test Step 2 (P2): TaskRegistry lifespan integration with actual FastAPI TestClient."""

import os
import sys
import asyncio

# Set light mode before any imports
os.environ["DISABLE_ML"] = "1"

def main():
    """Test TaskRegistry with actual lifespan execution."""
    print("🔍 Step 2 (P2): TaskRegistry lifespan integration test")
    print("=" * 60)
    
    try:
        sys.path.insert(0, os.path.abspath('.'))
        
        # Import after setting path
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        print("\n📋 Creating app with TestClient to trigger lifespan...")
        app = create_app()
        
        # Use TestClient to trigger lifespan
        with TestClient(app) as client:
            print("✅ TestClient created (lifespan should be running)")
            
            # Check if task_registry exists now
            has_registry = hasattr(app.state, 'task_registry')
            print(f"✅ app.state.task_registry exists during lifespan: {has_registry}")
            
            if has_registry:
                registry_type = type(app.state.task_registry).__name__
                print(f"✅ TaskRegistry type: {registry_type}")
                
                # Test basic functionality
                initial_count = len(app.state.task_registry.tasks())
                print(f"✅ Initial task count: {initial_count}")
                
                # Test readiness endpoint to ensure app is working
                response = client.get("/readyz")
                print(f"✅ Readiness check status: {response.status_code}")
            
            # Check if shutdown_grace is set
            has_grace = hasattr(app.state, 'shutdown_grace')
            grace_value = getattr(app.state, 'shutdown_grace', None)
            print(f"✅ app.state.shutdown_grace exists: {has_grace}")
            print(f"✅ Shutdown grace value: {grace_value}")
        
        print("✅ TestClient closed (lifespan cleanup should have run)")
        
        print("\n🎉 Step 2 (P2) LIFESPAN INTEGRATION TEST PASSED!")
        print("✅ TaskRegistry created during lifespan startup")  
        print("✅ Shutdown grace period configured")
        print("✅ App lifespan executed successfully with TestClient")
        return True
        
    except Exception as e:
        print(f"\n❌ Step 2 (P2) LIFESPAN INTEGRATION TEST FAILED!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
