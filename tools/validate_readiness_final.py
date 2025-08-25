#!/usr/bin/env python3
"""Focused readiness endpoint validation using httpx"""

import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath('.'))

async def test_readiness_endpoint():
    """Test readiness endpoint using httpx AsyncClient"""
    print("🧪 Testing readiness endpoint...")
    
    # Mock successful database
    async def mock_db_success():
        return AsyncMock()
    
    # Mock successful broker  
    class MockBrokerSuccess:
        def health_check(self):
            return True
    
    with patch('backend.database.connection.get_database_session', mock_db_success), \
         patch('backend.services.broker_service.BrokerService', MockBrokerSuccess):
        
        from backend.api.factory import create_app
        from httpx import AsyncClient, ASGITransport
        
        app = create_app()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test healthy scenario
            print("=== Testing Healthy Scenario ===")
            response = await client.get("/readyz")
            data = response.json()
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {data}")
            
            # Validate healthy response
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            assert data["status"] == "ready", f"Expected 'ready', got {data.get('status')}"
            assert "checks" in data, "Missing 'checks' field"
            assert "problems" in data, "Missing 'problems' field"
            assert data["problems"] == {}, f"Expected empty problems, got {data['problems']}"
            assert data["checks"]["database"] is True
            assert data["checks"]["broker"] is True
            
            print("✅ PASS: Healthy readiness returns 200 with correct structure")
    
    # Now test failure scenario
    async def mock_db_fail():
        raise Exception("Database connection failed")
    
    class MockBrokerFail:
        def health_check(self):
            return False
    
    with patch('backend.database.connection.get_database_session', mock_db_fail), \
         patch('backend.services.broker_service.BrokerService', MockBrokerFail):
        
        from backend.api.factory import create_app
        from httpx import AsyncClient, ASGITransport
        
        app = create_app()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test failure scenario
            print("\n=== Testing Failure Scenario ===")
            response = await client.get("/readyz")
            data = response.json()
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {data}")
            
            # Validate failure response
            assert response.status_code == 503, f"Expected 503, got {response.status_code}"
            assert data["status"] == "degraded", f"Expected 'degraded', got {data.get('status')}"
            assert "checks" in data, "Missing 'checks' field"
            assert "problems" in data, "Missing 'problems' field"
            
            # Both should be unhealthy
            assert data["checks"]["database"] is False
            assert data["checks"]["broker"] is False
            assert "database" in data["problems"], "Database should be in problems"
            assert "broker" in data["problems"], "Broker should be in problems"
            assert data["problems"]["database"] == "unhealthy"
            assert data["problems"]["broker"] == "unhealthy"
            
            print("✅ PASS: Failing readiness returns 503 with correct structure")
    
    print("\n🎉 All readiness validations PASSED!")
    print("✅ Healthy: 200 + status='ready' + empty problems")
    print("✅ Unhealthy: 503 + status='degraded' + populated problems")
    print("✅ Both responses include 'checks' and 'problems' fields")

if __name__ == "__main__":
    asyncio.run(test_readiness_endpoint())
