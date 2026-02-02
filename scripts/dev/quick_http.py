#!/usr/bin/env python3
"""Quick HTTP test using fastapi.testclient"""

import sys
import os
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath('.'))

def test_readiness_http():
    """Quick HTTP test of readiness endpoint"""
    print("🧪 Testing readiness via HTTP...")
    
    # Mock successful dependencies
    async def mock_db_success():
        return AsyncMock()
    
    class MockBrokerSuccess:
        def health_check(self):
            return True
    
    with patch('backend.database.connection.get_database_session', mock_db_success), \
         patch('backend.services.broker_service.BrokerService', MockBrokerSuccess):
        
        from backend.api.factory import create_app
        from fastapi.testclient import TestClient
        
        app = create_app()
        
        with TestClient(app) as client:
            print("Making request to /readyz...")
            
            try:
                response = client.get("/readyz", timeout=5)
                data = response.json()
                
                print(f"Status: {response.status_code}")
                print(f"Response: {data}")
                
                # Quick validation
                assert response.status_code == 200
                assert data["status"] == "ready"
                assert "checks" in data
                assert "problems" in data
                assert data["problems"] == {}
                
                print("✅ Readiness endpoint working via HTTP!")
                return True
                
            except Exception as e:
                print(f"❌ HTTP test failed: {e}")
                return False

if __name__ == "__main__":
    if test_readiness_http():
        print("✅ HTTP validation successful!")
    else:
        print("❌ HTTP validation failed!")
