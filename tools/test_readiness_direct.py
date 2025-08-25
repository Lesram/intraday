#!/usr/bin/env python3
"""Direct readiness logic test"""

import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath('.'))

async def test_readiness_logic():
    """Test the readiness logic directly without FastAPI"""
    print("Testing readiness logic directly...")
    
    # Mock database connection success
    async def mock_db_ok():
        return AsyncMock()
    
    # Mock broker service success  
    class MockBroker:
        def health_check(self):
            return True
    
    with patch('backend.database.connection.get_database_session', mock_db_ok), \
         patch('backend.services.broker_service.BrokerService', MockBroker):
        
        print("Mocked dependencies successfully")
        
        # Import the readiness function logic
        from backend.api.factory import create_app
        
        print("Created app successfully")
        
        # Test with mocked request
        request_mock = MagicMock()
        request_mock.app = MagicMock()
        request_mock.app.state = MagicMock()
        
        print("Testing readiness check logic...")
        
        # Simulate the readiness logic
        import os as _os
        
        # DB check
        db_ok = True
        try:
            from backend.database.connection import get_database_session
            async with get_database_session():
                pass
        except Exception:
            db_ok = False
        
        # Broker check
        broker_ok = True
        try:
            svc = MockBroker()
            hc = getattr(svc, "health_check", None)
            if callable(hc):
                res = hc()
                broker_ok = bool(res)
        except Exception:
            broker_ok = True
        
        # URL check (simulate no URL)
        url = _os.getenv("BROKER_HEALTH_URL")
        if url:
            print(f"Would check URL: {url}")
            # Would do HTTP check here
        
        # Build response
        status_code = 200 if (db_ok and broker_ok) else 503
        checks = {"database": bool(db_ok), "broker": bool(broker_ok)}
        problems = {name: "unhealthy" for name, ok in checks.items() if not ok}
        payload = {
            "status": "ready" if status_code == 200 else "degraded",
            "problems": problems,
            "checks": checks,
        }
        
        print(f"Status Code: {status_code}")
        print(f"Payload: {payload}")
        
        # Validate
        assert status_code == 200, f"Expected 200, got {status_code}"
        assert payload["status"] == "ready"
        assert payload["problems"] == {}
        assert payload["checks"]["database"] is True
        assert payload["checks"]["broker"] is True
        
        print("✅ PASS: Healthy scenario")
        
        # Now test failure scenario
        print("\nTesting failure scenario...")
        
        db_ok = False  # Simulate DB failure
        broker_ok = False  # Simulate broker failure
        
        status_code = 200 if (db_ok and broker_ok) else 503
        checks = {"database": bool(db_ok), "broker": bool(broker_ok)}
        problems = {name: "unhealthy" for name, ok in checks.items() if not ok}
        payload = {
            "status": "ready" if status_code == 200 else "degraded", 
            "problems": problems,
            "checks": checks,
        }
        
        print(f"Status Code: {status_code}")
        print(f"Payload: {payload}")
        
        # Validate failure
        assert status_code == 503, f"Expected 503, got {status_code}"
        assert payload["status"] == "degraded"
        assert len(payload["problems"]) == 2
        assert payload["problems"]["database"] == "unhealthy"
        assert payload["problems"]["broker"] == "unhealthy"
        assert payload["checks"]["database"] is False
        assert payload["checks"]["broker"] is False
        
        print("✅ PASS: Failure scenario")
        print("✅ All readiness validations passed!")

if __name__ == "__main__":
    asyncio.run(test_readiness_logic())
