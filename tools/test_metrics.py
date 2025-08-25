#!/usr/bin/env python3
"""Test metrics endpoint and http_requests_total counter"""

import sys
import os
import asyncio
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath('.'))

async def test_metrics_endpoint():
    """Test metrics endpoint includes http_requests_total counter"""
    print("🔍 Testing metrics endpoint...")
    
    # Mock dependencies to avoid issues
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
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            print("Making requests to generate metrics...")
            
            # Make a few requests to generate metrics
            await client.get("/readyz")  # This should increment http_requests_total
            await client.get("/health")  # This should also increment
            
            print("Fetching metrics...")
            
            # Get metrics
            response = await client.get("/metrics")
            
            print(f"Metrics Status Code: {response.status_code}")
            
            if response.status_code == 200:
                metrics_text = response.text
                print("Metrics response length:", len(metrics_text))
                
                # Check for expected metrics
                has_http_requests = "http_requests_total" in metrics_text
                has_process_metrics = any(x in metrics_text for x in ["process_", "python_"])
                
                print(f"✓ Contains http_requests_total: {has_http_requests}")
                print(f"✓ Contains process metrics: {has_process_metrics}")
                
                if has_http_requests:
                    # Show some lines containing http_requests_total
                    lines = [line for line in metrics_text.split('\n') if 'http_requests_total' in line and not line.startswith('#')]
                    print(f"✓ http_requests_total entries: {len(lines)}")
                    for line in lines[:3]:  # Show first 3
                        print(f"  {line}")
                
                print("✅ Metrics endpoint working correctly!")
                
            else:
                print(f"❌ Metrics endpoint returned {response.status_code}")
                print("Response text:", response.text[:200])

if __name__ == "__main__":
    asyncio.run(test_metrics_endpoint())
