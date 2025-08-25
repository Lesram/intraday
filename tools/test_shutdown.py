#!/usr/bin/env python3
"""Test shutdown logic directly"""

import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath('.'))

async def test_shutdown_logic():
    """Test the shutdown cancellation logic"""
    print("Testing shutdown logic...")
    
    # Mock dependencies
    async def mock_db_success():
        return AsyncMock()
    
    class MockBrokerSuccess:
        def health_check(self):
            return True
    
    with patch('backend.database.connection.get_database_session', mock_db_success), \
         patch('backend.services.broker_service.BrokerService', MockBrokerSuccess):
        
        from backend.api.factory import create_app
        from httpx import AsyncClient, ASGITransport
        
        app = create_app()
        
        # Create some background tasks to test shutdown
        background_tasks = []
        task_cancelled = asyncio.Event()
        
        async def mock_background_task(task_name):
            """Mock background task that can be cancelled"""
            try:
                await asyncio.sleep(10)  # Would run for 10s if not cancelled
            except asyncio.CancelledError:
                print(f"Task {task_name} was cancelled")
                task_cancelled.set()
                raise
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create background tasks
            task1 = asyncio.create_task(mock_background_task("task1"))
            task2 = asyncio.create_task(mock_background_task("task2"))
            background_tasks.extend([task1, task2])
            
            # Add tasks to app tracking
            app.state.tracked_tasks.update(background_tasks)
            
            # Test basic functionality
            response = await client.get("/readyz")
            print(f"Readiness check: {response.status_code}")
            
            # Give tasks a moment to start
            await asyncio.sleep(0.1)
        
        # App context is exiting - background tasks should be cancelled
        print("App context exited, checking if tasks were cancelled...")
        
        # Give cancellation a moment to propagate
        await asyncio.sleep(0.2)
        
        # Check if tasks were cancelled
        cancelled_count = sum(1 for t in background_tasks if t.cancelled() or t.done())
        print(f"Tasks cancelled/done: {cancelled_count}/{len(background_tasks)}")
        
        if cancelled_count == len(background_tasks):
            print("✅ Shutdown logic working - tasks were cancelled")
            return True
        else:
            print("❌ Some tasks were not cancelled")
            return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_shutdown_logic())
        if result:
            print("✅ Shutdown test passed!")
        else:
            print("❌ Shutdown test failed!")
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
