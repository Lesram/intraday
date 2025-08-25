#!/usr/bin/env python3
"""
Readiness Endpoint Validation Script
Tests both passing and failing readiness scenarios to ensure correct status codes and response shapes.
"""

import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.abspath('.'))

async def test_readiness_passing():
    """Test readiness endpoint when all checks pass"""
    print("=== Testing Passing Readiness ===")
    
    # Mock successful database connection
    async def mock_get_database_session():
        return AsyncMock()
    
    # Mock successful broker service
    class MockBrokerService:
        def health_check(self):
            return True
    
    with patch('backend.database.connection.get_database_session', mock_get_database_session), \
         patch('backend.services.broker_service.BrokerService', MockBrokerService), \
         patch.dict('os.environ', {}, clear=False):  # No BROKER_HEALTH_URL set
        
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        app = create_app()
        client = TestClient(app)
        
        # Test readiness endpoint
        response = client.get("/readyz")
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Validate response
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["status"] == "ready", f"Expected status='ready', got {data.get('status')}"
        
        # Validate both response shapes are present
        assert "checks" in data, "Missing 'checks' field for backward compatibility"
        assert "problems" in data, "Missing 'problems' field for new schema"
        
        checks = data["checks"]
        problems = data["problems"]
        
        assert checks["database"] is True, f"Expected database=True, got {checks.get('database')}"
        assert checks["broker"] is True, f"Expected broker=True, got {checks.get('broker')}"
        assert problems == {}, f"Expected empty problems map, got {problems}"
        
        print("✅ Passing readiness test PASSED")
        return True

async def test_readiness_failing():
    """Test readiness endpoint when checks fail"""
    print("\n=== Testing Failing Readiness ===")
    
    # Mock failing database connection
    async def mock_get_database_session_fail():
        raise Exception("Database connection failed")
    
    # Mock failing broker service
    class MockBrokerServiceFail:
        def health_check(self):
            return False
    
    with patch('backend.database.connection.get_database_session', mock_get_database_session_fail), \
         patch('backend.services.broker_service.BrokerService', MockBrokerServiceFail), \
         patch.dict('os.environ', {'BROKER_HEALTH_URL': 'http://test-broker/health'}, clear=False):
        
        # Mock httpx client to fail
        async def mock_httpx_get_fail(url):
            response_mock = MagicMock()
            response_mock.status_code = 503
            return response_mock
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_httpx_get_fail
            
            from backend.api.factory import create_app
            from fastapi.testclient import TestClient
            
            app = create_app()
            client = TestClient(app)
            
            # Test readiness endpoint
            response = client.get("/readyz")
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            
            # Validate response
            assert response.status_code == 503, f"Expected 503, got {response.status_code}"
            
            data = response.json()
            assert data["status"] == "degraded", f"Expected status='degraded', got {data.get('status')}"
            
            # Validate both response shapes are present
            assert "checks" in data, "Missing 'checks' field for backward compatibility"
            assert "problems" in data, "Missing 'problems' field for new schema"
            
            checks = data["checks"]
            problems = data["problems"]
            
            assert checks["database"] is False, f"Expected database=False, got {checks.get('database')}"
            assert checks["broker"] is False, f"Expected broker=False, got {checks.get('broker')}"
            
            # Problems map should contain entries for failed checks
            assert "database" in problems, "Expected 'database' in problems map"
            assert "broker" in problems, "Expected 'broker' in problems map"
            assert problems["database"] == "unhealthy", f"Expected database='unhealthy', got {problems.get('database')}"
            assert problems["broker"] == "unhealthy", f"Expected broker='unhealthy', got {problems.get('broker')}"
            
            print("✅ Failing readiness test PASSED")
            return True

async def test_readiness_partial_failure():
    """Test readiness endpoint when only some checks fail"""
    print("\n=== Testing Partial Failure Readiness ===")
    
    # Mock successful database, failing broker
    async def mock_get_database_session_ok():
        return AsyncMock()
    
    class MockBrokerServiceFail:
        def health_check(self):
            return False
    
    with patch('backend.database.connection.get_database_session', mock_get_database_session_ok), \
         patch('backend.services.broker_service.BrokerService', MockBrokerServiceFail), \
         patch.dict('os.environ', {}, clear=False):  # No BROKER_HEALTH_URL
        
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        app = create_app()
        client = TestClient(app)
        
        # Test readiness endpoint
        response = client.get("/readyz")
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        # Validate response
        assert response.status_code == 503, f"Expected 503, got {response.status_code}"
        
        data = response.json()
        assert data["status"] == "degraded", f"Expected status='degraded', got {data.get('status')}"
        
        checks = data["checks"]
        problems = data["problems"]
        
        assert checks["database"] is True, f"Expected database=True, got {checks.get('database')}"
        assert checks["broker"] is False, f"Expected broker=False, got {checks.get('broker')}"
        
        # Only broker should be in problems
        assert "database" not in problems, "Database should not be in problems (it passed)"
        assert "broker" in problems, "Expected 'broker' in problems map"
        assert problems["broker"] == "unhealthy", f"Expected broker='unhealthy', got {problems.get('broker')}"
        
        print("✅ Partial failure readiness test PASSED")
        return True

async def main():
    """Run all readiness validation tests"""
    print("🚀 Starting Readiness Endpoint Validation")
    
    try:
        # Run tests
        await test_readiness_passing()
        await test_readiness_failing()
        await test_readiness_partial_failure()
        
        print("\n🎉 All readiness validation tests PASSED!")
        print("\nValidated behaviors:")
        print("✅ Passing readiness returns 200 with status='ready' and empty problems")
        print("✅ Failing readiness returns 503 with status='degraded' and problems map")
        print("✅ Both 'checks' (backward compatibility) and 'problems' (new schema) are present")
        print("✅ Partial failures correctly populate problems map")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Readiness validation FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
