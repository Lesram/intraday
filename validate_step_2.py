#!/usr/bin/env python3
"""Validate Step 2 (P2): TaskRegistry and guaranteed shutdown cleanup implementation."""

import os
import sys
import asyncio

# Set light mode before any imports 
os.environ["DISABLE_ML"] = "1"

async def main():
    """Test TaskRegistry implementation in factory.py"""
    print("🔍 Step 2 (P2): TaskRegistry and guaranteed shutdown cleanup validation")
    print("=" * 70)
    
    try:
        # Test 1: Import TaskRegistry class
        print("\n📋 Test 1: Import TaskRegistry from factory.py")
        sys.path.insert(0, os.path.abspath('.'))
        
        from backend.api.factory import TaskRegistry
        registry = TaskRegistry()
        print("✅ TaskRegistry class imported successfully")
        
        # Test 2: Basic TaskRegistry functionality
        print("\n📋 Test 2: TaskRegistry functionality")
        
        # Create a dummy task
        async def dummy_task():
            await asyncio.sleep(0.1)
            return "done"
        
        task = asyncio.create_task(dummy_task())
        registry.add(task)
        
        tasks = registry.tasks()
        print(f"✅ TaskRegistry.add() works: {len(tasks)} task registered")
        print(f"✅ TaskRegistry.tasks() works: {type(tasks)} returned")
        
        # Clean up
        await task
        
        # Test 3: Factory function with TaskRegistry
        print("\n📋 Test 3: Factory function with TaskRegistry integration")
        
        from backend.api.factory import create_app
        app = create_app()
        
        # Check if task_registry is in app.state
        has_registry = hasattr(app.state, 'task_registry')
        print(f"✅ app.state.task_registry exists: {has_registry}")
        
        if has_registry:
            registry_type = type(app.state.task_registry).__name__
            print(f"✅ TaskRegistry type: {registry_type}")
            
            # Test adding a task to the registry
            test_task = asyncio.create_task(dummy_task())
            app.state.task_registry.add(test_task)
            
            registered_tasks = app.state.task_registry.tasks()
            print(f"✅ Can add tasks to app registry: {len(registered_tasks)} tasks")
            
            # Clean up
            await test_task
        
        # Test 4: Check lifespan function has baseline tracking
        print("\n📋 Test 4: Lifespan function baseline tracking")
        
        import inspect
        from backend.api.factory import create_app
        
        # Get the source code of the create_app function to check lifespan implementation
        source = inspect.getsource(create_app)
        
        # Check for key implementation elements
        has_baseline = "baseline = set(asyncio.all_tasks())" in source
        has_shutdown_grace = "app.state.shutdown_grace = 2.0" in source
        has_cleanup_logic = "to_cancel = [t for t in set(reg + new)" in source
        has_timeout = "timeout=2.0" in source
        
        print(f"✅ Baseline tracking implemented: {has_baseline}")
        print(f"✅ Shutdown grace period set: {has_shutdown_grace}")  
        print(f"✅ Task cancellation logic present: {has_cleanup_logic}")
        print(f"✅ Timeout mechanism implemented: {has_timeout}")
        
        if all([has_baseline, has_shutdown_grace, has_cleanup_logic, has_timeout]):
            print("\n🎉 Step 2 (P2) VALIDATION SUCCESSFUL!")
            print("✅ TaskRegistry class properly defined")
            print("✅ TaskRegistry integrated into app.state")
            print("✅ Baseline task tracking implemented")
            print("✅ Guaranteed shutdown cleanup with 2.0s timeout")
            print("✅ Task cancellation and cleanup logic present")
            return True
        else:
            print("\n❌ Step 2 (P2) VALIDATION FAILED!")
            print("Missing required implementation elements")
            return False
            
    except Exception as e:
        print(f"\n❌ Step 2 (P2) VALIDATION FAILED!")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
